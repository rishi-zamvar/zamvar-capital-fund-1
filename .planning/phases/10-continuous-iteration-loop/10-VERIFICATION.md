---
phase: 10-continuous-iteration-loop
verified: 2026-11-11T00:00:00Z
status: human_needed
score: 1/3 success criteria fully verified (SC2 verified; SC1 partial, needs CEO; SC3 partial, 2 bypasses)
gaps:
  - truth: "No config or playbook diff can auto-apply to the paper/live money path without passing the gate (SC3)"
    status: partial
    reason: "Two raw-SQL bypasses inside the phase's own threat model (A11 lists direct KB writes and SQL status flips as in scope, and the adversarial suite tests exactly those). Both change kb.load_params('weekly') with no passed gate run."
    artifacts:
      - path: "src/catalyst_trader/migrations/020_learn_gate.sql"
        issue: "kb_fitted_params_append_only only checks OLD.scenario_type. An UPDATE that turns a non-fitted node into fitted_params:weekly passes. Two variants confirmed: (a) an 'outcome' node carrying fitted_params:weekly attrs, then UPDATE kind='playbook'; (b) a playbook with scenario_type 'other', then UPDATE attrs_json to fitted_params:weekly. Both set hard_veto_drop=-0.9 and edge_min_pts=0.0 on the money path."
      - path: "src/catalyst_trader/migrations/020_learn_gate.sql"
        issue: "learn_gate_run has no BEFORE INSERT guard. A forged row (passed=1, content_sha and holdout_sha copied from the proposal and the holdout) plus UPDATE learn_proposal SET status='passed' lets the real gate.promote() succeed without evaluate() ever running. promote() re-verifies the shas but cannot tell a forged run from a real one."
    missing:
      - "BEFORE UPDATE trigger on kb_node that aborts when NEW (not only OLD) is a playbook whose scenario_type LIKE 'fitted_params:%', or when kind/scenario_type changes into that class"
      - "A guard on learn_gate_run inserts (for example a one-shot 'evaluating' ticket that only evaluate() arms, or require proposal status='proposed' at insert time and make the 'passed' status reachable only via a trigger off the gate_run insert) so a hand-inserted passed run cannot be promoted"
      - "Adversarial tests for the three attempts above"
human_verification:
  - test: "Hand-grade at least 20 REAL resolved cases into data/learn/judge_labels.json, then run calibrate() and record_calibration() with make_live_judge() in a CC session"
    expected: "qwk >= 0.6 and within-one >= 0.8 on real labels gives a passed learn_calibration row, and later judgements are stored calibrated=1"
    why_human: "All 10 seed labels are synthetic. No calibrated judge exists yet, by design."
  - test: "Curate data/learn/golden_set.json (3 windows seeded by Claude, needs_ceo_review) and freeze the first real holdout with weekly_cycle.py --freeze-holdout"
    expected: "Golden windows are confirmed and the holdout row is frozen on the real DB"
    why_human: "These are CEO decisions C2 and C3"
---

# Phase 10: Continuous-Iteration Loop Verification Report

**Phase goal:** The desk gets measurably better every week, but can never quietly overfit or reward-hack the money path.
**Verified:** 2026-11-11
**Status:** gaps_found
**Re-verification:** No. This is the first verification.

## Test Suite

`PYTHONPATH=src ../../../.venv/bin/python -m pytest -q -p no:cacheprovider` gives 2127 passed, 5 skipped, 3 xfailed.

- The Phase 10 subset (test_learn_*, test_weekly_cycle, test_kb_params) gives 135 passed, 1 skipped (live judge), 2 xfailed.
- The two xfails are the declared deferrals: headless judge auto-fire, and the LLM proposer.

## Success Criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Prediction vs realized scored by an LLM judge calibrated to hand-graded labels | PARTIAL / needs human | The harness is real (see below), but no calibrated judge exists (see below). |
| 2 | Loop proposes diffs; merge only via golden-set replay + guardrail + walk-forward on a frozen holdout | VERIFIED | Gate checks and the explicit promote path are in place (see below). |
| 3 | No diff can auto-apply to the money path without passing the gate | PARTIAL | The single promotion path holds against the 33 adversarial tests and 5 of my 8 scratch probes, but 2 bypasses were confirmed (see below). |

**SC1, what exists.**
- `judge.py`: JudgeVerdict (extra=forbid), a rubric with its RUBRIC_SHA, quadratic-weighted kappa, within-one agreement, and MAE.
- `calibrate()` passes only on 20 or more REAL labels. Judge errors count as failures.
- Migration 019: CHECK passed=0 OR n_real>=20; calibration rows are immutable; calibrated=1 is tied by trigger to a passed calibration of the same model and rubric.
- `judge_resolved` is idempotent and failure-tolerant.

**SC1, what is missing.**
- All 10 seed labels are `synthetic: true` and `needs_ceo_grading: true`. Today every judgement is stored with calibrated=0.
- The judge fires only from `--learn` inside a CC session. Auto-fire at resolution is a strict xfail, so "after each catalyst resolves" is weekly-batched, not per-event.

**SC2, what exists.**
- `evaluate()` runs these checks:
  - integrity: holdout re-hashed, content sha, base sha, replayable target, 20-run budget
  - guardrails: TUNABLE whitelist and bounds, type-preserving, safety knobs absent, drawdown floor and tolerance
  - golden: every case, patched >= baseline; an empty set fails closed
  - walk-forward: at least 12 weeks, a majority of 3 folds, deflated Sharpe with n_trials = runs spent + 1, XBI alpha >= baseline
- Non-weekly targets fail closed.
- Promotion is a separate step (`--promote`), and the loop never promotes (tested).

### Honesty of "calibrated to hand-graded labels"

This is represented honestly:

- The `_README` in `judge_labels.json` and every label's grader field say SYNTHETIC-PLACEHOLDER.
- `Label` refuses a synthetic label that claims it needs no grading.
- `calibrate()` reports synthetic agreement separately and never counts it.
- CONTEXT, SUMMARY and the operator doc all say the judge is UNCALIBRATED until the CEO grades.
- Judge scores are not a gate input (A5), so an uncalibrated judge cannot steer money.

Residual weaknesses:
- `synthetic` is a self-declared flag. Nothing cross-checks it against the grader string.
- `n_real` in learn_calibration is self-reported, so a raw INSERT with n_real=20 and passed=1 satisfies the CHECK.

Neither affects money, but SC1 cannot be called met until a real calibration exists.

## Bypass Probes (scratch, in-memory DB via the test fixtures, nothing written to the repo)

| Attempt | Result |
|---------|--------|
| Insert as 'claim', flip kind to playbook | held. 'claim' is not an allowed kind (CHECK). |
| Insert an `outcome` node with fitted_params:weekly attrs, then `UPDATE kind='playbook'` | **BYPASS**: load_params returns hard_veto_drop=-0.9, edge_min_pts=0.0 |
| Insert playbook scenario_type 'other', then UPDATE attrs_json to fitted_params:weekly | **BYPASS** |
| Raw INSERT of a passed learn_gate_run (copied shas) + status flip + real `gate.promote()` | **BYPASS**. The patch is still TUNABLE-bounded, but it never passed evaluate. |
| kind='Playbook' (case) | held (CHECK) |
| Duplicate `scenario_type` JSON key | held. The trigger and query_playbooks both use json_extract. |
| Status flip to 'passed' alone | held (no passed run) |
| NULL confidence fitted_params:weekly | held (weekly is always gated) |
| DROP TRIGGER then insert | bypass. This is raw DDL, out of A11 scope; noted only for completeness. |

The legitimate code that does `UPDATE kb_node SET attrs_json` (`kb.stamp_hedge_profile`, `playbook/store.py`, `playbook/tagger.py`) preserves scenario_type and kind, so I found no Python call path that triggers the UPDATE bypass. It is reachable only by raw SQL. That is still the same class of attack the adversarial suite claims to cover ("SQL status flip", "direct KB inserts").

## Holdout-Leak Review (proposal generation)

- `run_learn_cycle` gives the proposer only `TrainingReplay(replay, cutoff)`.
  - cutoff = holdout.start - embargo - 7 days, so the exit fill is included.
  - TrainingReplay raises HoldoutLeak when start or end > cutoff.
- `submit_proposal` rejects trained_through > cutoff.
- `grid_proposer` replays only [cutoff - 104w, cutoff].
- Layer A reads through `qw.as_of_view(conn, as_of)` (the Phase-7 point-in-time gateway), so a training-window replay does not read later bars.
- Base params come from load_params, which contains no holdout data.
- The judge pass may grade holdout-period trades, but grid_proposer does not read judgements.

No leak path was found for the shipped proposer. Residuals (warnings, not blockers):
1. The boundary is advisory for in-process code. `run_learn_cycle(proposer=...)` accepts any callable, which could close over `conn` or reach `train_replay._replay`. `trained_through` is self-declared. This matters for the deferred LLM proposer.
2. Dates are compared as strings (correct only for ISO yyyy-mm-dd).
3. `freeze_holdout` allows re-freezing the identical or an overlapping window. That resets both the 20-run budget and the DSR n_trials counter, which is a quiet adaptive-overfit path through an operator action (D2). Consider refusing overlap with any prior holdout, or carrying n_trials across overlapping holdouts.

## Requirements Coverage

| Req | Plans | Status | Evidence |
|-----|-------|--------|----------|
| LEARN-01 | 10-01, 10-03 | PARTIAL (needs human) | The harness and judge pass are complete. Calibration requires CEO-graded real labels. |
| LEARN-02 | 10-02, 10-03 | PARTIAL | Propose + gate + explicit promote are complete. The structural no-bypass has the 2 holes above. |

No orphaned requirements.

## Anti-Patterns

No TODO, placeholder or stub code was found in `learn/*.py`. The deferrals are explicit strict xfails. The `ponytail:` note on the one-knob grid is a documented ceiling.

## Gaps Summary

SC2 is met. SC3 has one root cause: migration 020 guards INSERTs into the money-path class, but not UPDATEs that move a row INTO that class, and it does not guard the creation of the gate-run evidence that `promote` trusts. Fixing it takes two small triggers plus three adversarial tests. SC1 depends on the CEO grading at least 20 real cases, and that dependency is disclosed honestly.

---
_Verified: 2026-11-11_
_Verifier: Claude (gsd-verifier)_


## Gap closure (orchestrator, 2026-11-11, after verification)

The two SC3 bypasses and the forged-verdict paths were closed in migration 020 and covered by 8 new
adversarial tests (tests/test_learn_gate_adversarial.py, 39 cases, all green; full suite 2133 passed):
- `kb_fitted_params_no_rewrite_into`: an UPDATE whose NEW row is a fitted_params / learn-tagged playbook is
  refused, so neither a kind flip (outcome -> playbook) nor an attrs rewrite into the namespace works.
- `learn_gate_run_binds_proposal`: a gate run must bind to a still-'proposed' proposal, with its current
  content sha and its holdout's frozen sha. There is no second verdict on an evaluated proposal.
- `learn_proposal_status_flow`: proposed -> passed|failed only when a matching gate run backs it;
  passed -> promoted only when an applied promotion backs it. Raw status flips are refused.
- Budget and DSR trial count now span every holdout that overlaps the active window
  (`gate.runs_spent`), so re-freezing the same window does not reset them.

**Residual (documented, CONTEXT A11):** someone with raw SQL can still INSERT a fabricated *passed* gate
run for a still-'proposed' proposal with the correct shas. SQL cannot re-verify a backtest computation.
This is outside the threat model (a human with write access to catalyst.db). Code paths and the diff
object itself cannot reach the money path without `learn.gate.evaluate` producing the pass.

Post-closure status: SC2 VERIFIED; SC3 VERIFIED within the A11 threat model; SC1 harness VERIFIED, but the
judge is honestly UNCALIBRATED until the CEO grades >= 20 real cases (human_needed).
