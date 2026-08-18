"""Movement-based screen + realized-catalyst-move backfill (universe/discover.py) — offline.

Phase 6.12 Plan 06: the market-cap CEILING is removed; a name is kept only if it actually MOVES on
its catalysts (per-name median realized move >= threshold). The multi-year historical catalysts +
their point-in-time realized moves are persisted (catalyst table + new catalyst_move table) as the
warm-start backfill, with NO look-ahead (knowable_asof = T+2 close date). ZERO live API — every
provider read (get_daily_bars, prices, options_cboe, edgar fundamentals) is monkeypatched.
"""

import pytest

from catalyst_trader.universe import discover


# ── builders ───────────────────────────────────────────────────────────────────────────────


def _cat(event_date="2024-05-31", ctype="pdufa", ref=None):
    return {"type": ctype, "event_date": event_date,
            "source_url": ref or f"https://sec.gov/{event_date}", "fetch_ts": "2026-08-17T00:00:00Z",
            "grade": "green"}


def _cand(cik=1, ticker="BBIO", *, catalysts=None, ta="oncology", **extra):
    c = {"cik": cik, "ticker": ticker, "company_name": f"{ticker} Inc.",
         "catalysts": catalysts if catalysts is not None else [_cat()],
         "source_feeds": {"edgar"}, "therapeutic_area": ta}
    c.update(extra)
    return c


def _daily(dates_closes):
    """[(iso_date, close), ...] -> get_daily_bars-shape bars (chronological)."""
    return [{"week_end": d, "open": c, "high": c, "low": c, "close": c, "volume": 1_000_000,
             "source": "nasdaq", "source_grade": "yellow"} for d, c in dates_closes]


# ── Task 2: realized-move math + knowable_asof (no look-ahead) ─────────────────────────────────


def test_realized_move_window_math(monkeypatch):
    # T-1=100 (10/01), T0=10/02, T+1=10/05, T+2=140 (10/06) -> |140/100-1| = 0.40
    window = _daily([("2026-10-01", 100.0), ("2026-10-02", 110.0),
                     ("2026-10-05", 130.0), ("2026-10-06", 140.0)])
    monkeypatch.setattr(discover, "get_daily_bars", lambda t, s, e, **k: window)
    result = discover._realized_catalyst_move("TEST", "2026-10-02")
    assert result is not None
    move, move_window, knowable_asof = result[0], result[1], result[2]
    assert move == pytest.approx(0.40)
    assert knowable_asof == "2026-10-06"  # the T+2 close date — the move is knowable only then
    assert move_window == "(-1,2)"


def test_move_none_when_future_catalyst(monkeypatch):
    # daily data stops at T+1 (T+2 has not closed yet) -> no computable move -> None (never imputed)
    window = _daily([("2026-10-01", 100.0), ("2026-10-02", 110.0), ("2026-10-05", 130.0)])
    monkeypatch.setattr(discover, "get_daily_bars", lambda t, s, e, **k: window)
    assert discover._realized_catalyst_move("TEST", "2026-10-02") is None


def test_move_none_when_month_precision(monkeypatch):
    # a YYYY-MM event_date has no day -> can't locate T-1/T+2 -> None (no network call either)
    def _boom(*a, **k):
        raise AssertionError("get_daily_bars must not be called for a month-precision date")

    monkeypatch.setattr(discover, "get_daily_bars", _boom)
    assert discover._realized_catalyst_move("TEST", "2026-10") is None


def test_move_none_when_no_daily_data(monkeypatch):
    monkeypatch.setattr(discover, "get_daily_bars", lambda t, s, e, **k: [])
    assert discover._realized_catalyst_move("TEST", "2026-10-02") is None


def test_name_move_stat_median():
    assert discover._name_move_stat([0.1, 0.4, 0.6]) == pytest.approx(0.4)
    assert discover._name_move_stat([]) is None


# ── Task 2: persist historical catalysts + moves (idempotent, point-in-time) ──────────────────


def test_persist_backfill_catalysts(monkeypatch, db):
    monkeypatch.setattr(discover, "_realized_catalyst_move",
                        lambda t, ed, **k: (0.30, "(-1,2)", "2024-06-03", "green"))
    cand = _cand(catalysts=[_cat("2024-05-31", ref="A"), _cat("2023-02-15", ref="B")])
    ids = discover._persist_backfill(db, cand)
    assert len(ids) == 2
    rows = db.execute(
        "SELECT ticker, source_origin, status, event_date FROM catalyst ORDER BY event_date"
    ).fetchall()
    assert len(rows) == 2
    for r in rows:
        assert r["ticker"] == "BBIO"
        assert r["source_origin"] == "curated_pdufa"
        assert r["status"] == "resolved"

    # idempotent re-run: same (ticker, external_ref) upserts, no duplicate catalysts
    discover._persist_backfill(db, cand)
    assert db.execute("SELECT COUNT(*) AS n FROM catalyst").fetchone()["n"] == 2


def test_persist_moves_pointintime(monkeypatch, db):
    monkeypatch.setattr(discover, "_realized_catalyst_move",
                        lambda t, ed, **k: (0.30, "(-1,2)", "2024-06-03", "green"))
    cand = _cand(catalysts=[_cat("2024-05-31", ref="A")])
    discover._persist_backfill(db, cand)
    moves = db.execute(
        "SELECT realized_move, move_window, knowable_asof, source_grade FROM catalyst_move"
    ).fetchall()
    assert len(moves) == 1
    assert moves[0]["realized_move"] == pytest.approx(0.30)
    assert moves[0]["knowable_asof"] == "2024-06-03"  # the T+2 close date (no look-ahead)
    assert moves[0]["move_window"] == "(-1,2)"

    # re-run UPSERTs on UNIQUE(catalyst_id, move_window) -> no duplicate move rows
    discover._persist_backfill(db, cand)
    assert db.execute("SELECT COUNT(*) AS n FROM catalyst_move").fetchone()["n"] == 1


def test_persist_backfill_attaches_name_move_stat(monkeypatch, db):
    # two catalysts with moves 0.2 and 0.4 -> median 0.3 attached to the candidate
    seq = iter([(0.2, "(-1,2)", "2024-06-03", "green"), (0.4, "(-1,2)", "2023-02-18", "green")])
    monkeypatch.setattr(discover, "_realized_catalyst_move", lambda t, ed, **k: next(seq))
    cand = _cand(catalysts=[_cat("2024-05-31", ref="A"), _cat("2023-02-15", ref="B")])
    discover._persist_backfill(db, cand)
    assert cand["realized_move_median"] == pytest.approx(0.3)
    assert cand["n_moves"] == 2


def test_persist_backfill_move_unknown(monkeypatch, db):
    # no computable move on any catalyst -> stat None, n_moves 0, still persists the catalyst rows
    monkeypatch.setattr(discover, "_realized_catalyst_move", lambda t, ed, **k: None)
    cand = _cand(catalysts=[_cat("2024-05-31", ref="A")])
    discover._persist_backfill(db, cand)
    assert cand["realized_move_median"] is None
    assert cand["n_moves"] == 0
    assert db.execute("SELECT COUNT(*) AS n FROM catalyst").fetchone()["n"] == 1
    assert db.execute("SELECT COUNT(*) AS n FROM catalyst_move").fetchone()["n"] == 0


# ── Task 3: move screen (cap ceiling removed) + rank-by-move + build_universe ──────────────────


def _bars(close=100.0, volume=350_000, n=8):
    return [{"week_end": f"2026-0{(i % 8) + 1}-01", "close": close, "volume": volume} for i in range(n)]


def _opt(*, call_bid=4.2, call_ask=4.6, put_bid=3.9, put_ask=4.3, call_oi=850, put_oi=780):
    return {"options_quote": {"call_bid": call_bid, "call_ask": call_ask, "put_bid": put_bid,
                              "put_ask": put_ask, "call_oi": call_oi, "put_oi": put_oi,
                              "expiry": "2026-10-16"}}


def _wire_screen(monkeypatch, *, bars, fund, opt, move=(0.30, "(-1,2)", "2024-06-03", "green")):
    monkeypatch.setattr(discover, "get_weekly_bars", lambda t, s, e, **k: bars)
    monkeypatch.setattr(discover, "fundamentals", lambda t: fund)
    monkeypatch.setattr(discover.options_cboe, "fetch", lambda t: opt)
    monkeypatch.setattr(discover, "_realized_catalyst_move", lambda t, ed, **k: move)


def test_cap_ceiling_removed_large_cap_admitted(monkeypatch):
    # BBIO-shape: cap = 150M shares * $100 = $15B (would be DROPPED by the old $10B ceiling)
    _wire_screen(monkeypatch, bars=_bars(100, 350_000),
                 fund={"shares_outstanding": 150_000_000, "cash_runway_months": 24}, opt=_opt())
    admitted, rejected = discover.screen_candidates({1: _cand(1, "BBIO")}, "2026-08-17")
    assert [r["ticker"] for r in admitted] == ["BBIO"]
    assert admitted[0]["market_cap"] == 15_000_000_000
    # no cap-over reason anywhere (ceiling fully removed)
    all_reasons = [rn for r in admitted + rejected for rn in r.get("reasons", [])]
    assert not any("market_cap" in rn and ">" in rn for rn in all_reasons)


def test_move_screen_keeps_mover(monkeypatch):
    _wire_screen(monkeypatch, bars=_bars(100, 350_000),
                 fund={"shares_outstanding": 10_000_000, "cash_runway_months": 24}, opt=_opt(),
                 move=(0.30, "(-1,2)", "2024-06-03", "green"))
    admitted, _ = discover.screen_candidates({1: _cand(1, "MOVER")}, "2026-08-17",
                                             criteria={"move_threshold": 0.10})
    assert admitted and admitted[0]["realized_move_median"] == pytest.approx(0.30)


def test_move_screen_no_longer_drops_sleeper(monkeypatch):
    # PIVOT-CORRECTION (Plan 07): the fixed move_threshold gate is RETIRED from screen_candidates
    # (tradeability-only). A below-old-threshold mover (0.03) that passes ADV/cap/optionable is now
    # ADMITTED; the volatility judgement moved to the BACKWARD score in select_members.
    _wire_screen(monkeypatch, bars=_bars(100, 350_000),
                 fund={"shares_outstanding": 10_000_000, "cash_runway_months": 24}, opt=_opt(),
                 move=(0.03, "(-1,2)", "2024-06-03", "green"))
    admitted, rejected = discover.screen_candidates({1: _cand(1, "SLEEP")}, "2026-08-17")
    assert [r["ticker"] for r in admitted] == ["SLEEP"]
    all_reasons = [rn for r in admitted + rejected for rn in r.get("reasons", [])]
    assert not any("move" in rn for rn in all_reasons)


def test_move_unknown_no_longer_rejected(monkeypatch):
    # PIVOT-CORRECTION (Plan 07): a name with no computable move is no longer dropped by the screen
    # (no move gate). Its realized_move_median is simply None; the n>=2 score gate handles history.
    _wire_screen(monkeypatch, bars=_bars(100, 350_000),
                 fund={"shares_outstanding": 10_000_000, "cash_runway_months": 24}, opt=_opt(),
                 move=None)  # no computable move
    admitted, rejected = discover.screen_candidates({1: _cand(1, "UNK")}, "2026-08-17")
    assert [r["ticker"] for r in admitted] == ["UNK"]
    assert "move_unknown" not in [rn for r in admitted + rejected for rn in r.get("reasons", [])]


def test_rank_by_move_magnitude():
    screened = [
        {"cik": 1, "ticker": "SML", "catalysts": [_cat()], "realized_move_median": 0.12, "n_moves": 1},
        {"cik": 2, "ticker": "BIG", "catalysts": [_cat()], "realized_move_median": 0.55, "n_moves": 1},
        {"cik": 3, "ticker": "MID", "catalysts": [_cat()], "realized_move_median": 0.30, "n_moves": 1},
    ]
    shortlist, _ = discover.size_to_density(screened, "2026-08-17", target_lambda=99.0)  # unreachable -> all
    assert [r["ticker"] for r in shortlist] == ["BIG", "MID", "SML"]  # biggest movers first


def _build_cand(cik, ticker, *, ta="oncology"):
    return _cand(cik, ticker, ta=ta, catalysts=[_cat("2024-05-31", ref=f"{ticker}-A"),
                                                _cat("2023-02-15", ref=f"{ticker}-B")])


def test_build_universe_persists_backfill_and_writes_cohort(monkeypatch, db):
    from catalyst_trader.universe.build import universe_as_of

    cands = {1: _build_cand(1, "BBIO"), 2: _build_cand(2, "AXSM", ta="cns")}
    monkeypatch.setattr(discover, "discover_candidates", lambda *a, **k: cands)
    monkeypatch.setattr(discover, "_realized_catalyst_move",
                        lambda t, ed, **k: (0.30, "(-1,2)", "2024-06-03", "green"))
    monkeypatch.setattr(discover, "get_weekly_bars", lambda t, s, e, **k: _bars(100, 350_000))
    monkeypatch.setattr(discover, "fundamentals",
                        lambda t: {"shares_outstanding": 150_000_000, "cash_runway_months": 24})
    monkeypatch.setattr(discover.options_cboe, "fetch", lambda t: _opt())

    assert db.execute("SELECT COUNT(*) AS n FROM catalyst").fetchone()["n"] == 0  # empty store (Blocker-1)
    summary = discover.build_universe(db, "2026-08-17")

    # warm-start backfill persisted (catalysts + moves)
    assert db.execute("SELECT COUNT(*) AS n FROM catalyst").fetchone()["n"] == 4  # 2 names x 2 catalysts
    assert db.execute("SELECT COUNT(*) AS n FROM catalyst_move").fetchone()["n"] == 4
    # append-only survivorship-free cohort written; Blocker-1: included>0 vs the (pre-backfill) empty store
    names = {u.ticker for u in universe_as_of(db, "2026-08-17") if u.included}
    assert {"BBIO", "AXSM"} <= names
    assert summary["included_count"] > 0
    # new summary fields
    assert summary["move_threshold"] == 0.10
    assert summary["n_move_unknown"] == 0
    assert summary["n_backfilled_catalysts"] == 4
    assert summary["n_moves_persisted"] == 4
    for a in summary["admissions"]:
        assert a["realized_move_median"] == pytest.approx(0.30)


def test_blocker_fixes_preserved(monkeypatch, db):
    captured = {}

    def _spy_build_snapshot(conn, as_of, seed_rows, *, criteria):
        captured["criteria"] = criteria
        captured["n_seed"] = len(seed_rows)
        return 1  # store writes 1 included row

    cands = {1: _build_cand(1, "BBIO")}
    monkeypatch.setattr(discover, "discover_candidates", lambda *a, **k: cands)
    monkeypatch.setattr(discover, "_realized_catalyst_move",
                        lambda t, ed, **k: (0.30, "(-1,2)", "2024-06-03", "green"))
    monkeypatch.setattr(discover, "get_weekly_bars", lambda t, s, e, **k: _bars(100, 350_000))
    monkeypatch.setattr(discover, "fundamentals",
                        lambda t: {"shares_outstanding": 10_000_000, "cash_runway_months": 24})
    monkeypatch.setattr(discover.options_cboe, "fetch", lambda t: _opt())
    monkeypatch.setattr(discover, "build_snapshot", _spy_build_snapshot)

    summary = discover.build_universe(db, "2026-08-17")
    # Blocker-1: min_catalyst_density passed as 0 (store-density floor stays disabled)
    assert captured["criteria"]["min_catalyst_density"] == 0
    # Blocker-2/3: included_count is DISTINCT from n_admitted and reconciles with the store's count
    assert summary["included_count"] == 1
    assert summary["n_admitted"] >= 1
    assert isinstance(summary["included_count"], int)
