"""Valuation tools — rNPV, cash-runway, pipeline value (QUANT-02).

Pure-python (stdlib `math` only). Each tool validates at the boundary and RAISES on
out-of-domain input rather than emitting a misleading inf/NaN (Pattern 2), and returns a
ToolResult snapshotting its verbatim inputs (QUANT-03). rNPV is the only defensible
pre-revenue biotech valuation — risk lives in the per-phase PoS weights, not the discount rate.
"""

import math

from .result import ToolResult

_VERSION = "1.0.0"


def _finite(x: float, name: str) -> float:
    if not math.isfinite(x):
        raise ValueError(f"{name} must be finite (got {x!r})")
    return x


def _prob(p: float, name: str) -> float:
    _finite(p, name)
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"{name} must be in [0, 1] (got {p!r})")
    return p


def rnpv(
    cashflows: list[tuple[float, float, float]],
    discount_rate: float,
    costs: list[tuple[float, float, float]] | None = None,
) -> ToolResult:
    """Risk-adjusted NPV.

    rNPV = Σ CF_t·pos_t/(1+r)^t  −  Σ Cost_t·p_reach_t/(1+r)^t
    cashflows: (year, cashflow_usd, cumulative_pos); costs: (year, cost_usd, prob_reach).
    """
    if not cashflows:
        raise ValueError("cashflows must be non-empty")
    _finite(discount_rate, "discount_rate")
    if discount_rate <= -1.0:
        raise ValueError("discount_rate must be > -1.0 ((1+r)^t divides by zero)")
    base = 1.0 + discount_rate

    pv_inflows = 0.0
    for year, cf, pos in cashflows:
        _finite(cf, "cashflow")  # negative is valid (a loss year); NaN/inf is not
        _prob(pos, "cumulative_pos")
        pv_inflows += cf * pos / base**year

    pv_costs = 0.0
    for year, cost, prob in costs or []:
        _finite(cost, "cost")
        _prob(prob, "prob_reach")
        pv_costs += cost * prob / base**year

    return ToolResult(
        tool="rnpv",
        tool_version=_VERSION,
        inputs={"cashflows": cashflows, "discount_rate": discount_rate, "costs": costs},
        value=pv_inflows - pv_costs,
        detail={"pv_inflows": pv_inflows, "pv_costs": pv_costs},
    )


def cash_runway(
    cash_usd: float,
    monthly_burn_usd: float,
    months_to_catalyst: float | None = None,
) -> ToolResult:
    """Months of cash at current burn. Refuses undefined runway (burn<=0) and negative cash."""
    _finite(cash_usd, "cash_usd")
    _finite(monthly_burn_usd, "monthly_burn_usd")
    if cash_usd < 0:
        raise ValueError("cash_usd cannot be negative")
    if monthly_burn_usd <= 0:
        raise ValueError("monthly_burn_usd must be > 0 (div-by-zero / undefined runway)")

    months = cash_usd / monthly_burn_usd
    detail: dict = {}
    if months_to_catalyst is not None:
        _finite(months_to_catalyst, "months_to_catalyst")
        detail["funded_past_catalyst"] = months >= months_to_catalyst

    return ToolResult(
        tool="cash_runway",
        tool_version=_VERSION,
        inputs={
            "cash_usd": cash_usd,
            "monthly_burn_usd": monthly_burn_usd,
            "months_to_catalyst": months_to_catalyst,
        },
        value=months,
        detail=detail,
    )


def pipeline_value(results: list[ToolResult]) -> ToolResult:
    """Sum per-asset rNPV values so agents never sum by hand. Rejects empty / value-less results."""
    if not results:
        raise ValueError("results must be non-empty")
    values = []
    for r in results:
        if r.value is None:
            raise ValueError("every result must carry a numeric value")
        values.append(r.value)

    return ToolResult(
        tool="pipeline_value",
        tool_version=_VERSION,
        inputs={"asset_values": values},
        value=sum(values),
        detail={"n_assets": len(values)},
    )
