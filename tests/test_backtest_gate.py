"""BACK-05 — the go/no-go gate is SAMPLE-BASED (N-driven), never calendar.

The gate consumes the 07-04 BaselineDistribution + a catalyst sample size N and emits an explicit
go/no-go verdict. Below the minimum sample it is a hard NO-GO regardless of how strong the metrics
look (that is what "sample-based, not calendar" MEANS — you cannot buy your way past a tiny N with a
lucky Sharpe). Above the floor it names every failing metric — no opaque no-go.
"""

import pytest

from catalyst_trader.backtest.engine import BaselineDistribution
from catalyst_trader.backtest.gate import THRESHOLDS, GateVerdict, sample_based_gate


def _dist(**over) -> BaselineDistribution:
    """A STRONG baseline (clears every default floor) with per-field overrides for the failing cases."""
    base = dict(
        win_rate=0.70, avg_win=0.05, avg_loss=-0.02, sharpe=1.5, sortino=2.0,
        max_drawdown=-0.08, hedge_effectiveness=0.6, n_trades=50, n_weeks=20,
    )
    base.update(over)
    return BaselineDistribution(**base)


def test_gate_insufficient_sample_is_no_go():
    """N below min_sample -> go=False EVEN with great metrics (proves sample-based, not calendar)."""
    verdict = sample_based_gate(_dist(), n_catalysts=THRESHOLDS["min_sample"] - 1, thresholds=THRESHOLDS)

    assert isinstance(verdict, GateVerdict)
    assert verdict.go is False
    assert any("sample" in r.lower() for r in verdict.reasons)
    assert verdict.n_catalysts == THRESHOLDS["min_sample"] - 1
    assert verdict.min_sample == THRESHOLDS["min_sample"]


def test_gate_go_when_metrics_and_sample_clear():
    """Sample floor cleared AND every metric passes -> go=True with no failure reasons."""
    verdict = sample_based_gate(_dist(), n_catalysts=THRESHOLDS["min_sample"] + 10, thresholds=THRESHOLDS)

    assert verdict.go is True
    assert verdict.reasons == []


def test_gate_names_each_failing_metric():
    """A low win_rate AND a too-deep drawdown -> BOTH named in reasons; go=False."""
    dist = _dist(win_rate=0.30, max_drawdown=-0.90)
    verdict = sample_based_gate(dist, n_catalysts=THRESHOLDS["min_sample"] + 10, thresholds=THRESHOLDS)

    assert verdict.go is False
    joined = " ".join(verdict.reasons).lower()
    assert "win_rate" in joined
    assert "max_drawdown" in joined


def test_gate_undefined_metric_is_named_no_go():
    """An undefined (None) ratio can't clear a floor -> it is a NAMED failure, never a silent pass."""
    verdict = sample_based_gate(
        _dist(sharpe=None), n_catalysts=THRESHOLDS["min_sample"] + 10, thresholds=THRESHOLDS
    )
    assert verdict.go is False
    assert any("sharpe" in r.lower() for r in verdict.reasons)


def test_gate_missing_threshold_raises():
    """thresholds is read by direct subscript — a missing floor raises, never a magic-number fallback."""
    incomplete = {k: v for k, v in THRESHOLDS.items() if k != "win_rate"}
    with pytest.raises(KeyError):
        sample_based_gate(_dist(), n_catalysts=THRESHOLDS["min_sample"] + 10, thresholds=incomplete)
