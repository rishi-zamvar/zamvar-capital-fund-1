"""Pairs / hedge-analysis tools — cointegration, correlation/β, conditional-payoff (QUANT-02).

cointegration() is the ONE tool that delegates to statsmodels: the ADF unit-root test
(Engle-Granger) and the Johansen trace test carry critical-value tables that are a bug farm
to hand-roll (§Don't Hand-Roll). correlation_beta() is a numpy one-liner. conditional_payoff()
is pure-python — the honest replacement for "0.7 correlated = hedged" (PITFALLS #1): it models
the target/peer payoff conditional on the catalyst branch and reports the un-netted worst case,
which feeds inverse-hedge sizing.

Signatures take plain lists (Pattern 3) so the reproducible `inputs` snapshot stays
JSON-serializable; conversion to numpy happens internally. Every tool validates at the boundary
and RAISES on out-of-domain input rather than emitting a misleading number (Pattern 2).
"""

import math

import numpy as np
from statsmodels.tsa.stattools import coint
from statsmodels.tsa.vector_ar.vecm import coint_johansen

from .result import ToolResult

_VERSION = "1.0.0"

# Johansen trace critical-value columns are [90%, 95%, 99%]; map a significance to its column.
_JOHANSEN_CRIT_COL = {0.10: 0, 0.05: 1, 0.01: 2}


def _aligned_finite(a: list[float], b: list[float], min_obs: int) -> tuple[np.ndarray, np.ndarray]:
    """Validate two price series share length >= min_obs and contain only finite values."""
    if len(a) != len(b):
        raise ValueError(f"series must be equal length (got {len(a)} vs {len(b)})")
    if len(a) < min_obs:
        raise ValueError(f"need >= {min_obs} aligned observations (got {len(a)})")
    arr_a = np.asarray(a, dtype=float)
    arr_b = np.asarray(b, dtype=float)
    if not (np.all(np.isfinite(arr_a)) and np.all(np.isfinite(arr_b))):
        raise ValueError("series must not contain NaN or inf")
    return arr_a, arr_b


def cointegration(
    price_a: list[float],
    price_b: list[float],
    method: str = "engle_granger",
    significance: float = 0.05,
) -> ToolResult:
    """Test two price series for cointegration.

    engle_granger: statsmodels two-step ADF → (t_stat, p_value, crit_values); cointegrated when
    p_value < significance. johansen: trace statistic vs its critical value at `significance`.
    Hedge ratio (β) is the OLS slope of a on b in both paths. Requires >= 30 aligned, finite obs
    (PITFALLS #3). Cointegration is necessary-not-sufficient for a hedge — the peer must also be
    catalyst-clean and modeled conditional on the catalyst (see conditional_payoff, PITFALLS #1).
    """
    arr_a, arr_b = _aligned_finite(price_a, price_b, min_obs=30)
    hedge_ratio = float(np.polyfit(arr_b, arr_a, 1)[0])  # OLS slope of a on b
    inputs = {
        "price_a": list(price_a),
        "price_b": list(price_b),
        "method": method,
        "significance": significance,
    }

    if method == "engle_granger":
        t_stat, p_value, crit = coint(arr_a, arr_b)
        return ToolResult(
            tool="cointegration",
            tool_version=_VERSION,
            inputs=inputs,
            value=float(p_value),
            detail={
                "method": "engle_granger",
                "p_value": float(p_value),
                "t_stat": float(t_stat),
                "crit_values": [float(c) for c in crit],
                "hedge_ratio": hedge_ratio,
                "cointegrated": bool(p_value < significance),
            },
        )

    if method == "johansen":
        col = _JOHANSEN_CRIT_COL.get(significance, 1)  # default 95% column
        endog = np.column_stack([arr_a, arr_b])
        jres = coint_johansen(endog, det_order=0, k_ar_diff=1)
        trace_stat = float(jres.lr1[0])  # H0: rank 0 (no cointegration)
        crit_value = float(jres.cvt[0, col])
        return ToolResult(
            tool="cointegration",
            tool_version=_VERSION,
            inputs=inputs,
            value=trace_stat,
            detail={
                "method": "johansen",
                "trace_stat": trace_stat,
                "crit_value": crit_value,
                "hedge_ratio": hedge_ratio,
                "cointegrated": bool(trace_stat > crit_value),
            },
        )

    raise ValueError(f"method must be 'engle_granger' or 'johansen' (got {method!r})")


def correlation_beta(
    asset_returns: list[float],
    market_returns: list[float],
) -> ToolResult:
    """Pearson correlation + market β (OLS slope) of an asset vs the market.

    Guards equal length >= 2, finite values, and non-zero variance in BOTH series (correlation
    and β are undefined on a constant series — raise rather than emit NaN, PITFALLS #1).
    """
    if len(asset_returns) != len(market_returns):
        raise ValueError(
            f"series must be equal length (got {len(asset_returns)} vs {len(market_returns)})"
        )
    if len(asset_returns) < 2:
        raise ValueError("need >= 2 observations for correlation/β")
    a = np.asarray(asset_returns, dtype=float)
    m = np.asarray(market_returns, dtype=float)
    if not (np.all(np.isfinite(a)) and np.all(np.isfinite(m))):
        raise ValueError("series must not contain NaN or inf")
    if a.std() == 0 or m.std() == 0:
        raise ValueError("zero variance — correlation/β undefined")

    correlation = float(np.corrcoef(a, m)[0, 1])
    beta = float(np.polyfit(m, a, 1)[0])
    return ToolResult(
        tool="correlation_beta",
        tool_version=_VERSION,
        inputs={"asset_returns": list(asset_returns), "market_returns": list(market_returns)},
        value=correlation,
        detail={"beta": beta},
    )


def conditional_payoff(
    target_up: float,
    target_down: float,
    peer_up: float,
    peer_down: float,
    w_target: float,
    w_peer: float,
) -> ToolResult:
    """2×2 catalyst-branch portfolio-return matrix over {target ↑/↓} × {peer ↑/↓}.

    The honest replacement for "0.7 correlated = hedged" (PITFALLS #1): each cell is the
    weighted portfolio return in that branch; `value` is the WORST cell — the combined
    worst-case, UN-netted — which is what inverse-hedge sizing must size against. Branch moves
    come from historical analog gaps (the caller supplies them). All inputs must be finite.
    """
    args = {
        "target_up": target_up,
        "target_down": target_down,
        "peer_up": peer_up,
        "peer_down": peer_down,
        "w_target": w_target,
        "w_peer": w_peer,
    }
    for name, x in args.items():
        if not math.isfinite(x):
            raise ValueError(f"{name} must be finite (got {x!r})")

    matrix = {
        "target_up_peer_up": w_target * target_up + w_peer * peer_up,
        "target_up_peer_down": w_target * target_up + w_peer * peer_down,
        "target_down_peer_up": w_target * target_down + w_peer * peer_up,
        "target_down_peer_down": w_target * target_down + w_peer * peer_down,
    }
    return ToolResult(
        tool="conditional_payoff",
        tool_version=_VERSION,
        inputs=args,
        value=min(matrix.values()),
        detail={"matrix": matrix},
    )
