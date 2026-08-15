"""desk/md.py — the MD/GP integration desk (the one point that sees all three workflows).

`cross_check` is a PURE, deterministic diff across the catalyst verdict / portfolio dossier /
diligence dossier plus two threaded values. NO LLM, NO conn/kb, NO arithmetic-by-agent: it
pre-computes exactly the inter-workflow inconsistencies the MD would otherwise hunt for, so
the MD call is a pure JUDGMENT call (agents interpret, the desk computes) and Plan 04's bounded
loop gets a deterministic `clean` boolean for convergence (the loop control is Python, never
an LLM decision).
"""

import json

from pydantic import BaseModel, ConfigDict

from catalyst_trader.contracts import (
    DebateVerdict,
    DiligenceDossier,
    RetriggerFlag,
    StrategyDossier,
    WeeklyFlag,
)


def _answered(item: str, coverage: list[str]) -> bool:
    """True iff some coverage string MENTIONS `item` (case/space-normalized substring).
    A red_flag/residual is 'answered' only when a kill criterion / priced residual / hedge
    mechanism actually names it — deterministic, the MD interprets the unanswered remainder."""
    n = " ".join(item.lower().split())
    return any(n in " ".join(c.lower().split()) for c in coverage if c)


def cross_check(
    verdict: DebateVerdict,
    dossier: StrategyDossier,
    dd: DiligenceDossier,
    *,
    catalyst_id: str,
    min_tradeable_size: float,
) -> dict:
    """Deterministic consistency diff across WF-1/2/3. No LLM, no arithmetic-by-agent, no conn/kb.

    catalyst_id: the authoritative catalyst id, threaded from reconcile's item catalyst — DebateVerdict
      carries NO catalyst id, so it MUST be passed explicitly (do NOT read it off the verdict).
    min_tradeable_size: the builder size floor, threaded from reconcile (kb.load_params) so the
      net-long-held-through check has a real data source with NO magic number and cross_check stays
      a pure function (no conn/kb inside).
    Returns structured booleans + the offending items; the MD interprets the flags.
    """
    # --- catalyst_id consistency: the verdict has none, so the threaded id is authoritative;
    #     compare it against the trade id and each DD per-dimension id (§4.1 escalation-worthy). ---
    trade_id = dossier.trade.catalyst_id
    dd_ids = sorted({d["catalyst_id"] for d in dd.per_dimension if d.get("catalyst_id")})
    catalyst_id_consistent = len({catalyst_id, trade_id, *dd_ids}) <= 1

    # --- DD no_go while the portfolio promotes: the core reconciliation tension ---
    dd_vs_portfolio = dd.verdict == "no_go" and dossier.decision == "promote"

    # --- direction drift between the debate verdict and the built trade (regression guard) ---
    direction_consistent = verdict.direction == dossier.trade.direction

    # --- uncovered DD red_flags: not answered by any kill criterion / priced residual (dissent_log)
    #     / hedge mechanism coverage (RECON-04). ---
    coverage = [*dossier.kill_criteria, *dossier.dissent_log]
    if dossier.trade.hedge is not None:
        coverage.append(dossier.trade.hedge.mechanism)
    uncovered_red_flags = [f for f in dd.red_flags if not _answered(f, coverage)]

    # --- DD residuals absent from the dossier's residual accounting (dissent_log surface) ---
    dd_vs_risk_residuals = [
        r for r in dd.residual_risks if not _answered(r, dossier.dissent_log)
    ]

    # --- net-long uncovered exposure held THROUGH the binary: the coverage/net-long/hold-through
    #     TRIPLE (RiskAssessment.ruin_at_size is NOT on the dossier). The 'tiny' floor is the
    #     threaded min_tradeable_size param — no magic number, no conn/kb inside. ---
    sizing_vs_survival = (
        dossier.which_risk_covered == "none"
        and dossier.trade.size_pct > min_tradeable_size
        and dossier.trade.holds_through_catalyst
    )

    clean = (
        catalyst_id_consistent
        and direction_consistent
        and not dd_vs_portfolio
        and not uncovered_red_flags
        and not dd_vs_risk_residuals
        and not sizing_vs_survival
    )

    return {
        "clean": clean,
        "catalyst_id_consistent": catalyst_id_consistent,
        "catalyst_ids": {"threaded": catalyst_id, "trade": trade_id, "diligence": dd_ids},
        "dd_vs_portfolio": dd_vs_portfolio,
        "direction_consistent": direction_consistent,
        "directions": {"verdict": verdict.direction, "trade": dossier.trade.direction},
        "uncovered_red_flags": uncovered_red_flags,
        "dd_vs_risk_residuals": dd_vs_risk_residuals,
        "sizing_vs_survival": sizing_vs_survival,
    }


# ============================================================================
# reconcile — the bounded MD/GP loop + general flag router (RECON-01..08)
#
# The MD's JUDGMENT is exactly one run_structured(MDReview) per round + one terminal
# run_structured(MDDecision). EVERYTHING else — cross_check, convergence, oscillation,
# cascade, act-or-log, the round cap — is deterministic Python (agents-never-do-arithmetic).
# ============================================================================


class MDReview(BaseModel):
    """The MD's per-round judgment (internal — NOT a public contract). extra='forbid'.

    flags: actioned re-triggers the MD raises this round (WF1/WF2), gap-not-answer.
    rerun_diligence: the act-route to WF3 — a fresh SEALED DD pass (no gap, the firewall).
    satisfied: the ONE per-round MD boolean the deterministic convergence `and` consumes.
    """

    model_config = ConfigDict(extra="forbid")
    flags: list[RetriggerFlag] = []
    rerun_diligence: bool = False
    satisfied: bool
    response_delta: str


def _gap_only(flags: list[RetriggerFlag], target: str | None = None) -> str:
    """Format re-trigger flags (optionally filtered by target) as a GAP string — the code-level
    gap-not-answer firewall (RECON-06). The input is RetriggerFlag, which structurally carries NO
    answer-shaped field, so the produced string cannot contain a verdict/direction/size."""
    picked = [f for f in flags if target is None or f.target == target]
    return "\n".join(
        f"DD/flag surfaced: {f.finding} (evidence_ref {f.evidence_ref}). "
        f"Material because: {f.why_material}"
        for f in picked
    )


def _md_review_prompt(packet: dict, sheet: dict, incoming_flags: list[WeeklyFlag]) -> str:
    """Assemble the MD's per-round review prompt from the decision packet (the three workflow
    artifacts) + the deterministic cross_check sheet + any incoming flags to route (RECON-08).
    Mirrors diligence.build_dimension_prompt's conditional-block assembly; aggregates existing
    contracts by REFERENCE (does not restate their logic)."""
    verdict: DebateVerdict = packet["verdict"]
    dossier: StrategyDossier = packet["dossier"]
    dd: DiligenceDossier = packet["dd"]

    flags_block = ""
    if incoming_flags:
        flags_block = "\nINCOMING FLAGS TO ROUTE (act-or-log — you decide, RECON-08):\n" + "\n".join(
            f"  - [{f.flag_type}] {f.ticker}: {f.finding} (evidence_ref {f.evidence_ref}) — {f.why_material}"
            for f in incoming_flags
        ) + "\n"

    return f"""You are the MD/GP. Reconcile the catalyst call, the portfolio build, and the independent
diligence into ONE view. Raise a RetriggerFlag ONLY for a material gap (the gap, never the answer);
route or LOG each incoming flag. Set satisfied=True only if there is no material open issue.

CATALYST CALL (Workflow-1)
  thesis:     {verdict.thesis}
  direction:  {verdict.direction}  confidence: {verdict.confidence}
  kill:       {verdict.kill_criteria}
  dissent:    {verdict.unresolved_dissent}

PORTFOLIO BUILD (Workflow-2)
  decision:   {dossier.decision}   which_risk_covered: {dossier.which_risk_covered}
  summary:    {dossier.verdict_summary}
  memo:       {dossier.position_memo}
  pre-mortem: {dossier.pre_mortem}
  dissent:    {dossier.dissent_log}

DILIGENCE (Workflow-3, sealed firewall)
  verdict:    {dd.verdict}
  red_flags:  {dd.red_flags}
  residuals:  {dd.residual_risks}
  strongest disconfirming: {dd.strongest_disconfirming_evidence}

DETERMINISTIC CROSS-CHECK SHEET (already computed — interpret, do not recompute):
{json.dumps(sheet, indent=2)}
{flags_block}"""


def _md_decide_prompt(packet: dict, rounds: list) -> str:
    """Assemble the terminal decision prompt from the packet + the immutable per-round log. The MD
    emits ONE MDDecision (enter/pass/escalate) + accepted_residuals priced at DECIDE-time."""
    verdict: DebateVerdict = packet["verdict"]
    dd: DiligenceDossier = packet["dd"]
    log = "\n".join(
        f"  round {r.round}: disposition={r.disposition}; delta={r.response_delta}; "
        f"convergence={r.convergence}"
        for r in rounds
    )
    return f"""You are the MD/GP. The bounded reconciliation loop is complete. Emit ONE terminal
decision (enter / pass / escalate). Price each accepted residual (how size/kill/hedge covers it).
Escalate ONLY on a genuine blocker you cannot resolve (completed staff work required).

FINAL CATALYST DIRECTION: {verdict.direction}   FINAL DD VERDICT: {dd.verdict}
UNRESOLVED DISSENT (preserve verbatim): {verdict.unresolved_dissent}
STRONGEST DISCONFIRMING (preserve verbatim): {dd.strongest_disconfirming_evidence}

ROUND LOG:
{log}
"""
