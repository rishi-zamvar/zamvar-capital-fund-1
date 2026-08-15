"""desk/builder.py (PORT-02 + HEDGE-01/04): DebateVerdict -> TradeProposal, the single-leg
estimated-move construction engine (the no-hedge case is the DEFAULT, and it is ENGINEERED —
not "size tiny and pray").

The builder ORCHESTRATES + INTERPRETS; the money math lives in the quant/risk tools (agents
never do arithmetic):
  - the payoff distribution is `quant.catalyst_move_estimate` (param-driven, cited),
  - the leg is sized on the ESTIMATED down-move via `risk.size_for_survival` (not a blanket 0.70),
  - the hold-through-vs-exit decision is `quant.hold_vs_exit` — expected-LOG-growth at the
    survival-constrained size f (Kelly-consistent), NEVER raw EV (BLOCKER-2),
  - SL/TP is `quant.adaptive_sl_tp_levels`, ADVISORY whenever the leg holds through the catalyst
    (a stop cannot fill inside an overnight gap),
  - the estimate is VETTED via `verifier.enforce_estimate` before finalize (a reject blocks it).

A candidate inverse (-1) peer is surfaced for the Risk committee to VALIDATE — the builder never
fabricates a validated hedge (TradeProposal.hedge is None out of the builder). Every builder
threshold is a loaded param; a missing builder param RAISES (no literal in the builder body).

# ponytail: flat async fn over the one run_structured seam, same shape as debate.py/risk.py — no
#           base classes, no config objects. The only narrative the LLM authors is pair_rationale;
#           every trade NUMBER is a deterministic tool output it can never inject.
"""

from pydantic import BaseModel, ConfigDict

from .. import kb
from ..contracts import EstimateVetting, TradeProposal
from ..quant.events import catalyst_move_estimate, hold_vs_exit
from ..quant.sizing import adaptive_sl_tp_levels
from . import evidence, risk
from .analysts import _get
from .runtime import run_structured
from .verifier import EstimateRejectedError, enforce_estimate


class BuilderNarrative(BaseModel):
    """The one narrative the LLM authors — the pair rationale. Every trade NUMBER is a
    deterministic tool output that OVERWRITES anything the model emits."""

    model_config = ConfigDict(extra="forbid")
    pair_rationale: str


def _ctype(catalyst) -> str:
    """The catalyst type as its plain string value (enum or str in -> str out), so it keys
    load_params / analog filters / enforce_estimate consistently."""
    ct = _get(catalyst, "catalyst_type")
    return getattr(ct, "value", ct)


def _candidate_peer(conn, target) -> str | None:
    """Top inverse (-1) peer ticker for the Risk committee to VALIDATE, or None. A +1 co-move
    peer is a conviction long, NEVER an idiosyncratic-hedge candidate (HEDGE-01) — filtered out.
    The builder only SURFACES the candidate; risk.validate_hedge decides if it holds THIS catalyst.

    # ponytail: top candidate only — the KB weight already ranks them; risk re-derives it anyway.
    """
    inverse = [p for p in kb.hedge_peers(conn, target) if p["payoff_direction"] == -1]
    return inverse[0]["peer"] if inverse else None


def _analog_context(verdict, target, ctype) -> str:
    return f"{ctype} catalyst for {target}: {verdict.thesis}"


def _narrative_prompt(verdict, target, candidate, ctype, extra="") -> str:
    return f"""You are the TRADE BUILDER authoring the pair rationale for a single-leg biotech
catalyst trade. Explain the leg and the (candidate) hedge in prose — emit NO numbers, sizes,
stops, or targets (those are computed deterministically and will overwrite anything you write).

CATALYST         {target} — {ctype}
DIRECTION        {verdict.direction} (confidence {verdict.confidence:.2f})
THESIS           {verdict.thesis}
CANDIDATE HEDGE  {candidate or 'NONE (honest fallback — size-tiny / exit-before-event)'}
KILL CRITERIA    {'; '.join(verdict.kill_criteria)}
{extra}
Write pair_rationale: why this leg, the candidate inverse peer (pending Risk re-validation this
catalyst), and the kill criteria that would falsify the thesis.
"""


async def build(conn, embed, verdict, catalyst, *, entry: float) -> TradeProposal | None:
    """Turn a `DebateVerdict` into a `TradeProposal` (or None = no trade this week, HEDGE-04).

    `entry` is the current leg price (the caller — 05-07 — supplies it; the builder can't invent a
    price). Fully offline under test: the narrative + comparability calls route through run_structured.
    """
    target = _get(catalyst, "ticker")
    catalyst_id = _get(catalyst, "catalyst_id")
    ctype = _ctype(catalyst)
    exit_by_date = _get(catalyst, "event_date_end") or _get(catalyst, "event_date")

    analogs = kb.analog_query(conn, embed, _analog_context(verdict, target, ctype),
                              filters={"type": ctype}, k=5)
    candidate = _candidate_peer(conn, target)

    # Estimate-driven fields (entry sizing, hold-through, SL/TP, estimate_vetting) are filled in
    # Task 2 — placeholder-but-valid defaults keep the skeleton TradeProposal valid for now.
    narrative = await run_structured(
        _narrative_prompt(verdict, target, candidate, ctype), BuilderNarrative, model="sonnet"
    )

    return TradeProposal(
        target_long=target,
        hedge=None,  # the builder NEVER validates — Risk owns validation (05-07 reconciles the object)
        pair_rationale=narrative.pair_rationale,
        entry=entry,
        exit_by_date=exit_by_date,
        stop_loss=entry, take_profit=entry,          # placeholder — Task 2: adaptive_sl_tp_levels
        size_pct=0.0,                                 # placeholder — Task 2: size_for_survival
        expected_return_pct=0.0,                      # placeholder — Task 2: est.value (display only)
        kb_analogs=[str(a["node_id"]) for a in analogs],
        holds_through_catalyst=False,                 # placeholder — Task 2: hold_vs_exit
        catalyst_id=catalyst_id,
        direction=verdict.direction,
        estimate_vetting=EstimateVetting(verdict="endorse", input_refs=[], reasons=[]),  # placeholder
        sl_advisory=False,                            # placeholder — Task 2: mirrors sl_tp advisory
    )
