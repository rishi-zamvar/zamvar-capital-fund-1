---
phase: 05-trade-builder-honest-hedge-ruin-avoidant-sizing-workflow-1b-2
plan: 02
subsystem: quant
tags: [catalyst-move-estimator, kelly, log-growth, hold-vs-exit, sl-tp, ToolResult, tdd]

# Dependency graph
requires:
  - phase: 03-quant-tool-library-rubric-base-rates
    provides: "ToolResult contract, sizing helpers (_finite/_prob), sl_tp_levels advisory gate, implied_move, conditional_payoff pattern"
  - phase: 05 (plan 01)
    provides: "TradeProposal/RiskAssessment contract extensions the builder consumes downstream"
provides:
  - "catalyst_move_estimate: two-state up/down mixture → signed EV + separate up/down magnitudes from historical analog gaps (offline core)"
  - "adaptive_sl_tp_levels: derives SL/TP from the estimate + params, delegates to sl_tp_levels (advisory gate stays in one place)"
  - "expected_log_growth + hold_vs_exit: Kelly-consistent hold-through-vs-exit decision (E[log(1+f·R)] at survival-constrained f, NOT raw EV)"
affects: [05-03, 05-04, 05-05, 05-06, 05-07, trade-builder, risk-committee]

# Tech tracking
tech-stack:
  added: []  # stdlib math/statistics only — no new deps
  patterns:
    - "Every threshold read from a params dict; a missing key RAISES (no numeric-literal fallback in tool bodies)"
    - "adaptive tool DELEGATES to the base tool so shared labels (advisory) live in one place"
    - "Growth-optimal decision math lives in a tested quant tool, never in the builder/agent body"

key-files:
  created:
    - src/catalyst_trader/quant/events.py
    - tests/test_events.py
  modified:
    - src/catalyst_trader/quant/sizing.py
    - src/catalyst_trader/quant/__init__.py
    - tests/test_sizing.py

key-decisions:
  - "implied_move blended as a magnitude prior only (per-branch, weight params.estimator.implied_blend); sign comes solely from the p_positive mixture — a prior can never flip direction"
  - "Down/up branch central estimate = median (robust to a single outlier gap); method is params-driven and only 'median' is accepted (unknown method raises)"
  - "hold_vs_exit decides by expected-LOG-growth at the same survival-constrained f for both branches; margin is a builder-supplied param (0.0 neutral default, not a hidden threshold)"
  - "expected_log_growth raises on any (1+f·R)<=0 — a non-survivable size is a sizing bug, never a silent -inf"
  - "default_down_move param (mentioned in the plan signature comment) deliberately NOT used — it would contradict the empty-branch-no-implied-move RAISE invariant"

patterns-established:
  - "params-required discipline: quant tools access params[...] directly so a missing key raises; no .get(default)"
  - "delegation over duplication for advisory/label logic"

requirements-completed: [PORT-02, PORT-03]

# Metrics
duration: ~20min
completed: 2026-08-15
---

# Phase 5 Plan 02: Catalyst move estimator + adaptive SL/TP + Kelly-consistent hold-vs-exit Summary

**Net-new quant primitives for Workflow-1b single-leg construction: a two-state up/down analog-gap move estimator (offline core, implied_move as magnitude prior only), an adaptive SL/TP that delegates its gap-exposed advisory gate to `sl_tp_levels`, and an `expected_log_growth`/`hold_vs_exit` decision that provably exits a positive-EV-but-fat-tail hold.**

## Performance

- **Duration:** ~20 min
- **Tasks:** 3 (all TDD: RED test commit → GREEN impl commit)
- **Files created:** 2 · **Files modified:** 3
- **Tests:** 516 → 564 (+48 new, all green, no regressions)

## Accomplishments
- `catalyst_move_estimate` produces `value = p·up_move − (1−p)·down_move` from median analog branches, with separate up/down magnitudes in `detail` that downstream sizing/TP/hold-vs-exit tools consume; works with zero options data.
- `implied_move` is a pluggable magnitude prior/clamp (per-branch blend), proven never to flip the mixture sign; empty branch falls back to `|implied_move|`, and empty-with-no-prior raises.
- `adaptive_sl_tp_levels` derives `sl_pct`/`tp_pct` from params + estimate then returns `sl_tp_levels(...)` verbatim — the advisory flag is inherited, not re-implemented (`res.tool == "sl_tp_levels"`).
- `expected_log_growth` + `hold_vs_exit` implement the LOCKED `<model_forms>` rule; the pinned crux test proves a hold with +0.32 raw EV (exceeding the run-up's +0.022) is rejected in favor of EXIT because the −70% tail sinks its log-growth (BLOCKER-2).

## Task Commits

TDD — each task is a RED (test) commit then a GREEN (feat) commit:

1. **Task 1: catalyst_move_estimate** — `bbf08f6` (test) → `5a6475c` (feat)
2. **Task 2: adaptive_sl_tp_levels** — `ffa0f68` (test) → `a67f372` (feat)
3. **Task 3: expected_log_growth + hold_vs_exit** — `16b08e8` (test) → `06c5cf6` (feat)

## Files Created/Modified
- `src/catalyst_trader/quant/events.py` — created: `catalyst_move_estimate`, `expected_log_growth`, `hold_vs_exit` + `_branch_magnitude` helper
- `src/catalyst_trader/quant/sizing.py` — added `adaptive_sl_tp_levels` (delegates to `sl_tp_levels`)
- `src/catalyst_trader/quant/__init__.py` — re-exported the 4 new tools + `__all__`
- `tests/test_events.py` — created: 37 cases (22 estimator, 15 log-growth/hold-vs-exit)
- `tests/test_sizing.py` — extended: 11 adaptive-SL/TP cases

## Decisions Made
See `key-decisions` frontmatter. Core: implied_move magnitude-only prior; median central estimate; log-growth (not raw EV) decision at a survival-constrained f; params-required raise discipline; `default_down_move` deliberately unused.

## Deviations from Plan
None - plan executed exactly as written. (`default_down_move` was named in a plan signature comment but the plan body mandates a RAISE on empty-branch-no-prior; using it would contradict that invariant, so it was correctly left out — not a deviation, the plan's behavior block governs.)

## Issues Encountered
None. Pydantic's `dict` inputs field preserved the outcome tuples verbatim, so the QUANT-03 reproducibility snapshot works without coercion.

## User Setup Required
None - pure-python, offline, no external service configuration.

## Next Phase Readiness
- The estimator's `detail.up_move`/`detail.down_move` are the inputs plans 05-03..05-07 wire into risk-of-ruin (gap), the TP anchor, and the `hold_vs_exit` branches.
- All four tools are on the `catalyst_trader.quant` public surface and fully tested.
- No blockers.

## Self-Check: PASSED

All created files present (events.py, test_events.py, 05-02-SUMMARY.md); all 6 task commits (3 test + 3 feat) verified in git history.

---
*Phase: 05-trade-builder-honest-hedge-ruin-avoidant-sizing-workflow-1b-2*
*Completed: 2026-08-15*
