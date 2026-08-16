"""backtest/layerb.py — Layer B: the guarded AGENTIC replay (BACK-03), labeled biased_optimistic.

Layer B runs the REAL desk pipeline (``run_desk``) on historical catalysts behind look-ahead
guardrails, then labels every result ``biased_optimistic=True``. Unlike Layer A (07-04, the
trustworthy NO-LLM baseline), Layer B DOES invoke the LLM desk — so it is honest about the fact
that the model's parametric memory leaks past outcomes EVEN behind a clean prompt and a web-free
seam. That label is a STRUCTURAL contract field, not a comment: Layer B is never the number you
trust, only the (optimistic) agentic comparison against the mechanical baseline and the forward
paper month.

The three look-ahead guardrails (research §BACK-03 — the desk is already web-free, a free seam):
  1. web-free      — the desk ALLOWED_TOOLS is asserted DISJOINT from the web denylist BEFORE the
                     run (reuses desk.guardrails); a smuggled web/fetch tool refuses the replay.
  2. point-in-time — catalysts come from build_event_set(latency_cfg=...) (07-02), so a catalyst
                     verified AFTER the simulated week is never replayed; the store's ``bars_asof``
                     / ``universe_as_of`` <= as_of guards keep the desk's quant reads point-in-time.
  3. outcome-blind — each catalyst is projected onto OutcomeBlindCatalyst (extra="forbid", the same
                     firewall technique as desk.diligence.DiligenceInput) BEFORE run_desk, so a
                     leaked realized-outcome field is a ValidationError, never a prompt leak.

Fully offline in tests: desk.runtime.run_structured is monkeypatched across the desk modules
(zero live API).
"""

from __future__ import annotations

import random

from pydantic import BaseModel, ConfigDict

from ..desk import guardrails
from ..desk.orchestrator import run_desk
from .events import build_event_set


# ============================== contracts =============================================


class OutcomeBlindCatalyst(BaseModel):
    """The historical catalyst PROJECTED to exactly the fields the desk may see before it decides.

    ``extra="forbid"`` is the look-ahead firewall (mirrors desk.diligence.DiligenceInput): the
    contract carries NO realized-outcome field, so projecting a catalyst that smuggles one
    (``realized_direction`` / ``realized_ret`` / ``outcome`` / ...) raises a ValidationError rather
    than leaking the answer into the analyst prompt.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    ticker: str
    catalyst_type: str
    event_date: str
    company_name: str | None = None
    catalyst_id: str | None = None


class LayerBResult(BaseModel):
    """One replayed catalyst's desk verdict + the HONEST biased_optimistic label (a real field)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ticker: str
    as_of: str
    event_date: str
    direction: str
    confidence: float
    biased_optimistic: bool = True  # STRUCTURAL: LLM memory leaks past outcomes — never trust this alone


class SampleLog(BaseModel):
    """What Layer B actually replayed vs skipped and why — never a silent truncation (Task 2)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    sampled: list[dict]
    dropped: list[dict]
    reason: str


class LayerBBatch(BaseModel):
    """run_layer_b's return: the labeled results + the sampling audit trail."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    results: list[LayerBResult]
    sample_log: SampleLog


# ============================== run_layer_b ===========================================


def _flatten(records: list[dict]) -> list[dict]:
    """One work-item per (as_of, catalyst) pair across the point-in-time event set."""
    return [
        {
            "as_of": rec["as_of"],
            "event_date": cat["event_date"],
            "catalyst": {
                "ticker": cat["ticker"],
                "catalyst_type": cat["catalyst_type"],
                "event_date": cat["event_date"],
            },
        }
        for rec in records
        for cat in rec["catalysts"]
    ]


def _assert_web_free() -> None:
    """Guardrail: the desk ALLOWED_TOOLS must be web-free before any replay. Reuses the shipped
    OPS-03 check (reads ALLOWED_TOOLS live, so a monkeypatched web tool is caught)."""
    if not guardrails._no_scrape_to_order():
        raise guardrails.GuardrailViolation(
            "Layer B refused: the desk ALLOWED_TOOLS is not web-free (look-ahead guardrail)"
        )


async def _replay_one(conn, item: dict) -> LayerBResult:
    """Project the catalyst outcome-blind, run the REAL desk, label it biased_optimistic."""
    cat = item["catalyst"]
    blind = OutcomeBlindCatalyst(
        ticker=cat["ticker"], catalyst_type=cat["catalyst_type"], event_date=cat["event_date"],
        company_name=cat.get("company_name"), catalyst_id=cat.get("catalyst_id"),
    )
    verdict = await run_desk(conn, blind.model_dump())
    return LayerBResult(
        ticker=cat["ticker"], as_of=item["as_of"], event_date=item["event_date"],
        direction=verdict.direction, confidence=verdict.confidence,
    )


async def run_layer_b(conn, embed, *, start: str, end: str, latency_cfg: dict | None = None) -> LayerBBatch:
    """Replay the REAL desk pipeline on the point-in-time historical catalysts behind the web-free +
    point-in-time + outcome-blind guardrails, labeling every result biased_optimistic=True.

    Offline via the mocked run_structured seam. Sampling (a logged drop-list) is added in Task 2;
    here every visible catalyst is replayed and recorded in the SampleLog as a full replay.
    """
    _assert_web_free()
    items = _flatten(build_event_set(conn, start=start, end=end, latency_cfg=latency_cfg))
    results = [await _replay_one(conn, it) for it in items]
    log = SampleLog(
        sampled=[it["catalyst"] for it in items], dropped=[],
        reason=f"full replay of all {len(items)} point-in-time catalysts (no sampling)",
    )
    return LayerBBatch(results=results, sample_log=log)
