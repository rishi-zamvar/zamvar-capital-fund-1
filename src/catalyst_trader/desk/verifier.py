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

from catalyst_trader.contracts import DebateVerdict, EstimateVetting
from catalyst_trader.desk import evidence, rollup
from catalyst_trader.desk.runtime import run_structured


class VerdictUnsupportedError(Exception):
    """Source-quote-or-drop left the verdict with no supporting evidence — cannot finalize."""


class SupportCheck(BaseModel):
    """The LLM's per-claim semantic judgment (the gated half)."""

    model_config = ConfigDict(extra="forbid")
    supported: bool
    reason: str


def _claim_for(ref: str, signals) -> str | None:
    """The claim text cited under `ref` (from analyst key_findings), else — when `ref` is a
    report's headline *_source — the precise '<field>=<value>' it backs (07.9-03), or None."""
    for sig in signals or []:
        for kf in sig.key_findings:
            if kf.evidence_ref == ref:
                return kf.claim
    for sig in signals or []:
        h = rollup.headline(sig)
        if h and h[2] == ref:
            return f"{h[0]}={h[1]}"
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


# --- §7 estimate vetting gate: the estimate-layer mirror of enforce ---------
#
# Same two-stage shape as enforce(): STRUCTURAL (deterministic, no LLM) first —
# cite-or-drop every estimator INPUT (reusing evidence.resolve/quote_supported) +
# the deterministic consistency checks; then a single gated SEMANTIC judgment on
# analog comparability (the one check that genuinely needs the LLM). It audits the
# ASSUMPTIONS behind catalyst_move_estimate + adaptive_sl_tp_levels — it NEVER
# recomputes the money numbers (the deterministic quant tools own the math). A
# reject raises EstimateRejectedError (blocks finalize), mirroring
# VerdictUnsupportedError blocking an unsupported verdict.

# ponytail: two calibration knobs, not literals in the body. Widen if calibration
#           shows false rejects. The per-type down-move reference itself lives in the
#           cited, versioned fitted_params (params["estimator"]["default_down_move"]).
_DOWN_MOVE_BAND = (0.5, 2.0)   # sanity band = [0.5x, 2x] the type's cited default_down_move
_P_POSITIVE_TOL = 0.15         # |P(positive) - verdict-implied prob| tolerance


class EstimateRejectedError(Exception):
    """A vetted estimate was rejected — blocks finalize (mirrors VerdictUnsupportedError).
    Carries the assembled EstimateVetting for the audit trail (OPS-01)."""

    def __init__(self, vetting: EstimateVetting):
        self.vetting = vetting
        super().__init__("; ".join(vetting.reasons) or "estimate rejected")


class AnalogComparability(BaseModel):
    """The LLM's semantic judgment: are the KB analogs comparable to THIS catalyst?"""

    model_config = ConfigDict(extra="forbid")
    comparable: bool
    reasons: list[str]


def _comparability_prompt(catalyst_type: str, analog_refs: list[str], verdict: DebateVerdict) -> str:
    return (
        "Judge whether the KB analog set feeding this catalyst-move estimate is COMPARABLE to the "
        "current catalyst — same catalyst type, similar phase / indication / drug-class. Off-type or "
        "cherry-picked analogs make the estimated gap distribution unreliable and must be rejected.\n"
        f"Current catalyst type: {catalyst_type}\n"
        f"Verdict thesis: {verdict.thesis}\n"
        f"Analog input refs: {', '.join(analog_refs)}\n"
        "Answer comparable=true only if the analogs are genuinely representative of THIS catalyst."
    )


def _is_analog(item: dict) -> bool:
    ref = item.get("ref") or ""
    return item.get("input") == "analogs" or "analog_query" in ref


async def enforce_estimate(
    conn,
    estimate_inputs: list[dict],
    *,
    verdict: DebateVerdict,
    params: dict,
    holds_through_catalyst: bool,
    sl_advisory: bool,
    down_move: float,
    catalyst_type: str,
    n_analogs: int,
) -> EstimateVetting:
    """Audit the ASSUMPTIONS behind catalyst_move_estimate + adaptive_sl_tp_levels before the
    builder consumes them — garbage-in caught before it becomes a position. NEVER recomputes money
    numbers. Raises EstimateRejectedError on reject (blocks finalize), mirroring enforce()."""
    input_refs: list[str] = []
    dropped_inputs: list[str] = []
    reasons: list[str] = []
    analog_refs: list[str] = []
    failed = False

    # 1. STRUCTURAL — cite-or-drop every input (reuse evidence.resolve/quote_supported).
    for item in estimate_inputs:
        ref = item.get("ref")
        src = evidence.resolve(conn, ref) if ref else None
        if src is None:
            dropped_inputs.append(ref if ref else f"<uncited:{item.get('input')}>")
            reasons.append(f"input {item.get('input')!r} dropped: ref {ref!r} unresolvable (cite-or-drop)")
            failed = True
            continue
        if isinstance(ref, str) and ref.startswith("kb:"):
            claim = item.get("claim") or str(item.get("value"))
            if not evidence.quote_supported(src, claim):
                dropped_inputs.append(ref)
                reasons.append(f"input {item.get('input')!r} dropped: claim not supported by cited source quote")
                failed = True
                continue
        # tool: refs are resolved-by-construction: no quote gate.
        input_refs.append(ref)
        if _is_analog(item):
            analog_refs.append(ref)

    # 2. DETERMINISTIC CONSISTENCY (cheap comparisons, no LLM).
    p_pos = next((i.get("value") for i in estimate_inputs if i.get("input") == "p_positive"), None)
    if p_pos is not None:
        implied = verdict.confidence if verdict.direction == "positive" else 1.0 - verdict.confidence
        if (verdict.direction == "positive") != (p_pos >= 0.5):
            reasons.append(
                f"P(positive)={p_pos} contradicts the Phase-4 {verdict.direction} verdict direction"
            )
            failed = True
        elif abs(p_pos - implied) > _P_POSITIVE_TOL:
            reasons.append(
                f"P(positive)={p_pos} outside tolerance of the verdict confidence {verdict.confidence}"
            )
            failed = True

    ref_move = params["estimator"]["default_down_move"]
    lo, hi = ref_move * _DOWN_MOVE_BAND[0], ref_move * _DOWN_MOVE_BAND[1]
    if not (lo <= down_move <= hi):
        reasons.append(
            f"estimated down-move {down_move} outside the {catalyst_type} sanity band "
            f"[{lo:.3f},{hi:.3f}] (relative to the cited default_down_move {ref_move})"
        )
        failed = True

    if holds_through_catalyst and not sl_advisory:
        reasons.append(
            "hold-through leg with a NON-advisory SL — the stop is gap-exposed and fictitious (reject)"
        )
        failed = True

    # 3. COLD-START — a flag, not an auto-reject (widen uncertainty / shrink-to-base-rate).
    uncertainty_widened = n_analogs < params["estimator"]["min_analogs"]
    if uncertainty_widened:
        reasons.append(
            f"cold-start: only {n_analogs} analogs (< {params['estimator']['min_analogs']}) — "
            "uncertainty widened / shrink-to-base-rate, not overclaimed"
        )

    if failed:
        vetting = EstimateVetting(
            verdict="reject", input_refs=input_refs, dropped_inputs=dropped_inputs,
            reasons=reasons, uncertainty_widened=uncertainty_widened,
        )
        raise EstimateRejectedError(vetting)

    # 4. SEMANTIC — analog comparability, spent only on structural survivors that carry analogs.
    if analog_refs:
        check = await run_structured(
            _comparability_prompt(catalyst_type, analog_refs, verdict),
            AnalogComparability, model="opus",
        )
        if not check.comparable:
            reasons.extend(check.reasons)
            vetting = EstimateVetting(
                verdict="reject", input_refs=input_refs, dropped_inputs=dropped_inputs,
                reasons=reasons, uncertainty_widened=uncertainty_widened,
            )
            raise EstimateRejectedError(vetting)

    return EstimateVetting(
        verdict="endorse", input_refs=input_refs, dropped_inputs=dropped_inputs,
        reasons=reasons, uncertainty_widened=uncertainty_widened,
    )
