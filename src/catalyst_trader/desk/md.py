"""desk/md.py — the MD/GP integration desk (the one point that sees all three workflows).

`cross_check` is a PURE, deterministic diff across the catalyst verdict / portfolio dossier /
diligence dossier plus two threaded values. NO LLM, NO conn/kb, NO arithmetic-by-agent: it
pre-computes exactly the inter-workflow inconsistencies the MD would otherwise hunt for, so
the MD call is a pure JUDGMENT call (agents interpret, the desk computes) and Plan 04's bounded
loop gets a deterministic `clean` boolean for convergence (the loop control is Python, never
an LLM decision).
"""

import json
import os
import re
import time

from pydantic import BaseModel, ConfigDict

from catalyst_trader import kb
from catalyst_trader.contracts import (
    DebateVerdict,
    DiligenceDossier,
    MDDecision,
    ReconciliationRound,
    RetriggerFlag,
    StrategyDossier,
    WeeklyFlag,
)
from catalyst_trader.desk import rollup
from catalyst_trader.desk.diligence import run_diligence
from catalyst_trader.desk.orchestrator import run_desk, run_portfolio
from catalyst_trader.desk.runtime import run_structured


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
    move_discrepancy_tol: float | None = None,
) -> dict:
    """Deterministic consistency diff across WF-1/2/3. No LLM, no arithmetic-by-agent, no conn/kb.

    catalyst_id: the authoritative catalyst id, threaded from reconcile's item catalyst — DebateVerdict
      carries NO catalyst id, so it MUST be passed explicitly (do NOT read it off the verdict).
    min_tradeable_size: the builder size floor, threaded from reconcile (kb.load_params) so the
      net-long-held-through check has a real data source with NO magic number and cross_check stays
      a pure function (no conn/kb inside).
    move_discrepancy_tol: the builder-field-vs-DD relative move gap tolerance, threaded from reconcile
      (kb.load_params()['field']). None = the check is DISABLED (default, so existing callers are
      byte-for-byte); the check also ABSTAINS when either move is absent (FF-05).
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

    # --- builder-field-vs-DD expected-move discrepancy (FF-05 loopback). Both moves must be present
    #     and the tol threaded in; abstains (no flag) when either is None or the check is disabled. ---
    fd = dossier.trade.expected_move_field
    builder_move = fd.get("point_estimate") if fd else None
    dd_move = dd.dd_expected_move
    move_discrepant = (
        move_discrepancy_tol is not None
        and builder_move is not None
        and dd_move not in (None, 0)
        and abs(builder_move - dd_move) / dd_move > move_discrepancy_tol
    )

    clean = (
        catalyst_id_consistent
        and direction_consistent
        and not dd_vs_portfolio
        and not uncovered_red_flags
        and not dd_vs_risk_residuals
        and not sizing_vs_survival
        and not move_discrepant
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
        "move_discrepant": move_discrepant,
        "expected_moves": {"builder": builder_move, "diligence": dd_move},
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

    dd_headlines = "\n".join(
        f"    {d['dimension']}: {h[0]}={h[1]} (source: {h[2]})"
        for d in dd.per_dimension if (h := rollup.headline(d))
    )

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
  HEADLINE NUMBERS (per dimension; absent = unknown):
{dd_headlines}

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


# --- deterministic loop control (agents-never-do-arithmetic) ---


def _classify(review: "MDReview", sheet: dict, dd: DiligenceDossier, seen_refs: set) -> tuple:
    """Deterministic disposition/convergence — NOT an LLM call. Returns (disposition, converged,
    diverged). converged = a Python `and` over cross_check['clean'] + (dd go OR the per-round MD
    boolean) + no-actioned-flags + review.satisfied. diverged (oscillation) = a RetriggerFlag whose
    evidence_ref was already seen. `cap_hit` is applied by the loop (it owns round_n)."""
    diverged = any(f.evidence_ref in seen_refs for f in review.flags)
    converged = (
        sheet["clean"]
        and (dd.verdict == "go" or review.satisfied)
        and not review.flags               # actioned re-triggers pending -> not converged (or only-refinements)
        and review.satisfied               # the ONE per-round MD boolean (NOT MDDecision.accepted_residuals)
    )
    if diverged:
        disposition = "diverged_pass"
    elif converged:
        disposition = "converged"
    else:
        disposition = "continue"
    return disposition, converged, diverged


def _criteria(sheet: dict, dd: DiligenceDossier, review: "MDReview") -> dict:
    """The per-round convergence criteria snapshot (each deterministic sub-check -> bool)."""
    return {
        "cross_check_clean": sheet["clean"],
        "dd_go": dd.verdict == "go",
        "md_satisfied": review.satisfied,
        "no_actioned_flags": not review.flags,
    }


def _unactioned(incoming_flags: list, actioned: list) -> list:
    """The incoming flags the MD did NOT convert into a RetriggerFlag this round (matched on
    evidence_ref). These go to ReconciliationRound.logged_flags — logged, never forced (RECON-08)."""
    actioned_refs = {f.evidence_ref for f in actioned}
    return [wf for wf in incoming_flags if wf.evidence_ref not in actioned_refs]


_SIZING_TOKENS = ("p_loss", "loss", "gap", "ruin", "size", "sizing")


def _workitem(verdict: DebateVerdict, item: dict, flags: list) -> dict:
    """Build the run_portfolio work-item {verdict, catalyst, entry, risk_inputs}. SIZING-GAP RULE:
    a sizing-related portfolio_build flag REFRESHES risk_inputs (p_loss/gap) from the flag's material
    fact BEFORE re-running — text extra_context alone won't move the deterministic size path.
    # ponytail: naive first-number extraction; upgrade to a typed sizing payload if flags carry structure.
    """
    ri = dict(item["risk_inputs"])
    entry = item["entry"]
    for f in flags:
        if f.target != "portfolio_build":
            continue
        text = f"{f.finding} {f.why_material}".lower()
        if not any(tok in text for tok in _SIZING_TOKENS):
            continue
        m = re.search(r"[-+]?\d*\.?\d+", f.finding)
        if not m:
            continue
        val = float(m.group())
        key = "p_loss" if ("loss" in text or "ruin" in text) else ("gap" if "gap" in text else "p_loss")
        ri[key] = val
    return {"verdict": verdict, "catalyst": item["catalyst"], "entry": entry, "risk_inputs": ri}


async def reconcile(conn, embed, item, *, max_rounds: int = 3,
                    blocker_path: str = ".monitor/blocker.json") -> MDDecision:
    """The bounded MD/GP reconciliation loop AND the general flag router (RECON-01..08).

    The SOLE MDDecision emitter and the one point consuming all three artifacts (verdict + dossier +
    dd). Incoming flags from ANY source (item['incoming_flags']) enter the round-1 review; the MD
    decides act-or-log. The MD's judgment is ONE run_structured(MDReview) per round + one terminal
    run_structured(MDDecision); convergence/oscillation/cascade/cap/act-or-log are deterministic.
    """
    verdict, dossier, dd = item["verdict"], item["dossier"], item["dd"]
    # Threaded cross_check inputs (loaded ONCE, pre-loop): the authoritative catalyst_id + the size
    # floor + the builder-field-vs-DD move tolerance. No magic number inside cross_check.
    catalyst_id = item["catalyst"]["catalyst_id"]
    _params = kb.load_params(conn, item["catalyst"]["catalyst_type"])
    min_tradeable_size = _params["builder"]["min_tradeable_size"]
    move_discrepancy_tol = _params["field"]["move_discrepancy_tol"]
    incoming_flags = list(item.get("incoming_flags", []))

    rounds: list[ReconciliationRound] = []
    seen_refs: set = set()
    packet = {"verdict": verdict, "dossier": dossier, "dd": dd}

    for round_n in range(1, max_rounds + 1):
        sheet = cross_check(verdict, dossier, dd, catalyst_id=catalyst_id,
                            min_tradeable_size=min_tradeable_size,
                            move_discrepancy_tol=move_discrepancy_tol)
        packet = {"verdict": verdict, "dossier": dossier, "dd": dd}
        review = await run_structured(_md_review_prompt(packet, sheet, incoming_flags),
                                      MDReview, model="opus")

        disposition, converged, diverged = _classify(review, sheet, dd, seen_refs)
        for f in review.flags:
            seen_refs.add(f.evidence_ref)
        if round_n == max_rounds and not converged and not diverged:
            disposition = "cap_hit"

        rounds.append(ReconciliationRound(
            round=round_n,
            md_flags=review.flags,
            logged_flags=_unactioned(incoming_flags, review.flags),
            response_delta=review.response_delta,
            convergence=_criteria(sheet, dd, review),
            cross_check=sheet,
            disposition=disposition,
        ))
        incoming_flags = []                    # consumed in round 1 — never re-fed

        if converged or diverged or round_n == max_rounds:
            break

        # --- cascade: re-trigger with a GAP (never the answer); DD always re-runs SEALED ---
        # ponytail: full cascade; gate WF-2 rerun on verdict-delta if token cost bites.
        if any(f.target == "catalyst_call" for f in review.flags):          # 1 -> 2 -> 3
            verdict = await run_desk(conn, item["catalyst"],
                                     extra_context=_gap_only(review.flags, "catalyst_call"))
            built = await run_portfolio(conn, embed, [_workitem(verdict, item, review.flags)],
                                        item["open_book"])
            dossier = built[0] if built else dossier
            dd = await run_diligence(conn, item["dd_input"], market_data=item["market_data"], embed=embed)
        elif any(f.target == "portfolio_build" for f in review.flags):      # 2 -> 3
            built = await run_portfolio(conn, embed, [_workitem(verdict, item, review.flags)],
                                        item["open_book"],
                                        extra_context=_gap_only(review.flags, "portfolio_build"))
            dossier = built[0] if built else dossier
            dd = await run_diligence(conn, item["dd_input"], market_data=item["market_data"], embed=embed)
        elif review.rerun_diligence:                                        # act-route to WF3 (sealed)
            dd = await run_diligence(conn, item["dd_input"], market_data=item["market_data"], embed=embed)

    decision = await run_structured(_md_decide_prompt(packet, rounds), MDDecision, model="opus")
    # Stamp the immutable record deterministically (audit integrity — the model never fabricates the log
    # or the preserved dissent; accepted_residuals stays the MD's decide-time judgment).
    decision = decision.model_copy(update={
        "round_log": rounds,
        "dissent_preserved": [*verdict.unresolved_dissent, dd.strongest_disconfirming_evidence],
    })
    # oscillation -> forced PASS (never leave PASS to the model); clear escalate-only fields.
    if rounds and rounds[-1].disposition == "diverged_pass" and decision.decision != "pass":
        decision = decision.model_copy(update={
            "decision": "pass", "blocker_class": None, "recommended_resolution": None,
        })
    # Escalate ONLY: surface the live decision-blocker banner (enter/pass never touch the file).
    if decision.decision == "escalate":
        _write_blocker(decision, catalyst_id, blocker_path)
    return decision


def _write_blocker(decision: MDDecision, packet_ref: str, path: str) -> None:
    """Write the live .monitor/blocker.json ATOMICALLY (tmp + os.replace) on escalate ONLY. Schema
    is the live {active,title,detail,options,since}; blocker_class rides in the title and the
    recommended_resolution (completed staff work) + a packet ref ride in the detail (RECON-07)."""
    payload = {
        "active": True,
        "title": f"MD escalation: {decision.blocker_class}",
        "detail": f"{decision.recommended_resolution}\n\nPacket: {packet_ref}",
        "options": ["confirm", "override"],
        "since": int(time.time()),
    }
    tmp = f"{path}.tmp"
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(tmp, "w") as fh:
        json.dump(payload, fh)
    os.replace(tmp, path)               # atomic swap — a reader never sees a half-written file


def lp_summary(decision: MDDecision) -> str:
    """GENERATE the LP relay FROM the decision record (RECON-05) — accepted_residuals + preserved
    dissent VERBATIM + the round count + a cap-hit flag. Source-quote-or-drop: nothing not traceable
    to the record."""
    cap_hit = bool(decision.round_log) and decision.round_log[-1].disposition == "cap_hit"
    lines = [
        f"MD decision: {decision.decision}",
        f"Reconciliation rounds: {len(decision.round_log)}",
    ]
    if cap_hit:
        lines.append("Reached the round cap without full convergence.")
    lines += [f"Accepted residual (priced): {r}" for r in decision.accepted_residuals]
    lines += [f"Preserved dissent: {d}" for d in decision.dissent_preserved]
    return "\n".join(lines)
