"""Money-path gateway wiring (DBOOK-08): backtest + shared sleeve + live desk read through
serving.asof — backtest at cutoff=W, live at cutoff=now — so both paths execute IDENTICAL read
code (decision B, live-vs-backtest drift eliminated). Behaviour-preserving: the shipped synth
baseline is unchanged; no raw point-in-time SCAN remains on the money-paths.
"""

import pytest

from catalyst_trader import db as _db
from catalyst_trader import serving, store
from catalyst_trader.backtest import events as bt_events
from catalyst_trader.backtest.engine import run_layer_a
from catalyst_trader.quant import weekly as qw
from tests.synth_history import seed_history, week_ends


def _conn():
    c = _db.connect(":memory:")
    _db.migrate(c)
    return c


# --- Task 1: backtest read-path + shared sleeve ---------------------------------------------

def test_backtest_reads_route_through_gateway(monkeypatch):
    conn = _conn()
    wk = seed_history(conn, tickers=["AAAA"], weeks=6)
    calls = {"n": 0}
    real = serving.asof

    def spy(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(serving, "asof", spy)
    bt_events.build_event_set(conn, start=wk[0], end=wk[-1])
    assert calls["n"] > 0  # the event-set builder reads through serving.asof, not raw store


def test_events_module_has_no_raw_pit_scan():
    import pathlib
    src = pathlib.Path(bt_events.__file__).read_text()
    assert "serving" in src
    assert "last_verified_at <=" not in src  # the ad-hoc post-filter is GONE (replaced by book.catalysts)
    assert "bars_asof" not in src and "universe_as_of" not in src  # raw PIT scans removed


def test_build_event_set_uses_bitemporal_catalysts():
    conn = _conn()
    wk = week_ends(8)
    # a catalyst whose version was recorded (last_verified_at) AFTER the week it would trade in
    seed_history(conn, tickers=["AAAA"], weeks=8,
                 catalysts=[{"ticker": "AAAA", "event_date": wk[5], "last_verified_at": wk[6]}])
    recs = build = bt_events.build_event_set(conn, start=wk[0], end=wk[-1], hold_days=60)
    by = {r["as_of"]: r for r in recs}
    # at wk[3] (< recorded_at wk[6]) the catalyst is not yet knowable -> excluded via book.catalysts()
    assert [c for c in by[wk[3]]["catalysts"] if c["ticker"] == "AAAA"] == []


def test_backtest_baseline_unchanged():
    # determinism + the catalyst leg survives the gateway wiring (the shipped baseline/reuse tests
    # lock the exact numbers; here we pin that the wired path is reproducible and non-empty).
    conn1, conn2 = _conn(), _conn()
    for c in (conn1, conn2):
        weeks = week_ends(12)
        cat = {"ticker": "CAT", "event_date": weeks[6], "last_verified_at": weeks[4]}
        seed_history(c, tickers=["XBI", "AAAA", "CAT"], weeks=12, catalysts=[cat])
        # CAT bars crafted for a decision-week drop trigger
        store.upsert_bars(c, "CAT", [
            {"week_end": weeks[4], "open": 10, "high": 10.5, "low": 9.8, "close": 10.0, "volume": 2e6},
            {"week_end": weeks[5], "open": 9.9, "high": 10, "low": 9.3, "close": 9.4, "volume": 2e6},
            {"week_end": weeks[6], "open": 7.0, "high": 8, "low": 6, "close": 7.5, "volume": 2e6},
        ])
    _, d1 = run_layer_a(conn1, None, start=week_ends(12)[2], end=week_ends(12)[10])
    _, d2 = run_layer_a(conn2, None, start=week_ends(12)[2], end=week_ends(12)[10])
    assert d1 == d2  # reproducible through the gateway
    assert d1.n_weeks == 9 and d1.n_trades >= 1


def test_sleeve_cutoff_defaults_to_as_of():
    conn = _conn()
    wk = seed_history(conn, tickers=["AAAA"], weeks=6)
    view = qw.as_of_view(conn, wk[-1])  # sleeve adapter at cutoff = the week
    # behaviour-identical to the raw store read at cutoff >= as_of (no lag)
    assert view.bars_asof(conn, "AAAA", wk[-1]) == store.bars_asof(conn, "AAAA", wk[-1])


def test_sleeve_bars_route_through_gateway(monkeypatch):
    conn = _conn()
    wk = seed_history(conn, tickers=["AAAA"], weeks=6)
    calls = {"n": 0}
    real = serving.asof

    def spy(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(serving, "asof", spy)
    qw.as_of_view(conn, wk[-1]).bars_asof(conn, "AAAA", wk[-1])
    assert calls["n"] > 0
