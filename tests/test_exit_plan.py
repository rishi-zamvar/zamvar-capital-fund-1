"""Tier-3 Task A / Task 1 — the DETERMINISTIC Exit Plan authored at entry.

Money-critical invariants under test (no agent in the hot path — this is pure arithmetic
off the football-field/verdict numbers the desk already produced):
  - the expectation band (no-stop zone) is entry*(1-down_move) .. entry*(1+up_move);
  - each scenario's pre-committed action is deterministic in holds_through / has_hedge;
  - thesis_invalidation.outcome flips with direction; magnitude_floor == down_move;
    disqualifying_news == kill_criteria;
  - time_barrier is the hard triple-barrier TIME leg (== exit_by_date);
  - ev_flip_guard fires (True) when remaining_upside*p - downside*(1-p) < threshold;
  - EXIT_PARAMS thresholds are direct-subscript — a missing key RAISES (no literal fallback);
  - the ExitPlan contract is extra="forbid".

Fully offline / pure — no conn, no LLM, no I/O.
"""

import pytest
from pydantic import ValidationError

from catalyst_trader.contracts import (
    EvFlipGuard,
    ExitPlan,
    ScenarioRow,
    ThesisInvalidation,
)
from catalyst_trader.desk import exit_plan as ep


def _plan(**over):
    base = dict(entry=100.0, up_move=0.20, down_move=0.10, p_positive=0.6,
                holds_through=True, stop=90.0, target=120.0, exit_by_date="2026-11-22",
                kill_criteria=["a Complete Response Letter is issued"],
                direction="positive", has_hedge=False)
    base.update(over)
    return ep.build_exit_plan(**base)


# --------------------------------------------------------------------------- band


def test_expectation_band_from_entry_up_down():
    plan = _plan(entry=100.0, up_move=0.20, down_move=0.10)
    lo, hi = plan.expectation_band
    assert lo == pytest.approx(100.0 * (1 - 0.10))   # 90.0
    assert hi == pytest.approx(100.0 * (1 + 0.20))   # 120.0


# --------------------------------------------------------------------- scenario table


def test_scenario_probabilities_from_verdict_and_params():
    plan = _plan(p_positive=0.6)
    by = {r.scenario: r for r in plan.scenario_table}
    assert set(by) == {"approval", "rejection", "mixed", "delay"}
    assert by["approval"].probability == pytest.approx(0.6)
    assert by["rejection"].probability == pytest.approx(0.4)
    # mixed/delay are conditional carve-outs read straight from EXIT_PARAMS
    assert by["mixed"].probability == pytest.approx(ep.EXIT_PARAMS["mixed_prob"])
    assert by["delay"].probability == pytest.approx(ep.EXIT_PARAMS["delay_prob"])


def test_approval_action_depends_on_holds_through():
    by_t = {r.scenario: r for r in _plan(holds_through=True).scenario_table}
    by_f = {r.scenario: r for r in _plan(holds_through=False).scenario_table}
    assert by_t["approval"].action == "hold_and_trail"
    assert by_f["approval"].action == "exit_on_open"


def test_rejection_action_depends_on_hedge():
    by_h = {r.scenario: r for r in _plan(has_hedge=True).scenario_table}
    by_n = {r.scenario: r for r in _plan(has_hedge=False).scenario_table}
    assert by_h["rejection"].action == "lean_hedge"
    assert by_n["rejection"].action == "exit_on_open"


def test_mixed_and_delay_actions_are_pre_committed():
    by = {r.scenario: r for r in _plan().scenario_table}
    assert by["mixed"].action == "exit_half"
    assert by["delay"].action == "exit_on_open"   # IV-crush / weekly-flat


def test_scenario_targets_are_football_field_prices():
    plan = _plan(entry=100.0, up_move=0.20, down_move=0.10)
    by = {r.scenario: r for r in plan.scenario_table}
    assert by["approval"].target == pytest.approx(100.0 * 1.20)
    assert by["rejection"].target == pytest.approx(100.0 * 0.90)


# -------------------------------------------------------------- thesis invalidation


def test_thesis_invalidation_outcome_flips_with_direction():
    assert _plan(direction="positive").thesis_invalidation.outcome == "rejection"
    assert _plan(direction="negative").thesis_invalidation.outcome == "approval"


def test_thesis_invalidation_floor_and_news():
    plan = _plan(down_move=0.10, kill_criteria=["CRL issued", "label carve-out"])
    ti = plan.thesis_invalidation
    assert ti.magnitude_floor == pytest.approx(0.10)
    assert ti.disqualifying_news == ["CRL issued", "label carve-out"]


# ------------------------------------------------------------------- time barrier


def test_time_barrier_is_exit_by_date():
    assert _plan(exit_by_date="2026-11-22").time_barrier == "2026-11-22"


# -------------------------------------------------------------------- ev flip guard


def test_ev_flip_guard_true_below_threshold():
    # remaining_upside*p - downside*(1-p) = 0.05*0.5 - 0.2*0.5 = -0.075 < 0 -> flip
    assert ep.ev_flip_guard(0.05, 0.5, 0.2, 0.0) is True


def test_ev_flip_guard_false_above_threshold():
    # 0.30*0.6 - 0.10*0.4 = 0.18 - 0.04 = 0.14 >= 0 -> no flip
    assert ep.ev_flip_guard(0.30, 0.6, 0.10, 0.0) is False


def test_ev_flip_guard_stored_inputs():
    plan = _plan(up_move=0.20, down_move=0.10, p_positive=0.6)
    g = plan.ev_flip
    assert g.upside == pytest.approx(0.20)
    assert g.downside == pytest.approx(0.10)
    assert g.p == pytest.approx(0.6)
    assert g.threshold == pytest.approx(ep.EXIT_PARAMS["ev_flip_threshold"])


# --------------------------------------------------------------------- contract + params


def test_exit_plan_rejects_extra_field():
    plan = _plan()
    with pytest.raises(ValidationError):
        ExitPlan(**{**plan.model_dump(), "stray": 1})


def test_scenario_row_rejects_extra_field():
    with pytest.raises(ValidationError):
        ScenarioRow(scenario="approval", probability=0.6, target=120.0,
                    action="hold_and_trail", stray=1)


def test_missing_exit_param_key_raises(monkeypatch):
    monkeypatch.setattr(ep, "EXIT_PARAMS", {})   # a missing threshold key is a hard error
    with pytest.raises(KeyError):
        _plan()


def test_build_exit_plan_is_deterministic():
    assert _plan() == _plan()   # same inputs -> byte-for-byte identical plan (out_default==out_explicit)
