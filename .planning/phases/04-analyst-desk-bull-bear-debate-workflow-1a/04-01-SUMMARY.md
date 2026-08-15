---
phase: 04-analyst-desk-bull-bear-debate-workflow-1a
plan: 01
subsystem: api
tags: [pydantic, contracts, debate, kill-criteria, CALL-03]

# Dependency graph
requires:
  - phase: 02-contracts-knowledge-base-skeleton
    provides: DebateVerdict + inter-layer pydantic contracts (extra=forbid spine)
provides:
  - DebateVerdict.direction is a binary Literal["positive","negative"] (enforced at model_validate)
  - DebateVerdict.kill_criteria is a required, non-empty list[str] (falsification criteria)
affects: [debate-moderator, plan-05, portfolio-construction, strategy-dossier]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Non-empty-list field_validator mirrors AnalystSignal._at_least_one_sourced_finding"
    - "Binary agent verdicts expressed as pydantic Literal, not free str"

key-files:
  created: []
  modified:
    - src/catalyst_trader/contracts/__init__.py
    - tests/test_contracts.py

key-decisions:
  - "direction is Literal[positive,negative] — 'binary' from CALL-03 is now enforced at the boundary, not a naming convention"
  - "kill_criteria is required with no default + non-empty validator — a verdict with no falsification criterion is rejected, not silently accepted"

patterns-established:
  - "Falsification/kill criteria are a first-class contract field, validated non-empty like sourced findings"

requirements-completed: [CALL-03]

# Metrics
duration: 4min
completed: 2026-08-15
---

# Phase 4 Plan 01: DebateVerdict Binary Direction + Kill Criteria Summary

**DebateVerdict now enforces a binary `direction: Literal["positive","negative"]` and a required non-empty `kill_criteria: list[str]`, making CALL-03's "binary verdict + explicit falsification criteria" a hard contract boundary.**

## Performance

- **Duration:** ~4 min
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- `direction` changed from free `str` to `Literal["positive","negative"]` — non-binary values (`neutral`, `up`) rejected at `model_validate`.
- Added required `kill_criteria: list[str]` with `_at_least_one_kill_criterion` validator (empty list rejected), mirroring `AnalystSignal._at_least_one_sourced_finding`.
- Three new contract tests cover binary enforcement, non-empty kill_criteria, and a fully-valid verdict. Full suite green (454 passed).

## Task Commits

Each task committed atomically (TDD):

1. **Task 1 RED: failing tests for binary direction + kill_criteria** - `31f5dc8` (test)
2. **Task 1 GREEN: binary DebateVerdict.direction + required kill_criteria** - `33573a9` (feat)

No REFACTOR commit — the GREEN change was minimal and already mirrored the existing validator pattern.

## Files Created/Modified
- `src/catalyst_trader/contracts/__init__.py` - DebateVerdict: Literal direction + kill_criteria field + validator
- `tests/test_contracts.py` - valid_debate_verdict builder updated with kill_criteria; 3 new DebateVerdict tests

## Decisions Made
- Kept the change additive/surgical to DebateVerdict only (Phase-5 consumers import it, none built yet). `extra="forbid"` preserved.
- `kill_criteria` has no default so omission is a hard error — a verdict that can't be falsified is not a valid verdict.

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
None. `python` alias absent on this host; used `python3` in the project `.venv`.

## Known Stubs
None.

## Next Phase Readiness
- Contract half of CALL-03 complete. The runtime half (grounded confidence, no positioning, moderator synthesis) is Plan 05, which can now construct DebateVerdict with both fields.

---
*Phase: 04-analyst-desk-bull-bear-debate-workflow-1a*
*Completed: 2026-08-15*

## Self-Check: PASSED

All modified files and both task commits (31f5dc8, 33573a9) verified present.
