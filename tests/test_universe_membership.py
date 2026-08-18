"""Backward-looking proven-PDUFA-volatility membership (universe/discover.py) — offline (Plan 07).

THE PIVOT (decision E): membership is scored BACKWARD from a name's PROVEN PAST PDUFA moves READ
FROM THE STORE (`catalyst_move` JOIN `catalyst` by ticker) — median magnitude + big-move frequency,
n>=2 required — then a percentile-cut fills the tradeable target (~80). N is an OUTPUT; there is NO
fixed move_threshold gate. Universe optionability is relaxed to "has listed options at all"
(bid>0 both legs); the strict OI/spread liquidity gate lives at the per-trade layer
(desk/diligence.options_liquid). ZERO live API — the score reads the persisted store; tradeability
reads (prices/options/fundamentals) are monkeypatched. NEVER hits the network.
"""

import pytest

from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    CatalystType,
    DatePrecision,
    DateType,
    SourceOrigin,
    SourceType,
    Status,
    Uncertainty,
)
from catalyst_trader.store import insert_catalyst
from catalyst_trader.universe import discover


# ── store-seeding helper (seed catalyst + catalyst_move rows directly; ZERO discovery/network) ──


def _seed_catalyst(conn, ticker, event_date, ref, *, ctype="pdufa", company_name=None):
    cat = Catalyst(
        ticker=ticker,
        company_name=company_name or f"{ticker} Inc.",
        catalyst_type=CatalystType(ctype),
        event_date=event_date,
        date_precision=DatePrecision.day,
        uncertainty_type=Uncertainty.firm,
        status=Status.resolved,
        source_origin=SourceOrigin.curated_pdufa,
        external_ref=ref,
        sources=[CatalystSource(
            source_name="edgar",
            source_url=ref,
            source_type=SourceType.primary,
            reported_date=event_date,
            date_type=DateType.actual,
            retrieved_at="2026-08-17T00:00:00Z",
        )],
    )
    return insert_catalyst(conn, cat)


def _seed_move(conn, cat_id, move, *, knowable="2024-06-03", window="(-1,2)", grade="green"):
    discover._upsert_move(conn, cat_id, move, window, knowable, grade)


def _seed_name(conn, ticker, moves, *, ctype="pdufa"):
    """Seed a name with one catalyst + catalyst_move per move value."""
    for i, m in enumerate(moves):
        cid = _seed_catalyst(conn, ticker, f"202{4 - (i % 5)}-05-{10 + i:02d}", f"{ticker}-{i}",
                             ctype=ctype)
        _seed_move(conn, cid, m)


def _opt(*, call_bid=4.2, call_ask=4.6, put_bid=3.9, put_ask=4.3, call_oi=850, put_oi=780):
    return {"options_quote": {"call_bid": call_bid, "call_ask": call_ask, "put_bid": put_bid,
                              "put_ask": put_ask, "call_oi": call_oi, "put_oi": put_oi,
                              "expiry": "2026-10-16"}}


def _bars(close=100.0, volume=350_000, n=8):
    return [{"week_end": f"2026-0{(i % 8) + 1}-01", "close": close, "volume": volume} for i in range(n)]


def _cand(cik, ticker, *, ta="oncology"):
    return {"cik": cik, "ticker": ticker, "company_name": ticker, "catalysts": [],
            "source_feeds": {"edgar"}, "therapeutic_area": ta}


# ══════════════════════════════════════════════════════════════════════════════════════════
# Task 1 — relaxed universe optionability + screen_candidates tradeability-only (no move gate)
# ══════════════════════════════════════════════════════════════════════════════════════════


def test_optionable_relaxed_admits_liquid_name(monkeypatch):
    # INSM shape: bid>0 both legs but low combined OI (<100) AND delayed wide spread/mid.
    # The OLD gate rejected this; the relaxed universe gate admits it (options exist).
    monkeypatch.setattr(discover.options_cboe, "fetch",
                        lambda t: _opt(call_bid=0.10, call_ask=1.00, put_bid=0.10, put_ask=1.00,
                                       call_oi=40, put_oi=30))
    assert discover._optionable("INSM") is True


def test_optionable_still_requires_bid_both_legs(monkeypatch):
    monkeypatch.setattr(discover.options_cboe, "fetch", lambda t: _opt(call_bid=0.0))
    assert discover._optionable("AAA") is False
    monkeypatch.setattr(discover.options_cboe, "fetch", lambda t: {"options_quote": None})
    assert discover._optionable("BBB") is False
    monkeypatch.setattr(discover.options_cboe, "fetch", lambda t: None)  # fetch degrade
    assert discover._optionable("CCC") is None


def test_screen_no_move_gate(monkeypatch):
    # a below-old-threshold mover (0.03) that passes ADV/cap/optionable is ADMITTED — the fixed
    # move_threshold gate is retired from screen_candidates (tradeability-only now).
    monkeypatch.setattr(discover, "get_weekly_bars", lambda t, s, e, **k: _bars(100, 350_000))
    monkeypatch.setattr(discover, "fundamentals",
                        lambda t: {"shares_outstanding": 10_000_000, "cash_runway_months": 24})
    monkeypatch.setattr(discover.options_cboe, "fetch", lambda t: _opt())
    monkeypatch.setattr(discover, "_realized_catalyst_move",
                        lambda t, ed, **k: (0.03, "(-1,2)", "2024-06-03", "green"))
    cand = {"cik": 1, "ticker": "SLEEP", "company_name": "SLEEP", "source_feeds": {"edgar"},
            "catalysts": [{"type": "pdufa", "event_date": "2024-05-31", "source_url": "u",
                           "fetch_ts": "2026-08-17T00:00:00Z", "grade": "green"}]}
    admitted, rejected = discover.screen_candidates({1: cand}, "2026-08-17")
    assert [r["ticker"] for r in admitted] == ["SLEEP"]
    all_reasons = [rn for r in admitted + rejected for rn in r.get("reasons", [])]
    assert not any("move" in rn for rn in all_reasons)  # no move_unknown / move_median reason


def test_screen_still_tradeability(monkeypatch):
    # ADV < $2M -> dropped
    monkeypatch.setattr(discover, "get_weekly_bars", lambda t, s, e, **k: _bars(10, 500_000))  # 1M ADV
    monkeypatch.setattr(discover, "fundamentals",
                        lambda t: {"shares_outstanding": 30_000_000, "cash_runway_months": 12})
    monkeypatch.setattr(discover.options_cboe, "fetch", lambda t: _opt())
    admitted, rejected = discover.screen_candidates({1: _cand(1, "THIN")}, "2026-08-17")
    assert not admitted and any("adv" in r for r in rejected[0]["reasons"])

    # not optionable (no live ATM pair) -> dropped
    monkeypatch.setattr(discover, "get_weekly_bars", lambda t, s, e, **k: _bars(100, 350_000))
    monkeypatch.setattr(discover, "fundamentals",
                        lambda t: {"shares_outstanding": 10_000_000, "cash_runway_months": 24})
    monkeypatch.setattr(discover.options_cboe, "fetch", lambda t: {"options_quote": None})
    admitted2, rejected2 = discover.screen_candidates({1: _cand(1, "NOPT")}, "2026-08-17")
    assert not admitted2 and "not_optionable" in rejected2[0]["reasons"]

    # degraded datum (no bars) -> cite-or-drop, never imputed
    monkeypatch.setattr(discover, "get_weekly_bars", lambda t, s, e, **k: [])
    monkeypatch.setattr(discover.options_cboe, "fetch", lambda t: _opt())
    admitted3, rejected3 = discover.screen_candidates({1: _cand(1, "DEGR")}, "2026-08-17")
    assert not admitted3
    assert rejected3[0]["adv_usd"] is None and "adv_unreadable" in rejected3[0]["reasons"]


# ══════════════════════════════════════════════════════════════════════════════════════════
# Task 2 — backward per-name volatility score from the store + n>=2 + insufficient-history list
# ══════════════════════════════════════════════════════════════════════════════════════════


def test_registry_moves_grouped_by_ticker(db):
    # two PDUFA moves for BBIO -> one entry with 2 moves; an adcom row is EXCLUDED under the default
    # catalyst_types=("pdufa",).
    _seed_name(db, "BBIO", [0.20, 0.35])
    aid = _seed_catalyst(db, "BBIO", "2022-03-01", "BBIO-adcom", ctype="adcom")
    _seed_move(db, aid, 0.99)
    reg = discover._registry_moves(db)
    assert set(reg) == {"BBIO"}
    assert sorted(reg["BBIO"]["moves"]) == [0.20, 0.35]  # adcom 0.99 excluded
    assert reg["BBIO"]["ticker"] == "BBIO"
    assert reg["BBIO"]["company_name"] == "BBIO Inc."


def test_name_volatility_score():
    v = discover._name_volatility([0.10, 0.30, 0.20])
    assert v["median_move"] == pytest.approx(0.20)
    assert v["big_move_frac"] == pytest.approx(2 / 3)  # 0.30 and 0.20 >= 0.15; 0.10 is not
    assert v["vol_score"] == pytest.approx(0.20 * (1 + 2 / 3))
    assert v["n_moves"] == 3


def test_min_events_gate():
    assert discover._name_volatility([0.40]) is None  # 1 event < min_events=2 -> not scorable
    assert discover._name_volatility([0.40, 0.10]) is not None  # 2 events -> scorable


def test_insufficient_history_list(db):
    _seed_name(db, "GOODVOL", [0.30, 0.40])   # 2 events -> scorable
    _seed_name(db, "ONESHOT", [0.55])          # 1 event -> insufficient (never fabricate a score)
    scorable, insufficient = discover.score_registry(db)
    assert {r["ticker"] for r in scorable} == {"GOODVOL"}
    assert {r["ticker"] for r in insufficient} == {"ONESHOT"}
    one = next(r for r in insufficient if r["ticker"] == "ONESHOT")
    assert one["n_moves"] == 1  # honest watch list carries the count, no vol_score
    assert "vol_score" not in one
    good = next(r for r in scorable if r["ticker"] == "GOODVOL")
    assert good["vol_score"] > 0 and good["n_moves"] == 2


def test_score_reads_only_catalyst_move(db, monkeypatch):
    # zero API: scoring must NOT touch any provider (prices/options/fundamentals). If it does, boom.
    def _boom(*a, **k):
        raise AssertionError("score_registry must be ZERO API (store-read only)")

    monkeypatch.setattr(discover, "get_weekly_bars", _boom)
    monkeypatch.setattr(discover, "get_daily_bars", _boom)
    monkeypatch.setattr(discover, "fundamentals", _boom)
    monkeypatch.setattr(discover.options_cboe, "fetch", _boom)
    _seed_name(db, "ZERO", [0.20, 0.30])
    scorable, _ = discover.score_registry(db)
    assert {r["ticker"] for r in scorable} == {"ZERO"}


def test_empty_registry_degrades(db):
    assert discover.score_registry(db) == ([], [])
