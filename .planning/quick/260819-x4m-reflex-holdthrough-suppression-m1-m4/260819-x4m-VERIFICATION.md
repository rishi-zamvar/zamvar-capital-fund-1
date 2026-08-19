---
phase: 260819-x4m-reflex-holdthrough-suppression-m1-m4
verified: 2026-08-19T00:00:00Z
status: passed
score: 4/4 truths verified
verdict: PASS
notes: >
  All four must_have truths met. M1 whole-hold suppression is genuinely and completely
  wired (all 42 daily catalyst legs exit reason="time", zero band/stop/tp — verified by
  running the engine, not by trusting SUMMARY). M4 headline + 3 caveats + off_map re-emit
  present. Edge restored directionally (-4.18% -> +7.67%, off_map 0.0%). Scope held to M1+M4.
  ONE finding recorded (non-blocking): the SUMMARY's characterization of the residual
  daily-vs-weekly gap as "entry-basis + exit-bar-granularity NOISE" is imprecise and
  understated. The residual is a SYSTEMATIC, directional exit-timing + entry-window effect,
  not noise. It does not block this mitigation; it names the next lever (Task-B exit timing).
residual_finding:
  title: "Weekly baseline is hold-to-gap-OPEN, not hold-to-time-barrier — the ~7.65pp/leg residual IS an exit-timing gap, not noise"
  status: non_blocking_second_order
  feeds: "future Task-B outcome-conditioned exit-timing mitigation (calibrate on the forward paper month, NOT these 42 in-sample legs)"
---

# Phase 260819-x4m — Reflex Hold-Through Suppression (M1) + Measurement Hygiene (M4) Verification

**Phase Goal:** A hold-through catalyst leg no longer gets price-exited by the daily reflex — the edge is restored — and the go/no-go reads the right number with the right caveats.
**Verified:** 2026-08-19
**Status:** PASS
**Re-verification:** No — initial verification.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| - | ----- | ------ | -------- |
| 1 | A `held_through=True` daily leg fires NO band/stop/tp — exits ONLY at the TIME barrier (or halt roll) | ✓ VERIFIED | `fill.py:191-194` guard `if held_through: continue` sits after `_skip` and after the TIME-barrier branch; loop can only reach the price-detection block when `held_through` is False. Live engine run over the real cache: **all 42 daily catalyst legs exit_reason == "time"** (0 band, 0 stop, 0 tp). Unit tests `test_held_through_dip_then_recover_holds_to_time_barrier` + `test_held_through_spike_then_fade_does_not_take_profit` + `test_held_through_still_off_map_on_halt_roll` all green. |
| 2 | A `held_through=False` daily leg still fires band/stop/tp exactly as before (byte-for-byte) | ✓ VERIFIED | Default `held_through: bool = False` in `reflex_exit` signature (`fill.py:139`) keeps every direct caller unchanged. `test_non_held_through_still_fires_band_stop_tp` (band exit) + `test_weekly_default_path_is_byte_for_byte` green. Weekly path calls `fill_price`, never `reflex_exit` (`engine.py:235`); reflex only reachable in the daily branch. |
| 3 | Daily hold-through paired return converges toward the weekly baseline — edge restored, no longer -4.18% | ✓ VERIFIED | Regenerated FINDINGS §1 (cache-only, 0 network): daily paired mean **+7.67%** (sum +321.95%) vs weekly **+15.31%** (sum +643.16%) on 42 paired legs. Pre-fix was daily -4.18% / weekly +12.68% / ~810pp destroyed. off_map re-measured **0/108 = 0.0%**. Direction of the edge is restored: daily flipped from net-destructive to strongly net-positive. (See adjudication for the residual gap — it is real and named, not a bug.) |
| 4 | `run_daily_backtest` emits the PAIRED covered-subset headline + in-sample warning + entry-basis caveat + post-fix off_map re-emit | ✓ VERIFIED | §1 "Paired covered-subset comparison (PRIMARY go/no-go)" present as headline; six prior sections renumbered §2–§7. All three caveats present inline: (i) IN-SAMPLE HEALTH WARNING, (ii) ENTRY-BASIS CAVEAT, (iii) POST-FIX off_map RE-EMIT (pre-fix 1/48 marked provisional). `--smoke` populates §1 offline and asserts all three caveat markers. |

**Score:** 4/4 truths verified.

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/catalyst_trader/backtest/fill.py` | `reflex_exit` accepts `held_through`; when True suppresses band/stop/tp for whole hold, keeps TIME barrier + halt roll | ✓ VERIFIED | Guard at line 191-194, placed AFTER `_skip` (188) and AFTER the TIME-barrier branch (180-186) so the time exit stays reachable. No catastrophic-gap guard. No new magic numbers (only the boolean flag). Docstring updated (166-169). |
| `src/catalyst_trader/backtest/engine.py` | `_fill_leg` threads `held_through` into the daily `reflex_exit` call | ✓ VERIFIED | Line 227: `exit_latency_bars=exit_latency_bars, held_through=held_through`. Weekly path (235) untouched. |
| `tests/test_backtest_reflex.py` | hold-through suppression tests + non-hold regression + updated pre-fix test to new contract | ✓ VERIFIED | 4 new M1 tests + `test_daily_reflex_holds_through_collapse_to_time_barrier` (renamed from `..._surfaces_off_map_on_leg`) now asserts `exit_reason=="time"` / `off_map is False`. |
| `tests/test_backtest_latency_sweep.py` | second pre-fix test updated to new contract | ✓ VERIFIED | `test_off_map_leg_carries_flag` switched to a halt-roll provider (asserts off_map True / reason "halt"); collateral `test_latency_sweep_shows_degradation_with_delay` provider redesigned to hold-to-barrier with latency-shifted fills. |
| `scripts/run_daily_backtest.py` | paired §1 headline + caveats, derived from computed LegOutcomes | ✓ VERIFIED | `paired_covered_subset` pairs catalyst legs by (week, ticker) from already-computed weekly/daily LegOutcomes (CONCERN-1 approach a). `collect()` NOT lifted; `_diag_exit_breakdown.py` untouched. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `engine.py::_fill_leg` | `reflex_exit` | `held_through=held_through` kwarg (daily branch) | ✓ WIRED | Line 227. |
| `fill.py::reflex_exit` | TIME-barrier-only exit for held_through | `if held_through: continue` guard | ✓ WIRED | Line 191; TIME branch at 180-186 reachable first each bar. |
| `run_daily_backtest.py` | paired subset | `paired_covered_subset(weekly_res, daily_res)` | ✓ WIRED | Lines 257 (live) + 308 (smoke); §1 populates under both cache and `--smoke`. |

### Behavioral Spot-Checks (run, actual output)

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Five money-path suites green | `pytest tests/test_backtest_{reflex,fill,engine,latency_sweep,daily_provider}.py -q` | **66 passed, 1 xfailed** (the deferred Task-B `test_off_map_escalates_to_reasoning_agent`) | ✓ PASS |
| Offline generator | `run_daily_backtest.py --smoke` | `run_daily_backtest --smoke: OK (7 sections + 3 caveats + paired subset populated)` | ✓ PASS |
| Cache-only regen | `run_daily_backtest.py` | `wrote 260819-p1x-FINDINGS.md (5422 bytes)`; §1 daily mean **+7.67%**, weekly **+15.31%**, off_map **0/108 = 0.0%** | ✓ PASS |
| No residual reflex culling | live engine, exit_reason tally on all daily catalyst legs | `{'time': 42}` — zero band/stop/tp | ✓ PASS |

### Anti-Patterns Found

None. No new magic numbers (only the boolean `held_through`, reusing the flag `_fill_leg` already carries). No duplication (one guard in shared `reflex_exit`; M4 reuses computed outcomes rather than lifting `collect()`). Guard placement is correct — the TIME barrier remains reachable, so a hold-through leg is never stranded.

## Scope Discipline (confirmed in-scope, nothing extra)

Verified NOT present (all vetter-rejected / deferred): M2 trailing stop, M2 catalyst-magnitude tp re-anchor, M1 catastrophic-gap guard (`2·vol_move`), M3 off_map-flag-on-bad-fill, M3 close-confirmation, any threshold tuning on the 48 legs. off_map re-measured to **0.0%** post-fix (the Task-B input). Scope stayed exactly M1 + M4.

---

## CRITICAL ADJUDICATION — the residual daily-vs-weekly gap

**Executor's claim:** the residual (daily +7.67% vs weekly +15.31%, HURT 25 / HELPED 17) is "the disclosed entry-basis difference + exit-bar granularity — NOT a new bug or lingering winner-culling."

**Verdict: the DIRECTIONAL claim is CORRECT and the fix is genuinely complete — but the "noise" framing is imprecise and understated. I CHALLENGE it.** I traced the per-leg mechanics on the actual cache (not the SUMMARY).

### What is fully confirmed (the fix is real, not a stub)
- **All 42 daily catalyst legs exit `reason == "time"`. Zero band/stop/tp.** There is NO lingering winner-culling and NO gap-open fill penalty on entry beyond the disclosed next-open basis. M1 did exactly what it claims.
- Recovery is real: the reflex went from culling winners (-4.18%) to holding them (+7.67%), a genuine ~+11.85pp/leg improvement, and off_map collapsed to 0.0%.

### Why "noise" is the wrong word — the residual is SYSTEMATIC, not random
The HURT/HELPED split is directional: of the 25 HURT legs, daily still ends positive on only **1**; 24 are gap-then-fade names. Two distinct, LARGE, directional structural effects drive it — and per-leg tracing shows they are *not small* against the residual:

1. **Entry basis (large for gap events).** Weekly enters at the decision-week CLOSE (pre-event); daily enters at the next tradeable daily OPEN, which for a catalyst that gaps at the open is *already post-gap*. Example RAPP: weekly entry **14.36**, daily entry **38.42** — the entire +166% catalyst move happened *between* the two entry points, so the daily path structurally missed the overnight gap.

2. **Exit policy (not merely "granularity").** The weekly "hold-through" model exits at the hold-week **OPEN** (`fill_price` uses `bar["open"]` = the gap open). The daily model holds all the way to the weekly **TIME barrier** (`exit_by = as_of + 7d`, end of hold week) through the post-event fade. These capture **disjoint, adjacent windows**: weekly = the catalyst gap; daily = everything *after* the gap. RAPP again: weekly exits at **38.42** (the gap open) = *exactly the price the daily path enters at*, then daily rides it down to **23.76**.

**The load-bearing correction:** the vet's premise that "the weekly baseline IS hold-to-barrier, so holding to the barrier recovers the edge" is factually off. The weekly baseline is **hold-to-gap-OPEN**, not hold-to-time-barrier. Holding to the time barrier (what the daily path now correctly does) does **not** reproduce the weekly number precisely *because* it holds through the fade the weekly gap-open exit avoids. The ~7.65pp/leg residual **IS** that exit-timing difference — a real strategy difference, not measurement noise.

### Is it a bug or a blocker? No.
- It is **not** a bug in M1 (all exits are "time"; suppression is complete).
- It is **not** lingering winner-culling (verified: zero price exits).
- It **does not** block this mitigation, which correctly did the one structural thing the adversarial vet cleared: stop the culling. Scope was M1+M4, and both are correct.

### The precise second-order finding (feeds a FUTURE mitigation, not this one)
The remaining lever is **EXIT TIMING**, not more suppression: the daily hold-through leg exits at the Friday time barrier and systematically gives the catalyst gap back to the post-event fade; the weekly baseline's superiority comes from exiting at/near the **event-day open**. Closing the residual would mean an earlier, event-anchored exit — which is exactly the **Task-B outcome-conditioned exit** territory the vet deferred, and it **must** be calibrated on the forward paper month, never on these 42 in-sample legs (curve-fit risk). Recommend the SUMMARY's "entry-basis + exit-bar-granularity noise" line be sharpened to: *"a systematic exit-timing gap (weekly captures the gap at the hold-week open; daily holds through the post-event fade to the weekly time barrier) plus a post-gap entry basis — a Task-B exit-timing question, not noise and not a bug."*

## Gaps Summary

No gaps. All four must_have truths met, all artifacts substantive + wired + data-flowing, all key links wired, scope held, tests green (66 passed / 1 expected xfail), edge restored directionally and reproducibly cache-only. The single residual is a correctly-out-of-scope, precisely-named second-order exit-timing finding for a future Task-B mitigation.

---

_Verified: 2026-08-19_
_Verifier: Claude (gsd-verifier)_
