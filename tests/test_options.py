"""RED-first exhaustive edge-case suite for the options context tools (OPS-04, QUANT-02/03).

implied_move (straddle + IV methods) and iv_crush (post-event or baseline path) are sizing/
CONTEXT inputs — a magnitude prior for the downside gap, never a directional P&L signal
(PITFALLS #10). Every tool RAISES on out-of-domain input (price<=0, negative IV, NaN/inf,
no complete method) rather than emitting a misleading number (Pattern 2). Written before the
logic exists (module absent = RED).
"""

import math

import pytest

from catalyst_trader.quant.result import ToolResult
from catalyst_trader.quant.options import implied_move, iv_crush


# ------------------------------------------------------------------- implied_move


def test_implied_move_zero_price_raises():
    # div-by-zero: underlying_price == 0 makes the straddle % undefined
    with pytest.raises(ValueError):
        implied_move(underlying_price=0.0, call_mid=5.0, put_mid=4.0)


def test_implied_move_negative_price_raises():
    with pytest.raises(ValueError):
        implied_move(underlying_price=-100.0, call_mid=5.0, put_mid=4.0)


def test_implied_move_negative_iv_raises():
    with pytest.raises(ValueError):
        implied_move(underlying_price=100.0, iv=-0.5, days_to_event=30)


def test_implied_move_nan_raises():
    with pytest.raises(ValueError):
        implied_move(underlying_price=100.0, call_mid=math.nan, put_mid=4.0)


def test_implied_move_no_complete_method_raises():
    # neither a full straddle nor a full IV method supplied
    with pytest.raises(ValueError):
        implied_move(underlying_price=100.0)


def test_implied_move_extreme_iv_finite():
    # 300% IV, 7 days to event — must stay finite, not blow up
    r = implied_move(underlying_price=100.0, iv=3.0, days_to_event=7)
    assert math.isfinite(r.value)
    assert r.value > 0


def test_implied_move_happy_straddle():
    r = implied_move(underlying_price=100.0, call_mid=5.0, put_mid=4.0)
    assert r.value == pytest.approx(0.09)
    assert isinstance(r, ToolResult)


def test_implied_move_happy_iv_method():
    r = implied_move(underlying_price=100.0, iv=0.5, days_to_event=365)
    assert r.value == pytest.approx(0.5)


def test_implied_move_inputs_snapshot():
    # QUANT-03: .inputs is the verbatim call args
    r = implied_move(underlying_price=100.0, call_mid=5.0, put_mid=4.0)
    assert r.inputs == {
        "underlying_price": 100.0,
        "call_mid": 5.0,
        "put_mid": 4.0,
        "iv": None,
        "days_to_event": None,
    }


# ----------------------------------------------------------------------- iv_crush


def test_iv_crush_negative_pre_raises():
    with pytest.raises(ValueError):
        iv_crush(pre_event_iv=-3.0, post_event_iv=0.5)


def test_iv_crush_negative_post_raises():
    with pytest.raises(ValueError):
        iv_crush(pre_event_iv=3.0, post_event_iv=-0.5)


def test_iv_crush_nan_raises():
    with pytest.raises(ValueError):
        iv_crush(pre_event_iv=math.nan, post_event_iv=0.5)


def test_iv_crush_no_reference_raises():
    # neither post_event_iv nor baseline_iv supplied
    with pytest.raises(ValueError):
        iv_crush(pre_event_iv=3.0)


def test_iv_crush_happy_post_path():
    # extreme biotech binary: 300% pre → 50% post
    r = iv_crush(pre_event_iv=3.0, post_event_iv=0.5)
    assert r.value == pytest.approx(2.5)
    assert isinstance(r, ToolResult)


def test_iv_crush_happy_baseline_path():
    r = iv_crush(pre_event_iv=3.0, baseline_iv=0.5)
    assert r.value == pytest.approx(2.5)


def test_iv_crush_inputs_snapshot():
    # QUANT-03: .inputs is the verbatim call args
    r = iv_crush(pre_event_iv=3.0, post_event_iv=0.5)
    assert r.inputs == {
        "pre_event_iv": 3.0,
        "post_event_iv": 0.5,
        "baseline_iv": None,
    }
