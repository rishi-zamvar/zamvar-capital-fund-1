"""Tier-3 Task A / Task 2 — the intraweek DAILY reflex (weekly preserved as the coarsest knob).

Money-critical invariants under test:
  - reflex_exit is PURE and fires the FIRST triggered exit, filling at the NEXT bar's open
    (no same-bar-fill bias) — band breach / adaptive stop / take-profit;
  - a stop that GAPS below the stop level fills at the GAP OPEN, never the stop (the fill.py
    gap-open discipline, reused — the classic optimistic-backtest lie is refused);
  - the hard TIME barrier exits at that bar's own open (triple-barrier first-to-hit);
  - a halted intended-fill bar rolls forward to the next NON-skipped open; no resumption -> None;
  - off_map marks a move outside the band by more than max(up,down)*off_map_mult (and a halt roll);
  - the WEEKLY path is byte-for-byte preserved (default granularity == explicit weekly), with the
    new LegOutcome off_map/exit_reason fields defaulting False/None.

Fully offline: synthetic daily bars are injected via a fake provider (mirrors verify_moves'
bars_provider seam) — ZERO live get_daily_bars, ZERO network, ZERO live DB in the reflex path.
"""

import pytest

from catalyst_trader import db as _db
from catalyst_trader.backtest.engine import LegOutcome, run_layer_a
from catalyst_trader.backtest.fill import reflex_exit
from catalyst_trader.desk.exit_plan import EXIT_PARAMS

from tests.synth_history import week_ends
from tests.test_backtest_engine import _seed_std  # reuse the offline catalyst seed


# --------------------------------------------------------------------------- helpers


def _bar(day, o, h, lo, c, vol=1_000_000.0, **extra):
    return {"week_end": day, "open": o, "high": h, "low": lo, "close": c, "volume": vol, **extra}


_FAR = "2099-01-01"  # a time_barrier far past the crafted bars (so TIME never preempts)
_MULT = EXIT_PARAMS["off_map_mult"]


# ============================== reflex_exit — the pure fill model =====================


def test_band_breach_exits_at_next_bar_open():
    bars = [
        _bar("2024-01-02", 100, 101, 99, 88),   # close 88 < band[0]=90 -> thesis-down band breach
        _bar("2024-01-03", 87, 90, 86, 89),     # fill at THIS open (next bar)
    ]
    rx = reflex_exit(bars, entry=100.0, side="long", band=(90.0, 120.0), stop=80.0,
                     target=130.0, time_barrier=_FAR, slippage=0.0, off_map_mult=_MULT)
    assert rx["reason"] == "band"
    assert rx["fill"] == pytest.approx(87.0)          # the NEXT bar open, not the breach close
    assert rx["exit"] == "2024-01-03"


def test_stop_that_gaps_fills_at_gap_open_not_stop_level():
    bars = [
        _bar("2024-01-02", 100, 101, 84, 92),   # low 84 <= stop 85 (close 92 inside band -> stop, not band)
        _bar("2024-01-03", 80, 82, 79, 81),     # next open 80 GAPS below the stop
    ]
    rx = reflex_exit(bars, entry=100.0, side="long", band=(90.0, 120.0), stop=85.0,
                     target=130.0, time_barrier=_FAR, slippage=0.01, off_map_mult=_MULT)
    assert rx["reason"] == "stop"
    assert rx["fill"] == pytest.approx(80.0 * (1 - 0.01))   # the GAP OPEN far side, slippage-worsened
    assert rx["fill"] != pytest.approx(85.0 * (1 - 0.01))   # NEVER the jumped stop level


def test_take_profit_fires_at_next_open():
    bars = [
        _bar("2024-01-02", 100, 116, 99, 112),  # high 116 >= target 115 (close 112 inside band)
        _bar("2024-01-03", 118, 119, 117, 118),
    ]
    rx = reflex_exit(bars, entry=100.0, side="long", band=(90.0, 120.0), stop=80.0,
                     target=115.0, time_barrier=_FAR, slippage=0.0, off_map_mult=_MULT)
    assert rx["reason"] == "tp"
    assert rx["fill"] == pytest.approx(118.0)


def test_time_barrier_forces_exit_at_that_bar_open():
    bars = [
        _bar("2024-01-02", 100, 101, 99, 100),  # inside band, nothing triggers
        _bar("2024-01-03", 101, 102, 100, 101),
        _bar("2024-01-04", 103, 104, 102, 103),  # date >= time_barrier -> exit at THIS open
    ]
    rx = reflex_exit(bars, entry=100.0, side="long", band=(90.0, 120.0), stop=80.0,
                     target=130.0, time_barrier="2024-01-04", slippage=0.0, off_map_mult=_MULT)
    assert rx["reason"] == "time"
    assert rx["fill"] == pytest.approx(103.0)   # the time-barrier bar's OWN open
    assert rx["exit"] == "2024-01-04"


def test_halted_fill_bar_rolls_to_next_available_open():
    bars = [
        _bar("2024-01-02", 100, 101, 99, 88),           # band breach
        _bar("2024-01-03", 0, 0, 0, 0, vol=0.0),        # intended fill bar HALTED (_skip) -> roll
        _bar("2024-01-04", 86, 87, 85, 86),             # next available open
    ]
    rx = reflex_exit(bars, entry=100.0, side="long", band=(90.0, 120.0), stop=80.0,
                     target=130.0, time_barrier=_FAR, slippage=0.0, off_map_mult=_MULT)
    assert rx["reason"] == "halt"
    assert rx["off_map"] is True                          # a halt roll is off the clean map (Task-B seam)
    assert rx["fill"] == pytest.approx(86.0)
    assert rx["exit"] == "2024-01-04"


def test_halt_with_no_resumption_returns_none():
    bars = [
        _bar("2024-01-02", 100, 101, 99, 88),           # band breach
        _bar("2024-01-03", 0, 0, 0, 0, vol=0.0),        # halted, and no later bar -> unfillable
    ]
    rx = reflex_exit(bars, entry=100.0, side="long", band=(90.0, 120.0), stop=80.0,
                     target=130.0, time_barrier=_FAR, slippage=0.0, off_map_mult=_MULT)
    assert rx is None


def test_off_map_set_on_outsized_move():
    # band=(90,120): up_frac=0.2, down_frac=0.1 -> ref=0.2; off-map excess threshold = 0.2*mult of entry.
    bars = [
        _bar("2024-01-02", 100, 101, 40, 55),   # close 55 -> excess (90-55)/100 = 0.35 > 0.2*1.5=0.30
        _bar("2024-01-03", 54, 55, 53, 54),
    ]
    rx = reflex_exit(bars, entry=100.0, side="long", band=(90.0, 120.0), stop=30.0,
                     target=130.0, time_barrier=_FAR, slippage=0.0, off_map_mult=1.5)
    assert rx["reason"] == "band"
    assert rx["off_map"] is True


def test_normal_breach_is_not_off_map():
    bars = [
        _bar("2024-01-02", 100, 101, 99, 88),   # excess (90-88)/100 = 0.02 < 0.30 -> on-map
        _bar("2024-01-03", 87, 88, 86, 87),
    ]
    rx = reflex_exit(bars, entry=100.0, side="long", band=(90.0, 120.0), stop=30.0,
                     target=130.0, time_barrier=_FAR, slippage=0.0, off_map_mult=1.5)
    assert rx["off_map"] is False


def test_no_trigger_no_time_barrier_returns_none():
    bars = [_bar("2024-01-02", 100, 101, 99, 100)]   # inside band, never reaches time_barrier
    rx = reflex_exit(bars, entry=100.0, side="long", band=(90.0, 120.0), stop=80.0,
                     target=130.0, time_barrier=_FAR, slippage=0.0, off_map_mult=_MULT)
    assert rx is None


# ============================== M1: hold-through price-exit suppression ===============
# A held_through=True leg is IN the binary event it came for — it must NOT be band/stop/tp'd out;
# it can exit ONLY at the TIME barrier (or a halt roll). held_through=False stays byte-for-byte.


def test_held_through_dip_then_recover_holds_to_time_barrier():
    # intraweek DIP breaches band-lower AND touches the stop, then recovers, then time barrier.
    bars = [
        _bar("2024-01-02", 100, 101, 78, 85),    # close 85 < band[0]=90 AND low 78 <= stop 80
        _bar("2024-01-03", 95, 100, 94, 98),     # recovers back inside band
        _bar("2024-01-04", 110, 112, 108, 110),  # date >= time_barrier -> exit at THIS open
    ]
    rx = reflex_exit(bars, entry=100.0, side="long", band=(90.0, 120.0), stop=80.0,
                     target=115.0, time_barrier="2024-01-04", slippage=0.0, off_map_mult=_MULT,
                     held_through=True)
    assert rx["reason"] == "time"           # NOT band, NOT stop
    assert rx["fill"] == pytest.approx(110.0)  # the time-barrier bar's OWN open
    assert rx["exit"] == "2024-01-04"
    assert rx["off_map"] is False


def test_held_through_spike_then_fade_does_not_take_profit():
    # intraweek SPIKE past target, then a fade, then time barrier — the reflex does NOT harvest tp.
    bars = [
        _bar("2024-01-02", 100, 130, 99, 118),   # high 130 >= target 115 (close 118 inside band)
        _bar("2024-01-03", 112, 114, 108, 110),  # fade, inside band
        _bar("2024-01-04", 111, 112, 110, 111),  # time barrier -> exit at THIS open
    ]
    rx = reflex_exit(bars, entry=100.0, side="long", band=(90.0, 120.0), stop=80.0,
                     target=115.0, time_barrier="2024-01-04", slippage=0.0, off_map_mult=_MULT,
                     held_through=True)
    assert rx["reason"] == "time"            # NOT tp
    assert rx["fill"] == pytest.approx(111.0)


def test_held_through_still_off_map_on_halt_roll():
    # the halt-only off_map seam survives for held_through legs (only band-excess off_map is gone).
    bars = [
        _bar("2024-01-02", 100, 101, 99, 100),          # inside band, held through
        _bar("2024-01-03", 0, 0, 0, 0, vol=0.0),        # time-barrier bar HALTED -> roll
        _bar("2024-01-04", 105, 106, 104, 105),         # next available open
    ]
    rx = reflex_exit(bars, entry=100.0, side="long", band=(90.0, 120.0), stop=80.0,
                     target=115.0, time_barrier="2024-01-03", slippage=0.0, off_map_mult=_MULT,
                     held_through=True)
    assert rx["reason"] == "halt"
    assert rx["off_map"] is True
    assert rx["fill"] == pytest.approx(105.0)
    assert rx["exit"] == "2024-01-04"


def test_non_held_through_still_fires_band_stop_tp():
    # held_through=False (the default) -> the reflex fires band/stop/tp exactly as before (regression).
    bars = [
        _bar("2024-01-02", 100, 101, 99, 88),   # close 88 < band[0]=90 -> band breach
        _bar("2024-01-03", 87, 90, 86, 89),     # fill at THIS open
    ]
    rx = reflex_exit(bars, entry=100.0, side="long", band=(90.0, 120.0), stop=80.0,
                     target=115.0, time_barrier=_FAR, slippage=0.0, off_map_mult=_MULT,
                     held_through=False)
    assert rx["reason"] == "band"
    assert rx["fill"] == pytest.approx(87.0)


# ============================== weekly byte-for-byte preservation =====================


def _conn():
    conn = _db.connect(":memory:")
    _db.migrate(conn)
    return conn


def test_weekly_default_path_is_byte_for_byte():
    conn = _conn()
    weeks = _seed_std(conn)
    default_res, default_dist = run_layer_a(conn, None, start=weeks[2], end=weeks[10])
    weekly_res, weekly_dist = run_layer_a(conn, None, start=weeks[2], end=weeks[10],
                                          granularity="weekly")
    assert default_res == weekly_res           # the granularity knob's default IS weekly
    assert default_dist == weekly_dist
    # the new LegOutcome fields default off/None on the weekly money-path
    for wk in weekly_res:
        for leg in wk.legs:
            assert leg.off_map is False
            assert leg.exit_reason is None


def test_leg_outcome_new_fields_default():
    leg = LegOutcome(ticker="CAT", side="long", entry=10.0, fill=9.0, exit="2024-02-01",
                     realized_ret=-0.1, held_through=True, is_catalyst=True, p=0.6, size_pct=0.02)
    assert leg.off_map is False
    assert leg.exit_reason is None


# ============================== daily reflex threaded through run_layer_a =============


def test_daily_reflex_holds_through_collapse_to_time_barrier():
    # POST-M1 CONTRACT (was test_daily_reflex_surfaces_off_map_on_leg): a held_through=True catalyst
    # leg no longer band-exits on an intraweek collapse — it HOLDS to the time barrier. The
    # band-excess off_map seam is suppressed; only a halt roll can set off_map for a hold-through leg.
    conn = _conn()
    weeks = _seed_std(conn)

    def fake_daily(ticker, week_start, week_end):
        # a catastrophic intraweek collapse the OLD reflex would have band-exited on.
        return [
            _bar(week_start, 5.0, 5.0, 0.01, 0.01),   # intraweek collapse -> would-be band breach
            _bar(week_end, 0.02, 0.03, 0.01, 0.02),   # week_end == exit_by == time_barrier -> exit here
        ]

    results, _dist = run_layer_a(conn, None, start=weeks[5], end=weeks[5],
                                 granularity="daily", daily_bars_provider=fake_daily)
    cat_legs = [l for wk in results for l in wk.legs if l.ticker == "CAT" and l.is_catalyst]
    assert cat_legs, "the verified catalyst should still produce a leg on the daily knob"
    assert cat_legs[0].exit_reason == "time"   # holds to the barrier, no band exit
    assert cat_legs[0].off_map is False         # band-excess off_map suppressed for hold-through
