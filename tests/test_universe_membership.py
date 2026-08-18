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
    # UNIV-09 (widened default): the adcom move (0.99) now COUNTS alongside the two pdufa moves
    # (was excluded under the old pdufa-only default; this pivot-correction is documented).
    _seed_name(db, "BBIO", [0.20, 0.35])
    aid = _seed_catalyst(db, "BBIO", "2022-03-01", "BBIO-adcom", ctype="adcom")
    _seed_move(db, aid, 0.99)
    reg = discover._registry_moves(db)
    assert set(reg) == {"BBIO"}
    assert sorted(reg["BBIO"]["moves"]) == [0.20, 0.35, 0.99]  # adcom now counted (widened default)
    assert reg["BBIO"]["ticker"] == "BBIO"
    assert reg["BBIO"]["company_name"] == "BBIO Inc."


def test_registry_moves_counts_readout_only_name(db):
    # UNIV-09 pool-grower: a name measurable ONLY via trial_readout is now visible (invisible under
    # the old pdufa-only default).
    _seed_name(db, "READONLY", [0.22, 0.28], ctype="trial_readout")
    reg = discover._registry_moves(db)
    assert "READONLY" in reg
    assert sorted(reg["READONLY"]["moves"]) == [0.22, 0.28]


def test_score_counts_all_live_parity(db):
    # 1 pdufa + 1 trial_readout -> n_moves==2 -> scorable (was <2 pdufa-only -> insufficient).
    pid = _seed_catalyst(db, "MIXED", "2024-05-31", "MIXED-p", ctype="pdufa")
    _seed_move(db, pid, 0.30)
    rid = _seed_catalyst(db, "MIXED", "2023-02-15", "MIXED-r", ctype="trial_readout")
    _seed_move(db, rid, 0.40)
    scorable, insufficient = discover.score_registry(db)
    assert {r["ticker"] for r in scorable} == {"MIXED"}
    assert next(r for r in scorable if r["ticker"] == "MIXED")["n_moves"] == 2
    assert not insufficient


def test_default_catalyst_types_widened():
    # guard against silent regression to pdufa-only
    assert discover._LIVE_PARITY_SCORE_TYPES == ("pdufa", "trial_readout", "adcom")
    import inspect

    for fn in (discover._registry_moves, discover.score_registry, discover.select_members):
        assert inspect.signature(fn).parameters["catalyst_types"].default == (
            "pdufa", "trial_readout", "adcom")


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


# ══════════════════════════════════════════════════════════════════════════════════════════
# Task 3 — select_members percentile-cut (N as output) + build_universe rewire
# ══════════════════════════════════════════════════════════════════════════════════════════


def _wire_tradeable(monkeypatch, *, untradeable=frozenset()):
    """Monkeypatch the tradeability reads to controlled values (ZERO network). Tickers in
    `untradeable` fail optionability (a top-scorer that must be skipped)."""
    monkeypatch.setattr(discover, "_dollar_adv", lambda t, as_of, **k: 7_000_000)
    monkeypatch.setattr(discover, "_market_cap",
                        lambda t, as_of: (1_000_000_000, {"cash_runway_months": 24}))
    monkeypatch.setattr(discover, "_optionable", lambda t: t not in untradeable)


def test_select_members_percentile_cut_N_output(db, monkeypatch):
    _wire_tradeable(monkeypatch)
    # 100 scorable names, all tradeable; vol_score strictly increases with i -> top 80 are members.
    for i in range(100):
        m = 0.20 + i * 0.001
        _seed_name(db, f"N{i:03d}", [m, m])  # both >= 0.15 -> big_move_frac 1.0 -> vol_score = m*2
    members, rejected, report = discover.select_members(db, "2026-08-17", target_size=80)
    assert report["N"] == 80 and len(members) == 80
    assert report["n_scorable"] == 100
    assert report["cut_percentile"] == round(1 - 80 / 100, 4) == 0.2
    assert report["target_reached"] is True
    # the 80 highest-i (highest vol_score) names are the members
    assert {m["ticker"] for m in members} == {f"N{i:03d}" for i in range(20, 100)}


def test_select_members_ranks_by_vol_score(db, monkeypatch):
    _wire_tradeable(monkeypatch)
    _seed_name(db, "LOW", [0.16, 0.16])   # vol_score 0.32
    _seed_name(db, "MID", [0.30, 0.30])   # vol_score 0.60
    _seed_name(db, "HIGH", [0.55, 0.55])  # vol_score 1.10
    members, _, _ = discover.select_members(db, "2026-08-17", target_size=80)
    assert [m["ticker"] for m in members] == ["HIGH", "MID", "LOW"]  # biggest movers first


def test_select_members_honest_underfill(db, monkeypatch):
    _wire_tradeable(monkeypatch)
    for t in ("AAA", "BBB", "CCC"):
        _seed_name(db, t, [0.30, 0.40])
    members, _, report = discover.select_members(db, "2026-08-17", target_size=80)
    assert report["N"] == 3 and len(members) == 3      # honest under-fill, never padded to 80
    assert report["target_reached"] is False
    assert report["cut_percentile"] == 0.0             # 1 - 3/3


def test_select_members_skips_untradeable(db, monkeypatch):
    # HIGH is the top scorer but not optionable -> skipped; MID/LOW take the two slots.
    _wire_tradeable(monkeypatch, untradeable={"HIGH"})
    _seed_name(db, "LOW", [0.16, 0.16])
    _seed_name(db, "MID", [0.30, 0.30])
    _seed_name(db, "HIGH", [0.55, 0.55])
    members, rejected, report = discover.select_members(db, "2026-08-17", target_size=2)
    assert {m["ticker"] for m in members} == {"MID", "LOW"}
    assert "HIGH" not in {m["ticker"] for m in members}
    high_rej = next(r for r in rejected if r["ticker"] == "HIGH")
    assert "not_optionable" in high_rej["reasons"]


def test_insufficient_history_not_member(db, monkeypatch):
    _wire_tradeable(monkeypatch)
    _seed_name(db, "GOOD", [0.30, 0.40])   # 2 events -> eligible
    _seed_name(db, "ONESHOT", [0.55])       # 1 event -> never a member
    members, _, report = discover.select_members(db, "2026-08-17", target_size=80)
    assert {m["ticker"] for m in members} == {"GOOD"}
    assert "ONESHOT" in report["insufficient_history"]
    assert report["n_insufficient"] == 1


# ── build_universe rewire (discover+backfill -> select_members -> build_snapshot) ─────────────


def _wire_build_backward(monkeypatch, cands):
    """discover_candidates returns `cands`; _persist_backfill runs REAL (seeds the store the scorer
    then reads); tradeability reads controlled; NEVER hits the network."""
    monkeypatch.setattr(discover, "discover_candidates", lambda *a, **k: cands)
    monkeypatch.setattr(discover, "_realized_catalyst_move",
                        lambda t, ed, **k: (0.30, "(-1,2)", "2024-06-03", "green"))
    _wire_tradeable(monkeypatch)


def _bk_cand(cik, ticker, *, ta="oncology"):
    # two PAST day-precision pdufa catalysts -> 2 moves after backfill -> n>=2 scorable
    return {"cik": cik, "ticker": ticker, "company_name": f"{ticker} Inc.", "source_feeds": {"edgar"},
            "therapeutic_area": ta,
            "catalysts": [
                {"type": "pdufa", "event_date": "2024-05-31", "source_url": f"{ticker}-A",
                 "fetch_ts": "2026-08-17T00:00:00Z", "grade": "green"},
                {"type": "pdufa", "event_date": "2023-02-15", "source_url": f"{ticker}-B",
                 "fetch_ts": "2026-08-17T00:00:00Z", "grade": "green"},
            ]}


def test_build_universe_backward_writes_cohort(db, monkeypatch):
    from catalyst_trader.universe.build import universe_as_of

    cands = {1: _bk_cand(1, "BBIO"), 2: _bk_cand(2, "AXSM", ta="cns")}
    _wire_build_backward(monkeypatch, cands)
    assert db.execute("SELECT COUNT(*) AS n FROM catalyst").fetchone()["n"] == 0  # empty store (Blocker-1)

    summary = discover.build_universe(db, "2026-08-17")

    # registry persisted (warm-start) THEN scored from the store
    assert db.execute("SELECT COUNT(*) AS n FROM catalyst").fetchone()["n"] == 4
    assert db.execute("SELECT COUNT(*) AS n FROM catalyst_move").fetchone()["n"] == 4
    names = {u.ticker for u in universe_as_of(db, "2026-08-17") if u.included}
    assert {"BBIO", "AXSM"} <= names
    assert summary["included_count"] > 0  # Blocker-1: min_catalyst_density=0
    # backward-membership summary fields
    assert summary["N"] == 2 and summary["n_scorable"] == 2
    assert "cut_percentile" in summary and summary["n_insufficient"] == 0
    for a in summary["admissions"]:
        assert a["vol_score"] == pytest.approx(0.30 * 2)  # median 0.30 * (1 + big_move_frac 1.0)
        assert a["n_moves"] == 2


def test_blocker_fixes_preserved(db, monkeypatch):
    captured = {}

    def _spy_build_snapshot(conn, as_of, seed_rows, *, criteria):
        captured["criteria"] = criteria
        captured["n_seed"] = len(seed_rows)
        return 1  # store writes 1 included row

    cands = {1: _bk_cand(1, "BBIO")}
    _wire_build_backward(monkeypatch, cands)
    monkeypatch.setattr(discover, "build_snapshot", _spy_build_snapshot)

    summary = discover.build_universe(db, "2026-08-17")
    # Blocker-1: min_catalyst_density passed 0 (store-density floor stays disabled)
    assert captured["criteria"]["min_catalyst_density"] == 0
    # Blocker-3: included_count is DISTINCT from N and reconciles with the store's included==1 count
    assert summary["included_count"] == 1
    assert summary["N"] == 1
    assert isinstance(summary["included_count"], int)


def test_no_fixed_move_threshold(db, monkeypatch):
    # membership must NOT read a fixed move_threshold gate anywhere (the cut is relative percentile).
    cands = {1: _bk_cand(1, "BBIO")}
    _wire_build_backward(monkeypatch, cands)
    summary = discover.build_universe(db, "2026-08-17", criteria={"move_threshold": 0.99})
    # a would-be 0.99 threshold changes nothing — BBIO (median move 0.30) is still a member
    assert summary["N"] == 1
    assert "move_threshold" not in summary
    _, _, report = discover.select_members(db, "2026-08-17", criteria={"move_threshold": 0.99})
    assert "move_threshold" not in report
