"""Options context tools — implied-move + IV-crush (QUANT-02).

These are SIZING/CONTEXT inputs, never directional P&L (PITFALLS #10): implied_move gives a
model-free magnitude prior for the event gap; iv_crush estimates the vol collapse to sanity-
check that prior. Pure-python (`math` only). Every tool validates at the boundary and RAISES
on out-of-domain input rather than emitting inf/NaN (Pattern 2). Signatures take plain floats
so the reproducible `inputs` snapshot stays JSON-serializable.
"""

import math

from .result import ToolResult

_VERSION = "1.0.0"

_DAYS_PER_YEAR = 365


def _finite_nonneg(name: str, x: float) -> None:
    """Reject NaN/inf and negative values — IVs, prices and premia are all >= 0."""
    if not math.isfinite(x):
        raise ValueError(f"{name} must be finite (got {x!r})")
    if x < 0:
        raise ValueError(f"{name} must be >= 0 (got {x})")


def implied_move(
    underlying_price: float,
    call_mid: float | None = None,
    put_mid: float | None = None,
    iv: float | None = None,
    days_to_event: int | None = None,
) -> ToolResult:
    """Estimate the market's implied % move around a catalyst.

    Straddle method (preferred, model-free): (call_mid + put_mid) / underlying_price. IV method:
    iv · sqrt(days_to_event / 365). Requires exactly one complete method's inputs; the straddle
    wins when both are supplied. underlying_price must be > 0 and every supplied leg finite and
    non-negative. `value` is the implied % move — a magnitude prior for the downside gap in
    sizing, NEVER a directional signal (PITFALLS #10).
    """
    if not math.isfinite(underlying_price):
        raise ValueError(f"underlying_price must be finite (got {underlying_price!r})")
    if underlying_price <= 0:
        raise ValueError(f"underlying_price must be > 0 (got {underlying_price})")
    for name, x in (("call_mid", call_mid), ("put_mid", put_mid), ("iv", iv)):
        if x is not None:
            _finite_nonneg(name, x)

    inputs = {
        "underlying_price": underlying_price,
        "call_mid": call_mid,
        "put_mid": put_mid,
        "iv": iv,
        "days_to_event": days_to_event,
    }

    if call_mid is not None and put_mid is not None:
        method = "straddle"
        move = (call_mid + put_mid) / underlying_price
    elif iv is not None and days_to_event is not None:
        if days_to_event < 0:
            raise ValueError(f"days_to_event must be >= 0 (got {days_to_event})")
        method = "iv"
        move = iv * math.sqrt(days_to_event / _DAYS_PER_YEAR)
    else:
        raise ValueError(
            "supply a complete method: straddle (call_mid + put_mid) or IV (iv + days_to_event)"
        )

    return ToolResult(
        tool="implied_move",
        tool_version=_VERSION,
        inputs=inputs,
        value=move,
        detail={"method": method},
    )


def iv_crush(
    pre_event_iv: float,
    post_event_iv: float | None = None,
    baseline_iv: float | None = None,
) -> ToolResult:
    """Estimate the IV-crush magnitude: pre_event_iv − (post_event_iv or baseline_iv).

    Biotech binaries routinely run 150–300% pre-event IV that collapses to baseline after the
    print. Since this book trades equities, the crush is a CONTEXT/sizing input (sanity-checks
    the implied move), never P&L (PITFALLS #10). Requires post_event_iv or baseline_iv; all
    supplied IVs must be finite and non-negative.
    """
    _finite_nonneg("pre_event_iv", pre_event_iv)
    if post_event_iv is not None:
        _finite_nonneg("post_event_iv", post_event_iv)
        reference, ref_name = post_event_iv, "post_event_iv"
    elif baseline_iv is not None:
        _finite_nonneg("baseline_iv", baseline_iv)
        reference, ref_name = baseline_iv, "baseline_iv"
    else:
        raise ValueError("supply post_event_iv or baseline_iv")

    return ToolResult(
        tool="iv_crush",
        tool_version=_VERSION,
        inputs={
            "pre_event_iv": pre_event_iv,
            "post_event_iv": post_event_iv,
            "baseline_iv": baseline_iv,
        },
        value=pre_event_iv - reference,
        detail={"reference": ref_name},
    )
