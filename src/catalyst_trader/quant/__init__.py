"""Quant tool library — one import surface for deterministic, reproducible money-math.

Agents call these tools instead of doing arithmetic; every tool returns a `ToolResult`
carrying a verbatim, immutable snapshot of its inputs (QUANT-03) plus a version tag
(QUANT-01). Import everything from here:

    from catalyst_trader.quant import kelly, rnpv, cointegration, base_rate

Submodules import their own numpy/statsmodels deps at module top, so importing the package
pulls those in — that is intentional (the desk always uses the whole toolbox).
"""

from .base_rates import base_rate, load_base_rates
from .events import catalyst_move_estimate
from .options import implied_move, iv_crush
from .pairs import cointegration, conditional_payoff, correlation_beta
from .performance import attribution, cumulative_return, sharpe, sortino
from .portfolio import concentration, exposure
from .result import ToolResult
from .rubric import load_weights, score_rubric
from .sizing import fractional_kelly, kelly, risk_of_ruin, sl_tp_levels
from .valuation import cash_runway, rnpv

__all__ = [
    "ToolResult",
    # valuation
    "rnpv",
    "cash_runway",
    # sizing
    "kelly",
    "fractional_kelly",
    "risk_of_ruin",
    "sl_tp_levels",
    # pairs
    "cointegration",
    "correlation_beta",
    "conditional_payoff",
    # options
    "implied_move",
    "iv_crush",
    # performance
    "sharpe",
    "sortino",
    "cumulative_return",
    "attribution",
    # portfolio
    "concentration",
    "exposure",
    # rubric
    "load_weights",
    "score_rubric",
    # base rates
    "load_base_rates",
    "base_rate",
    # events
    "catalyst_move_estimate",
]
