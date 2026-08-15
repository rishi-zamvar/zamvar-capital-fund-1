---
phase: 05-trade-builder-honest-hedge-ruin-avoidant-sizing-workflow-1b-2
plan: 05
subsystem: testing
tags: [verifier, estimate-vetting, cite-or-drop, run_structured, offline-tests, PORT-02, OPS-01]

# Dependency graph
requires:
  - phase: 04-analyst-desk-bull-bear-debate-workflow-1a
    provides: verifier.enforce two-stage structural→semantic gate + evidence.resolve/quote_supported + run_structured seam
  - phase: 05-trade-builder (05-01)
    provides: EstimateVetting contract + TradeProposal.estimate_vetting field
  - phase: 03-quant-tool-library
    provides: fitted_params/load_params (default_down_move, min_analogs) + base_rates
provides:
  - "enforce_estimate(...) — estimate-layer mirror of verifier.enforce; audits estimator/SL-TP ASSUMPTIONS (never the arithmetic)"
  - "EstimateRejectedError — raise-to-block-finalize, carries the EstimateVetting audit trail"
  - "AnalogComparability schema + _comparability_prompt for the one LLM-judged check"
affects: [05-06 builder wiring, 05-07 promotion/dossier, phase-9 refit]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Two-stage structural(deterministic)→semantic(gated LLM) gate reused verbatim from verifier.enforce, new subject (estimator inputs)"
    - "Cite-or-drop on estimator inputs via evidence.resolve + quote_supported (kb: quote gate, tool: resolved-by-construction)"
    - "Raise-to-block-finalize with the assembled verdict attached to the exception (audit trail)"
    - "Calibration knobs as named module constants with ponytail comments, not literals in the body"

key-files:
  created:
    - tests/test_desk_estimate_gate.py
    - tests/fixtures/agent_responses/estimate_comparability.json
  modified:
    - src/catalyst_trader/desk/verifier.py

key-decisions:
  - "Down-move sanity band derived from params['estimator']['default_down_move'] (the type's cited, versioned reference), NOT quant.base_rate — base_rates.csv has no per-catalyst-type down-move row (crl_penalty is pdufa-only), so the fitted-param default_down_move is the only universal per-type source; band = [0.5x, 2x] as a named calibration knob"
  - "A dropped (uncited/quote-unsupported) estimator input forces reject — stricter than verifier.enforce (which only raises when ALL support is lost) because every estimator input is load-bearing provenance"
  - "Cold-start (n_analogs < min_analogs) is a flag (uncertainty_widened=True), never an auto-reject; carried through onto the endorsed EstimateVetting"

patterns-established:
  - "enforce_estimate colocated as a sibling of enforce in desk/verifier.py — max reuse of resolve/quote_supported/run_structured, only the checklist + schema are new"

requirements-completed: [PORT-02, OPS-01]

# Metrics
duration: 9min
completed: 2026-08-15
---

# Phase 5 Plan 5: Estimate Vetting Gate Summary

**enforce_estimate — the estimate-layer mirror of verifier.enforce: cite-or-drop on every estimator input + deterministic consistency checks (P(positive)↔verdict, down-move sanity band, hold-through/non-advisory SL) + a single LLM analog-comparability judgment, blocking finalize on reject with EstimateRejectedError.**

## Performance

- **Duration:** ~9 min
- **Completed:** 2026-08-15
- **Tasks:** 2
- **Files modified:** 3 (1 modified, 2 created)

## Accomplishments
- Added `enforce_estimate(...)` + `EstimateRejectedError` as siblings of `enforce`/`VerdictUnsupportedError` in `desk/verifier.py`, reusing `evidence.resolve`/`quote_supported` and the `run_structured` seam verbatim — no rebuilt machinery.
- Structural stage: cite-or-drop every estimator input (kb: passes the quote gate, tool: resolved-by-construction, uncited/unresolvable → dropped + reject) plus three deterministic consistency checks and a cold-start uncertainty-widening flag.
- Semantic stage: one gated opus `AnalogComparability` judgment on the analog survivors — the only LLM-judged check; off-type analogs → reject.
- A reject raises `EstimateRejectedError` with the assembled `EstimateVetting` attached (OPS-01 audit trail); mirrors Phase-4 blocking of unsupported verdicts.
- 11 offline tests (monkeypatched `run_structured`, in-memory db); full suite 597 → 608 green, zero regression, zero live API.

## Task Commits

1. **Task 1: enforce_estimate structural stage (cite-or-drop + deterministic consistency + blocking)** - `e2aec49` (feat) — TDD RED→GREEN in one commit (7 structural tests + implementation)
2. **Task 2: semantic analog-comparability stage + endorse path** - `11dd6fa` (test) — 4 semantic/endorse tests locking behavior already implemented in the shared function

## Files Created/Modified
- `src/catalyst_trader/desk/verifier.py` - Added `EstimateRejectedError`, `AnalogComparability`, `_comparability_prompt`, `_is_analog`, and `enforce_estimate` (two-stage gate); imported `EstimateVetting`.
- `tests/test_desk_estimate_gate.py` - 11 offline tests: uncited/kb-quote drops, each deterministic rejection, cold-start widening, blocking, endorse path, off-type reject, semantic-gated-to-survivors.
- `tests/fixtures/agent_responses/estimate_comparability.json` - comparable=true fixture (the comparable=false variant is inlined in the off-type test).

## Decisions Made
- **Down-move band source = `params['estimator']['default_down_move']`, not `quant.base_rate`.** `base_rates.csv` has no per-catalyst-type down-move metric (only `crl_penalty` = pdufa-specific; ph3_readout/conference/earnings would raise). The fitted-param `default_down_move` IS the type's cited, versioned reference (seeded from base_rates + gap studies), so it is the correct universal per-type source. Band `[0.5x, 2x]` is a named calibration knob (`_DOWN_MOVE_BAND`) with a ponytail upgrade note.
- **Dropped input → reject** (stricter than `enforce`): every estimator input is load-bearing provenance, so any uncited/quote-unsupported input blocks finalize rather than being silently pruned.
- Implemented both stages in the single `enforce_estimate` function; Task 2's commit adds its behavioral tests (the semantic block is the natural completion of the same function).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Down-move band source resolved to fitted-params, not quant.base_rate**
- **Found during:** Task 1 (down-move sanity band)
- **Issue:** The plan/interfaces named `quant.base_rate(...)` as the "type's expected down-move band source", but `base_rate()` is keyed by (metric, phase, indication) and has no per-catalyst-type down-move row — calling it for pdufa/ph3_readout/conference/earnings down-moves would raise (no matching metric).
- **Fix:** Used `params['estimator']['default_down_move']` (the cited, versioned per-type reference seeded from base_rates.csv + gap studies) as the band center, with a `[0.5x, 2x]` named calibration constant. Consistency check still enforced deterministically; still offline.
- **Files modified:** src/catalyst_trader/desk/verifier.py
- **Verification:** `test_base_rate_band_reject` (down_move=0.95 outside [0.225,0.90]) rejects; endorse path (0.45) passes.
- **Committed in:** e2aec49

---

**Total deviations:** 1 auto-fixed (1 blocking).
**Impact on plan:** The intent (a deterministic per-type down-move sanity band that rejects overclaimed gaps) is fully met; only the data source was corrected to one that actually exists per catalyst type. No scope creep.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `enforce_estimate` is ready for 05-06 to wire into the builder (audit the `catalyst_move_estimate` + `adaptive_sl_tp_levels` inputs before consuming them) and record `estimate_vetting` onto the `TradeProposal`.
- No blockers.

---
*Phase: 05-trade-builder-honest-hedge-ruin-avoidant-sizing-workflow-1b-2*
*Completed: 2026-08-15*

## Self-Check: PASSED

All created/modified files exist on disk; both task commits (e2aec49, 11dd6fa) present in history.
