"""Portfolio tools — concentration + exposure (QUANT-02).

concentration = Herfindahl Σwᵢ² (with the max single-name magnitude in detail); exposure =
gross Σ|wᵢ| (with net Σwᵢ in detail). The honest long/long framing (PITFALLS #1): gross uses
abs, so two longs show 2× — the PM/Risk agent sees real directional risk instead of a netted
illusion. Pure-python. Both RAISE on an empty book or any NaN/inf weight rather than emitting
a misleading number (Pattern 2); plain-list signatures keep the `inputs` snapshot JSON-serializable.
"""

import math

from .result import ToolResult

_VERSION = "1.0.0"


def _validate(weights: list[float]) -> None:
    """Reject an empty book or any non-finite weight before doing arithmetic."""
    if not weights:
        raise ValueError("weights must be non-empty")
    for w in weights:
        if not math.isfinite(w):
            raise ValueError(f"weights must all be finite (got {w!r})")


def concentration(weights: list[float]) -> ToolResult:
    """Herfindahl concentration Σwᵢ² of a book, with the max single-name magnitude in detail.

    1.0 = a single-name book (maximally concentrated); lower = more diversified. max_weight
    uses abs so a large short leg counts as concentration too.
    """
    _validate(weights)
    return ToolResult(
        tool="concentration",
        tool_version=_VERSION,
        inputs={"weights": list(weights)},
        value=sum(w * w for w in weights),
        detail={"max_weight": max(abs(w) for w in weights)},
    )


def exposure(weights: list[float]) -> ToolResult:
    """Gross exposure Σ|wᵢ| of a book, with net Σwᵢ in detail.

    PITFALLS #1: gross is the abs sum, so two 0.6 longs report 1.2 gross — NOT netted to some
    smaller number. Net (the signed sum) is surfaced separately so the honest directional risk
    (gross) is never hidden behind a comforting net.
    """
    _validate(weights)
    return ToolResult(
        tool="exposure",
        tool_version=_VERSION,
        inputs={"weights": list(weights)},
        value=sum(abs(w) for w in weights),
        detail={"net": sum(weights)},
    )
