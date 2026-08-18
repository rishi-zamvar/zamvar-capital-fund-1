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


# ── E9: multiple-testing-honest skill + benchmark-relative (edge vs beta) ──────────────────────

def _skew_kurt(r: "np.ndarray") -> tuple[float, float]:
    """Population skewness (g3) and NON-excess kurtosis (g4). Used by the deflated Sharpe."""
    mu = r.mean(); sd = r.std(ddof=0)
    if sd == 0:
        raise ValueError("zero volatility — higher moments undefined")
    z = (r - mu) / sd
    return float((z ** 3).mean()), float((z ** 4).mean())


def deflated_sharpe(returns: list[float], *, n_trials: int, periods_per_year: int) -> ToolResult:
    """Deflated Sharpe Ratio (Bailey & López de Prado 2014) — the probability the strategy's TRUE
    Sharpe beats the threshold you'd expect from the BEST of `n_trials` random strategies, corrected
    for skew/kurtosis and sample length. value in [0,1]; >0.95 = skill survives multiple testing.

    Uses the per-period Sharpe (annualization cancels in the ratio). n_trials>=1; T>=2.
    """
    from statistics import NormalDist
    r = _to_array(returns, min_len=2)
    if n_trials < 1:
        raise ValueError("n_trials must be >= 1")
    T = len(r)
    sd = r.std(ddof=1)
    if sd == 0:
        raise ValueError("zero volatility — deflated Sharpe undefined")
    sr = float(r.mean() / sd)                      # per-period Sharpe
    g3, g4 = _skew_kurt(r)
    denom = 1.0 - g3 * sr + ((g4 - 1.0) / 4.0) * sr ** 2
    if denom <= 0:
        raise ValueError("non-positive variance term — deflated Sharpe undefined")
    N = NormalDist()
    gamma = 0.5772156649015329                     # Euler–Mascheroni
    # expected max Sharpe under n_trials i.i.d. null strategies (LdP), scaled by the SR estimation SE
    se_sr = math.sqrt(denom / (T - 1))
    if n_trials == 1:
        sr0 = 0.0  # single trial: no multiple-testing inflation, threshold is just SR>0 (=PSR)
    else:
        z1 = N.inv_cdf(1.0 - 1.0 / n_trials)
        z2 = N.inv_cdf(1.0 - 1.0 / (n_trials * math.e))
        sr0 = se_sr * ((1.0 - gamma) * z1 + gamma * z2)
    dsr = N.cdf((sr - sr0) * math.sqrt(T - 1) / math.sqrt(denom))
    return ToolResult(
        tool="deflated_sharpe", tool_version=_VERSION,
        inputs={"returns": list(returns), "n_trials": n_trials, "periods_per_year": periods_per_year},
        value=float(dsr),
        detail={"sr_per_period": sr, "sr_annualized": sr * math.sqrt(periods_per_year),
                "sr0_threshold": float(sr0), "skew": g3, "kurtosis": g4, "n_obs": T},
    )


def benchmark_relative(returns: list[float], benchmark: list[float], *, periods_per_year: int) -> ToolResult:
    """CAPM decomposition vs a benchmark (rf=0): is the return EDGE (alpha) or just BETA?

    value = annualized alpha. detail carries beta, correlation, annualized excess return, tracking
    error, and information ratio. Equal-length series, >=2 points.
    """
    r = _to_array(returns, min_len=2)
    b = _to_array(benchmark, min_len=2)
    if len(r) != len(b):
        raise ValueError(f"length mismatch: {len(r)} vs {len(b)}")
    var_b = b.var(ddof=1)
    if var_b == 0:
        raise ValueError("benchmark has zero variance — beta undefined")
    beta = float(np.cov(r, b, ddof=1)[0, 1] / var_b)
    alpha_pp = float(r.mean() - beta * b.mean())
    diff = r - b
    te = float(diff.std(ddof=1) * math.sqrt(periods_per_year))
    corr = float(np.corrcoef(r, b)[0, 1])
    excess_ann = float(diff.mean() * periods_per_year)
    ir = excess_ann / te if te else 0.0
    return ToolResult(
        tool="benchmark_relative", tool_version=_VERSION,
        inputs={"returns": list(returns), "benchmark": list(benchmark), "periods_per_year": periods_per_year},
        value=float(alpha_pp * periods_per_year),   # annualized alpha
        detail={"beta": beta, "correlation": corr, "alpha_annual": float(alpha_pp * periods_per_year),
                "excess_return_annual": excess_ann, "tracking_error": te, "information_ratio": ir},
    )
