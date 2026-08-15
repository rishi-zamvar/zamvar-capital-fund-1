---
phase: 07-verifier-guardrails-backtest-harness
plan: 01
subsystem: quant
tags: [numpy, performance-metrics, drawdown, hedge-effectiveness, backtest, ToolResult]

# Dependency graph
requires:
  - phase: 03-quant-tool-library-rubric-base-rates
    provides: quant/performance.py (sharpe/sortino/cumulative_return/attribution), ToolResult contract, _to_array guard, library-wide reproducibility invariant
provides:
  - max_drawdown, win_rate, avg_win_loss, hedge_effectiveness in quant/performance.py (numpy-only)
  - the four new metrics exported from catalyst_trader.quant and covered by the QUANT-03 inputs-snapshot invariant
  - baseline-distribution + hedge-effectiveness inputs the backtest harness (BACK-02) and go/no-go gate (BACK-05, Plan 07-05) consume
affects: [07-02, 07-03, 07-04, 07-05, backtest-harness, go-no-go-gate]

# Tech tracking
tech-stack:
  added: []  # numpy only — already pulled in via statsmodels; NO new dependency (quantstats/empyrical barred)
  patterns:
    - "New money-metrics mirror the existing sharpe/sortino discipline verbatim: _to_array empty/NaN guard, frozen ToolResult with verbatim inputs snapshot, value=None for an undefined ratio (never inf/divide)"

key-files:
  created: []
  modified:
    - src/catalyst_trader/quant/performance.py
    - src/catalyst_trader/quant/__init__.py
    - tests/test_performance.py
    - tests/test_quant_library.py

key-decisions:
  - "tool_version reuses the module _VERSION='1.0.0' (matching the existing four metrics), not the plan interface-doc's loose '1' — the reproducibility test only asserts a non-empty version string; codebase consistency wins"
  - "max_drawdown guards a LEADING -100% wipeout (running_peak==0 → 0/0) with np.where(running_peak>0, ..., -1.0) under np.errstate, so a wipeout is a computed -1.0, never a NaN in a risk number"
  - "avg_win_loss and hedge_effectiveness return value=None on an undefined ratio / no-down-days (no false 1.0, no divide-by-zero), mirroring how sharpe/sortino refuse to emit inf"

patterns-established:
  - "Adding a money-metric = add it to test_quant_library HAPPY_PATH so the library-wide inputs==kwargs invariant provably covers it; an unwired metric is provably un-covered"

requirements-completed: [BACK-02]

# Metrics
duration: 6min
completed: 2026-08-15
---

# Phase 7 Plan 01: Baseline-Distribution Metrics Summary

**Four numpy-only money-metrics — max_drawdown (wipeout-safe), win_rate (strict >0), avg_win_loss (None on undefined ratio), and hedge_effectiveness (target-down offset fraction) — built beside the existing sharpe/sortino, exported, and covered by the QUANT-03 reproducibility invariant with zero new dependencies.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-08-15T23:17:17Z
- **Completed:** 2026-08-15T23:21:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- `max_drawdown` — worst peak-to-trough on the compounded `cumprod(1+r)` equity curve, ≤ 0; a −100% period yields a computed −1.0 (leading-wipeout 0/0 guarded, no NaN)
- `win_rate` — strict `count(r>0)/n`; a flat 0.0 is not a win
- `avg_win_loss` — avg_win / avg_loss (positive magnitude) ratio; `value=None` when there are no losses (undefined, no divide)
- `hedge_effectiveness` — over target-down periods, the fraction where the paired hedge leg actually offset (>0); equal-length enforced; `value=None` on no-down-days; `net_pnl_target` vs `net_pnl_combined` in detail for loss-reduction reporting
- All four publicly importable from `catalyst_trader.quant` and wired into the library-wide inputs-snapshot invariant (QUANT-03)

## Task Commits

Each task was committed atomically (TDD RED→GREEN folded per task since the shared test-module import couples test+impl into one collectable unit):

1. **Task 1: max_drawdown + win_rate + avg_win_loss** - `f6a2c71` (feat)
2. **Task 2: hedge_effectiveness + public export + reproducibility invariant** - `8dba793` (feat)

_Note: RED was run and confirmed failing (ImportError) before each GREEN implementation._

## Files Created/Modified
- `src/catalyst_trader/quant/performance.py` - Added the 4 metric functions beside sharpe/sortino/cumulative_return/attribution (numpy only)
- `src/catalyst_trader/quant/__init__.py` - Extended the `.performance` import + `__all__` with the 4 new names
- `tests/test_performance.py` - Added exhaustive edge-case suites (wipeout, strict-win, undefined-ratio, no-down-days, empty/NaN/length-mismatch raise)
- `tests/test_quant_library.py` - Added the 4 metrics to HAPPY_PATH so the QUANT-03 inputs==kwargs invariant covers them

## Decisions Made
- Reused `_VERSION="1.0.0"` for `tool_version` (codebase consistency over the plan's loose `"1"`).
- `max_drawdown` wraps the equity/peak division in `np.errstate(invalid="ignore", divide="ignore")` + `np.where(running_peak>0, ..., -1.0)` so a leading wipeout is −1.0, not NaN, and no RuntimeWarning leaks.

## Deviations from Plan
None - plan executed exactly as written. (The `_VERSION` vs `"1"` choice is a consistency call within the plan's stated intent, not a scope change.)

## Issues Encountered
- Initial `max_drawdown` implementation emitted a numpy divide RuntimeWarning on the leading-wipeout case (0/0 before `np.where` selects). Resolved by wrapping the division in `np.errstate` — result was already correct, this only silences the warning on a money path.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Baseline-distribution metrics (max DD, win rate, avg win/loss) + hedge-effectiveness are ready for the mechanical backtest harness (Plans 07-02..04) and the go/no-go gate (Plan 07-05, BACK-05).
- Zero new dependencies; full suite green (866 passed).

---
*Phase: 07-verifier-guardrails-backtest-harness*
*Completed: 2026-08-15*

## Self-Check: PASSED

All modified files exist, both task commits (`f6a2c71`, `8dba793`) are in history, and all 4 metric functions are present in performance.py.
