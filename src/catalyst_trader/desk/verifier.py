"""CALL-04 fact-check verifier: source-quote-or-drop, enforced before a
``DebateVerdict`` finalizes. No claim survives into the verdict without a
resolvable, supporting source — the reasoning-layer mirror of the KB's provenance
invariant.

Two-stage gate over the verdict's ``evidence_refs``:

  1. STRUCTURAL (deterministic, no LLM). Resolve every ref via ``desk.evidence.resolve``.
     Unresolvable -> drop. A ``kb:`` ref must ALSO pass the quote-substring gate
     (``quote_supported``) against its cited claim -> drop if unsupported. A ``tool:``
     ref (quant results AND KB ``analog_query`` / ``query_playbooks``, which return
     catalyst/playbook node ids not evidence_source ids) is resolved-by-construction:
     it passes structurally with no KB lookup and no quote gate.

  2. SEMANTIC (LLM, gated). For each structural survivor — the load-bearing refs that
     back the thesis/direction — ask ``run_structured`` (opus, the strongest tier for
     this judgment) whether the source actually supports the claim; drop the unsupported.

If no supporting ref survives, the verdict's thesis is unbacked -> raise
``VerdictUnsupportedError`` (finalize is blocked). Otherwise return the verdict with
``evidence_refs`` pruned to the survivors.
"""

from pydantic import BaseModel, ConfigDict

from catalyst_trader.contracts import DebateVerdict
from catalyst_trader.desk import evidence
from catalyst_trader.desk.runtime import run_structured


class VerdictUnsupportedError(Exception):
    """Source-quote-or-drop left the verdict with no supporting evidence — cannot finalize."""


class SupportCheck(BaseModel):
    """The LLM's per-claim semantic judgment (the gated half)."""

    model_config = ConfigDict(extra="forbid")
    supported: bool
    reason: str


def _claim_for(ref: str, signals) -> str | None:
    """The claim text cited under `ref` (from analyst key_findings), or None."""
    for sig in signals or []:
        for kf in sig.key_findings:
            if kf.evidence_ref == ref:
                return kf.claim
    return None


def _support_prompt(ref: str, claim: str, verdict: DebateVerdict) -> str:
    return (
        "Judge whether the cited source SUPPORTS the claim backing this catalyst verdict.\n"
        f"Verdict thesis: {verdict.thesis}\n"
        f"Direction: {verdict.direction}\n"
        f"Claim: {claim}\n"
        f"Cited evidence_ref: {ref}\n"
        "Answer supported=true only if the source substantively backs the claim."
    )


async def enforce(conn, verdict: DebateVerdict, *, signals=None) -> DebateVerdict:
    """Gate `verdict` on source-quote-or-drop; return it with evidence_refs pruned to the
    survivors, or raise VerdictUnsupportedError if no support survives."""
    # 1. STRUCTURAL — deterministic, no LLM.
    structural: list[str] = []
    for ref in verdict.evidence_refs:
        source = evidence.resolve(conn, ref)
        if source is None:
            continue  # unresolvable -> drop
        if ref.startswith("kb:"):
            claim = _claim_for(ref, signals)
            if not claim or not evidence.quote_supported(source, claim):
                continue  # cited quote not found in the source -> drop
        # tool: refs are resolved-by-construction: no KB lookup, no quote gate.
        structural.append(ref)

    # 2. SEMANTIC — LLM, spent only on the load-bearing structural survivors.
    survivors: list[str] = []
    for ref in structural:
        claim = _claim_for(ref, signals) or verdict.thesis
        check = await run_structured(_support_prompt(ref, claim, verdict), SupportCheck, model="opus")
        if check.supported:
            survivors.append(ref)

    # 3. FINALIZE GATE.
    if not survivors:
        raise VerdictUnsupportedError(
            "every evidence_ref failed source-quote-or-drop; verdict cannot finalize on unsupported evidence"
        )
    return verdict.model_copy(update={"evidence_refs": survivors})
