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


def sample_catalysts(items: list[dict], *, n: int, strategy: str = "stratified", seed: int = 0) -> dict:
    """Deterministically pick ``n`` work-items, LOGGING every dropped one (never a silent [:N] cap).

    ``n >= len(items)`` -> all sampled, none dropped. Otherwise, by ``strategy``:
      - "stratified": round-robin across catalyst_type buckets (seeded shuffle within each) so the
        sample keeps the type mix rather than over-weighting whichever type happens to sort first;
      - "random": a single seeded shuffle, then the first n.

    Returns ``{"sampled": [...], "dropped": [...], "reason": str}`` — the drop-list is the sanctioned
    mechanism; a silent slice would hide which catalysts the baseline never saw.

    # ponytail: stratified is a naive equal round-robin over catalyst_type; swap in a proportional
    #           allocator if the type mix ever needs weighting — the drop-list contract is unchanged.
    """
    items = list(items)
    if n >= len(items):
        return {"sampled": items, "dropped": [],
                "reason": f"n={n} >= available {len(items)}: full replay, none dropped"}

    rng = random.Random(seed)
    idx = list(range(len(items)))
    if strategy == "random":
        rng.shuffle(idx)
        sel = idx[:n]  # NOT a silent cap: the complement is computed + logged as `dropped` below
    elif strategy == "stratified":
        buckets: dict = {}
        for i in idx:
            buckets.setdefault(items[i]["catalyst"]["catalyst_type"], []).append(i)
        for b in buckets.values():
            rng.shuffle(b)
        sel = []
        keys = sorted(buckets)  # deterministic bucket order
        while len(sel) < n:
            progressed = False
            for k in keys:
                if buckets[k]:
                    sel.append(buckets[k].pop(0))
                    progressed = True
                    if len(sel) == n:
                        break
            if not progressed:  # safety: cannot happen since n < total, but never spin forever
                break
    else:
        raise ValueError(f"unknown sampling strategy {strategy!r}; use 'stratified' or 'random'")

    sel_set = set(sel)
    sampled = [items[i] for i in sel]
    dropped = [items[i] for i in idx if i not in sel_set]
    return {"sampled": sampled, "dropped": dropped,
            "reason": (f"{strategy} sample n={n} of {len(items)} (seed={seed}); "
                       f"{len(dropped)} catalysts logged as dropped (not silently capped)")}


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


def _log_entry(item: dict) -> dict:
    """The audit-log shape for one sampled/dropped catalyst (its identity + the week it was seen)."""
    return {**item["catalyst"], "as_of": item["as_of"]}


async def run_layer_b(
    conn, embed, *, start: str, end: str, latency_cfg: dict | None = None,
    n: int | None = None, strategy: str = "stratified", seed: int = 0,
) -> LayerBBatch:
    """Replay the REAL desk pipeline on the point-in-time historical catalysts behind the web-free +
    point-in-time + outcome-blind guardrails, labeling every result biased_optimistic=True.

    Offline via the mocked run_structured seam. ``n`` bounds the SAMPLE (Layer B is expensive — it
    invokes the LLM desk per catalyst); ``n=None`` replays everything. Whatever is not sampled is
    recorded in the SampleLog drop-list with a reason — NEVER a silent cap.
    """
    _assert_web_free()
    items = _flatten(build_event_set(conn, start=start, end=end, latency_cfg=latency_cfg))
    sample = sample_catalysts(items, n=(len(items) if n is None else n), strategy=strategy, seed=seed)
    results = [await _replay_one(conn, it) for it in sample["sampled"]]
    log = SampleLog(
        sampled=[_log_entry(it) for it in sample["sampled"]],
        dropped=[_log_entry(it) for it in sample["dropped"]],
        reason=sample["reason"],
    )
    return LayerBBatch(results=results, sample_log=log)
