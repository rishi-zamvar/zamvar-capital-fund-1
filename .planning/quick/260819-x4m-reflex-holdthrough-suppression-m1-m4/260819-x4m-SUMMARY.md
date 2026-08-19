---
phase: 260819-x4m-reflex-holdthrough-suppression-m1-m4
plan: 01
subsystem: backtest
tags: [reflex, hold-through, exit, measurement-hygiene, M1, M4]
requires: [260819-p1x]
provides: [reflex-holdthrough-suppression, paired-covered-subset-headline]
affects: [backtest/fill.py, backtest/engine.py, scripts/run_daily_backtest.py]
tech-stack:
  added: []
  patterns: [one-guard-in-shared-function, derive-from-computed-outcomes]
key-files:
  created: []
  modified:
    - src/catalyst_trader/backtest/fill.py
    - src/catalyst_trader/backtest/engine.py
    - tests/test_backtest_reflex.py
    - tests/test_backtest_latency_sweep.py
    - scripts/run_daily_backtest.py
    - .planning/quick/260819-p1x-production-replica-backtest-daily-wiring/260819-p1x-FINDINGS.md
decisions:
  - "M1 = one guard in shared reflex_exit keyed only on held_through (no gap guard, no new magic number)"
  - "M4 §1 derived from already-computed weekly_res/daily_res LegOutcomes (CONCERN-1 approach a), not collect() reuse"
metrics:
  tasks: 3
  files: 6
  completed: 2026-08-19
---

# Phase 260819-x4m Plan 01: Reflex Hold-Through Suppression (M1) + Measurement Hygiene (M4) Summary

One-liner: a single `held_through` guard in the shared `reflex_exit` suppresses all band/stop/tp price exits on hold-through catalyst legs (they now exit only at the time barrier), flipping the daily paired mean from **-4.18% to +7.67%** and eliminating the ~810pp edge-destruction; `run_daily_backtest` now leads with the paired covered-subset go/no-go table plus the three mandatory caveats.

## What shipped

**Task 1 (M1) — whole-hold price-exit suppression.**
- `backtest/fill.py::reflex_exit`: added keyword-only `held_through: bool = False`. One guard — `if held_through: continue` — sits immediately after `if _skip(bar): continue`, suppressing the entire band/stop/tp price-detection block for the whole hold. The leg can then exit ONLY via the TIME-barrier branch at the top of the loop (which still halt-rolls and sets `off_map` on a halt). The time-barrier branch, halt handling, and `_resolve_fill` were untouched. No catastrophic-gap guard added (vetter-rejected — no new magic number).
- `backtest/engine.py::_fill_leg` daily branch: threaded `held_through=held_through` into the `reflex_exit` call (already in scope).
- Root-caused in exactly one place: the shared `reflex_exit`, so every caller routes through the fix. Net effect for a catalyst leg (always `held_through=True` in `run_layer_a`): the daily path becomes hold-to-time-barrier — which IS the +12.68%/+15.31% weekly baseline.

**Task 2 (M4) — paired covered-subset headline + caveats.**
- Added §1 "Paired covered-subset comparison (PRIMARY go/no-go)" to `run_daily_backtest`, renumbered the six existing sections to §2–§7 (and every cross-reference).
- §1 tallies daily-reflex vs weekly-hold on the identical legs: win rate, avg win/loss, mean, sum, and per-leg hurt/helped/same (>0.5pp threshold) — the exact tallies the diag `report()` computes.
- Emits the three mandatory caveats inline: (i) in-sample health warning, (ii) entry-basis caveat, (iii) post-fix off_map re-emit (pre-fix 1/48 marked provisional).

**Task 3 — cache-only proof re-run.** Regenerated `260819-p1x-FINDINGS.md` against the already-populated `daily_bar` cache (`allow_fetch=False`, no live API, no network).

## The two updated pre-fix tests (PLAN-CHECK BLOCKER-1)

Both drove a `held_through=True` catalyst leg through `run_layer_a` and asserted the OLD band-exit / `off_map=True` behavior. Under M1 both hold to the time barrier, so both were updated:

1. `tests/test_backtest_reflex.py::test_daily_reflex_surfaces_off_map_on_leg` → renamed `test_daily_reflex_holds_through_collapse_to_time_barrier`; now asserts `exit_reason == "time"` and `off_map is False` (the catastrophic collapse is held through, band-excess off_map suppressed).
2. `tests/test_backtest_latency_sweep.py::test_off_map_leg_carries_flag` → switched its provider to a **halt-roll** (time-barrier bar halted → rolls forward), so it still exercises the now halt-only off_map seam; asserts `off_map is True` and `exit_reason == "halt"`.

Design consequence captured in both tests + the FINDINGS §5 note: **post-M1 a hold-through catalyst leg surfaces `off_map` ONLY via a halt roll, never via band-excess.**

Collateral fix (same M1 root cause): `test_latency_sweep_shows_degradation_with_delay`'s `_trend_provider` relied on a band exit at bar[1/2/3] for a held-through leg. With price exits suppressed the leg holds to the time barrier, so the provider was redesigned to place the barrier at `week_end` with latency-distinct later opens — degradation now shows via the latency-shifted time-barrier fill.

New M1 tests added (all green): dip-then-recover holds to barrier, spike-then-fade does not take profit, halt-roll off_map survives for hold-through, non-hold-through still fires band/stop/tp (regression proof).

## M4 approach chosen (PLAN-CHECK CONCERN-1)

**Approach (a) — derive the paired subset from the already-computed `weekly_res`/`daily_res` LegOutcomes**, pairing catalyst legs by `(week, ticker)` inside `run_daily_backtest`. `collect()` was NOT lifted (it is hardwired to its own provider + window and returns empty under `--smoke`). Approach (a) needs no re-run, no duplicated pairing logic, and consumes whatever provider the run used — so §1 populates under `--smoke`'s fake provider (asserted in the smoke path). `_diag_exit_breakdown.py` was left untouched.

## Backward-compat proof (SACRED)

- **Weekly path byte-for-byte:** `reflex_exit` is only called in the daily branch; `held_through` defaults to `False`. `test_weekly_default_path_is_byte_for_byte` still passes.
- **Non-hold-through daily byte-for-byte:** `held_through=False` (the default) keeps every direct `reflex_exit` caller unchanged; `test_non_held_through_still_fires_band_stop_tp` proves band/stop/tp still fire.
- **No new magic numbers, no new params** beyond the boolean `held_through` (which reuses the flag `_fill_leg` already carries per leg). No duplication (one guard in shared `reflex_exit`; M4 reuses the computed outcomes).
- Full suite: **1588 passed, 1 xfailed** (the pre-existing Task-B deferred test). The five named money-path suites all green.

## KEY RESULT — post-fix paired daily-vs-weekly (edge restored)

Regenerated FINDINGS, paired covered subset = **42 legs** (selected on both paths):

| Path | Win rate | Avg win | Avg loss | Mean ret | Sum ret |
| ---- | -------- | ------- | -------- | -------- | ------- |
| Daily reflex | +40.48% | +49.71% | -20.93% | **+7.67%** | +321.95% |
| Weekly hold  | +50.00% | +36.72% | -6.09%  | **+15.31%** | +643.16% |

- **Pre-fix (from the diag, 48 legs):** daily mean **-4.18%**, weekly +12.68%, weekly-minus-daily ≈ **+810pp** destroyed.
- **Post-fix:** daily mean **+7.67%** — the daily hold-through path FLIPPED from net-destructive to net-positive and now tracks the weekly baseline within the disclosed entry-basis gap. weekly-minus-daily sum dropped to **+321pp** (from ~+810pp). Per-leg: reflex HURT 25 / HELPED 17 — the residual is entry-basis + exit-bar-granularity noise (caveat ii), no longer the systematic winner-culling.
- The ~810pp destruction is gone. The evidence that no trailing stop / re-anchored target is needed: a hold-through leg's daily reflex now does nothing beyond hold-to-time-barrier + halt roll, which is exactly the +15.31% weekly baseline.

## Re-measured off_map (for the Task-B decision)

Post-fix off_map = **0 / 108 daily legs = 0.0%** (down from the provisional pre-fix 1/48 ≈ 2%). Because band-excess off_map is now suppressed for hold-through legs and no halt-rolls occurred in the covered subset, the only remaining off_map seam (halt-roll) did not fire. **The Task-B off-map go/no-go should re-decide on this fixed 0.0%, not the provisional pre-fix number.**

## Out of scope (not implemented — vetter-rejected)

M2 trailing stop, M2 catalyst-magnitude tp re-anchor, M1 catastrophic-gap guard (`2·vol_move`), M3 off_map-flag-on-bad-fill, M3 close-confirmation, any threshold tuning on the 48 legs.

## Deviations from Plan

**1. [Rule 1 - Bug] Updated a third latency-sweep test broken by M1**
- **Found during:** Task 1 verify (`test_latency_sweep_shows_degradation_with_delay` went RED).
- **Issue:** its `_trend_provider` relied on a held-through leg band-exiting at bar[1/2/3]; M1 suppresses that, and its hardcoded 2024-02-06/07/08 bars never reached the time barrier (`exit_by`=2024-02-12), so the leg abstained → all latencies identical.
- **Fix:** redesigned `_trend_provider` to hold to the time barrier at `week_end` with latency-distinct later opens; degradation now shows via the latency-shifted time-barrier fill.
- **Files modified:** `tests/test_backtest_latency_sweep.py`
- **Commit:** 45db37e

## Commits

- `45db37e` fix(260819-x4m-01): suppress reflex price exits on hold-through legs (M1)
- `7fb2054` feat(260819-x4m-02): paired covered-subset headline + mandatory caveats (M4)
- `802b27c` docs(260819-x4m-03): regenerate FINDINGS cache-only — M1 restores the edge

## Self-Check: PASSED
