"""RED-first exhaustive edge-case suite for the sizing tools (OPS-04, QUANT-02/03).

This is the single biggest money lever: kelly / fractional_kelly / risk_of_ruin / sl_tp_levels.
The arithmetic itself is the guardrail against sizing for the 1%/week target instead of
survival (PITFALLS #5, #2). Every tool must RAISE on out-of-domain input (div-0, negative,
NaN) rather than emit inf/NaN. risk_of_ruin is deterministic (no RNG) so it is reproducible
(QUANT-03) and testable (OPS-04) — and structurally has NO return-target parameter. Written
before the logic exists (module absent = RED).
"""

import math

import pytest

from catalyst_trader.quant.result import ToolResult
from catalyst_trader.quant.sizing import (
    fractional_kelly,
    kelly,
    risk_of_ruin,
    sl_tp_levels,
)

# --------------------------------------------------------------------------- kelly


def test_kelly_happy_path_hand_computed():
    # f* = p/L - q/W = 0.6/1.0 - 0.4/1.0 = 0.2
    res = kelly(p_win=0.6, win_frac=1.0, loss_frac=1.0)
    assert isinstance(res, ToolResult)
    assert res.value == pytest.approx(0.2)


def test_kelly_asymmetric_hand_computed():
    # f* = 0.5/0.5 - 0.5/2.0 = 1.0 - 0.25 = 0.75
    res = kelly(p_win=0.5, win_frac=2.0, loss_frac=0.5)
    assert res.value == pytest.approx(0.75)


def test_kelly_loss_frac_zero_raises():
    # div-by-zero: p/L undefined
    with pytest.raises(ValueError):
        kelly(p_win=0.6, win_frac=1.0, loss_frac=0.0)


def test_kelly_win_frac_zero_raises():
    with pytest.raises(ValueError):
        kelly(p_win=0.6, win_frac=0.0, loss_frac=1.0)


def test_kelly_negative_edge_clamps_to_zero():
    # poor odds -> f* < 0 -> clamp to 0 (no edge = no bet)
    res = kelly(p_win=0.3, win_frac=1.0, loss_frac=1.0)  # 0.3 - 0.7 = -0.4 -> 0
    assert res.value == 0.0


def test_kelly_on_minus70_binary_is_tiny_never_inflates():
    # the survival guardrail (PITFALLS #5): a -70% binary with poor odds -> SMALL, never
    # scaled up toward the 1%/week target. Here f* is negative -> clamped to 0.
    res = kelly(p_win=0.30, win_frac=0.40, loss_frac=0.70)
    assert res.value < 0.05


@pytest.mark.parametrize("bad_p", [float("nan"), -0.1, 1.1, 2.0, -1.0])
def test_kelly_p_win_out_of_range_or_nan_raises(bad_p):
    with pytest.raises(ValueError):
        kelly(p_win=bad_p, win_frac=1.0, loss_frac=1.0)


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_kelly_nan_inf_fracs_raise(bad):
    with pytest.raises(ValueError):
        kelly(p_win=0.6, win_frac=bad, loss_frac=1.0)
    with pytest.raises(ValueError):
        kelly(p_win=0.6, win_frac=1.0, loss_frac=bad)


def test_kelly_p_win_one_is_finite_no_crash():
    res = kelly(p_win=1.0, win_frac=1.0, loss_frac=0.7)
    assert math.isfinite(res.value)


def test_kelly_inputs_snapshot_matches_call_args():  # QUANT-03
    res = kelly(p_win=0.6, win_frac=1.0, loss_frac=1.0)
    assert res.inputs == {"p_win": 0.6, "win_frac": 1.0, "loss_frac": 1.0}


# ------------------------------------------------------------------ fractional_kelly


def test_fractional_kelly_happy_path():
    res = fractional_kelly(kelly_fraction=0.2, fraction=0.25)
    assert isinstance(res, ToolResult)
    assert res.value == pytest.approx(0.05)


def test_fractional_kelly_default_quarter():
    res = fractional_kelly(kelly_fraction=0.4)
    assert res.value == pytest.approx(0.1)


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_fractional_kelly_nan_inf_raises(bad):
    with pytest.raises(ValueError):
        fractional_kelly(kelly_fraction=bad)
    with pytest.raises(ValueError):
        fractional_kelly(kelly_fraction=0.2, fraction=bad)


def test_fractional_kelly_negative_fraction_raises():
    with pytest.raises(ValueError):
        fractional_kelly(kelly_fraction=0.2, fraction=-0.25)


def test_fractional_kelly_inputs_snapshot():  # QUANT-03
    res = fractional_kelly(kelly_fraction=0.2, fraction=0.25)
    assert res.inputs == {"kelly_fraction": 0.2, "fraction": 0.25}


# --------------------------------------------------------------------- risk_of_ruin


def test_risk_of_ruin_no_return_target_parameter():
    # structural guardrail: sizing must NEVER be coupled to the 1%/week return target.
    import inspect

    params = set(inspect.signature(risk_of_ruin).parameters)
    assert params == {"p_loss", "size_pct", "gap", "ruin_drawdown", "n_trades"}
    assert not any("return" in p or "target" in p for p in params)


def test_risk_of_ruin_happy_mid_case():
    res = risk_of_ruin(p_loss=0.4, size_pct=0.2, gap=0.70, ruin_drawdown=0.5, n_trades=52)
    assert isinstance(res, ToolResult)
    assert 0.0 < res.value < 1.0
    assert isinstance(res.detail["max_survivable_consecutive_losses"], int)


def test_risk_of_ruin_full_size_is_certain_ruin():
    # size ~100% with a -70% gap: one hit blows past a 50% drawdown -> ruin ~1
    res = risk_of_ruin(p_loss=0.4, size_pct=1.0, gap=0.70, ruin_drawdown=0.5, n_trades=52)
    assert res.value == pytest.approx(1.0, abs=1e-9)
    assert res.detail["max_survivable_consecutive_losses"] == 0


def test_risk_of_ruin_monotonic_in_size():
    # the core survival property: bigger position -> at-least-as-high ruin probability
    small = risk_of_ruin(p_loss=0.4, size_pct=0.10, n_trades=52).value
    mid = risk_of_ruin(p_loss=0.4, size_pct=0.20, n_trades=52).value
    large = risk_of_ruin(p_loss=0.4, size_pct=0.40, n_trades=52).value
    assert small <= mid <= large


def test_risk_of_ruin_deterministic_no_rng():
    a = risk_of_ruin(p_loss=0.4, size_pct=0.2, n_trades=52).value
    b = risk_of_ruin(p_loss=0.4, size_pct=0.2, n_trades=52).value
    assert a == b


def test_risk_of_ruin_negative_size_raises():
    with pytest.raises(ValueError):
        risk_of_ruin(p_loss=0.4, size_pct=-0.1, n_trades=52)


def test_risk_of_ruin_zero_size_raises():
    with pytest.raises(ValueError):
        risk_of_ruin(p_loss=0.4, size_pct=0.0, n_trades=52)


def test_risk_of_ruin_size_over_one_raises():
    with pytest.raises(ValueError):
        risk_of_ruin(p_loss=0.4, size_pct=1.5, n_trades=52)


def test_risk_of_ruin_zero_trades_raises():
    with pytest.raises(ValueError):
        risk_of_ruin(p_loss=0.4, size_pct=0.2, n_trades=0)


@pytest.mark.parametrize("bad_p", [float("nan"), -0.1, 1.1])
def test_risk_of_ruin_bad_p_loss_raises(bad_p):
    with pytest.raises(ValueError):
        risk_of_ruin(p_loss=bad_p, size_pct=0.2, n_trades=52)


@pytest.mark.parametrize("bad_gap", [0.0, -0.1, 1.5, float("nan")])
def test_risk_of_ruin_bad_gap_raises(bad_gap):
    with pytest.raises(ValueError):
        risk_of_ruin(p_loss=0.4, size_pct=0.2, gap=bad_gap, n_trades=52)


@pytest.mark.parametrize("bad_dd", [0.0, -0.1, 1.5, float("nan")])
def test_risk_of_ruin_bad_ruin_drawdown_raises(bad_dd):
    with pytest.raises(ValueError):
        risk_of_ruin(p_loss=0.4, size_pct=0.2, ruin_drawdown=bad_dd, n_trades=52)


def test_risk_of_ruin_inputs_snapshot():  # QUANT-03
    res = risk_of_ruin(p_loss=0.4, size_pct=0.2, gap=0.70, ruin_drawdown=0.5, n_trades=52)
    assert res.inputs == {
        "p_loss": 0.4,
        "size_pct": 0.2,
        "gap": 0.70,
        "ruin_drawdown": 0.5,
        "n_trades": 52,
    }


# ---------------------------------------------------------------------- sl_tp_levels


def test_sl_tp_happy_path_hand_computed():
    res = sl_tp_levels(entry=100.0, sl_pct=0.1, tp_pct=0.2)
    assert isinstance(res, ToolResult)
    assert res.value == pytest.approx(2.0)  # reward:risk = 0.2/0.1
    assert res.detail["stop"] == pytest.approx(90.0)
    assert res.detail["target"] == pytest.approx(120.0)


def test_sl_tp_sl_pct_zero_raises():
    # R:R undefined (div-by-zero)
    with pytest.raises(ValueError):
        sl_tp_levels(entry=100.0, sl_pct=0.0, tp_pct=0.2)


@pytest.mark.parametrize("sl,tp", [(-0.1, 0.2), (0.1, -0.2)])
def test_sl_tp_negative_pct_raises(sl, tp):
    with pytest.raises(ValueError):
        sl_tp_levels(entry=100.0, sl_pct=sl, tp_pct=tp)


def test_sl_tp_bad_entry_raises():
    with pytest.raises(ValueError):
        sl_tp_levels(entry=0.0, sl_pct=0.1, tp_pct=0.2)
    with pytest.raises(ValueError):
        sl_tp_levels(entry=-100.0, sl_pct=0.1, tp_pct=0.2)


def test_sl_tp_holds_through_catalyst_is_advisory():
    # PITFALLS #2: the gap jumps the stop on a binary event -> advisory only
    res = sl_tp_levels(entry=100.0, sl_pct=0.1, tp_pct=0.2, holds_through_catalyst=True)
    assert res.detail["advisory"] is True
    assert "gap" in res.detail["reason"].lower()


def test_sl_tp_not_advisory_when_not_held_through():
    res = sl_tp_levels(entry=100.0, sl_pct=0.1, tp_pct=0.2, holds_through_catalyst=False)
    assert res.detail.get("advisory") is not True


def test_sl_tp_inputs_snapshot():  # QUANT-03
    res = sl_tp_levels(entry=100.0, sl_pct=0.1, tp_pct=0.2)
    assert res.inputs == {
        "entry": 100.0,
        "sl_pct": 0.1,
        "tp_pct": 0.2,
        "holds_through_catalyst": False,
    }
