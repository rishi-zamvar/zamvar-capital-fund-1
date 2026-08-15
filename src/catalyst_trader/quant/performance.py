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


def max_drawdown(returns: list[float]) -> ToolResult:
    """Worst peak-to-trough on the COMPOUNDED equity curve: min(equity/running_peak − 1) ≤ 0.

    A −1.0 (−100%) period zeroes equity → drawdown −1.0, computed not crashed. The
    `running_peak > 0` guard keeps a leading wipeout (peak == 0) from emitting 0/0 = NaN into a
    risk number. Monotonic-up curve → 0.0. Raises on an empty series or any NaN.
    """
    r = _to_array(returns, min_len=1)
    equity = np.cumprod(1.0 + r)
    running_peak = np.maximum.accumulate(equity)
    with np.errstate(invalid="ignore", divide="ignore"):  # 0/0 on a leading wipeout → guarded below
        drawdown = np.where(running_peak > 0, equity / running_peak - 1.0, -1.0)
    return ToolResult(
        tool="max_drawdown",
        tool_version=_VERSION,
        inputs={"returns": list(returns)},
        value=float(drawdown.min()),
    )


def win_rate(trade_returns: list[float]) -> ToolResult:
    """Fraction of trades that MADE money: count(r > 0) / n. A flat 0.0 is NOT a win (strict >).

    all-wins → 1.0; all-losses/all-flat → 0.0. Raises on an empty series or any NaN.
    """
    r = _to_array(trade_returns, min_len=1)
    n_win = int((r > 0).sum())
    return ToolResult(
        tool="win_rate",
        tool_version=_VERSION,
        inputs={"trade_returns": list(trade_returns)},
        value=float(n_win / len(r)),
        detail={"n_win": n_win, "n_total": len(r)},
    )


def avg_win_loss(trade_returns: list[float]) -> ToolResult:
    """Average win / average loss (as a positive magnitude); ratio is `value`.

    value == None when there are no losses (undefined ratio — never a divide-by-zero or inf).
    avg_win / avg_loss default to 0.0 when a side is empty. Raises on an empty series or any NaN.
    """
    r = _to_array(trade_returns, min_len=1)
    wins = r[r > 0]
    losses = r[r < 0]
    avg_win = float(wins.mean()) if wins.size else 0.0
    avg_loss = float(-losses.mean()) if losses.size else 0.0  # positive magnitude
    ratio = float(avg_win / avg_loss) if avg_loss > 0 else None
    return ToolResult(
        tool="avg_win_loss",
        tool_version=_VERSION,
        inputs={"trade_returns": list(trade_returns)},
        value=ratio,
        detail={
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "n_win": int(wins.size),
            "n_loss": int(losses.size),
        },
    )


def hedge_effectiveness(
    target_legs: list[float], hedge_legs: list[float]
) -> ToolResult:
    """Over TARGET-DOWN periods, the fraction where the paired hedge leg actually offset (> 0).

    The legs are paired per-period and MUST be equal length (mismatch raises — a misaligned pair
    is a bug, not a number). value == None when there are NO target-down periods (undefined — never
    a false 1.0). `detail` carries net_pnl_target vs net_pnl_combined so the baseline can also
    report loss-reduction. Raises on an empty series or any NaN.
    """
    t = _to_array(target_legs, min_len=1)
    h = _to_array(hedge_legs, min_len=1)
    if t.size != h.size:
        raise ValueError(f"paired legs must be equal length, got {t.size} vs {h.size}")
    down = t < 0
    down_count = int(down.sum())
    offset_count = int((h[down] > 0).sum())
    value = float(offset_count / down_count) if down_count else None
    return ToolResult(
        tool="hedge_effectiveness",
        tool_version=_VERSION,
        inputs={"target_legs": list(target_legs), "hedge_legs": list(hedge_legs)},
        value=value,
        detail={
            "down_count": down_count,
            "offset_count": offset_count,
            "net_pnl_target": float(t.sum()),
            "net_pnl_combined": float((t + h).sum()),
        },
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
