"""desk/rollup.py (07.9 Plan 3) — the single-thesis roll-up (guideline §6) + the structured renderer
the downstream consumers (debate / verifier / MD) read.

Deterministic and null-propagating: the agents never do arithmetic, so every roll-up number is
computed here from the reports' own fields, and is None the moment an input is None (an empty
slot is a finding — never a fabricated 0). Works on report models AND on `model_dump()` dicts
(the DD dossier stores per_dimension as dicts).

# ponytail: one headline map + four small pure functions. No size/conviction (sizing is risk.py's).
"""

from pydantic import BaseModel

from ..contracts import Rollup

ROLLUP_PARAMS = {"lens_disagreement_tol": 0.15}  # |Clinical P - Regulatory P| above this = disagreement

# dimension -> (headline number path, paired source path). Covers the 4 lens dims + the 8 DD dims
# (lens "regulatory" and DD "regulatory" are the same RegulatoryReport).
HEADLINES = {
    "clinical": ("pos_estimate", "pos_estimate_source"),
    "trial_stats": ("pos_estimate", "pos_estimate_source"),
    "regulatory": ("poa.point", "poa.point_source"),
    "financial": ("rnpv.rnpv_m", "rnpv.rnpv_source"),
    "market_sentiment": ("asymmetry.ev_pct", "asymmetry.ev_source"),
    "financials": ("runway.runway_months", "runway_months_source"),
    "ownership_flow": ("short_interest.si_pct_float", "si_pct_float_source"),
    "options_move": ("expected_move.expected_move_pct", "expected_move_pct_source"),
    "hedge_revalidation": ("conditional_worst", "conditional_worst_source"),
    "liquidity": ("tradeability.volume", "tradeability.volume_source"),
    "historical_analog": ("analog_realized_move_pct", "analog_realized_move_pct_source"),
}

_BASE_FIELDS = {"dimension", "ticker", "catalyst_id", "thesis", "score", "confidence",
                "key_findings", "kb_analogs_queried", "unknowns"}


def _as_dict(report) -> dict:
    return report.model_dump() if isinstance(report, BaseModel) else dict(report)


def _at(d: dict, path: str):
    for k in path.split("."):
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def headline(report) -> tuple[str, float, str] | None:
    """(path, value, source) of the report's ONE headline number, or None if unset/unknown dim."""
    d = _as_dict(report)
    paths = HEADLINES.get(d.get("dimension"))
    if not paths or _at(d, paths[0]) is None:
        return None
    return paths[0], _at(d, paths[0]), _at(d, paths[1])


def _leaves(d: dict, prefix: str = ""):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from _leaves(v, f"{prefix}{k}.")
        elif v not in (None, [], ""):
            yield f"{prefix}{k}", v


def render(report) -> list[str]:
    """The report's structured, NON-NULL data points (empty slots are not rendered as data) + its
    headline with source. Base fields (thesis/findings/...) are rendered by the caller as before."""
    d = {k: v for k, v in _as_dict(report).items() if k not in _BASE_FIELDS}
    lines = [f"  · {path}={val}" for path, val in _leaves(d)]
    h = headline(report)
    if h:
        lines.append(f"  HEADLINE {h[0]}={h[1]} (source: {h[2]})")
    return lines


def _by_dim(reports) -> dict:
    return {_as_dict(r)["dimension"]: _as_dict(r) for r in reports}


def _implied_p(x, z, y) -> float | None:
    """§4(C) priced-in probability p = (X - Y) / (Z - Y); None when undefined or outside [0, 1]."""
    if None in (x, z, y) or z == y:
        return None
    p = (x - y) / (z - y)
    return p if 0.0 <= p <= 1.0 else None


def rollup(reports, *, params: dict = ROLLUP_PARAMS) -> Rollup:
    """Guideline §6 over the 4 lens reports (missing lens -> its fields null)."""
    by = _by_dim(reports)
    pos = _at(by.get("clinical", {}), "pos_estimate")
    poa = _at(by.get("regulatory", {}), "poa.point")
    ps = [p for p in (pos, poa) if p is not None]
    fundamental = sum(ps) / len(ps) if ps else None
    disagree = abs(pos - poa) > params["lens_disagreement_tol"] if len(ps) == 2 else None

    mkt = by.get("market_sentiment", {})
    implied = _implied_p(_at(mkt, "implied_prob.x"), _at(mkt, "implied_prob.z"), _at(mkt, "implied_prob.y"))
    edge = fundamental - implied if fundamental is not None and implied is not None else None

    return Rollup(
        fundamental_p_approval=fundamental,
        lenses_disagree=disagree,
        market_implied_p_approval=implied,
        edge=edge,
        solvency_clears_catalyst=_at(by.get("financial", {}), "runway.clears_catalyst"),
        driver=_at(mkt, "asymmetry.driver"),
        expression=_at(mkt, "asymmetry.expression"),
    )


def render_rollup(r: Rollup) -> str:
    """The roll-up as a context block (null fields shown as 'unknown' — an honest gap, not data)."""
    fmt = lambda v: "unknown" if v is None else (f"{v:.2f}" if isinstance(v, float) else v)  # noqa: E731
    body = "\n".join(f"  {k}={fmt(v)}" for k, v in r.model_dump().items())
    return ("ROLL-UP (deterministic §6 — fundamental vs market-implied P(approval); interpret, do not recompute):\n"
            + body)
