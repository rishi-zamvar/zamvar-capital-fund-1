---
phase: 10-continuous-iteration-loop
plan: 01
requirements: [LEARN-01]
key-files:
  created: [src/catalyst_trader/migrations/019_learn_judge.sql, src/catalyst_trader/learn/judge.py, data/learn/judge_labels.json, tests/test_learn_judge.py, tests/test_learn_judge_live.py]
---
# 10-01 Summary — post-resolution judge + calibration harness

- `learn/judge.py`: JudgeVerdict boundary contract; RUBRIC (1-5) + RUBRIC_SHA; build_case (paper_position +
  Phase-8 attribution + Phase-9 review snapshot); score_case; quadratic_weighted_kappa; calibrate (passes only
  on >= 20 REAL labels, qwk >= 0.6, within-one >= 0.8; synthetic reported, never counted; judge errors counted);
  record_calibration; judge_resolved (idempotent, failure-tolerant); make_live_judge (run_structured, no tools).
- Migration 019: learn_calibration (immutable, CHECK passed=0 OR n_real>=20) + learn_judgement (UNIQUE
  position, calibrated=1 trigger-bound to a passed calibration of the same model + rubric).
- Seed labels: 10 cases, ALL synthetic + needs_ceo_grading (judge is UNCALIBRATED until the CEO grades).
- Deferred: headless judge auto-fire at resolution = strict xfail. Live judge test behind LEARN_LIVE_JUDGE=1.
- Plan-check warnings W1 (forgeable calibration) and W2 (rubric binding) folded in.
