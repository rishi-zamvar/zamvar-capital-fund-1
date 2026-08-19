"""Tier-3 Task A / Task 3 — latency-honest fills + T+0/T+1/T+2 sweep + the off-map/Task-B seam.

Money-critical invariants under test:
  - the daily reflex fills at the NEXT bar open on ENTRIES AND EXITS (signal-at-close ->
    next-bar-open, no same-bar-fill bias);
  - exit_latency_bars (default 0 = T+0, byte-for-byte current) shifts the EXIT fill by that many
    additional bars beyond the next-open bar; a latency past the in-window bars degrades to the LAST
    available open (honest, never look-ahead);
  - latency_sweep re-runs the daily backtest once per delay and returns one BaselineDistribution per
    delay so degradation-with-delay is reportable (an edge alive only at T+0 is fragile);
  - the off-map escalation seam surfaces off_map on the LegOutcome but invokes NO reasoning agent —
    Task B's off-map reasoning-latency exit path ships here as a DEFERRED xfail test (not built).

Fully offline: ':memory:' + injected synthetic daily bars — ZERO live get_daily_bars / network / DB.
"""

import pytest

from catalyst_trader import db as _db
from catalyst_trader.backtest.engine import BaselineDistribution, latency_sweep, run_layer_a
from catalyst_trader.backtest.fill import reflex_exit
from catalyst_trader.desk.exit_plan import EXIT_PARAMS

from tests.test_backtest_engine import _seed_std


_FAR = "2099-01-01"
_MULT = EXIT_PARAMS["off_map_mult"]


def _bar(day, o, h, lo, c, vol=1_000_000.0, **extra):
    return {"week_end": day, "open": o, "high": h, "low": lo, "close": c, "volume": vol, **extra}


def _conn():
    conn = _db.connect(":memory:")
    _db.migrate(conn)
    return conn


# ============================== exit_latency_bars — the shift ========================

# band breach at bar 0 -> T+0 fills at bar 1 open; latency shifts to bar 2 / bar 3 opens.
_LAT_BARS = [
    _bar("2024-01-02", 100, 101, 99, 88),   # band breach (close 88 < band[0]=90)
    _bar("2024-01-03", 87, 88, 86, 87),     # T+0 exit fill open
    _bar("2024-01-04", 80, 81, 79, 80),     # T+1 exit fill open
    _bar("2024-01-05", 70, 71, 69, 70),     # T+2 exit fill open
]


def _rx(latency):
    return reflex_exit(_LAT_BARS, entry=100.0, side="long", band=(90.0, 120.0), stop=50.0,
                       target=200.0, time_barrier=_FAR, slippage=0.0, off_map_mult=_MULT,
                       exit_latency_bars=latency)


def test_t0_exit_fills_at_next_bar_open():
    rx = _rx(0)
    assert rx["fill"] == pytest.approx(87.0)     # the next-open bar
    assert rx["exit"] == "2024-01-03"


def test_latency_one_shifts_exit_one_bar_later():
    rx = _rx(1)
    assert rx["fill"] == pytest.approx(80.0)
    assert rx["exit"] == "2024-01-04"


def test_latency_two_shifts_exit_two_bars_later():
    rx = _rx(2)
    assert rx["fill"] == pytest.approx(70.0)
    assert rx["exit"] == "2024-01-05"


def test_latency_past_window_degrades_to_last_open():
    rx = _rx(9)                                   # far beyond the in-window bars
    assert rx["fill"] == pytest.approx(70.0)      # degrades to the LAST available open (no look-ahead)
    assert rx["exit"] == "2024-01-05"


def test_default_latency_is_t0():
    # the knob defaults to 0 (byte-for-byte the Task-2 current behaviour)
    rx = reflex_exit(_LAT_BARS, entry=100.0, side="long", band=(90.0, 120.0), stop=50.0,
                     target=200.0, time_barrier=_FAR, slippage=0.0, off_map_mult=_MULT)
    assert rx["fill"] == pytest.approx(87.0)


# ============================== latency_sweep — T+0/1/2 degradation ==================


def _trend_provider(ticker, week_start, week_end):
    # entry at the first bar's open; a monotonic slide so each later exit open differs
    # -> each latency yields a distinct fill -> a distinct distribution (degradation visible).
    return [
        _bar(week_start, 10.0, 10.1, 4.9, 5.0),   # entry open 10, close 5 -> band breach
        _bar("2024-02-06", 7.0, 7.1, 6.9, 7.0),   # T+0 exit
        _bar("2024-02-07", 6.0, 6.1, 5.9, 6.0),   # T+1 exit
        _bar("2024-02-08", 5.0, 5.1, 4.9, 5.0),   # T+2 exit
    ]


def test_latency_sweep_returns_a_distribution_per_delay():
    conn = _conn()
    weeks = _seed_std(conn)
    sweep = latency_sweep(conn, None, start=weeks[5], end=weeks[5],
                          daily_bars_provider=_trend_provider, delays=(0, 1, 2))
    assert [s["latency"] for s in sweep] == [0, 1, 2]
    assert all(isinstance(s["distribution"], BaselineDistribution) for s in sweep)


def test_latency_sweep_shows_degradation_with_delay():
    conn = _conn()
    weeks = _seed_std(conn)
    sweep = latency_sweep(conn, None, start=weeks[5], end=weeks[5],
                          daily_bars_provider=_trend_provider, delays=(0, 1, 2))
    dists = [s["distribution"] for s in sweep]
    # a later exit fills lower on the slide -> the result must MOVE as delay grows (not identical)
    assert not (dists[0] == dists[1] == dists[2])


# ============================== off-map seam surfaces on the leg =====================


def test_off_map_leg_carries_flag():
    conn = _conn()
    weeks = _seed_std(conn)

    def collapse(ticker, week_start, week_end):
        return [_bar(week_start, 5.0, 5.0, 0.01, 0.01), _bar(week_end, 0.02, 0.03, 0.01, 0.02)]

    results, _dist = run_layer_a(conn, None, start=weeks[5], end=weeks[5],
                                 granularity="daily", daily_bars_provider=collapse)
    cat = [l for wk in results for l in wk.legs if l.ticker == "CAT" and l.is_catalyst]
    assert cat and cat[0].off_map is True


# ============================== Task B — DEFERRED (xfail) ============================


@pytest.mark.xfail(strict=True,
                   reason="Task B: off-map -> single reasoning agent, reasoning-latency-modeled "
                          "fill — NOT YET WIRED (deferred wiring ships as an xfail test)")
def test_off_map_escalates_to_reasoning_agent():
    # Task B: an off_map leg routes to a SINGLE reasoning agent whose exit fill is modeled with
    # REASONING latency (the agent's think-time), not just bar latency. The agent + its hook are
    # deliberately out of Task A scope — only the off_map flag + this deferred test exist today.
    from catalyst_trader.backtest import engine
    assert hasattr(engine, "reasoning_exit"), "the Task-B off-map reasoning-exit hook is not built"
