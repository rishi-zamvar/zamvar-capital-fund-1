"""backtest/gate.py — BACK-05: the SAMPLE-BASED go/no-go gate before paper trading.

``sample_based_gate`` turns the 07-04 BaselineDistribution + a catalyst sample size N into an
explicit go/no-go verdict. It is SAMPLE-BASED, never calendar (mirrors the Phase-8 EXEC-02 go-live
discipline): below ``thresholds["min_sample"]`` it is a hard NO-GO regardless of how strong the
metrics look — you cannot clear the gate with a lucky Sharpe on a handful of catalysts; only a big
enough N earns a metric-based verdict. There is NO time/weeks/date term anywhere in the decision.

Above the sample floor it emits go/no-go from the baseline metrics (win rate, Sharpe, max-drawdown,
hedge-effectiveness), NAMING every failing metric so the no-go is never opaque. An undefined (None)
ratio cannot clear a floor, so it is a named failure, never a silent pass.

Thresholds are read by DIRECT SUBSCRIPT — a missing floor raises KeyError rather than falling back to
a magic number. ``THRESHOLDS`` is the documented default set the PM retunes once the real baseline
lands (research §BACK-05 / Decision 7: sizing/SL-TP/entry tuning is unlocked by the baseline).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .engine import BaselineDistribution

# Documented default floors — the PM RETUNES these post-baseline (they are assumptions, the moat).
# min_sample is the N-floor that makes the gate sample-based; the rest are per-metric floors.
THRESHOLDS: dict[str, float] = {
    "min_sample": 30,          # a real go/no-go needs a statistically meaningful catalyst N
    "win_rate": 0.50,          # better than a coin flip on realized direction
    "sharpe": 0.50,            # risk-adjusted return floor (periods_per_year=52, freq footgun cured)
    "max_drawdown": -0.25,     # not worse than -25% peak-to-trough (dd is negative; >= floor passes)
    "hedge_effectiveness": 0.30,  # the peer leg must offset the target leg often enough to matter
}


class GateVerdict(BaseModel):
    """The explicit go/no-go decision — go plus every reason it failed (empty reasons == clean go)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    go: bool
    reasons: list[str]
    n_catalysts: int
    min_sample: int


def _below_floor(name: str, value: float | None, floor: float) -> str | None:
    """Return a named-failure string if `value` does not clear `floor` (None never clears)."""
    if value is None:
        return f"{name} is undefined (cannot clear floor {floor})"
    if value < floor:
        return f"{name}={value:.3f} below floor {floor}"
    return None


def sample_based_gate(
    distribution: BaselineDistribution, *, n_catalysts: int, thresholds: dict
) -> GateVerdict:
    """Emit a sample-based (never calendar) go/no-go verdict from the baseline distribution.

    N below ``thresholds["min_sample"]`` -> NO-GO with an insufficient-sample reason, whatever the
    metrics say. Above it -> go iff win_rate / sharpe / max_drawdown / hedge_effectiveness each clear
    their floor; every miss is named. Thresholds are read by direct subscript (missing key raises).
    """
    min_sample = thresholds["min_sample"]

    # SAMPLE GATE FIRST: a tiny N is an automatic NO-GO — this is what makes the gate sample-based.
    if n_catalysts < min_sample:
        return GateVerdict(
            go=False,
            reasons=[f"insufficient sample (N={n_catalysts} < min {min_sample})"],
            n_catalysts=n_catalysts,
            min_sample=min_sample,
        )

    reasons = [
        r for r in (
            _below_floor("win_rate", distribution.win_rate, thresholds["win_rate"]),
            _below_floor("sharpe", distribution.sharpe, thresholds["sharpe"]),
            _below_floor("max_drawdown", distribution.max_drawdown, thresholds["max_drawdown"]),
            _below_floor("hedge_effectiveness", distribution.hedge_effectiveness,
                         thresholds["hedge_effectiveness"]),
        )
        if r is not None
    ]
    return GateVerdict(
        go=not reasons, reasons=reasons, n_catalysts=n_catalysts, min_sample=min_sample
    )
