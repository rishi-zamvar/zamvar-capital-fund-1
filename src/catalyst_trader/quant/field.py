"""Football-field aggregator — combine per-method expected-move magnitudes into the
convergence point estimate (FF-02/FF-03).

The "football field" stacks every independent method's implied move on one axis; the
recommendation anchors on the CONVERGENCE ZONE where methods cluster, not the arithmetic
mean. Our proxy for that zone is the confidence-weighted TRIMMED MEDIAN of the surviving
per-method magnitudes — outlier-robust, no arbitrary kernel bandwidth, and (per the
forecast-combination literature) matches or beats estimated inverse-variance/Bayesian weights
when per-method error variances are unknown and few/correlated.

Discipline (mirrors the rest of quant/): magnitudes only (the sign is the debate verdict's,
never voted on here); abstaining methods are OMITTED by the caller, never entered as 0 (which
would bias the estimate toward zero); every threshold is read from params["field"] by direct
subscript — a missing key RAISES, there is no numeric literal fallback in the body; out-of-domain
input RAISES rather than emitting a misleading NaN (Pattern 2). Same inputs in → identical frozen
ToolResult out (stdlib math/statistics only, deterministic, offline).
"""

from statistics import mean, pstdev

from .result import ToolResult
from .valuation import _finite

_VERSION = "1.0.0"


def _cut_low_tail(pairs: list[tuple[float, float]], cut: float) -> list[tuple[float, float]]:
    """Drop `cut` units of weight off the FRONT of a magnitude-sorted (mag, weight) list.

    A contribution straddling the cut boundary keeps its residual weight (fractional trim);
    fully-consumed contributions drop out entirely.
    """
    out: list[tuple[float, float]] = []
    remaining = cut
    for mag, w in pairs:
        if remaining <= 0:
            out.append((mag, w))
        elif w <= remaining:
            remaining -= w  # this contribution is entirely trimmed away
        else:
            out.append((mag, w - remaining))
            remaining = 0.0
    return out


def _weighted_median(pairs: list[tuple[float, float]]) -> float:
    """Magnitude where cumulative weight crosses half of total weight (straddle → average)."""
    half = sum(w for _, w in pairs) / 2.0
    cum = 0.0
    for i, (mag, w) in enumerate(pairs):
        cum += w
        if cum > half:
            return mag
        if cum == half:  # exact split → average the two straddling magnitudes
            return (mag + pairs[i + 1][0]) / 2.0 if i + 1 < len(pairs) else mag
    return pairs[-1][0]


def expected_move_field(methods: list[dict], params: dict) -> ToolResult:
    """Assemble the expected-move football field → the convergence point estimate.

    methods: [{"method": str, "magnitude": float>=0, "weight": float>0, "ref": str}] — abstaining
             methods are omitted by the caller, never passed as 0.
    params["field"]: {"min_methods": int, "trim_frac": float, "dispersion_wide": float} — every
             threshold read by direct subscript; a missing key RAISES.

    value  = confidence-weighted trimmed MEDIAN of the surviving magnitudes (the convergence zone).
    detail = {contributions, point_estimate, low, high, dispersion, agreement, n_methods,
              method_labels, refs}; agreement = "wide" if dispersion >= dispersion_wide else "tight".
    """
    field = params["field"]  # missing block → KeyError (no literal fallback)
    min_methods = field["min_methods"]
    trim_frac = field["trim_frac"]
    dispersion_wide = field["dispersion_wide"]

    if len(methods) < min_methods:
        raise ValueError(
            f"expected_move_field needs >= {min_methods} methods (got {len(methods)}) — "
            "a one-method 'field' is false precision"
        )

    pairs: list[tuple[float, float]] = []
    for m in methods:
        magnitude = _finite(m["magnitude"], "magnitude")
        if magnitude < 0:
            raise ValueError(f"magnitude must be >= 0 (got {magnitude!r}) — the field carries no sign")
        weight = _finite(m["weight"], "weight")
        if weight <= 0:
            raise ValueError(f"weight must be > 0 (got {weight!r})")
        pairs.append((magnitude, weight))

    pairs.sort(key=lambda p: p[0])
    if trim_frac > 0:
        cut = trim_frac * sum(w for _, w in pairs)
        pairs = _cut_low_tail(pairs, cut)  # low tail
        pairs = _cut_low_tail(pairs[::-1], cut)[::-1]  # high tail (mirror)
    if not pairs:
        raise ValueError(f"trim_frac={trim_frac!r} removed every contribution — over-trimmed")

    value = _weighted_median(pairs)
    survivors = [mag for mag, _ in pairs]
    mu = mean(survivors)
    dispersion = pstdev(survivors) / mu if len(survivors) >= 2 and mu > 0 else 0.0

    return ToolResult(
        tool="expected_move_field",
        tool_version=_VERSION,
        inputs={"methods": methods, "params": params},
        value=value,
        detail={
            "contributions": methods,
            "point_estimate": value,
            "low": min(survivors),
            "high": max(survivors),
            "dispersion": dispersion,
            "agreement": "wide" if dispersion >= dispersion_wide else "tight",
            "n_methods": len(methods),
            "method_labels": [m["method"] for m in methods],
            "refs": [m["ref"] for m in methods],
        },
    )
