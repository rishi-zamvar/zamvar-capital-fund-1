---
phase: 10-continuous-iteration-loop
plan: 03
requirements: [LEARN-01, LEARN-02]
key-files:
  created: [src/catalyst_trader/learn/loop.py, tests/test_learn_loop.py]
  modified: [scripts/weekly_cycle.py, tests/test_weekly_cycle.py, docs/operator-weekly-cycle.md]
---
# 10-03 Summary — the weekly learning cycle

- `learn/loop.py`: grid_proposer (one knob at a time over TUNABLE bounds, in-sample Sharpe on the training
  window via TrainingReplay only) + run_learn_cycle (judge -> propose -> submit -> evaluate; stops cleanly
  on an exhausted run budget; never promotes).
- `scripts/weekly_cycle.py`: `--learn` (CC session: live judge + Layer-A replay + XBI benchmark + golden
  file), `--promote ID`, `--freeze-holdout START END`; cores learn_cmd / promote_cmd / freeze_holdout_cmd.
  Whole-file grep: no opener/broker, no insert_playbook/insert_claim/seed_fitted_params; learn_cmd never promotes.
- A PASSING proposal in the cycle still leaves load_params unchanged (tested) until --promote.
- Deferred: LLM proposer = strict xfail. Operator doc section "Learning loop".
