---
phase: 07-verifier-guardrails-backtest-harness
plan: 05
subsystem: backtest
tags: [backtest, layer-b, guarded-agentic-replay, biased-optimistic, outcome-blind, web-free, point-in-time, sampling, drop-list, go-no-go-gate, sample-based, offline]

# Dependency graph
requires:
  - phase: 07-verifier-guardrails-backtest-harness
    provides: "07-02 build_event_set (point-in-time, last_verified_at-filtered) + effective_asof; 07-04 BaselineDistribution (win_rate/avg_win-loss/sharpe/sortino/max_drawdown/hedge_effectiveness); 07-03 guardrails._no_scrape_to_order web-free assertion"
  - phase: 04-analyst-desk-bull-bear-debate-workflow-1a
    provides: "desk.orchestrator.run_desk (the REAL Workflow-1a pipeline) + ALLOWED_TOOLS (already web-free); desk.runtime.run_structured (the single mockable SDK seam)"
  - phase: 06-independent-diligence-firewall-workflow-3
    provides: "desk.diligence.DiligenceInput — the extra=forbid outcome-blind firewall technique mirrored here"
provides:
  - "backtest/layerb.py::run_layer_b — the guarded AGENTIC replay of the REAL desk pipeline on historical catalysts, labeled biased_optimistic=True, run on a sample with a logged drop-list (BACK-03)"
  - "OutcomeBlindCatalyst — the extra=forbid look-ahead firewall a historical catalyst is projected onto before run_desk (a leaked realized-outcome field is a ValidationError)"
  - "sample_catalysts + SampleLog — deterministic stratified/random sampling that records EVERY dropped catalyst (no silent [:N] cap)"
  - "backtest/gate.py::sample_based_gate + GateVerdict + THRESHOLDS — the N-driven (never calendar) go/no-go gate consuming the 07-04 BaselineDistribution (BACK-05)"
affects: [08-paper-trading, go-live-gate]

# Tech tracking
tech-stack:
  added: []  # reuses run_desk + guardrails + build_event_set + BaselineDistribution; stdlib random only, NO new dependency
  patterns:
    - "Layer B labels every result biased_optimistic=True as a STRUCTURAL contract field (not a comment) — the honest admission that LLM parametric memory leaks past outcomes even behind a clean prompt + web-free seam; Layer B is never the trustworthy number (that is Layer A / the paper month)"
    - "The historical catalyst is PROJECTED onto OutcomeBlindCatalyst (extra=forbid, mirroring DiligenceInput) BEFORE run_desk — the outcome-blind firewall is a type fact, not a policy check"
    - "The web-free guardrail REUSES the shipped 07-03 guardrails._no_scrape_to_order (reads ALLOWED_TOOLS live) so a monkeypatched web tool is caught — the desk is already web-free, so this is a free assertion seam"
    - "Sampling NEVER silently truncates: sample_catalysts computes the dropped complement and logs it with a reason; the go/no-go gate is sample-based (N-floor first) never calendar — there is no datetime/weeks term in the decision"

key-files:
  created:
    - src/catalyst_trader/backtest/layerb.py
    - src/catalyst_trader/backtest/gate.py
    - tests/test_backtest_layerb.py
    - tests/test_backtest_gate.py
  modified: []

key-decisions:
  - "run_layer_b replays run_desk (the catalyst-call — the prediction Layer B scores) per point-in-time catalyst; run_portfolio/run_diligence are NOT threaded because they need per-verdict risk_inputs (entry/p_loss/gap/analog_gaps/prices) with no added test value offline — run_desk is the honest, testable core of the guarded replay"
  - "Point-in-time feeding rides on build_event_set(latency_cfg=...) (the catalyst last_verified_at <= effective_asof filter) + the store's bars_asof/universe_as_of <= as_of guards; the desk has no separate market-context feed to shift, so the event-set filter IS the point-in-time guarantee for Layer B"
  - "sample_catalysts default strategy is stratified round-robin over catalyst_type (seeded, deterministic) so the sample keeps the type mix; a naive equal round-robin, flagged for a proportional allocator upgrade if needed"
  - "the gate reads thresholds by direct subscript (missing key raises KeyError) — no magic-number fallback in the body; THRESHOLDS is the documented default (min_sample=30 + per-metric floors) the PM retunes post-baseline; an undefined (None) sharpe/hedge_effectiveness is a NAMED failure, never a silent pass"

patterns-established:
  - "Layer B is the (honestly-labeled) optimistic agentic comparison against Layer A's trustworthy mechanical baseline; the sample-based gate is the explicit unlock before the Phase-8 paper month"

requirements-completed: [BACK-03, BACK-05]

# Metrics
duration: 13min
completed: 2026-08-15
---

# Phase 7 Plan 05: Layer B Guarded Replay + Go/No-Go Gate Summary

**The last two backtest pieces: Layer B — the guarded AGENTIC replay that runs the REAL desk pipeline (run_desk) on the 07-02 point-in-time historical catalysts behind web-free + point-in-time + outcome-blind guardrails, labels every result biased_optimistic=True as a structural contract field, and runs on a sample with a logged drop-list (no silent caps); and the go/no-go gate — a sample-based (N-driven, never calendar) verdict computed from the 07-04 BaselineDistribution that names every failing metric. Fully offline via the mocked run_structured seam, zero new dependencies.**

## Performance
- **Duration:** ~13 min
- **Tasks:** 3
- **Files created:** 4

## Accomplishments
- **run_layer_b — guarded replay + honest label + firewalls (Task 1)** — projects each point-in-time historical catalyst onto `OutcomeBlindCatalyst` (`extra=forbid`, a leaked realized-outcome field is a ValidationError), asserts the desk ALLOWED_TOOLS is web-free (reuses `guardrails._no_scrape_to_order`, caught if monkeypatched), runs the REAL `run_desk`, and wraps the verdict in a frozen `LayerBResult` carrying the STRUCTURAL `biased_optimistic=True`. Offline via the run_structured seam patched across analysts/debate/verifier/diligence/md.
- **Sampling + logged drop-list (Task 2)** — `sample_catalysts` (deterministic stratified round-robin by catalyst_type, or seeded random) returns `{sampled, dropped, reason}` and NEVER silently truncates; the `SampleLog` is threaded onto `LayerBBatch` so the caller sees exactly what was replayed vs skipped and why. `run_layer_b` gains `n/strategy/seed`; `n < available` populates the drop-list, `n >= available` is a full replay.
- **sample_based_gate — the go/no-go gate (Task 3)** — the N-floor is checked FIRST: below `min_sample` it is a hard NO-GO regardless of metrics (sample-based, not calendar). Above it, `win_rate/sharpe/max_drawdown/hedge_effectiveness` each clear their floor or are named in `reasons`; an undefined (None) ratio is a named failure. Thresholds read by direct subscript (missing key raises); `THRESHOLDS` is the documented default the PM retunes.

## Task Commits
Each task committed atomically on `main` (TDD RED confirmed before each GREEN):
1. **Task 1: run_layer_b — guarded replay + biased_optimistic + outcome-blind + web-free** — `bb4d23f` (feat)
2. **Task 2: Layer B sampling + logged drop-list (no silent caps)** — `848e5a0` (feat)
3. **Task 3: gate.py — sample-based go/no-go from the baseline distribution** — `26e9ebf` (feat)

## Files Created
- `src/catalyst_trader/backtest/layerb.py` (~170 lines) — `run_layer_b` + `sample_catalysts` + the `OutcomeBlindCatalyst`/`LayerBResult`/`SampleLog`/`LayerBBatch` frozen contracts
- `src/catalyst_trader/backtest/gate.py` (~90 lines) — `sample_based_gate` + `GateVerdict` + the `THRESHOLDS` default
- `tests/test_backtest_layerb.py` — 8 tests: mocked-seam replay, biased_optimistic label, outcome-blind firewall, web-free refusal, sample drop-list, sample-all, no-silent-cap, deterministic sampling
- `tests/test_backtest_gate.py` — 5 tests: insufficient-sample-is-no-go (with strong metrics), go-when-clear, names-each-failing-metric, undefined-metric-named-no-go, missing-threshold-raises

## Decisions Made
- run_layer_b replays `run_desk` (the catalyst call) — the honest testable core of the guarded replay; run_portfolio/run_diligence deferred (need per-verdict risk_inputs, no added offline test value).
- Point-in-time feeding rides on `build_event_set(latency_cfg=...)` + the store `<= as_of` guards.
- Gate reads thresholds by direct subscript (missing key raises); undefined ratio is a named failure; THRESHOLDS is a documented default the PM retunes post-baseline.

## Deviations from Plan
None material. Two clarifications within the plan's stated intent:
- **[Rule 2 - correctness] The web-free assertion REUSES `guardrails._no_scrape_to_order` rather than re-implementing an inline denylist check.** The plan offered either; the shipped 07-03 check already reads both orchestrator + diligence ALLOWED_TOOLS live, so a monkeypatched web tool is caught with zero new logic (the lazy reuse IS the correct fix). Files: `layerb.py`.
- **Layer B replays `run_desk` only** (not the full run_portfolio/run_diligence/reconcile chain). run_desk is the prediction Layer B scores; the heavier chain needs per-verdict risk_inputs that add no offline test value. Documented in the module docstring; grep-confirmed the real pipeline is invoked.

## Issues Encountered
None. Task 2 tests were split out of the initial file so Task 1's atomic commit did not import the not-yet-defined `sample_catalysts` (TDD RED must fail on the assertion, not a collection error).

## User Setup Required
None — fully offline, zero new dependencies, zero external configuration.

## Next Phase Readiness
- Phase 7 is COMPLETE: Layer A (trustworthy baseline) + Layer B (honestly-labeled agentic replay) + the sample-based go/no-go gate are the honest measurement of the whole strategy vs history. The gate is the explicit unlock before the Phase-8 paper month; `THRESHOLDS` is the retune knob and `run_layer_b`'s `n/strategy/seed` bound the (expensive) agentic replay.
- Carry-forward unchanged: real ~1yr earnings/PDUFA calendar ingestion into the store (tests run on the synthetic fixture); real realized-outcome scoring of Layer B predictions belongs with the paper/live outcome record.
- Full suite green: **919 passed** (906 prior + 13 new). 2 pre-existing statsmodels ComplexWarnings (out of scope).

---
*Phase: 07-verifier-guardrails-backtest-harness*
*Completed: 2026-08-15*

## Self-Check: PASSED

All 4 created files exist on disk; all three task commits (`bb4d23f`, `848e5a0`, `26e9ebf`) are in history. `grep biased_optimistic layerb.py` shows the structural field; `grep run_desk layerb.py` confirms the real pipeline is replayed; the gate decision has no datetime/calendar term. Full suite: 919 passed.
