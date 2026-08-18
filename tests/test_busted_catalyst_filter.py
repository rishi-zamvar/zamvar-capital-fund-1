"""E10 — recent-catalyst (busted/falling-knife) exclusion for the statistical sleeve."""
from catalyst_trader import db as _db
from catalyst_trader.backtest.engine import _recent_catalyst_tickers


def _cat(conn, cid, ticker, ev, recorded):
    conn.execute(
        "INSERT INTO catalyst (id,ticker,catalyst_type,event_date,date_precision,uncertainty_type,"
        "status,source_origin,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (cid, ticker, "trial_readout", ev, "day", "firm", "resolved", "curated_pdufa", recorded, recorded))
    conn.execute("INSERT INTO catalyst_version (catalyst_id,event_date,recorded_at) VALUES (?,?,?)",
                 (cid, ev, recorded))
    conn.commit()


def test_recent_catalyst_within_window_flagged():
    c = _db.connect(":memory:"); _db.migrate(c)
    _cat(c, 1, "CAPR", "2026-06-20", "2026-01-01")   # 3wk before as_of, knowable early
    got = _recent_catalyst_tickers(c, "2026-07-10", lookback_days=56)
    assert "CAPR" in got


def test_catalyst_outside_lookback_not_flagged():
    c = _db.connect(":memory:"); _db.migrate(c)
    _cat(c, 1, "CAPR", "2026-01-01", "2025-06-01")   # ~6mo before as_of -> outside 56d
    got = _recent_catalyst_tickers(c, "2026-07-10", lookback_days=56)
    assert "CAPR" not in got


def test_future_catalyst_not_flagged_as_recent():
    c = _db.connect(":memory:"); _db.migrate(c)
    _cat(c, 1, "CAPR", "2026-09-01", "2026-01-01")   # event AFTER as_of -> not a recent/past catalyst
    got = _recent_catalyst_tickers(c, "2026-07-10", lookback_days=56)
    assert "CAPR" not in got


def test_unknowable_catalyst_excluded():
    c = _db.connect(":memory:"); _db.migrate(c)
    _cat(c, 1, "CAPR", "2026-06-20", "2026-08-01")   # recorded AFTER as_of -> not knowable yet
    got = _recent_catalyst_tickers(c, "2026-07-10", lookback_days=56)
    assert "CAPR" not in got
