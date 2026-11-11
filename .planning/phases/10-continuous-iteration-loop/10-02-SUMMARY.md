---
phase: 10-continuous-iteration-loop
plan: 02
requirements: [LEARN-02]
key-files:
  created: [src/catalyst_trader/migrations/020_learn_gate.sql, src/catalyst_trader/learn/gate.py, data/learn/golden_set.json, tests/test_learn_gate.py, tests/test_learn_gate_adversarial.py]
  modified: [src/catalyst_trader/kb.py, tests/test_kb_params.py, tests/test_playbook_generalize.py]
---
# 10-02 Summary — the promotion gate + structural no-auto-apply

- `learn/gate.py`: TUNABLE whitelist (bounds only tighten the tradeability bar; safety knobs absent),
  apply_patch/check_patch, frozen holdout (manifest = weeks + catalysts + price-bar digest, re-hashed at
  evaluate AND promote), training_cutoff = holdout.start - embargo - 7d (exit fill included, plan-check W3),
  TrainingReplay (HoldoutLeak), submit_proposal (ProposedDiff extra=forbid), evaluate (integrity +
  guardrails + golden regression + walk-forward folds / DSR with n_trials = runs spent / XBI alpha / drawdown,
  run budget 20), promote (sole writer; confidence top+(1-top)/10 with top=0.3 when none, plan-check W4),
  layer_a_replay (run_layer_a) + xbi_benchmark (engine._fill_leg).
- Migration 020: holdout/gate-run immutable, proposal content immutable, one-shot promotion tickets only for
  passed runs, kb_node insert trigger (any fitted_params:weekly, any fitted_params above 0.3, any
  learn_promotion_id) must match an armed ticket exactly; fitted_params versions append-only.
- kb.query_playbooks tie-break `id ASC` (plan-check B1).
- Adversarial suite: 33 bypass attempts (forged fields, safety/gate-targeted patches, skip/fail gate, SQL
  status flip, double promote, post-gate mutation incl. trigger dropped, holdout update/delete/drift/re-freeze,
  training leak, direct KB inserts at 0.9 / 0.31 / 0.1-weekly, forged + mismatched + consumed promotion
  tickets, in-place edit/delete of a version, grep invariant).
- Existing tests re-pointed: two ungated fitted_params inserts moved to the seed tier; the "future fit shadows
  the seed" test now asserts the ungated refit is REFUSED.
- Real Layer-A plumbing on synthetic history runs end-to-end and fails honestly (all-defensive synthetic book).
