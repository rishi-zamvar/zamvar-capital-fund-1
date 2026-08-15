"""The research layer (CALL-02 + CALL-03): a bounded bull<->bear debate in REAL
context isolation, then a moderator that synthesizes a binary `DebateVerdict`.

Real isolation, not fake consensus: bull and bear are SEPARATE `run_structured`
invocations (fresh isolated sessions). Each side is handed only the shared
AnalystSignals + the opponent's prior FINAL argument text — never the opponent's
private `scratchpad`/transcript. The debate is bounded to `rounds` bull/bear
exchanges (no unbounded loop). A single moderator call on the strongest tier
(`opus`) then emits a binary verdict: direction + confidence anchored to a cited
base rate/analog, non-empty kill criteria, and BOTH sides' strongest point —
naming the losing side. No sizing/positioning here (that is Phase 5).

# ponytail: flat Python fan-out over the one run_structured seam. Argument is a
#           2-field internal schema (shareable case + private scratchpad); the
#           scratchpad is what makes isolation testable — it is never threaded.
"""

from pydantic import BaseModel, ConfigDict

from ..contracts import AnalystSignal, DebateVerdict
from . import MAX_ROUNDS
from .runtime import run_structured


class Argument(BaseModel):
    """One side's turn: the shareable case (threaded to the opponent) + private
    reasoning (`scratchpad`) that stays in this side's session and is NEVER
    passed across — that non-sharing is the real context isolation (CALL-02)."""

    model_config = ConfigDict(extra="forbid")
    argument: str
    evidence_refs: list[str] = []
    scratchpad: str = ""


def _evidence_context(signals: list[AnalystSignal]) -> str:
    """Flatten the analyst signals into the shared, citation-carrying context both
    sides reason over. Findings keep their evidence_ref so arguments stay grounded."""
    lines = []
    for s in signals:
        lines.append(f"[{s.dimension}] score={s.score:+.2f} confidence={s.confidence:.2f}")
        for f in s.key_findings:
            lines.append(f"  - {f.claim}  (cite: {f.evidence_ref})")
        for u in s.unknowns:
            lines.append(f"  - UNKNOWN: {u}")
    return "\n".join(lines)


def _side_prompt(role: str, evidence: str, prior: Argument | None) -> str:
    """Build one side's isolated prompt: shared signals + ONLY the opponent's prior
    FINAL argument text (never their scratchpad). `role` is BULL or BEAR."""
    stance = "positive" if role == "BULL" else "negative"
    rebuttal = (
        f"\nThe opposing side just argued:\n\"\"\"\n{prior.argument}\n\"\"\"\n"
        "Rebut its strongest claim head-on; do not strawman it.\n"
        if prior is not None
        else "\nYou open the debate.\n"
    )
    return f"""You are the {role} analyst in a bounded bull/bear debate over a biotech catalyst.
Argue the {stance} case for the readout, grounded ONLY in the shared signals below.

SHARED ANALYST SIGNALS
{evidence}
{rebuttal}
RULES
  - Cite every claim with the evidence_ref it rests on (tool:... or kb:...); no uncited assertions.
  - Put your final, shareable case in `argument` and your evidence_refs in `evidence_refs`.
  - Keep private reasoning/strategy in `scratchpad` — it stays with you and is not shown to the opponent.
"""


def _moderator_prompt(evidence: str, bull: Argument, bear: Argument) -> str:
    """Build the moderator prompt: synthesize the two final arguments into a binary,
    grounded, kill-criteria verdict that names BOTH sides' strongest point."""
    return f"""You are the DEBATE MODERATOR. Synthesize the bull and bear cases into a single
binary verdict on whether this catalyst reads POSITIVE or NEGATIVE. Judge the arguments on
their merits and the shared evidence — do not just count sides.

SHARED ANALYST SIGNALS
{evidence}

BULL FINAL CASE
{bull.argument}

BEAR FINAL CASE
{bear.argument}

REQUIREMENTS for the DebateVerdict:
  - direction: BINARY — exactly "positive" or "negative".
  - confidence: ANCHOR it to a cited base_rate or historical analog from the signals, and LOWER
    it for every material UNKNOWN that remains unresolved. Calibrated, not a vibe.
  - bull_strongest_point AND bear_strongest_point: name the single strongest surviving point on
    EACH side — including the losing side's best argument.
  - kill_criteria: at least one explicit falsification condition that would prove the verdict wrong.
  - evidence_refs: carry the cited refs the verdict rests on.
  - Emit NO sizing, entry, stop, take-profit, or position fields — this is a pure directional
    prediction; positioning happens downstream.
"""


async def run(signals: list[AnalystSignal], catalyst, rounds: int = MAX_ROUNDS,
              *, extra_context: str | None = None) -> DebateVerdict:
    """Run a bounded, context-isolated bull/bear debate then a moderator synthesis.

    Bull and bear each run in their own `run_structured` session per round (real
    isolation); only the opponent's prior FINAL argument text is threaded across.
    After `rounds` exchanges the moderator emits the validated binary DebateVerdict.
    Fully offline under test — every call routes through the run_structured seam.

    `extra_context` (RECON-02): a GP/DD re-trigger — a material fact the prior round left out.
    It is injected ONCE into the shared `evidence` string that BOTH side prompts AND the
    moderator prompt read, so the WHOLE debate re-reasons from the gap (it is a fact to weigh,
    NOT a conclusion to adopt). Default None = the `if extra_context:` block never runs =
    `evidence` is untouched = the prompts are byte-for-byte identical to the no-retrigger path.
    """
    evidence = _evidence_context(signals)
    if extra_context:
        evidence += ("\n\nMD RE-TRIGGER — new material fact the prior round did not address "
                     "(re-reason; do NOT assume a conclusion):\n" + extra_context)
    bull_arg: Argument | None = None
    bear_arg: Argument | None = None

    for _ in range(rounds):
        bull_arg = await run_structured(
            _side_prompt("BULL", evidence, prior=bear_arg), Argument, model="sonnet"
        )
        bear_arg = await run_structured(
            _side_prompt("BEAR", evidence, prior=bull_arg), Argument, model="sonnet"
        )

    return await run_structured(
        _moderator_prompt(evidence, bull_arg, bear_arg), DebateVerdict, model="opus"
    )
