---
phase: 03-quant-tool-library-rubric-base-rates
plan: 08
subsystem: testing
tags: [quant, pydantic, reproducibility, coverage, public-api]

# Dependency graph
requires:
  - phase: 03 (plans 01-07)
    provides: ToolResult contract + all quant submodules (valuation, sizing, pairs, options, performance, portfolio, rubric, base_rates)
provides:
  - One public import surface (catalyst_trader.quant) re-exporting ToolResult + all 18 tools + rubric/base-rate loaders
  - Library-wide reproducibility invariant test (inputs==kwargs snapshot + immutability across every tool)
  - Full-suite green + 98% quant coverage with the most money-critical tool (risk_of_ruin) at 100%
affects: [phase-04-analyst-desk, phase-05-strategy-sizing, any-agent-calling-quant-tools]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "One import surface: agents do `from catalyst_trader.quant import <tool>` — no reaching into submodules"
    - "Library-wide invariant via a single parametrized table (HAPPY_PATH) — a new tool not wired in is provably uncovered"

key-files:
  created:
    - tests/test_quant_library.py
  modified:
    - src/catalyst_trader/quant/__init__.py
    - tests/test_sizing.py

key-decisions:
  - "Export exactly the 18 verbatim-inputs tools + loaders; pipeline_value stays submodule-only (its inputs snapshot is derived asset_values, not verbatim kwargs — would break the library-wide inputs==kwargs invariant)"
  - "HAPPY_PATH kwargs authored to equal each tool's inputs snapshot exactly (including default fields), so inputs==kwargs is a true reproducibility check, not an approximation"

patterns-established:
  - "Adding a quant tool requires adding it to HAPPY_PATH or it is provably outside the reproducibility invariant"

requirements-completed: [QUANT-01, QUANT-03, OPS-04]

# Metrics
duration: 12min
completed: 2026-08-15
---

# Phase 3 Plan 08: Quant Library Import Surface + Reproducibility Invariant Summary

**One public `catalyst_trader.quant` import surface re-exporting all 18 tools + loaders, gated by a single parametrized test proving every tool returns a `ToolResult` whose `inputs` verbatim-equals its call kwargs (QUANT-03), with the full suite green at 98% quant coverage.**

## Performance

- **Duration:** ~12 min
- **Completed:** 2026-08-15
- **Tasks:** 2 of 3 (Task 3 descoped by orchestrator — see Deviations)
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments
- `quant/__init__.py` now re-exports `ToolResult` + all 18 ToolResult-returning tools + `load_weights`/`score_rubric`/`load_base_rates`/`base_rate` with an explicit `__all__` — agents import the whole toolbox from one line (QUANT-01).
- `tests/test_quant_library.py`: two parametrized tests over a `HAPPY_PATH` table covering every tool — (a) returns a `ToolResult`, (b) `inputs == kwargs` verbatim, (c) `tool_version` non-empty, plus field-reassignment raises (immutability). Closes QUANT-03 / Pitfall 6 library-wide. Also asserts every `__all__` name is importable.
- Full suite green (451 tests); `catalyst_trader.quant` coverage 98%, `sizing.py` at 100% — the most money-critical tool (`risk_of_ruin`) has no uncovered branch (OPS-04).

## Task Commits

1. **Task 1: Wire the one import surface + library-wide invariant test** - `d1cf30d` (feat)
2. **Task 2: Full-suite + coverage gate** - `0205fb2` (test)

_Task 3 (HTML report + TOKEN-NOTES) descoped — see Deviations._

## Files Created/Modified
- `tests/test_quant_library.py` - Library-wide parametrized inputs-snapshot + immutability invariant; import-surface presence check
- `src/catalyst_trader/quant/__init__.py` - Full public re-export surface with `__all__`
- `tests/test_sizing.py` - Added coverage for `risk_of_ruin`'s ruin-cannot-fit-horizon branch

## Decisions Made
- **pipeline_value stays submodule-only.** It aggregates other results, so its `inputs` snapshot is derived (`asset_values`), not the verbatim call kwargs. Exporting it on the surface would make the library-wide "inputs equal call args" invariant false for one member. The plan's re-export list already omitted it; kept it reachable via `catalyst_trader.quant.valuation.pipeline_value`.
- **HAPPY_PATH kwargs match each tool's snapshot exactly**, including fields left at their defaults (e.g. `implied_move` iv/days_to_event=None, `score_rubric` factor_scores only), so `inputs == kwargs` is a real equality assertion.

## Deviations from Plan

### Orchestrator-directed scope change

**1. Task 3 (HTML report + TOKEN-NOTES) skipped**
- **Found during:** Plan intake — the executor prompt's `<success_criteria>` explicitly states: *"Do NOT generate the phase HTML report or update TOKEN-NOTES — those are orchestrator-handled at phase close."*
- **Action:** Executed Tasks 1 and 2 only; left `docs/phase-reports/phase-03-report.html` and `.planning/TOKEN-NOTES.md` untouched for the orchestrator to produce at phase close.
- **Impact:** The two in-scope objectives (import surface + library-wide invariant, coverage gate) are fully delivered. No functional gap.

### Auto-added (Rule 2 — missing coverage on a money tool)

**2. [Rule 2] Added a test for `risk_of_ruin`'s horizon-impossible branch**
- **Found during:** Task 2 (coverage report)
- **Issue:** `sizing.py` lines 114/119 (ruinous streak cannot fit in `n_trades` → value 0.0) were uncovered on the single most money-critical tool; the plan requires "no money tool left uncovered."
- **Fix:** Added `test_risk_of_ruin_is_zero_when_ruinous_streak_cannot_fit_in_horizon` (tiny size vs short horizon → 0.0).
- **Verification:** `sizing.py` coverage 98%→100%; full suite green.
- **Committed in:** `0205fb2`

---

**Total deviations:** 1 orchestrator-directed scope change, 1 Rule-2 auto-add.
**Impact on plan:** In-scope objectives fully met. No scope creep.

## Issues Encountered
None. The parametrized `inputs == kwargs` assertion passed for all 18 tools on first run — the ToolResult snapshot contract was already implemented consistently across the submodules.

## Next Phase Readiness
- The quant library is a single callable import surface with a machine-enforced reproducibility contract — Phase 4 (Analyst Desk) and Phase 5 (Strategy/Sizing) can call any tool via `from catalyst_trader.quant import ...` and trust every emitted number carries its inputs.
- Phase-close artifacts (HTML report + TOKEN-NOTES retrospective) are the orchestrator's responsibility at phase close.

---
*Phase: 03-quant-tool-library-rubric-base-rates*
*Completed: 2026-08-15*

## Self-Check: PASSED

All created files exist; both task commits (d1cf30d, 0205fb2) present in history.
