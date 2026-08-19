"""desk/exit_plan.py (Tier-3 Task A / Task 1): the DETERMINISTIC Exit Plan authored at entry.

No agent in the hot path — the judgment was spent at entry (the debate + the football field).
This module is PURE arithmetic over the numbers the builder ALREADY produced (est up/down move,
p_positive, hold-vs-exit verdict, SL/TP, exit_by_date, kill_criteria, candidate hedge): it emits
the band + the pre-committed scenario table + the typed thesis-invalidation + the hard TIME
barrier + the EV-flip guard inputs. The intraweek reflex (Task 2) and the exit review read it.

Thresholds live in a module-level EXIT_PARAMS dict (precedent: diligence.DILIGENCE_PARAMS) —
direct subscript, a missing key RAISES (no literal fallback in the body, CLAUDE.md no-magic-
numbers rule). This is NOT the kb.load_params fitted-param seam: the fitted CSV is catalyst-shaped
and carries no exit knobs.

# ponytail: flat pure functions over what the desk already computed — no conn, no run_structured,
#           no config objects. The agentic OFF-MAP exit brain is Task B (deferred); this is the core.
"""

from __future__ import annotations

from ..contracts import EvFlipGuard, ExitPlan, ScenarioRow, ThesisInvalidation

# Module-level thresholds — the single, seed-proof exit-knob source (a missing key RAISES).
EXIT_PARAMS = {
    "mixed_prob": 0.15,          # conditional carve-out: a muddled/partial outcome (exit half to de-risk)
    "delay_prob": 0.10,          # conditional carve-out: event slips / IV crush -> weekly-flat, exit
    "ev_flip_threshold": 0.0,    # remaining_upside*p - downside*(1-p) < this => flip (trim/exit)
    "off_map_mult": 1.5,         # a move > max(up,down)*this is off the scenario map (Task 2 reflex seam)
}


def ev_flip_guard(remaining_upside: float, p: float, downside: float, threshold: float) -> bool:
    """True when the remaining expected value has flipped below `threshold` -> trim or exit.

    Pure: remaining_upside*p - downside*(1-p) < threshold. The reflex re-evaluates this at the
    CURRENT price (remaining_upside shrinks as price rises into the target), so a trade whose
    thesis has already paid out its edge is exited rather than held for the last, negative-EV inch.
    """
    return remaining_upside * p - downside * (1 - p) < threshold


def build_exit_plan(*, entry: float, up_move: float, down_move: float, p_positive: float,
                    holds_through: bool, stop: float, target: float, exit_by_date: str,
                    kill_criteria: list[str], direction: str, has_hedge: bool) -> ExitPlan:
    """Author the deterministic ExitPlan from the desk's football-field/verdict numbers.

    PURE — no conn, no LLM, no I/O. Same inputs -> byte-for-byte identical plan (the builder's
    out_default == out_explicit equality rests on this).

    Args mirror what builder.build() already holds before its TradeProposal return: `entry` (arg),
    `up_move`/`down_move` (est.detail), `p_positive` (verdict), `holds_through` (hold_vs_exit),
    `stop`/`target` (adaptive_sl_tp_levels), `exit_by_date` (catalyst window), `kill_criteria` +
    `direction` (verdict), `has_hedge` (candidate inverse peer is not None).
    """
    approval_target = entry * (1 + up_move)
    rejection_target = entry * (1 - down_move)
    band = (rejection_target, approval_target)  # the no-stop zone: down-edge .. up-edge

    # Pre-committed, deterministic actions (the decision was made at entry, not at the event).
    approval_action = "hold_and_trail" if holds_through else "exit_on_open"
    rejection_action = "lean_hedge" if has_hedge else "exit_on_open"
    scenario_table = [
        ScenarioRow(scenario="approval", probability=p_positive,
                    target=approval_target, action=approval_action),
        ScenarioRow(scenario="rejection", probability=1.0 - p_positive,
                    target=rejection_target, action=rejection_action),
        # mixed = football-field midpoint (a partial/muddled resolution) -> take half off
        ScenarioRow(scenario="mixed", probability=EXIT_PARAMS["mixed_prob"],
                    target=(approval_target + rejection_target) / 2.0, action="exit_half"),
        # delay = event slips / IV crush -> weekly-flat (entry) -> exit on open
        ScenarioRow(scenario="delay", probability=EXIT_PARAMS["delay_prob"],
                    target=entry, action="exit_on_open"),
    ]

    thesis_invalidation = ThesisInvalidation(
        outcome="rejection" if direction == "positive" else "approval",
        magnitude_floor=down_move,
        disqualifying_news=list(kill_criteria),
    )

    ev_flip = EvFlipGuard(upside=up_move, downside=down_move, p=p_positive,
                          threshold=EXIT_PARAMS["ev_flip_threshold"])

    return ExitPlan(
        expectation_band=band,
        scenario_table=scenario_table,
        thesis_invalidation=thesis_invalidation,
        time_barrier=exit_by_date,  # hard triple-barrier TIME leg
        ev_flip=ev_flip,
    )
