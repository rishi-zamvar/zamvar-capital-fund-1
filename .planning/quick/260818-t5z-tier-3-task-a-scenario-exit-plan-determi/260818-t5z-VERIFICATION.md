---
phase: quick-260818-t5z
verified: 2026-08-19T00:00:00Z
status: passed
score: 7/7 must-haves verified
---

# Tier-3 Task A: Scenario Exit Plan + Intraweek Reflex + Latency-Honest Backtest — Verification Report

**Phase Goal:** Ship the DETERMINISTIC exit core (no agent in the hot path): an Exit Plan authored at entry (band + scenario table + typed thesis-invalidation + hard TIME barrier + EV-flip guard), an intraweek daily reflex in the backtest with honest fills, and latency-honest fills + a T+0/1/2 sweep — with the weekly money-path byte-for-byte preserved and an off-map/Task-B deferred seam.

**Verified:** 2026-08-19
**Status:** PASS
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Deterministic Exit Plan (band + scenario table + typed thesis-invalidation + hard TIME barrier + EV-flip guard) authored from football-field/verdict; no agent in hot path; `EXIT_PARAMS` module-level with missing-key-raises; `off_map_mult` in EXIT_PARAMS not a fill.py literal | ✓ VERIFIED | `desk/exit_plan.py:41-89` `build_exit_plan` is pure (no conn/LLM/I/O); `EXIT_PARAMS` at `:23-28` direct subscript incl `off_map_mult` (:27); `fill.py` has NO `1.5` literal (grep clean), `off_map_mult` is a param at `fill.py:137,205` |
| 2 | `ExitPlan`/`ScenarioRow`/`ThesisInvalidation`/`EvFlipGuard` all extra="forbid"+frozen; `TradeProposal.exit_plan` optional default None | ✓ VERIFIED | `contracts/__init__.py:120,131,141,154` all `ConfigDict(extra="forbid", frozen=True)`; `:181` `exit_plan: ExitPlan | None = None` |
| 3 | Builder authors plan + sets `TradeProposal(exit_plan=...)`; every other field byte-for-byte; `size_for_survival` still owns sizing (no resize in exit_plan path) | ✓ VERIFIED | `desk/builder.py:261-266` `build_exit_plan(...)`, `:286` `exit_plan=exit_plan`; `:215,276` `size = risk.size_for_survival(...)` → `size_pct=size.value` unchanged; `build_exit_plan` signature takes/returns no size; `test_desk_builder` green incl `out_default==out_explicit` |
| 4 | Daily reflex: first-to-hit band/stop/tp/time; next-bar-open fills; gap-open stops (fill is gap open, never stop level); halt rolls to next-available-open, None if none; reuses `_worsen`/`_skip`; weekly byte-for-byte | ✓ VERIFIED | `fill.py:127-210` `reflex_exit` pure, TIME-first then band/stop/tp per bar, fill at `i+1` open; `_resolve_fill:101-124` fills at bar open (never stop level), rolls past `_skip` bars, returns None w/o resumption, reuses `_worsen`; weekly assertion `test_backtest_reflex.py:153-160` `default_res == weekly_res` |
| 5 | `LegOutcome` gains `off_map`/`exit_reason` optional; `_fill_leg`+`run_layer_a` gain `granularity`/`daily_bars_provider` (C1 up_move/vol_move/params threaded+defaulted); weekly path byte-for-byte; `latency_sweep()` T+0/1/2 degradation; `exit_latency_bars` shifts exit fill | ✓ VERIFIED | `engine.py:70-71` optional fields; `:186-188` `_fill_leg` new params defaulted; `:270-274` `run_layer_a` knobs; C1 threaded `:312-317`; `latency_sweep:382-399` re-runs per delay; `exit_latency_bars` shifts fill `fill.py:176,196` |
| 6 | Off-map escalation seam (flag on LegOutcome) + a COLLECTED xfail test marking Task B's reasoning-latency path deferred | ✓ VERIFIED | `engine.py:70` `off_map`; `test_backtest_latency_sweep.py:141-149` `@pytest.mark.xfail(strict=True)` `test_off_map_escalates_to_reasoning_agent` asserts `hasattr(engine,"reasoning_exit")`; pytest collected it: `1 xfailed` |
| 7 | No-look-ahead: reflex reads only bars at/after signal; signal-at-close → next-bar-open on BOTH entries and exits | ✓ VERIFIED | Entry: `engine.py:215-218` entry fills at first tradeable daily-bar open (next open after as_of close); Exit: `fill.py:196` fill at `i+1` open; `_resolve_fill` never reads before `fill_idx` |

**Score:** 7/7 truths verified

### Required Artifacts

| Artifact | Status | Details |
| --- | --- | --- |
| `desk/exit_plan.py` | ✓ VERIFIED | 89 lines; `build_exit_plan` + `EXIT_PARAMS` + `ev_flip_guard`; pure |
| `contracts/__init__.py` | ✓ VERIFIED | `class ExitPlan` (+3 supporting) + `TradeProposal.exit_plan` |
| `desk/builder.py` | ✓ VERIFIED | imports + calls `build_exit_plan`, attaches to proposal, sizing untouched |
| `backtest/fill.py` | ✓ VERIFIED | `reflex_exit` + `_resolve_fill` reusing `_skip`/`_worsen` |
| `backtest/engine.py` | ✓ VERIFIED | LegOutcome fields, `_fill_leg`/`run_layer_a` knobs, `latency_sweep` |
| `tests/test_exit_plan.py` | ✓ VERIFIED | passes |
| `tests/test_backtest_reflex.py` | ✓ VERIFIED | passes incl weekly byte-for-byte |
| `tests/test_backtest_latency_sweep.py` | ✓ VERIFIED | passes + xfail seam |

### Key Link Verification

| From | To | Via | Status |
| --- | --- | --- | --- |
| `builder.py` | `exit_plan.py` | `build_exit_plan(...)` before `TradeProposal(...)` | ✓ WIRED (builder.py:261) |
| `engine.py` | `fill.py` | `reflex_exit` from `_fill_leg` daily branch | ✓ WIRED (engine.py:209-223) |
| `engine.py` | injected `daily_bars_provider` | `run_layer_a` threads it | ✓ WIRED (engine.py:210,315) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| New suites offline | `pytest test_exit_plan test_backtest_reflex test_backtest_latency_sweep -q -rxs` | `36 passed, 1 xfailed in 1.63s` | ✓ PASS |
| Regression byte-for-byte | `pytest test_backtest_engine test_backtest_fill test_backtest_events test_backtest_gate test_desk_builder test_contracts test_backtest_latency -q` | `154 passed in 1.76s` | ✓ PASS |
| Weekly default == no-knob | `test_weekly_default_path_is_byte_for_byte` asserts `default_res==weekly_res` + `default_dist==weekly_dist` | pass | ✓ PASS |
| Task-B xfail collected | `-rxs` output | `XFAIL ... test_off_map_escalates_to_reasoning_agent` | ✓ PASS |

### Offline Purity

grep of the 3 new test files for `get_daily_bars`, `httpx`, `requests`, `urllib`, `socket`, live-DB connect: NONE found. Only `_db.connect(":memory:")` (in-memory) + injected `fake_daily`/synthetic bars. Offline-clean.

### Anti-Patterns Found

None. `off_map_mult` correctly lives in `EXIT_PARAMS` (C2), not a literal in fill.py. C1 `up_move`/`vol_move`/`params` threaded and defaulted so weekly callers are untouched. No stub returns, no TODO/placeholder in the shipped modules.

### Requirements Coverage

| Requirement | Status | Evidence |
| --- | --- | --- |
| EXIT-PLAN | ✓ SATISFIED | Truth 1-3, `test_exit_plan.py` (16 tests) |
| REFLEX | ✓ SATISFIED | Truth 4, `test_backtest_reflex.py` (12 tests) |
| LATENCY-HONEST | ✓ SATISFIED | Truth 5-6, `test_backtest_latency_sweep.py` (8 tests + xfail) |

### Human Verification Required

None for Task A scope. Two items are explicitly deferred (documented, not gaps):
- Task B off-map reasoning-latency exit brain (only the flag + strict xfail seam ship here, by design).
- Production wiring of `providers.prices.get_daily_bars` into `daily_bars_provider` (injected offline seam today; a later main-dir step, as the plan states).

### Gaps Summary

No gaps. All 7 must_have truths are met with file:line evidence; both verification command sets pass (36 passed / 1 xfailed; 154 passed); weekly money-path is proven byte-for-byte (`default_res == weekly_res`); the deferred Task-B path ships as a collected strict xfail per the project's deferred-wiring rule; all new tests are fully offline. The shipped code delivers the phase goal, not merely the tasks.

---

_Verified: 2026-08-19_
_Verifier: Claude (gsd-verifier)_
