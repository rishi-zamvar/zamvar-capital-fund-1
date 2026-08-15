"""RED-first exhaustive edge-case suite for the pairs/hedge tools (OPS-04, QUANT-02/03).

cointegration (statsmodels Engle-Granger + Johansen), correlation_beta (numpy), and the
conditional_payoff matrix — the honest replacement for "0.7 correlated = hedged" (PITFALLS #1)
that feeds inverse-hedge sizing. Every tool RAISES on out-of-domain input (short/empty series,
mismatched length, zero variance, NaN/inf) rather than emitting a misleading number (Pattern 2).
Cointegration needs >=30 aligned observations. Fixtures are deterministic (seeded rng) so the
suite is reproducible. Written before the logic exists (module absent = RED).
"""

import math

import numpy as np
import pytest

from catalyst_trader.quant.result import ToolResult
from catalyst_trader.quant.pairs import (
    cointegration,
    conditional_payoff,
    correlation_beta,
)


# --------------------------------------------------------------------------- fixtures


def _cointegrated_pair(n: int = 60, seed: int = 42):
    """b = a + small stationary noise → strongly cointegrated, hedge ratio ≈ 1."""
    rng = np.random.default_rng(seed)
    a = np.cumsum(rng.normal(0, 1, n)) + 100.0
    b = a + rng.normal(0, 0.3, n)
    return list(a), list(b)


def _independent_pair(n: int = 60, seed: int = 7):
    """Two independent random walks → not cointegrated (spurious pairing)."""
    rng = np.random.default_rng(seed)
    a = np.cumsum(rng.normal(0, 1, n)) + 100.0
    b = np.cumsum(rng.normal(0, 1, n)) + 100.0
    return list(a), list(b)


# --------------------------------------------------------------------- cointegration


def test_cointegration_short_series_raises():
    a, b = _cointegrated_pair(n=20)  # < 30 aligned observations
    with pytest.raises(ValueError):
        cointegration(a, b)


def test_cointegration_mismatched_length_raises():
    a, b = _cointegrated_pair(n=40)
    with pytest.raises(ValueError):
        cointegration(a, b[:-1])


def test_cointegration_nan_in_series_raises():
    a, b = _cointegrated_pair(n=40)
    a[5] = float("nan")
    with pytest.raises(ValueError):
        cointegration(a, b)


def test_cointegration_inf_in_series_raises():
    a, b = _cointegrated_pair(n=40)
    b[3] = float("inf")
    with pytest.raises(ValueError):
        cointegration(a, b)


def test_cointegration_happy_cointegrated_true_with_hedge_ratio():
    a, b = _cointegrated_pair(n=60)
    res = cointegration(a, b)
    assert isinstance(res, ToolResult)
    assert res.value == res.detail["p_value"]
    assert res.detail["cointegrated"] is True
    assert res.value < 0.05
    assert math.isfinite(res.detail["hedge_ratio"])
    # b ≈ a → OLS slope of a on b ≈ 1.0
    assert res.detail["hedge_ratio"] == pytest.approx(1.0, abs=0.1)
    assert res.detail["method"] == "engle_granger"


def test_cointegration_independent_series_not_cointegrated():
    a, b = _independent_pair(n=60)
    res = cointegration(a, b)
    assert res.detail["cointegrated"] is False
    assert res.value >= 0.05


def test_cointegration_johansen_path():
    a, b = _cointegrated_pair(n=60)
    res = cointegration(a, b, method="johansen")
    assert res.detail["method"] == "johansen"
    assert res.detail["cointegrated"] is True
    assert math.isfinite(res.detail["hedge_ratio"])


def test_cointegration_unknown_method_raises():
    a, b = _cointegrated_pair(n=40)
    with pytest.raises(ValueError):
        cointegration(a, b, method="bogus")


def test_cointegration_inputs_snapshot():
    a, b = _cointegrated_pair(n=40)
    res = cointegration(a, b, method="engle_granger", significance=0.05)
    assert res.inputs["price_a"] == a
    assert res.inputs["price_b"] == b
    assert res.inputs["method"] == "engle_granger"
    assert res.inputs["significance"] == 0.05


# ------------------------------------------------------------------- correlation_beta


def test_correlation_beta_zero_variance_raises():
    with pytest.raises(ValueError):
        correlation_beta([5.0, 5.0, 5.0, 5.0], [1.0, 2.0, 3.0, 4.0])


def test_correlation_beta_zero_variance_market_raises():
    with pytest.raises(ValueError):
        correlation_beta([1.0, 2.0, 3.0, 4.0], [3.0, 3.0, 3.0, 3.0])


def test_correlation_beta_single_point_raises():
    with pytest.raises(ValueError):
        correlation_beta([1.0], [2.0])


def test_correlation_beta_mismatched_length_raises():
    with pytest.raises(ValueError):
        correlation_beta([1.0, 2.0, 3.0], [1.0, 2.0])


def test_correlation_beta_nan_raises():
    with pytest.raises(ValueError):
        correlation_beta([1.0, 2.0, float("nan"), 4.0], [1.0, 2.0, 3.0, 4.0])


def test_correlation_beta_perfectly_correlated():
    res = correlation_beta([1.0, 2.0, 3.0, 4.0], [1.0, 2.0, 3.0, 4.0])
    assert isinstance(res, ToolResult)
    assert res.value == pytest.approx(1.0)
    assert res.detail["beta"] == pytest.approx(1.0)


def test_correlation_beta_happy_hand_computed_beta():
    # asset = 2 * market → beta = 2.0, correlation = 1.0
    res = correlation_beta([2.0, 4.0, 6.0, 8.0], [1.0, 2.0, 3.0, 4.0])
    assert res.detail["beta"] == pytest.approx(2.0)
    assert res.value == pytest.approx(1.0)


def test_correlation_beta_negative_correlation():
    res = correlation_beta([4.0, 3.0, 2.0, 1.0], [1.0, 2.0, 3.0, 4.0])
    assert res.value == pytest.approx(-1.0)
    assert res.detail["beta"] == pytest.approx(-1.0)


def test_correlation_beta_inputs_snapshot():
    a = [2.0, 4.0, 6.0, 8.0]
    m = [1.0, 2.0, 3.0, 4.0]
    res = correlation_beta(a, m)
    assert res.inputs == {"asset_returns": a, "market_returns": m}


# ------------------------------------------------------------------ conditional_payoff


def test_conditional_payoff_extreme_worst_case_un_netted():
    # target −70% / peer +40% branch inputs; worst cell = both down, un-netted weighted sum.
    res = conditional_payoff(
        target_up=0.10, target_down=-0.70,
        peer_up=0.40, peer_down=-0.30,
        w_target=0.5, w_peer=0.5,
    )
    assert isinstance(res, ToolResult)
    worst = 0.5 * -0.70 + 0.5 * -0.30  # both-down cell
    assert res.value == pytest.approx(worst)
    assert res.value < 0


def test_conditional_payoff_four_cells_and_min():
    res = conditional_payoff(
        target_up=0.20, target_down=-0.20,
        peer_up=0.10, peer_down=-0.10,
        w_target=0.6, w_peer=0.4,
    )
    matrix = res.detail["matrix"]
    assert len(matrix) == 4
    assert res.value == pytest.approx(min(matrix.values()))
    # best cell = both up
    assert max(matrix.values()) == pytest.approx(0.6 * 0.20 + 0.4 * 0.10)


def test_conditional_payoff_inputs_snapshot():
    res = conditional_payoff(
        target_up=0.20, target_down=-0.20,
        peer_up=0.10, peer_down=-0.10,
        w_target=0.6, w_peer=0.4,
    )
    assert res.inputs == {
        "target_up": 0.20, "target_down": -0.20,
        "peer_up": 0.10, "peer_down": -0.10,
        "w_target": 0.6, "w_peer": 0.4,
    }


def test_conditional_payoff_nan_raises():
    with pytest.raises(ValueError):
        conditional_payoff(
            target_up=float("nan"), target_down=-0.20,
            peer_up=0.10, peer_down=-0.10,
            w_target=0.6, w_peer=0.4,
        )
