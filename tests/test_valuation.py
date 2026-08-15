"""RED-first exhaustive edge-case suite for the valuation tools (OPS-04, QUANT-02/03).

Money-critical: every tool must RAISE on out-of-domain input, never emit inf/NaN. Columns
covered per tool: div-by-zero, negative, empty/short, NaN/inf, extreme, happy — plus a
QUANT-03 inputs-snapshot assertion. Written before the logic exists (module absent = RED).
"""

import math

import pytest

from catalyst_trader.quant.result import ToolResult
from catalyst_trader.quant.valuation import cash_runway, pipeline_value, rnpv

# --------------------------------------------------------------------------- rNPV


def test_rnpv_happy_path_hand_computed():
    # CF·pos/(1+r)^t = 500e6 * 0.30 / 1.25**3 = 150e6 / 1.953125 = 76.8e6
    res = rnpv([(3, 500e6, 0.30)], discount_rate=0.25)
    assert isinstance(res, ToolResult)
    assert res.value == pytest.approx(76_800_000.0)
    assert res.detail["pv_inflows"] == pytest.approx(76_800_000.0)
    assert res.detail["pv_costs"] == pytest.approx(0.0)


def test_rnpv_with_costs_subtracts_risk_adjusted_pv():
    # inflow 76.8e6, cost 100e6 * 0.5 / 1.25**1 = 40e6 -> rNPV = 36.8e6
    res = rnpv([(3, 500e6, 0.30)], discount_rate=0.25, costs=[(1, 100e6, 0.5)])
    assert res.value == pytest.approx(36_800_000.0)
    assert res.detail["pv_inflows"] == pytest.approx(76_800_000.0)
    assert res.detail["pv_costs"] == pytest.approx(40_000_000.0)


def test_rnpv_negative_cashflow_is_valid_loss_year():
    # a negative cashflow (loss year) must COMPUTE, not raise
    res = rnpv([(1, -100e6, 1.0)], discount_rate=0.20)
    assert res.value == pytest.approx(-100e6 / 1.20)


def test_rnpv_discount_rate_minus_one_raises():
    # (1 + r)^t divides by zero
    with pytest.raises(ValueError):
        rnpv([(3, 500e6, 0.30)], discount_rate=-1.0)


def test_rnpv_discount_rate_below_minus_one_raises():
    with pytest.raises(ValueError):
        rnpv([(3, 500e6, 0.30)], discount_rate=-1.5)


def test_rnpv_empty_cashflows_raises():
    with pytest.raises(ValueError):
        rnpv([], discount_rate=0.25)


@pytest.mark.parametrize("bad_pos", [math.nan, math.inf, -0.1, 1.1])
def test_rnpv_pos_out_of_domain_raises(bad_pos):
    with pytest.raises(ValueError):
        rnpv([(3, 500e6, bad_pos)], discount_rate=0.25)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_rnpv_nan_inf_cashflow_raises(bad):
    with pytest.raises(ValueError):
        rnpv([(3, bad, 0.30)], discount_rate=0.25)


@pytest.mark.parametrize("bad", [math.nan, math.inf])
def test_rnpv_nan_inf_discount_rate_raises(bad):
    with pytest.raises(ValueError):
        rnpv([(3, 500e6, 0.30)], discount_rate=bad)


def test_rnpv_cost_prob_out_of_domain_raises():
    with pytest.raises(ValueError):
        rnpv([(3, 500e6, 0.30)], discount_rate=0.25, costs=[(1, 100e6, 1.5)])


def test_rnpv_extreme_high_discount_long_horizon_is_finite():
    res = rnpv([(20, 1e9, 0.10)], discount_rate=0.40)
    assert math.isfinite(res.value)
    assert res.value > 0


def test_rnpv_inputs_snapshot_matches_call_args():
    cashflows = [(3, 500e6, 0.30)]
    costs = [(1, 100e6, 0.5)]
    res = rnpv(cashflows, discount_rate=0.25, costs=costs)
    assert res.inputs["cashflows"] == cashflows
    assert res.inputs["discount_rate"] == 0.25
    assert res.inputs["costs"] == costs
    assert res.tool == "rnpv"


# --------------------------------------------------------------------- cash_runway


def test_cash_runway_happy_with_catalyst():
    res = cash_runway(cash_usd=100e6, monthly_burn_usd=5e6, months_to_catalyst=12)
    assert isinstance(res, ToolResult)
    assert res.value == 20.0
    assert res.detail["funded_past_catalyst"] is True


def test_cash_runway_not_funded_past_catalyst():
    res = cash_runway(cash_usd=100e6, monthly_burn_usd=5e6, months_to_catalyst=24)
    assert res.value == 20.0
    assert res.detail["funded_past_catalyst"] is False


def test_cash_runway_no_catalyst_omits_flag():
    res = cash_runway(cash_usd=100e6, monthly_burn_usd=5e6)
    assert res.value == 20.0
    assert "funded_past_catalyst" not in res.detail


def test_cash_runway_zero_burn_raises():
    with pytest.raises(ValueError):
        cash_runway(cash_usd=100e6, monthly_burn_usd=0)


def test_cash_runway_negative_burn_raises():
    with pytest.raises(ValueError):
        cash_runway(cash_usd=100e6, monthly_burn_usd=-1e6)


def test_cash_runway_negative_cash_raises():
    with pytest.raises(ValueError):
        cash_runway(cash_usd=-1.0, monthly_burn_usd=5e6)


@pytest.mark.parametrize(
    "cash,burn,cat",
    [
        (math.nan, 5e6, None),
        (100e6, math.nan, None),
        (math.inf, 5e6, None),
        (100e6, math.inf, None),
        (100e6, 5e6, math.nan),
    ],
)
def test_cash_runway_nan_inf_raises(cash, burn, cat):
    with pytest.raises(ValueError):
        cash_runway(cash_usd=cash, monthly_burn_usd=burn, months_to_catalyst=cat)


def test_cash_runway_burn_far_exceeds_cash_is_near_zero():
    res = cash_runway(cash_usd=1.0, monthly_burn_usd=1e9)
    assert res.value == pytest.approx(0.0, abs=1e-6)
    assert math.isfinite(res.value)


def test_cash_runway_inputs_snapshot_matches_call_args():
    res = cash_runway(cash_usd=100e6, monthly_burn_usd=5e6, months_to_catalyst=12)
    assert res.inputs == {"cash_usd": 100e6, "monthly_burn_usd": 5e6, "months_to_catalyst": 12}
    assert res.tool == "cash_runway"


# ------------------------------------------------------------------ pipeline_value


def test_pipeline_value_sums_asset_rnpvs():
    a = rnpv([(3, 500e6, 0.30)], discount_rate=0.25)  # 76.8e6
    b = rnpv([(1, -100e6, 1.0)], discount_rate=0.20)  # -83.33e6
    res = pipeline_value([a, b])
    assert isinstance(res, ToolResult)
    assert res.value == pytest.approx(a.value + b.value)
    assert res.detail["n_assets"] == 2


def test_pipeline_value_empty_list_raises():
    with pytest.raises(ValueError):
        pipeline_value([])


def test_pipeline_value_rejects_result_without_value():
    bad = ToolResult(tool="rnpv", tool_version="1.0.0", inputs={}, value=None)
    with pytest.raises(ValueError):
        pipeline_value([bad])
