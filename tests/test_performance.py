"""RED-first exhaustive edge-case suite for the performance tools (OPS-04, QUANT-02/03).

sharpe / sortino / cumulative_return / attribution — hand-rolled numpy math. The headline case
is the FREQ FOOTGUN (PITFALLS #2): sharpe/sortino take a REQUIRED `periods_per_year`, so the
annualization factor is an explicit caller decision, never a silent library default. This suite
proves 252-daily and 52-weekly books produce correctly different (√(252/52)-scaled) Sharpe from
the same returns. Every money-tool RAISES on empty/single-point series, zero volatility, or any
NaN rather than emitting inf/NaN (Pattern 2). Written before the logic exists (module absent = RED).
"""

import math

import pytest

from catalyst_trader.quant.result import ToolResult
from catalyst_trader.quant.performance import (
    sharpe,
    sortino,
    cumulative_return,
    attribution,
    max_drawdown,
    win_rate,
    avg_win_loss,
    hedge_effectiveness,
)


# --------------------------------------------------------------------------- sharpe


def test_sharpe_zero_volatility_raises():
    # constant returns → sd == 0 → Sharpe undefined, must raise not emit inf
    with pytest.raises(ValueError):
        sharpe([0.01, 0.01, 0.01], periods_per_year=252)


def test_sharpe_empty_raises():
    with pytest.raises(ValueError):
        sharpe([], periods_per_year=252)


def test_sharpe_single_point_raises():
    # ddof=1 std is undefined on a single observation
    with pytest.raises(ValueError):
        sharpe([0.01], periods_per_year=252)


def test_sharpe_nan_raises():
    with pytest.raises(ValueError):
        sharpe([0.01, math.nan, 0.02], periods_per_year=252)


def test_sharpe_freq_footgun_scales_with_periods_per_year():
    # THE HEADLINE: same returns, 52 vs 252, must differ AND the 252 value must equal the
    # 52 value scaled by √(252/52) — proving annualization is applied, not silently dropped.
    returns = [0.01, 0.02, -0.01, 0.03]
    weekly = sharpe(returns, periods_per_year=52).value
    daily = sharpe(returns, periods_per_year=252).value
    assert weekly != pytest.approx(daily)
    assert daily == pytest.approx(weekly * math.sqrt(252 / 52))


def test_sharpe_happy_hand_computed():
    # returns=[0.01, 0.03], ppy=52: mean=0.02, sd(ddof=1)=0.01414214,
    # 0.02/0.01414214 * sqrt(52) = 10.198
    r = sharpe([0.01, 0.03], periods_per_year=52)
    assert r.value == pytest.approx(10.198, rel=1e-3)
    assert isinstance(r, ToolResult)


def test_sharpe_risk_free_lowers_value():
    # a positive risk-free rate reduces excess return → lower Sharpe
    base = sharpe([0.01, 0.02, 0.03], periods_per_year=252).value
    with_rf = sharpe([0.01, 0.02, 0.03], periods_per_year=252, risk_free=0.05).value
    assert with_rf < base


def test_sharpe_inputs_snapshot():
    # QUANT-03: .inputs is the verbatim call args, periods_per_year included
    r = sharpe([0.01, 0.03], periods_per_year=52, risk_free=0.02)
    assert r.inputs == {
        "returns": [0.01, 0.03],
        "periods_per_year": 52,
        "risk_free": 0.02,
    }


# -------------------------------------------------------------------------- sortino


def test_sortino_no_downside_raises():
    # upside vol but nothing below mar → zero downside deviation → undefined, must raise
    with pytest.raises(ValueError):
        sortino([0.01, 0.02, 0.03], periods_per_year=52)


def test_sortino_empty_raises():
    with pytest.raises(ValueError):
        sortino([], periods_per_year=52)


def test_sortino_single_point_raises():
    with pytest.raises(ValueError):
        sortino([-0.01], periods_per_year=52)


def test_sortino_nan_raises():
    with pytest.raises(ValueError):
        sortino([0.01, math.nan, -0.02], periods_per_year=52)


def test_sortino_happy_hand_computed():
    # returns=[0.02, -0.01, 0.03, -0.02], mar=0, ppy=52:
    # mean=0.005, downside=[0,-0.01,0,-0.02], dd=sqrt(mean(sq))=0.01118034,
    # 0.005/0.01118034 * sqrt(52) = 3.225
    r = sortino([0.02, -0.01, 0.03, -0.02], periods_per_year=52)
    assert r.value == pytest.approx(3.225, rel=1e-3)
    assert isinstance(r, ToolResult)


def test_sortino_freq_scales_with_periods_per_year():
    returns = [0.02, -0.01, 0.03, -0.02]
    weekly = sortino(returns, periods_per_year=52).value
    daily = sortino(returns, periods_per_year=252).value
    assert daily == pytest.approx(weekly * math.sqrt(252 / 52))


def test_sortino_inputs_snapshot():
    r = sortino([0.02, -0.01, 0.03], periods_per_year=52, mar=0.0, risk_free=0.01)
    assert r.inputs == {
        "returns": [0.02, -0.01, 0.03],
        "periods_per_year": 52,
        "mar": 0.0,
        "risk_free": 0.01,
    }


# ------------------------------------------------------------------ cumulative_return


def test_cumulative_return_empty_raises():
    with pytest.raises(ValueError):
        cumulative_return([])


def test_cumulative_return_nan_raises():
    with pytest.raises(ValueError):
        cumulative_return([0.1, math.nan])


def test_cumulative_return_wipeout_computed_not_crashed():
    # a -100% return anywhere zeroes the compounded equity → cumulative == -1.0 exactly
    r = cumulative_return([0.5, -1.0, 0.3])
    assert r.value == pytest.approx(-1.0)
    assert isinstance(r, ToolResult)


def test_cumulative_return_happy():
    # (1.1)(1.1) - 1 = 0.21
    r = cumulative_return([0.1, 0.1])
    assert r.value == pytest.approx(0.21)


def test_cumulative_return_inputs_snapshot():
    r = cumulative_return([0.1, 0.1])
    assert r.inputs == {"returns": [0.1, 0.1]}


# ------------------------------------------------------------------------ attribution


def test_attribution_components_not_summing_to_total_raises():
    with pytest.raises(ValueError):
        attribution({"catalyst": 0.03, "beta": 0.01}, total=0.10)


def test_attribution_nan_component_raises():
    with pytest.raises(ValueError):
        attribution({"catalyst": math.nan, "beta": 0.01}, total=0.01)


def test_attribution_happy():
    components = {"catalyst": 0.03, "beta": 0.01, "hedge": -0.01}
    r = attribution(components, total=0.03)
    assert r.value == pytest.approx(0.03)
    assert r.detail["residual"] == pytest.approx(0.0, abs=1e-9)
    assert r.detail["components"] == components
    assert isinstance(r, ToolResult)


def test_attribution_inputs_snapshot():
    components = {"catalyst": 0.03, "beta": 0.01, "hedge": -0.01}
    r = attribution(components, total=0.03)
    assert r.inputs == {"components": components, "total": 0.03}


# ------------------------------------------------------------------------ max_drawdown


def test_max_drawdown_monotonic_is_zero():
    # a strictly-rising equity curve never troughs below its running peak → 0.0
    r = max_drawdown([0.1, 0.2, 0.05, 0.1])
    assert r.value == pytest.approx(0.0)
    assert isinstance(r, ToolResult)


def test_max_drawdown_hand_computed():
    # equity = [1.1, 1.32, 0.924, 1.0164]; peak = [1.1, 1.32, 1.32, 1.32]
    # trough drawdown at idx 2: 0.924/1.32 - 1 = -0.30
    r = max_drawdown([0.1, 0.2, -0.3, 0.1])
    assert r.value == pytest.approx(-0.30)


def test_max_drawdown_wipeout_computed_not_crashed():
    # a -100% period zeroes equity → max drawdown == -1.0, computed not crashed
    r = max_drawdown([0.5, -1.0, 0.3])
    assert r.value == pytest.approx(-1.0)
    assert isinstance(r, ToolResult)


def test_max_drawdown_leading_wipeout_no_nan():
    # a -100% on the FIRST period → running peak is 0; must be -1.0, never NaN
    r = max_drawdown([-1.0, 0.2])
    assert r.value == pytest.approx(-1.0)


def test_max_drawdown_empty_raises():
    with pytest.raises(ValueError):
        max_drawdown([])


def test_max_drawdown_nan_raises():
    with pytest.raises(ValueError):
        max_drawdown([0.1, math.nan, -0.2])


def test_max_drawdown_inputs_snapshot():
    r = max_drawdown([0.1, -0.2])
    assert r.inputs == {"returns": [0.1, -0.2]}


# ---------------------------------------------------------------------------- win_rate


def test_win_rate_hand_computed():
    # 2 of 4 strictly > 0 → 0.5
    r = win_rate([0.1, -0.2, 0.05, -0.01])
    assert r.value == pytest.approx(0.5)
    assert r.detail == {"n_win": 2, "n_total": 4}
    assert isinstance(r, ToolResult)


def test_win_rate_zero_is_not_a_win():
    # a flat 0.0 return is NOT a win (strict >) → [0.0, 0.1] is 1 of 2 = 0.5
    r = win_rate([0.0, 0.1])
    assert r.value == pytest.approx(0.5)


def test_win_rate_all_wins():
    r = win_rate([0.1, 0.2, 0.3])
    assert r.value == pytest.approx(1.0)


def test_win_rate_all_losses():
    r = win_rate([-0.1, -0.2, 0.0])  # the 0.0 is flat, not a win
    assert r.value == pytest.approx(0.0)


def test_win_rate_empty_raises():
    with pytest.raises(ValueError):
        win_rate([])


def test_win_rate_nan_raises():
    with pytest.raises(ValueError):
        win_rate([0.1, math.nan])


def test_win_rate_inputs_snapshot():
    r = win_rate([0.0, 0.1])
    assert r.inputs == {"trade_returns": [0.0, 0.1]}


# ------------------------------------------------------------------------- avg_win_loss


def test_avg_win_loss_hand_computed():
    # wins=[0.10,0.20] avg_win=0.15; losses=[-0.05,-0.15] avg_loss magnitude=0.10
    # ratio = 0.15/0.10 = 1.5
    r = avg_win_loss([0.10, 0.20, -0.05, -0.15])
    assert r.value == pytest.approx(1.5)
    assert r.detail["avg_win"] == pytest.approx(0.15)
    assert r.detail["avg_loss"] == pytest.approx(0.10)
    assert r.detail["n_win"] == 2
    assert r.detail["n_loss"] == 2
    assert isinstance(r, ToolResult)


def test_avg_win_loss_no_losses_ratio_none():
    # all wins → avg_loss == 0 → ratio undefined → value is None (no inf, no divide)
    r = avg_win_loss([0.1, 0.2, 0.3])
    assert r.value is None
    assert r.detail["avg_loss"] == pytest.approx(0.0)


def test_avg_win_loss_no_wins():
    # all losses → avg_win == 0 → ratio 0.0
    r = avg_win_loss([-0.1, -0.2])
    assert r.value == pytest.approx(0.0)
    assert r.detail["avg_win"] == pytest.approx(0.0)


def test_avg_win_loss_empty_raises():
    with pytest.raises(ValueError):
        avg_win_loss([])


def test_avg_win_loss_nan_raises():
    with pytest.raises(ValueError):
        avg_win_loss([0.1, math.nan])


def test_avg_win_loss_inputs_snapshot():
    r = avg_win_loss([0.1, -0.05])
    assert r.inputs == {"trade_returns": [0.1, -0.05]}


# ------------------------------------------------------------------ hedge_effectiveness


def test_hedge_effectiveness_hand_computed():
    # target down on 3 periods (idx 0,2,3); hedge > 0 on 2 of those (idx 0, 3) → 2/3
    target = [-0.1, 0.2, -0.05, -0.03]
    hedge = [0.08, -0.01, -0.02, 0.04]
    r = hedge_effectiveness(target, hedge)
    assert r.value == pytest.approx(2 / 3)
    assert r.detail["down_count"] == 3
    assert r.detail["offset_count"] == 2
    assert isinstance(r, ToolResult)


def test_hedge_effectiveness_net_pnl_reported():
    # detail carries both legs' net P&L so the baseline can report loss-reduction
    r = hedge_effectiveness([-0.1, -0.05], [0.08, 0.04])
    assert r.detail["net_pnl_target"] == pytest.approx(-0.15)
    assert r.detail["net_pnl_combined"] == pytest.approx(-0.03)


def test_hedge_effectiveness_no_down_days_value_none():
    # no target-down period → undefined, value is None (no false 1.0)
    r = hedge_effectiveness([0.1, 0.2], [-0.01, 0.03])
    assert r.value is None
    assert r.detail["down_count"] == 0


def test_hedge_effectiveness_length_mismatch_raises():
    with pytest.raises(ValueError):
        hedge_effectiveness([-0.1, 0.2, -0.05], [0.08, -0.01])


def test_hedge_effectiveness_empty_raises():
    with pytest.raises(ValueError):
        hedge_effectiveness([], [])


def test_hedge_effectiveness_nan_raises():
    with pytest.raises(ValueError):
        hedge_effectiveness([-0.1, math.nan], [0.08, 0.02])


def test_hedge_effectiveness_inputs_snapshot():
    r = hedge_effectiveness([-0.1, 0.2], [0.08, -0.01])
    assert r.inputs == {"target_legs": [-0.1, 0.2], "hedge_legs": [0.08, -0.01]}
