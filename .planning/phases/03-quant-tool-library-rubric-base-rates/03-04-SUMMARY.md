---
phase: 03-quant-tool-library-rubric-base-rates
plan: 04
subsystem: quant
tags: [pairs, cointegration, correlation, beta, conditional-payoff, hedge, statsmodels, tdd, money-critical]
requires: [QUANT-01, "03-01 ToolResult", statsmodels, numpy]
provides: [QUANT-02 pairs slice, "cointegration()", "correlation_beta()", "conditional_payoff()"]
affects: ["Phase 5 hedge selection + Risk Committee", "Phase 6 diligence pairs re-validation", "Plan 08 __init__ re-export surface"]
tech-stack:
  added: []
  patterns:
    - "delegate the one hard stat test (cointegration) to statsmodels; hand-roll nothing else"
    - "plain-list signatures, numpy internally (Pattern 3) — inputs snapshot stays JSON-serializable"
    - "validate-at-boundary raise ValueError (never emit inf/NaN)"
    - "ToolResult inputs snapshot (QUANT-03)"
key-files:
  created:
    - src/catalyst_trader/quant/pairs.py
  modified: []
  committed-prior:
    - tests/test_pairs.py
decisions:
  - "cointegration delegates to statsmodels coint (Engle-Granger) + coint_johansen (Johansen trace) — critical-value tables are a bug farm to hand-roll (the one 'don't hand-roll')"
  - "hedge ratio (β) is np.polyfit(price_b, price_a, 1)[0] — OLS slope of a on b — in BOTH cointegration paths (consistent, simple)"
  - "engle_granger returns value=p_value; johansen returns value=trace_stat (no p-value) + trace_stat>crit_value cointegrated bool; significance maps to the 90/95/99% column"
  - "cointegration guards >=30 aligned finite observations (PITFALLS #3); correlation_beta guards >=2 + non-zero variance in BOTH series"
  - "conditional_payoff value = min cell (combined worst-case, UN-netted) — the honest replacement for '0.7 correlated = hedged' (PITFALLS #1), sizes the inverse hedge"
metrics:
  duration: 6min
  completed: 2026-08-15
---

# Phase 3 Plan 04: Pairs / Hedge-Analysis Tools Summary

Cointegration (statsmodels Engle-Granger + Johansen, ≥30-obs guard), numpy correlation/β, and the pure-python catalyst-branch conditional-payoff matrix — the core of the inverse-hedge validation. The payoff matrix reports the un-netted worst case (target ↓ × peer ↓), which is what survival-first sizing must size against; cointegration is the one tool that honestly delegates the hard critical-value stats to statsmodels rather than hand-rolling an ADF/Johansen bug farm.

## What shipped

- `src/catalyst_trader/quant/pairs.py` (~190 lines):
  - **`cointegration(price_a, price_b, method="engle_granger", significance=0.05)`** — `engle_granger` calls `statsmodels.tsa.stattools.coint` → `value=p_value`, `detail={t_stat, crit_values, hedge_ratio, cointegrated: p_value<significance, method}`. `johansen` calls `coint_johansen(endog, det_order=0, k_ar_diff=1)` → `value=trace_stat`, `detail={trace_stat, crit_value, hedge_ratio, cointegrated: trace_stat>crit_value, method}`; significance→crit-column via `{0.10:0, 0.05:1, 0.01:2}` (default 95%). Hedge ratio = `np.polyfit(price_b, price_a, 1)[0]` in both. Raises on mismatched length, `<30` obs, and any NaN/inf; raises on unknown method.
  - **`correlation_beta(asset_returns, market_returns)`** — `value = np.corrcoef(a, m)[0,1]`, `detail={"beta": np.polyfit(m, a, 1)[0]}`. Raises on mismatched length, `<2` obs, NaN/inf, and zero variance in either series (corr/β undefined).
  - **`conditional_payoff(target_up, target_down, peer_up, peer_down, w_target, w_peer)`** — pure-python 2×2 matrix over {target ↑/↓}×{peer ↑/↓}, each cell `w_target·target_move + w_peer·peer_move`; `value = min(matrix)` (un-netted worst case), `detail={"matrix": {4 named cells}}`. Raises on any non-finite input.
  - Shared `_aligned_finite` boundary guard for the two series-based tools.

## Requirements

QUANT-01 (callable, versioned tools), QUANT-02 (pairs slice: cointegration + correlation/β + conditional-payoff), QUANT-03 (verbatim inputs snapshot on every result), OPS-04 (exhaustive edge-case TDD, tests before logic). PITFALLS #1 (honest conditional-hedge payoff, no fake correlation-hedge) and #3 (short-series guard) encoded as tested arithmetic.

## TDD

- **RED** (Task 1, `919f176`): `tests/test_pairs.py` — 22 test functions covering short/mismatched/NaN/inf series, zero-variance, unknown-method guards; a deterministic (seeded rng) cointegrated-vs-independent assertion with hedge-ratio ≈ 1.0; the Johansen path; hand-computed β (=2.0) and ±1 correlation; the un-netted worst-case + 4-cell matrix; QUANT-03 inputs snapshots. Failed at collection (module absent).
- **GREEN** (Task 2, `91834af`): implementation makes all 22 pass. No refactor needed.

## Verification

- `.venv/bin/pytest tests/test_pairs.py -q` → **22 passed** (2 warnings — statsmodels-internal ComplexWarning in `coint_johansen` eigenvalue casting, not our code)
- `.venv/bin/pytest -q` (full suite) → **339 passed**

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

- src/catalyst_trader/quant/pairs.py — FOUND
- commit 919f176 (RED) — FOUND
- commit 91834af (GREEN) — FOUND
