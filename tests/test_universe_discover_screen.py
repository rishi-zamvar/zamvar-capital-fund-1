"""Screen + measure-and-grow + write (universe/discover.py) — offline (Phase 6.12 Plan 02).

Consumes Plan 01's CIK-keyed candidate set and produces a survivorship-free `universe_as_of`
cohort sized by MEASURING forward catalyst density (N is an OUTPUT, never hard-coded). ZERO live
API — every provider read (prices, options_cboe, edgar fundamentals) is monkeypatched.
"""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


# ── builders ───────────────────────────────────────────────────────────────────────────────


def _cats(n, ctype="pdufa"):
    return [
        {"type": ctype, "event_date": "2026-10-01", "source_url": f"u{i}",
         "fetch_ts": "2026-08-17T00:00:00Z", "grade": "green"}
        for i in range(n)
    ]


def _cand(cik, ticker, *, ta="oncology", ncat=1, ctype="pdufa", **extra):
    c = {"cik": cik, "ticker": ticker, "company_name": ticker, "catalysts": _cats(ncat, ctype),
         "source_feeds": {"edgar"}, "therapeutic_area": ta}
    c.update(extra)
    return c


def _bars(close, volume, n=8):
    return [{"week_end": f"2026-0{(i % 8) + 1}-01", "close": close, "volume": volume} for i in range(n)]


def _opt(*, call_bid=4.2, call_ask=4.6, put_bid=3.9, put_ask=4.3, call_oi=850, put_oi=780):
    return {"options_quote": {"call_bid": call_bid, "call_ask": call_ask, "put_bid": put_bid,
                              "put_ask": put_ask, "call_oi": call_oi, "put_oi": put_oi,
                              "expiry": "2026-10-16"}}


def _wire(monkeypatch, *, bars, fund, opt, move=(0.30, "(-1,2)", "2024-06-03", "green")):
    from catalyst_trader.universe import discover

    monkeypatch.setattr(discover, "get_weekly_bars", lambda t, s, e, **k: bars)
    monkeypatch.setattr(discover, "fundamentals", lambda t: fund)
    monkeypatch.setattr(discover.options_cboe, "fetch", lambda t: opt)
    # Plan 06 added a realized-move gate to screen_candidates; patch it so these size/optionability
    # tests exercise their own axis (a passing move by default) and NEVER hit the network.
    monkeypatch.setattr(discover, "_realized_catalyst_move", lambda t, ed, **k: move)
    return discover


def _one(admitted, rejected, ticker):
    pool = admitted + rejected
    return next(r for r in pool if r["ticker"] == ticker)


# ── Task 1: screen_candidates ────────────────────────────────────────────────────────────────


def test_adv_floor_admits_above_5m(monkeypatch):
    # close 100 * vol 350k / 5 = 7,000,000 daily $ADV; cap = 10M shares * 100 = $1B
    d = _wire(monkeypatch, bars=_bars(100, 350_000), fund={"shares_outstanding": 10_000_000, "cash_runway_months": 24}, opt=_opt())
    admitted, rejected = d.screen_candidates({1: _cand(1, "AAA")}, "2026-08-17")
    assert [r["ticker"] for r in admitted] == ["AAA"]
    assert not admitted[0]["flags"].get("size_tiny")


def test_adv_size_tiny_tier_2to5m_kept_flagged(monkeypatch):
    # close 30 * vol 500k / 5 = 3,000,000 daily $ADV -> in [2M,5M) -> KEPT + size_tiny
    d = _wire(monkeypatch, bars=_bars(30, 500_000), fund={"shares_outstanding": 20_000_000, "cash_runway_months": 12}, opt=_opt())
    admitted, rejected = d.screen_candidates({1: _cand(1, "AAA")}, "2026-08-17")
    assert admitted and admitted[0]["flags"].get("size_tiny") is True


def test_adv_below_2m_dropped(monkeypatch):
    # close 10 * vol 500k / 5 = 1,000,000 daily $ADV -> below $2M -> dropped
    d = _wire(monkeypatch, bars=_bars(10, 500_000), fund={"shares_outstanding": 30_000_000, "cash_runway_months": 12}, opt=_opt())
    admitted, rejected = d.screen_candidates({1: _cand(1, "AAA")}, "2026-08-17")
    assert not admitted
    assert any("adv" in r for r in rejected[0]["reasons"])


def test_cap_band_admits_200m_to_10b(monkeypatch):
    d = _wire(monkeypatch, bars=_bars(100, 350_000), fund={"shares_outstanding": 10_000_000, "cash_runway_months": 24}, opt=_opt())
    admitted, _ = d.screen_candidates({1: _cand(1, "AAA")}, "2026-08-17")
    assert admitted[0]["market_cap"] == 1_000_000_000


def test_cap_ceiling_removed_large_cap_admitted(monkeypatch):
    # Plan 06 (decision C): the market-cap CEILING is REMOVED. cap = 120M shares * 100 = $12B was
    # dropped by the old $10B ceiling; it is now ADMITTED (only the $200M floor remains). No hedge-
    # peer band flag exists anymore, and no cap-over reason is ever emitted.
    d = _wire(monkeypatch, bars=_bars(100, 350_000), fund={"shares_outstanding": 120_000_000, "cash_runway_months": 24}, opt=_opt())
    admitted, rejected = d.screen_candidates({1: _cand(1, "BIG")}, "2026-08-17")
    assert [r["ticker"] for r in admitted] == ["BIG"]
    assert admitted[0]["market_cap"] == 12_000_000_000
    all_reasons = [rn for r in admitted + rejected for rn in r.get("reasons", [])]
    assert not any("market_cap" in rn and ">" in rn for rn in all_reasons)


def test_optionability_oi_floor_relaxed_admits(monkeypatch):
    # PIVOT-CORRECTION (Plan 07, UNIV-02c): the universe layer no longer gates on OI>=100. A liquid
    # name with bid>0 both legs but low combined OI (INSM shape on delayed EOD quotes) is ADMITTED;
    # the strict OI floor now lives at the per-trade layer (desk/diligence.options_liquid).
    d = _wire(monkeypatch, bars=_bars(100, 350_000), fund={"shares_outstanding": 10_000_000, "cash_runway_months": 24},
              opt=_opt(call_oi=30, put_oi=40))  # 70 < old-100 gate — now irrelevant to membership
    admitted, rejected = d.screen_candidates({1: _cand(1, "AAA")}, "2026-08-17")
    assert [r["ticker"] for r in admitted] == ["AAA"]


def test_optionability_spread_ceiling_relaxed_admits(monkeypatch):
    # PIVOT-CORRECTION (Plan 07, UNIV-02c): the wide-spread rejection is removed from the universe
    # layer (delayed build-time per-strike spread is unreliable). bid>0 both legs -> optionable.
    d = _wire(monkeypatch, bars=_bars(100, 350_000), fund={"shares_outstanding": 10_000_000, "cash_runway_months": 24},
              opt=_opt(call_bid=0.1, call_ask=1.0, put_bid=0.1, put_ask=1.0))
    admitted, rejected = d.screen_candidates({1: _cand(1, "AAA")}, "2026-08-17")
    assert [r["ticker"] for r in admitted] == ["AAA"]


def test_optionability_bid_both_legs(monkeypatch):
    d = _wire(monkeypatch, bars=_bars(100, 350_000), fund={"shares_outstanding": 10_000_000, "cash_runway_months": 24},
              opt=_opt(call_bid=0.0))  # a leg with bid==0 -> not optionable
    admitted, rejected = d.screen_candidates({1: _cand(1, "AAA")}, "2026-08-17")
    assert not admitted and "not_optionable" in rejected[0]["reasons"]


def test_optionability_required(monkeypatch):
    d = _wire(monkeypatch, bars=_bars(100, 350_000), fund={"shares_outstanding": 10_000_000, "cash_runway_months": 24}, opt=None)
    admitted, rejected = d.screen_candidates({1: _cand(1, "AAA")}, "2026-08-17")
    assert not admitted and "optionability_unreadable" in rejected[0]["reasons"]


def test_cite_or_drop_on_degrade(monkeypatch):
    # bars [] -> ADV None + latest close None -> cap None; dropped with reasons, NOT imputed
    d = _wire(monkeypatch, bars=[], fund={"shares_outstanding": 10_000_000, "cash_runway_months": 24}, opt=_opt())
    admitted, rejected = d.screen_candidates({1: _cand(1, "AAA")}, "2026-08-17")
    assert not admitted
    rec = rejected[0]
    assert rec["adv_usd"] is None and rec["market_cap"] is None
    assert "adv_unreadable" in rec["reasons"] and "market_cap_unreadable" in rec["reasons"]


def test_runway_read(monkeypatch):
    d = _wire(monkeypatch, bars=_bars(100, 350_000), fund={"shares_outstanding": 10_000_000, "cash_runway_months": 18}, opt=_opt())
    admitted, _ = d.screen_candidates({1: _cand(1, "AAA")}, "2026-08-17")
    assert admitted[0]["cash_runway_months"] == 18

    # runway unreadable (not burning / missing) -> flagged, not a hard drop (cap still readable)
    d2 = _wire(monkeypatch, bars=_bars(100, 350_000), fund={"shares_outstanding": 10_000_000, "cash_runway_months": None}, opt=_opt())
    admitted2, _ = d2.screen_candidates({1: _cand(1, "AAA")}, "2026-08-17")
    assert admitted2 and admitted2[0]["flags"].get("runway_unknown") is True


def test_ta_diversity_cap():
    from catalyst_trader.universe import discover

    admitted = [
        {"ticker": f"T{i}", "therapeutic_area": "oncology", "catalysts": _cats(6 - i), "reasons": []}
        for i in range(6)  # densities 6,5,4,3,2,1
    ]
    kept = discover._enforce_diversity(admitted, max_per_ta=4)
    assert len(kept) == 4
    assert {r["ticker"] for r in kept} == {"T0", "T1", "T2", "T3"}  # the 4 densest
    demoted = [r for r in admitted if r not in kept]
    assert all("ta_cluster_full" in r["reasons"] for r in demoted)


# ── Task 2: size_to_density — measure-and-grow, N as output ───────────────────────────────────


def test_N_is_output_grows_until_target():
    from catalyst_trader.universe import discover

    screened = [_cand(i, f"T{i}", ncat=1) for i in range(5)]
    # window 12mo, 1 catalyst each -> lambda = n/52; target 0.05 reached at 3 names (3/52=0.0577)
    shortlist, report = discover.size_to_density(screened, "2026-08-17", target_lambda=0.05)
    assert len(shortlist) == 3
    assert report["n_admitted"] == 3
    assert report["target_reached"] is True


def test_earnings_never_counted():
    from catalyst_trader.universe import discover

    live = [_cand(i, f"L{i}", ncat=1, ctype="pdufa") for i in range(3)]
    base = discover._count_tradeable_catalysts(live)
    earnings = _cand(99, "EARN", ncat=5, ctype="earnings")
    assert discover._count_tradeable_catalysts(live + [earnings]) == base  # earnings never lift it


def test_target_not_reached_is_honest():
    from catalyst_trader.universe import discover

    screened = [_cand(i, f"T{i}", ncat=1) for i in range(2)]  # thin pool
    shortlist, report = discover.size_to_density(screened, "2026-08-17", target_lambda=1.75)
    assert report["target_reached"] is False
    assert report["n_admitted"] == 2  # honest under-fill: pool exhausted, no over-grow


def test_safety_cap_caps_N():
    from catalyst_trader.universe import discover

    screened = [_cand(i, f"T{i}", ncat=1) for i in range(200)]
    shortlist, report = discover.size_to_density(screened, "2026-08-17", target_lambda=10.0, safety_cap=90)
    assert len(shortlist) <= 90 and report["n_admitted"] == 90


def test_densest_first():
    from catalyst_trader.universe import discover

    screened = [_cand(1, "LOW", ncat=1), _cand(2, "HIGH", ncat=5), _cand(3, "MID", ncat=2)]
    shortlist, _ = discover.size_to_density(screened, "2026-08-17", target_lambda=99.0)  # unreachable -> all
    assert [r["ticker"] for r in shortlist] == ["HIGH", "MID", "LOW"]


def test_recalibration_note_present():
    from catalyst_trader.universe import discover

    _, report = discover.size_to_density([_cand(1, "T", ncat=1)], "2026-08-17")
    note = report["base_rate_recalibration_note"]
    assert note and "7.5" in note


# ── Task 3: build_universe — emit seed_rows -> build_snapshot (append-only cohort) ────────────


def _screen_rec(cik, ticker, *, ta="oncology", ncat=1, adv=7_000_000, cap=1_000_000_000, delisted=False):
    return {"cik": cik, "ticker": ticker, "company_name": ticker, "catalysts": _cats(ncat),
            "source_feeds": {"edgar"}, "therapeutic_area": ta, "adv_usd": adv, "market_cap": cap,
            "cash_runway_months": 24, "flags": {}, "reasons": [], "delisted": delisted}


def _wire_build(monkeypatch, admitted):
    from catalyst_trader.universe import discover

    monkeypatch.setattr(discover, "discover_candidates", lambda *a, **k: {r["cik"]: r for r in admitted})
    monkeypatch.setattr(discover, "screen_candidates", lambda cands, as_of, criteria=None: (list(admitted), []))
    # Plan 06: build_universe now persists a warm-start backfill (catalysts + realized moves) before
    # screening. These cohort-write tests mock screen_candidates, so stub the backfill to a no-op
    # (its own persistence + move computation is covered in test_universe_move_screen.py) — keeps
    # these tests offline and focused on the append-only cohort.
    monkeypatch.setattr(discover, "_persist_backfill", lambda conn, cand: [])
    return discover


def test_build_universe_writes_cohort(monkeypatch, db):
    from catalyst_trader.universe.build import universe_as_of

    d = _wire_build(monkeypatch, [_screen_rec(1, "AAA"), _screen_rec(2, "BBB", ta="cardio")])
    summary = d.build_universe(db, "2026-08-17")
    names = {u.ticker for u in universe_as_of(db, "2026-08-17") if u.included}
    assert {"AAA", "BBB"} <= names
    assert summary["n_admitted"] >= 2


def test_seed_rows_carry_screen_data(monkeypatch, db):
    from catalyst_trader.universe.build import universe_as_of

    d = _wire_build(monkeypatch, [_screen_rec(1, "AAA")])
    d.build_universe(db, "2026-08-17")
    row = next(u for u in universe_as_of(db, "2026-08-17") if u.ticker == "AAA")
    crit = json.loads(row.criteria_json)
    assert crit["market_cap"] == 1_000_000_000
    assert crit["adv_usd"] == 7_000_000
    assert crit["therapeutic_area"] == "oncology"


def test_rerun_writes_new_cohort_never_overwrites(monkeypatch, db):
    from catalyst_trader.universe.build import universe_as_of

    d = _wire_build(monkeypatch, [_screen_rec(1, "AAA")])
    d.build_universe(db, "2026-08-17")
    d.build_universe(db, "2026-09-17")
    cohorts = [r["as_of_date"] for r in db.execute("SELECT DISTINCT as_of_date FROM universe_snapshot").fetchall()]
    assert set(cohorts) == {"2026-08-17", "2026-09-17"}  # two distinct cohorts
    # D1's cohort is still intact (append-only, survivorship-free)
    assert any(u.ticker == "AAA" for u in universe_as_of(db, "2026-08-17"))


def test_cohort_nonempty_with_empty_catalyst_store(monkeypatch, db):
    """Blocker-1 trap: an EMPTY `catalyst` table (do NOT seed it) must still yield included_count>0
    because build_universe passes min_catalyst_density=0. A seeded table would mask the trap."""
    assert db.execute("SELECT COUNT(*) AS n FROM catalyst").fetchone()["n"] == 0  # unseeded
    d = _wire_build(monkeypatch, [_screen_rec(1, "AAA"), _screen_rec(2, "BBB", ta="cardio")])
    summary = d.build_universe(db, "2026-08-17")
    assert summary["included_count"] > 0
    included = [u for u in __import__("catalyst_trader.universe.build", fromlist=["universe_as_of"]).universe_as_of(db, "2026-08-17") if u.included]
    assert len(included) > 0


def test_delisted_retained(monkeypatch, db):
    from catalyst_trader.universe.build import universe_as_of

    d = _wire_build(monkeypatch, [_screen_rec(1, "AAA"), _screen_rec(2, "DEAD", delisted=True)])
    d.build_universe(db, "2026-08-17")
    dead = next(u for u in universe_as_of(db, "2026-08-17") if u.ticker == "DEAD")
    assert dead.delisted is True  # retained, not dropped (survivorship-free)


def test_summary_has_provenance_and_tradeoff(monkeypatch, db):
    d = _wire_build(monkeypatch, [_screen_rec(1, "AAA"), _screen_rec(2, "BBB", ta="cardio")])
    summary = d.build_universe(db, "2026-08-17")
    assert summary["admissions"]
    for a in summary["admissions"]:
        assert a["source_url"] and a["fetch_ts"] and a["grade"]
    assert "measured_lambda" in summary and "target_reached" in summary
    assert isinstance(summary["included_count"], int)  # distinct field, reconciles with n_admitted
    assert summary["included_count"] <= summary["n_admitted"]
    assert "tradeoff" in summary and summary["tradeoff"]
