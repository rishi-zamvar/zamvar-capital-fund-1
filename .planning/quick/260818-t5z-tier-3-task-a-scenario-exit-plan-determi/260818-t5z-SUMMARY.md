---
phase: quick-260818-t5z
plan: 01
subsystem: backtest
tags: [exit-plan, reflex, latency-honest, backtest, triple-barrier, football-field]

# Dependency graph
requires:
  - phase: desk/builder + quant/sizing
    provides: adaptive_sl_tp_levels, size_for_survival, catalyst_move_estimate, the football-field/verdict numbers the Exit Plan reads
  - phase: backtest/fill + backtest/engine
    provides: _skip/_worsen gap-open discipline, run_layer_a weekly loop, the serving-gateway fill seam
provides:
  - deterministic ExitPlan authored at entry (band + scenario table + typed thesis-invalidation + hard TIME barrier + EV-flip guard) — no agent in the hot path
  - fill.reflex_exit() — intraweek daily exit model (next-bar-open fills, gap-open stops, halt roll, off_map seam)
  - engine granularity + daily_bars_provider + exit_latency_bars knobs on run_layer_a/_fill_leg; off_map/exit_reason on LegOutcome
  - latency_sweep() T+0/T+1/T+2 degradation helper
  - the off-map -> Task-B reasoning-latency escalation seam (flag + deferred xfail)
affects: [tier-3-task-b, backtest-production-wiring, exit-review, desk-dashboard]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "EXIT_PARAMS module-level threshold dict (diligence.DILIGENCE_PARAMS precedent) — direct subscript, missing key raises, no literal fallback"
    - "granularity knob whose DAILY setting is a superset of the byte-for-byte-preserved WEEKLY money-path"
    - "injected daily_bars_provider seam (mirrors verify_moves' bars_provider) — offline tests, production wiring deferred"
    - "deferred wiring ships as a strict xfail test in the introducing PR"

key-files:
  created:
    - src/catalyst_trader/desk/exit_plan.py
    - tests/test_exit_plan.py
    - tests/test_backtest_reflex.py
    - tests/test_backtest_latency_sweep.py
  modified:
    - src/catalyst_trader/contracts/__init__.py
    - src/catalyst_trader/desk/builder.py
    - src/catalyst_trader/backtest/fill.py
    - src/catalyst_trader/backtest/engine.py

key-decisions:
  - "OFF_MAP_MULT is an EXIT_PARAMS key (C2), not a bare literal in fill.py — a NEW threshold follows the dict discipline; fill.py's half_spread literals stay grandfathered"
  - "Exit Plan is PURE/deterministic — the agentic authoring is Task B; this computes the plan from the football-field/verdict numbers the desk already produced"
  - "The Exit Plan NEVER resizes — size_for_survival stays the sole sizing owner"
  - "Daily reflex fills entries AND exits at next-bar open; stops fill at the gap open, never the stop level (reuses _skip/_worsen)"
  - "off_map is a MARK only — the reflex still exits deterministically/pessimistically; Task B's brain is out of scope"

patterns-established:
  - "Pure deterministic authoring module + module-level param dict for money thresholds"
  - "granularity/latency knobs default to the current behaviour so the existing money-path is byte-for-byte preserved"

requirements-completed: [EXIT-PLAN, REFLEX, LATENCY-HONEST]

# Metrics
duration: ~40min
completed: 2026-08-19
---

# Tier-3 Task A: Scenario Exit Plan + Intraweek Reflex + Latency-Honest Backtest Summary

**The desk now pre-commits a deterministic Exit Plan at entry (band + scenario table + typed thesis-invalidation + hard TIME barrier + EV-flip guard) and the production-replica backtest runs a daily intraweek reflex with next-bar-open fills, gap-open stops, halt handling, and a T+0/1/2 latency sweep — with the entire existing weekly money-path preserved byte-for-byte.**

## Performance

- **Duration:** ~40 min
- **Tasks:** 3/3 (each strict TDD: RED test -> GREEN minimum code)
- **Files:** 4 created, 4 modified
- **Tests:** 36 new (16 exit_plan + 12 reflex + 8 latency_sweep) + 1 deferred xfail; full suite 1571 passed / 1 xfailed

## Accomplishments

- **Task 1 — deterministic Exit Plan:** `desk/exit_plan.py::build_exit_plan()` is pure/deterministic and authors the whole plan from numbers the builder already holds. `EXIT_PARAMS` holds every threshold (direct subscript, missing key raises). Wired into `builder.build()` and attached via the new optional `TradeProposal.exit_plan` — every other proposal field stays byte-for-byte (`out_default == out_explicit` still holds); sizing untouched.
- **Task 2 — intraweek daily reflex:** `fill.reflex_exit()` fires the first triggered exit (band / adaptive stop / take-profit / hard TIME barrier), filling at the next bar open; a stop that gaps fills at the gap open (never the stop level); a halted fill bar rolls to the next available open, no resumption -> None. The `granularity="daily"` engine path reuses `adaptive_sl_tp_levels` for stop/target and threads through `run_layer_a`. Weekly stays the coarsest, byte-for-byte-preserved knob.
- **Task 3 — latency-honest fills + sweep:** daily entries AND exits fill at next-bar open; `exit_latency_bars` shifts the exit fill (degrading to the last open past the window); `latency_sweep()` reports T+0/1/2 degradation. `off_map` surfaces on the `LegOutcome`; Task B's off-map reasoning-latency exit ships as a strict xfail.

## Task Commits

1. **Task 1: deterministic Exit Plan authored at entry** - `6ec874d` (feat)
2. **Task 2: intraweek daily reflex (weekly preserved as coarsest knob)** - `7715497` (feat)
3. **Task 3: latency-honest fills + T+0/1/2 sweep + off-map/Task-B seam** - `6c43cf9` (feat)

## Reuse Map (wired, NOT rebuilt)

| Reused tool | Where | How |
|-------------|-------|-----|
| `adaptive_sl_tp_levels` (quant/sizing.py) | `_fill_leg` daily branch | derives stop/target prices for the reflex |
| `size_for_survival` (desk/risk.py) | builder | untouched — Exit Plan never resizes |
| `fill._skip` / `fill._worsen` (backtest/fill.py) | `reflex_exit` / `_resolve_fill` | gap-open + halt-skip + slippage discipline reused, not re-implemented |
| `diligence.DILIGENCE_PARAMS` pattern | `exit_plan.EXIT_PARAMS` | module-level threshold dict, missing-key-raises |
| verify_moves `bars_provider` seam | `daily_bars_provider` | injected offline daily-bar callable |
| `run_layer_a` | `latency_sweep` | thin re-run-and-collect, no new money math |
| `tests/synth_history.py` + `_seed_std` | all new offline tests | `:memory:` + migrate + injected synthetic bars |

## Plan-Check Follow-ups Honored

- **C1:** `_fill_leg` gained `up_move`/`vol_move`/`params` (defaulted -> weekly callers unchanged); the catalyst-leg call passes `ev` as up_move and `stat_gap` as vol_move. `ev` is now computed just before the fill (pure of `filled`, so the weekly value/ordering is unchanged). Only the daily branch consumes them.
- **C2:** `OFF_MAP_MULT` lives as `EXIT_PARAMS["off_map_mult"]` (not a literal in fill.py); `reflex_exit` takes `off_map_mult`, the daily `_fill_leg` passes `EXIT_PARAMS["off_map_mult"]`.

## Backward-Compat Proof

Weekly money-path and existing TradeProposal fields byte-for-byte. Green regression suites:
`test_backtest_engine`, `test_backtest_fill`, `test_backtest_events`, `test_backtest_gate`,
`test_desk_builder` (incl. `out_default == out_explicit`), `test_contracts`, `test_backtest_latency`.
A dedicated test asserts `run_layer_a` default == explicit `granularity="weekly"` (results + distribution) with the new `off_map`/`exit_reason` LegOutcome fields defaulting `False`/`None`. Full suite: **1571 passed, 1 xfailed**.

## Deviations from Plan

None — plan executed as written (both plan-check follow-ups folded in as specified).

## Deferred

- **Task B — off-map reasoning brain:** the agentic single-reasoning-agent exit with a reasoning-latency-modeled fill. Only the `off_map` flag on `LegOutcome` + the strict xfail `test_off_map_escalates_to_reasoning_agent` exist today (no `engine.reasoning_exit` hook built).
- **Production wiring of `providers.prices.get_daily_bars`:** `daily_bars_provider` is the injected offline seam; wiring a real as-of-scoped daily-bar provider (no-look-ahead, mirrors the options_snapshot backtest provider) is a later main-dir step. All Task-A tests inject synthetic bars.

## Self-Check: PASSED

- Files exist: `src/catalyst_trader/desk/exit_plan.py`, `tests/test_exit_plan.py`, `tests/test_backtest_reflex.py`, `tests/test_backtest_latency_sweep.py` (all FOUND).
- Commits exist: `6ec874d`, `7715497`, `6c43cf9` (all FOUND in git log).
- All three new suites + all named regression suites green; full suite 1571 passed / 1 xfailed.
