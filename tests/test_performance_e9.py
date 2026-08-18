"""E9 — deflated Sharpe (multiple-testing-honest) + benchmark-relative (edge vs beta)."""
import math
import pytest
from catalyst_trader.quant.performance import deflated_sharpe, benchmark_relative


def test_deflated_sharpe_high_for_strong_consistent_edge():
    # a strongly positive, low-vol series survives many trials
    r = [0.02] * 60
    # constant returns -> zero vol raises; add tiny noise
    r = [0.02 + (0.0001 if i % 2 else -0.0001) for i in range(60)]
    dsr = deflated_sharpe(r, n_trials=10, periods_per_year=52)
    assert 0.0 <= dsr.value <= 1.0
    assert dsr.value > 0.95  # obvious edge survives multiple testing


def test_deflated_sharpe_low_for_noise():
    # zero-mean noise -> no skill -> DSR well below significance
    import random
    random.seed(1)
    r = [random.gauss(0, 0.02) for _ in range(60)]
    dsr = deflated_sharpe(r, n_trials=50, periods_per_year=52)
    assert dsr.value < 0.95


def test_deflated_sharpe_falls_as_trials_rise():
    r = [0.006 + (0.001 if i % 3 else -0.001) for i in range(80)]
    lo = deflated_sharpe(r, n_trials=1, periods_per_year=52).value
    hi = deflated_sharpe(r, n_trials=500, periods_per_year=52).value
    assert hi <= lo  # more trials -> higher threshold -> lower/equal DSR


def test_deflated_sharpe_requires_trials_and_points():
    with pytest.raises(ValueError):
        deflated_sharpe([0.01, 0.02], n_trials=0, periods_per_year=52)
    with pytest.raises(ValueError):
        deflated_sharpe([0.01], n_trials=5, periods_per_year=52)


def test_benchmark_relative_pure_beta_has_zero_alpha():
    # strat == 0.5 * benchmark exactly -> beta 0.5, alpha ~0
    b = [0.01, -0.02, 0.03, 0.00, 0.015, -0.01, 0.02, -0.005]
    r = [x * 0.5 for x in b]
    br = benchmark_relative(r, b, periods_per_year=52)
    assert abs(br.detail["beta"] - 0.5) < 1e-9
    assert abs(br.value) < 1e-9          # annualized alpha ~ 0
    assert br.detail["correlation"] > 0.99


def test_benchmark_relative_detects_alpha():
    # strat = beta*bench + constant positive alpha each period
    b = [0.01, -0.02, 0.03, 0.00, 0.015, -0.01, 0.02, -0.005]
    r = [x * 0.5 + 0.004 for x in b]
    br = benchmark_relative(r, b, periods_per_year=52)
    assert br.value > 0                  # positive annualized alpha
    assert abs(br.detail["beta"] - 0.5) < 1e-9


def test_benchmark_relative_length_mismatch_raises():
    with pytest.raises(ValueError):
        benchmark_relative([0.01, 0.02, 0.03], [0.01, 0.02], periods_per_year=52)
