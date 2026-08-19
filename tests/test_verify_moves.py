"""Offline TDD for FIX B — verify + correct the signed T-1..T+2 realized move from cached bars.

Every test is in-memory (the `db` fixture) with synthetic bars; the bars_provider seam is INJECTED
so nothing here touches the network or the live catalyst.db (zero API — CLAUDE.md frugality).
"""

from catalyst_trader.playbook.verify_moves import (
    correct_move,
    find_move_divergences,
    recompute_signed_move,
)


def _bar(week_end, close):
    return {"ticker": "VERA", "week_end": week_end, "close": close}


# A T-1..T+2 window around event_date "2026-01-02": indices are T-1, T0, T+1, T+2.
def _window_bars(c_tm1, c_tp2, ticker="VERA"):
    return [
        {"ticker": ticker, "week_end": "2026-01-01", "close": c_tm1},  # T-1
        {"ticker": ticker, "week_end": "2026-01-02", "close": 97.0},   # T0 (event_date)
        {"ticker": ticker, "week_end": "2026-01-03", "close": 92.0},   # T+1
        {"ticker": ticker, "week_end": "2026-01-05", "close": c_tp2},  # T+2
    ]


# ── recompute_signed_move (pure, SIGNED) ─────────────────────────────────────

def test_given_daily_bars_when_recompute_then_signed_minus1_plus2():
    bars = _window_bars(100.0, 83.0)
    got = recompute_signed_move(bars, "2026-01-02")
    assert got is not None
    assert abs(got - (83.0 / 100.0 - 1.0)) < 1e-9  # -0.17 SIGNED, not abs


def test_given_positive_window_when_recompute_then_positive_signed():
    bars = _window_bars(100.0, 117.0)
    assert abs(recompute_signed_move(bars, "2026-01-02") - 0.17) < 1e-9


def test_given_month_precision_event_when_recompute_then_none():
    bars = _window_bars(100.0, 83.0)
    assert recompute_signed_move(bars, "2026-01") is None  # len != 10 -> never imputed


def test_given_missing_tplus2_when_recompute_then_none():
    bars = _window_bars(100.0, 83.0)[:3]  # drop T+2
    assert recompute_signed_move(bars, "2026-01-02") is None


def test_given_no_bar_at_or_after_event_when_recompute_then_none():
    bars = [_bar("2025-12-01", 100.0), _bar("2025-12-02", 101.0)]
    assert recompute_signed_move(bars, "2026-01-02") is None


# ── find_move_divergences (injectable bars_provider, offline) ────────────────

def _seed_move(conn, *, ticker, event_date, realized_move, move_window="(-1,2)"):
    cur = conn.execute(
        "INSERT INTO catalyst (ticker, catalyst_type, event_date, date_precision, uncertainty_type, "
        "status, source_origin, created_at, updated_at) VALUES "
        "(?, 'pdufa', ?, 'day', 'firm', 'resolved', 'curated_pdufa', '2026-01-01', '2026-01-01')",
        (ticker, event_date),
    )
    cid = cur.lastrowid
    conn.execute(
        "INSERT INTO catalyst_move (catalyst_id, realized_move, move_window, knowable_asof, computed_at) "
        "VALUES (?, ?, ?, ?, '2026-01-01')",
        (cid, realized_move, move_window, event_date),
    )
    conn.commit()
    return cid


def test_given_stored_move_diverges_when_find_divergences_then_flagged(db):
    cid = _seed_move(db, ticker="VERA", event_date="2026-01-02", realized_move=+0.17)
    # bars imply -0.17 but the stored value is +0.17 (a sign-flip suspect)
    provider = lambda tk, ed: _window_bars(100.0, 83.0, ticker=tk)
    divs = find_move_divergences(db, provider, tol=0.02)
    assert len(divs) == 1
    d = divs[0]
    assert d["catalyst_id"] == cid and d["ticker"] == "VERA"
    assert d["stored"] == 0.17
    assert abs(d["recomputed"] - (-0.17)) < 1e-9
    assert "delta" in d


def test_given_within_tolerance_when_find_divergences_then_not_flagged(db):
    # recomputed = +0.17; stored = 0.171 -> delta 0.001 < default tol
    _seed_move(db, ticker="ZBIO", event_date="2026-01-02", realized_move=0.171)
    provider = lambda tk, ed: _window_bars(100.0, 117.0, ticker=tk)
    assert find_move_divergences(db, provider, tol=0.02) == []


def test_given_recompute_none_when_find_divergences_then_never_flagged(db):
    # no usable window -> recompute None -> keep the stored value, never flag (cite-or-drop)
    _seed_move(db, ticker="LYRA", event_date="2026-01-02", realized_move=0.99)
    provider = lambda tk, ed: [_bar("2025-12-01", 100.0)]  # no bar at/after event, short window
    assert find_move_divergences(db, provider, tol=0.02) == []


# ── correct_move (idempotent single-row UPDATE) ──────────────────────────────

def test_given_divergence_when_correct_move_then_row_updated(db):
    cid = _seed_move(db, ticker="QURE", event_date="2026-01-02", realized_move=+0.30)
    other = _seed_move(db, ticker="VERA", event_date="2026-02-02", realized_move=+0.10)

    correct_move(db, cid, "(-1,2)", -0.17)

    got = db.execute(
        "SELECT realized_move FROM catalyst_move WHERE catalyst_id=? AND move_window='(-1,2)'", (cid,)
    ).fetchone()["realized_move"]
    assert abs(got - (-0.17)) < 1e-9
    # the other row is untouched
    untouched = db.execute(
        "SELECT realized_move FROM catalyst_move WHERE catalyst_id=?", (other,)
    ).fetchone()["realized_move"]
    assert untouched == 0.10
