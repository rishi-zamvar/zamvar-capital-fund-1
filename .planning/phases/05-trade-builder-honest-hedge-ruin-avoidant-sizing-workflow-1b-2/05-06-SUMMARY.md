---
phase: 05-trade-builder-honest-hedge-ruin-avoidant-sizing-workflow-1b-2
plan: 06
subsystem: desk
tags: [builder, trade-proposal, estimated-move, hold-vs-exit, log-growth, honest-hedge, PORT-02, HEDGE-01, HEDGE-04]

# Dependency graph
requires:
  - phase: 05 (05-01)
    provides: TradeProposal + Hedge + EstimateVetting contracts
  - phase: 05 (05-02)
    provides: catalyst_move_estimate, adaptive_sl_tp_levels, hold_vs_exit (expected-LOG-growth)
  - phase: 05 (05-03)
    provides: kb.load_params (estimator/sl_tp/builder groups) + hedge_peers + analog_query
  - phase: 05 (05-04)
    provides: risk.size_for_survival (no-return-target survival sizing)
  - phase: 05 (05-05)
    provides: verifier.enforce_estimate + EstimateRejectedError (vet-before-finalize)
  - phase: 04
    provides: run_structured seam + evidence.tool_ref citation minting
provides:
  - "desk/builder.py::build(conn, embed, verdict, catalyst, *, entry) -> TradeProposal | None — single-leg estimated-move construction"
  - "_candidate_peer(conn, target) — top -1 inverse peer for Risk to validate (+1 filtered, HEDGE-01)"
  - "BuilderNarrative schema — the one LLM-authored field (pair_rationale); every number is a deterministic tool output"
affects: [05-07 promotion/dossier + risk reconciliation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Flat async fn over the one run_structured seam (mirrors debate.py/risk.py) — no base classes, no config objects"
    - "Builder orchestrates + interprets; money math (estimate, sizing, hold-vs-exit, SL/TP) is all deterministic tool output (agents never do arithmetic)"
    - "Hold-through decided by quant hold_vs_exit (expected-LOG-growth at survival size f), NEVER raw EV (BLOCKER-2) — enforced by a source-grep test + acceptance guard"
    - "Every builder threshold read from params['builder'] (missing key raises); no literal thresholds in the builder body"
    - "Estimate vetted via enforce_estimate BEFORE finalize; reject OR below-min size -> return None (zero-trade allowed)"

key-files:
  created:
    - src/catalyst_trader/desk/builder.py
    - tests/test_desk_builder.py
    - tests/fixtures/agent_responses/trade_builder_proposal.json
  modified: []

key-decisions:
  - "build() takes a keyword-only `entry: float` (current leg price) — the plan signature omitted a price source but TradeProposal.entry + adaptive_sl_tp_levels require one; the builder can't invent a price, so the caller (05-07) supplies it (deviation, Rule 3)"
  - "catalyst is a plain dict (matches the already-shipped risk.assess convention); field access via the reused analysts._get helper (handles dict OR Catalyst model)"
  - "p_positive is cited to the catalyst_move_estimate tool_ref (its reproducible inputs-hash pins p_positive), since the verdict is not a resolvable kb:/tool: ref; still consistency-checked against the verdict by enforce_estimate"
  - "The candidate inverse peer is SURFACED (via _candidate_peer + threaded into the narrative), not stored on the proposal: TradeProposal.hedge is None out of the builder — risk.validate_hedge (05-07) owns validation and re-derives the candidate itself"
  - "The positive-EV-but-log-growth-favors-exit crux is tested by fixing f=1.0 (the tail penalty only bites at large f; at realistic survival sizes ~0.03 hold-vs-exit ≈ EV). The structural guarantee — the builder CALLS hold_vs_exit and never a raw-EV branch — is enforced by a source grep + spy test."

requirements-completed: [PORT-02, HEDGE-01, HEDGE-04]

# Metrics
duration: 18min
completed: 2026-08-15
---

# Phase 5 Plan 6: Trade Builder (Estimated-Move Construction) Summary

**`desk/builder.py` turns a `DebateVerdict` into a `TradeProposal`: it estimates the catalyst payoff distribution (param-driven, cited), sizes the leg on the estimated down-move via `size_for_survival`, decides hold-through-vs-exit by the quant `hold_vs_exit` tool (expected-LOG-growth at the survival-constrained size — never raw EV), sets advisory-only SL/TP on hold-through legs, vets the estimate via `enforce_estimate` before finalizing, and surfaces a candidate `-1` inverse peer for Risk to validate — every threshold a loaded param, the return target never a sizing input.**

## Performance

- **Duration:** ~18 min
- **Completed:** 2026-08-15
- **Tasks:** 2 (each TDD RED→GREEN)
- **Files:** 3 created, 0 modified

## Accomplishments
- `build(conn, embed, verdict, catalyst, *, entry)` — the single-leg estimated-move engine, a flat async fn over the one `run_structured` seam (mirrors `debate.py`/`risk.py`).
- Candidate inverse peer surfaced via `_candidate_peer` (top `-1` peer; `+1` co-move filtered out, HEDGE-01); the builder NEVER fabricates a validated hedge — `TradeProposal.hedge` is `None` out of the builder (validation is Risk's job).
- Estimate → vet → size → hold-vs-exit → advisory SL/TP wired entirely through the deterministic tools: `catalyst_move_estimate`, `size_for_survival` (gap = est `down_move`, not a blanket 0.70), `hold_vs_exit` (expected-LOG-growth at `f = size.value`), `adaptive_sl_tp_levels` (advisory on hold-through), `enforce_estimate` (reject blocks finalize → `None`).
- Every builder threshold (`min_tradeable_size`, `log_growth_margin`, `runup_capture_frac`) read from `params["builder"]`; a missing key RAISES (no literal in the body). Zero-trade allowed: below-min size or a rejected estimate returns `None`.
- `expected_return_pct` is display-only (`est.value`); it never feeds `size_pct` (1% is never a sizing input).
- 19 offline tests (monkeypatched `run_structured`, in-memory KB analogs); full suite **608 → 627 green**, zero regression, zero live API.

## Task Commits

1. **Task 1: builder skeleton (candidate peer, verdict carry, no fabricated hedge)** — `c302009` (test RED) → `20c3ae6` (feat GREEN)
2. **Task 2: estimated-move construction (estimate → vet → hold-vs-exit → advisory SL/TP)** — `06d2532` (test RED) → `aba9d6e` (feat GREEN)

## Files Created/Modified
- `src/catalyst_trader/desk/builder.py` — `build`, `_candidate_peer`, `_split_moves`, `BuilderNarrative`, prompt helpers.
- `tests/test_desk_builder.py` — 19 offline tests (candidate filtering, verdict carry, down-move-as-gap, hold-vs-exit-at-f, hold/exit follow-through, +EV-log-favors-exit crux, reject/below-min → None, missing-param raise, no-raw-EV source guard).
- `tests/fixtures/agent_responses/trade_builder_proposal.json` — the BuilderNarrative pair_rationale fixture.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `build()` takes a keyword-only `entry: float` price**
- **Found during:** Task 1 (assembling a valid TradeProposal).
- **Issue:** The plan signature `build(conn, embed, verdict, catalyst)` sources no price, but `TradeProposal.entry` and `adaptive_sl_tp_levels(entry, ...)` both require the current leg price, and there is no price feed wired into the desk this phase.
- **Fix:** Added a keyword-only `entry: float` parameter — the caller (05-07 orchestrator) supplies the current price; the builder can't invent one. `entry` is a plumbing input, not a threshold, so it does not violate the no-magic-numbers rule. Acceptance grep `async def build(` still holds.
- **Files modified:** src/catalyst_trader/desk/builder.py
- **Committed in:** 20c3ae6

**2. [Rule 3 - Blocking] `catalyst` is a dict; p_positive cited to the estimate tool_ref**
- **Found during:** Task 1/2.
- **Issue:** The plan used attribute access (`catalyst.ticker`) but the already-shipped `risk.assess` takes a plain dict; and the plan said "cite p_positive to the verdict," but a verdict is not a resolvable `kb:`/`tool:` ref (enforce_estimate would drop it).
- **Fix:** `catalyst` is a dict, read via the reused `analysts._get` (handles dict OR Catalyst model) for consistency with `risk.assess`. p_positive is cited to `catalyst_move_estimate`'s `tool_ref` (its reproducible inputs-hash pins p_positive); enforce_estimate still consistency-checks p_positive against the verdict direction/confidence.
- **Files modified:** src/catalyst_trader/desk/builder.py
- **Committed in:** aba9d6e

---

**Total deviations:** 2 auto-fixed (both blocking, plumbing/consistency). No scope change — the money-critical invariants (down-move sizing, log-growth hold decision, advisory SL, vet-before-finalize, param-driven thresholds) are all met exactly as specified.

## Known Stubs
None. `TradeProposal.hedge = None` out of the builder is intentional and specified (HEDGE-04 honest fallback shape) — the candidate peer is surfaced for `risk.validate_hedge` (05-07), which owns validation. Not a stub.

## Issues Encountered
Two test-side import omissions (`risk`, `EstimateRejectedError`) caught immediately on the Task-2 GREEN run and fixed in the same commit.

## User Setup Required
None.

## Next Phase Readiness
- `build()` is ready for 05-07 to compose: fan builds over the week's verdicts, reconcile the `risk.assess` validated `Hedge` onto the proposal, author the memo/pre-mortem (kill_criteria already threaded), and run the PM promote/kill.
- Carry-forward: 05-07 must supply the current `entry` price per leg.
- No blockers.

---
*Phase: 05-trade-builder-honest-hedge-ruin-avoidant-sizing-workflow-1b-2*
*Completed: 2026-08-15*

## Self-Check: PASSED

All created files exist on disk; all four task commits (c302009, 20c3ae6, 06d2532, aba9d6e) present in history. Full suite 627 green; `! grep -qE "est\.value\s*>"` holds.
