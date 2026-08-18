"""BACK-04: the pessimistic gap-open fill model.

Money invariant under test: a held-through binary fills at the GAP-OPEN far side, never the
stop level — a stop is jumped by the gap and cannot fill inside it. Slippage is a tunable
far-side haircut. An event is skipped ONLY if halted/delisted/zero-volume/zero-quote; volume
caps are ignored by design.
"""

import pytest

from catalyst_trader.backtest.fill import fill_price


def _bar(**kw):
    b = {"week_end": "2024-01-15", "open": 8.0, "high": 10.5, "low": 7.5, "close": 9.0,
         "volume": 2_000_000.0, "delisted": False}
    b.update(kw)
    return b


def test_held_through_binary_fills_at_gap_open_not_sl():
    # Long entered at ~10; a down-gap opens at 8.0; the stop sat at 9.0. The stop CANNOT fill at
    # 9.0 — price gapped straight through it — so the fill is the gap open worsened by slippage.
    bars = [_bar(week_end="2024-01-08", open=10.0, close=10.0), _bar(open=8.0)]
    sl_level = 9.0
    fill = fill_price(bars, side="long", held_through=True, slippage=0.01, sl_level=sl_level)
    assert fill == pytest.approx(8.0 * (1 - 0.01))   # gap-open far side
    assert fill != sl_level                           # NOT the stop
    assert fill < sl_level                            # strictly worse than the stop (the whole point)


def test_slippage_haircut_worsens_fill():
    bars = [_bar(open=8.0)]
    small = fill_price(bars, side="long", held_through=True, slippage=0.01)
    large = fill_price(bars, side="long", held_through=True, slippage=0.05)
    assert large < small   # bigger haircut -> worse (lower) long fill
    # symmetric for a short: worse = higher
    s_small = fill_price(bars, side="short", held_through=True, slippage=0.01)
    s_large = fill_price(bars, side="short", held_through=True, slippage=0.05)
    assert s_large > s_small


def test_not_held_through_fills_far_side():
    bars = [_bar(low=7.5, high=10.5)]
    long_fill = fill_price(bars, side="long", held_through=False, slippage=0.01)
    short_fill = fill_price(bars, side="short", held_through=False, slippage=0.01)
    assert long_fill == pytest.approx(7.5 * (1 - 0.01))    # long exits at the low far side
    assert short_fill == pytest.approx(10.5 * (1 + 0.01))  # short exits at the high far side


@pytest.mark.parametrize("skip_bar", [
    {"delisted": True},
    {"halted": True},
    {"volume": 0.0},
    {"volume": None},
    {"open": 0.0},
    {"close": None},
])
def test_skip_halted_zero_volume_zero_quote_returns_none(skip_bar):
    bars = [_bar(**skip_bar)]
    assert fill_price(bars, side="long", held_through=True, slippage=0.01) is None


def test_volume_cap_ignored():
    # A large-but-nonzero volume must NOT be skipped — volume caps are out of scope by design.
    bars = [_bar(volume=999_000_000.0)]
    assert fill_price(bars, side="long", held_through=True, slippage=0.01) is not None


def test_empty_bars_raises():
    with pytest.raises(ValueError):
        fill_price([], side="long", held_through=True, slippage=0.01)


# E8 — price-tiered half-spread cost (Robinhood commission-free)

def test_half_spread_wider_for_cheaper_names():
    from catalyst_trader.backtest.fill import half_spread_pct
    assert half_spread_pct(0.5) > half_spread_pct(3) > half_spread_pct(10) > half_spread_pct(50) > half_spread_pct(200)
    assert half_spread_pct(0) == half_spread_pct(-5) == 0.010  # bad price -> widest


def test_fill_leg_cost_reduces_return_both_sides():
    # a flat entry->exit (no move) should be NEGATIVE after paying half-spread on both sides.
    import sqlite3
    from catalyst_trader import db as _db, store
    from catalyst_trader.backtest.engine import _fill_leg
    c = _db.connect(":memory:"); _db.migrate(c)
    store.upsert_bars(c, "AAAA", [
        {"week_end": "2026-01-05", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 100},
        {"week_end": "2026-01-12", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 100},
    ])
    with_cost = _fill_leg(c, "AAAA", "2026-01-05", "2026-01-12", held_through=True, slippage=0.0, apply_costs=True)
    no_cost = _fill_leg(c, "AAAA", "2026-01-05", "2026-01-12", held_through=True, slippage=0.0, apply_costs=False)
    assert no_cost[2] == 0.0            # flat, no cost -> zero
    assert with_cost[2] < 0.0           # flat, with cost -> loses the round-trip spread
    assert with_cost[2] == pytest.approx(-2 * 0.0025, abs=1e-4)  # $10 tier hs=0.0025, both sides
