"""Performance tools — sharpe, sortino, cumulative_return, attribution (QUANT-02).

Hand-rolled numpy math (research §Tool Catalog #10): quantstats/empyrical/vectorbt are rejected
as heavyweight and — worse — they hide the annualization factor that silently corrupts Sharpe
(the documented `freq` footgun, PITFALLS #2). Here `periods_per_year` is a REQUIRED argument on
sharpe + sortino: a weekly book passes 52, a daily book 252, and the caller can never forget it.
Every tool RAISES on empty/single-point series, zero volatility / zero downside deviation, or any
NaN rather than emitting inf/NaN into a P&L number (Pattern 2). Plain-list signatures (Pattern 3)
keep the `inputs` snapshot JSON-serializable; pandas stays out of the API.
"""

import math

import numpy as np

from .result import ToolResult

_VERSION = "1.0.0"


def _to_array(returns: list[float], min_len: int) -> np.ndarray:
    """Validate a returns series and coerce to a float ndarray.

    Rejects too-short series (ddof=1 std needs ≥2 points) and any non-finite value before any
    arithmetic runs, so a NaN/inf can never propagate into a Sharpe/return number.
    """
    if len(returns) < min_len:
        raise ValueError(f"need at least {min_len} return(s), got {len(returns)}")
    r = np.asarray(returns, dtype=float)
    if not np.all(np.isfinite(r)):
        raise ValueError("returns must all be finite (no NaN/inf)")
    return r


def sharpe(returns: list[float], periods_per_year: int, risk_free: float = 0.0) -> ToolResult:
    """Annualized Sharpe ratio. `periods_per_year` is REQUIRED — the freq-footgun cure.

    Sharpe = mean(excess) / std(excess, ddof=1) · √periods_per_year, where excess subtracts the
    per-period risk-free rate. Raises on <2 points, any NaN, or zero volatility (constant returns
    → undefined, never inf).
    """
    r = _to_array(returns, min_len=2)
    excess = r - risk_free / periods_per_year
    sd = excess.std(ddof=1)
    if sd == 0:
        raise ValueError("zero volatility — Sharpe undefined")
    return ToolResult(
        tool="sharpe",
        tool_version=_VERSION,
        inputs={
            "returns": list(returns),
            "periods_per_year": periods_per_year,
            "risk_free": risk_free,
        },
        value=float(excess.mean() / sd * np.sqrt(periods_per_year)),
    )


def sortino(
    returns: list[float],
    periods_per_year: int,
    mar: float = 0.0,
    risk_free: float = 0.0,
) -> ToolResult:
    """Annualized Sortino ratio. `periods_per_year` is REQUIRED — same freq-footgun cure.

    Like Sharpe but the denominator is the downside deviation — the target semideviation of
    excess returns below the minimum acceptable return `mar`: √mean(min(excess−mar, 0)²), over
    all observations. Raises on <2 points, any NaN, or zero downside deviation (no returns below
    mar → undefined, never inf).
    """
    r = _to_array(returns, min_len=2)
    excess = r - risk_free / periods_per_year
    downside = np.minimum(excess - mar, 0.0)
    dd = math.sqrt(float(np.mean(downside**2)))
    if dd == 0:
        raise ValueError("zero downside deviation — Sortino undefined")
    return ToolResult(
        tool="sortino",
        tool_version=_VERSION,
        inputs={
            "returns": list(returns),
            "periods_per_year": periods_per_year,
            "mar": mar,
            "risk_free": risk_free,
        },
        value=float((excess.mean() - mar) / dd * np.sqrt(periods_per_year)),
    )


def cumulative_return(returns: list[float]) -> ToolResult:
    """Compounded total return: ∏(1 + rᵢ) − 1.

    A −1.0 (−100%) period zeroes compounded equity → value == −1.0 (a computed wipeout, not a
    crash). Raises on an empty series or any NaN.
    """
    r = _to_array(returns, min_len=1)
    return ToolResult(
        tool="cumulative_return",
        tool_version=_VERSION,
        inputs={"returns": list(returns)},
        value=float(np.prod(1 + r) - 1),
    )


def attribution(components: dict[str, float], total: float) -> ToolResult:
    """Decompose realized P&L into named components that must reconcile to the total.

    Guards the reconciliation: the components must sum to `total` within a tight tolerance
    (rel 1e-6), else ValueError — a decomposition that doesn't add up is a bug, not a number to
    emit. Any NaN component is rejected. `value` = total; `detail` carries the components verbatim
    plus the residual (total − Σcomponents), which is ≈0 on a valid decomposition.
    """
    if not all(math.isfinite(v) for v in components.values()):
        raise ValueError("components must all be finite (no NaN/inf)")
    if not math.isfinite(total):
        raise ValueError("total must be finite")
    residual = total - sum(components.values())
    if not math.isclose(sum(components.values()), total, rel_tol=1e-6, abs_tol=1e-9):
        raise ValueError(
            f"components sum to {sum(components.values())!r}, not total {total!r} "
            f"(residual {residual!r})"
        )
    return ToolResult(
        tool="attribution",
        tool_version=_VERSION,
        inputs={"components": dict(components), "total": total},
        value=float(total),
        detail={"components": dict(components), "residual": residual},
    )
