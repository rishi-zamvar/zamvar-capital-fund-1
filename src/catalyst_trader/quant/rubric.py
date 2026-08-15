"""Tunable 8-factor biotech scoring rubric (FRAME-01/02, QUANT-03).

Weights live in data/rubric_weights.json — DATA, not code — so the Phase-10 learning loop
just rewrites the file (bumping `version`) with no code change. `load_weights` is the guard
that keeps a rewritten file from poisoning a score: every factor must be present, every weight
in [0, 1], and Σweights ≈ 1.0. `score_rubric` produces a 0–100 composite and surfaces the PoS
factor separately (it's the dominant driver of a binary catalyst).
"""

import json
from pathlib import Path

from .result import ToolResult

_VERSION = "1.0.0"
DATA_DIR = Path(__file__).resolve().parents[3] / "data"  # repo-root/data

# The 8 rubric factors (FRAME-01). Order is documentation only; scoring is key-based.
_FACTORS = (
    "pos",
    "cash_runway",
    "trial_design",
    "endpoint_credibility",
    "regulatory_precedent",
    "pipeline_concentration",
    "management",
    "commercial",
)


def load_weights(path: str | Path = DATA_DIR / "rubric_weights.json") -> dict:
    """Read + validate the weights JSON. Raises ValueError on any corrupt file so a bad
    learning-loop rewrite can never reach score_rubric."""
    data = json.loads(Path(path).read_text())
    weights = data.get("weights")
    if not isinstance(weights, dict):
        raise ValueError("weights file missing a 'weights' object")

    missing = set(_FACTORS) - weights.keys()
    unknown = weights.keys() - set(_FACTORS)
    if missing:
        raise ValueError(f"weights missing factor(s): {sorted(missing)}")
    if unknown:
        raise ValueError(f"weights has unknown factor(s): {sorted(unknown)}")

    for factor, w in weights.items():
        if not 0.0 <= w <= 1.0:  # reject negative or >1 (the learning loop rewrites this file)
            raise ValueError(f"weight for {factor!r} out of range [0,1]: {w}")

    if abs(sum(weights.values()) - 1.0) > 1e-6:
        raise ValueError(f"weights must sum to 1.0, got {sum(weights.values())}")

    return data


def score_rubric(factor_scores: dict[str, float], weights: dict | None = None) -> ToolResult:
    """Composite = Σ(scoreᵢ · weightᵢ) · 10 → 0–100. Each factor score must be in [0, 10];
    unknown/missing factor keys are rejected. `weights` defaults to load_weights()."""
    if weights is None:
        weights = load_weights()
    w = weights["weights"]

    missing = w.keys() - factor_scores.keys()
    unknown = factor_scores.keys() - w.keys()
    if missing:
        raise ValueError(f"factor_scores missing: {sorted(missing)}")
    if unknown:
        raise ValueError(f"factor_scores has unknown factor(s): {sorted(unknown)}")

    for factor, s in factor_scores.items():
        if not 0.0 <= s <= 10.0:
            raise ValueError(f"score for {factor!r} out of range [0,10]: {s}")

    composite = sum(factor_scores[f] * w[f] for f in w) * 10.0
    return ToolResult(
        tool="score_rubric",
        tool_version=_VERSION,
        inputs={"factor_scores": factor_scores},
        value=composite,
        detail={"pos_factor": factor_scores["pos"], "weights_version": weights["version"]},
    )
