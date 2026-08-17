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
