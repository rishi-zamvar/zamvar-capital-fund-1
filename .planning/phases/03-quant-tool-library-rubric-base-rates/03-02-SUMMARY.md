---
phase: 03-quant-tool-library-rubric-base-rates
plan: 02
subsystem: quant
tags: [valuation, rnpv, cash-runway, tdd, money-critical]
requires: [QUANT-01, "03-01 ToolResult"]
provides: [QUANT-02 valuation slice, "rnpv()", "cash_runway()", "pipeline_value()"]
affects: ["Plan 07 rubric (pipeline value factor)", "Phase 4 analyst desk"]
tech-stack:
  added: []
  patterns: ["pure-python stdlib math only", "validate-at-boundary raise ValueError", "ToolResult inputs snapshot (QUANT-03)"]
key-files:
  created:
    - src/catalyst_trader/quant/valuation.py
  modified: []
  committed-prior:
    - tests/test_valuation.py
decisions:
  - "funded_past_catalyst uses runway >= months_to_catalyst (inclusive)"
  - "pipeline_value snapshots per-asset values (asset_values) — ToolResults aren't JSON-serializable"
  - "__init__ re-export surface left deferred to Plan 08; tests import from the module directly"
metrics:
  duration: 5min
  completed: 2026-08-14
---

# Phase 3 Plan 02: Valuation Tools Summary

Probability-adjusted DCF (rNPV), cash-runway, and pipeline value as pure-python functions that raise on out-of-domain input and return a ToolResult snapshotting their exact inputs.

## What shipped

- `src/catalyst_trader/quant/valuation.py` (~130 lines, stdlib `math` only):
  - **`rnpv(cashflows, discount_rate, costs=None)`** — `Σ CF_t·pos_t/(1+r)^t − Σ Cost_t·p_reach_t/(1+r)^t`. `detail={"pv_inflows","pv_costs"}`. Negative cashflows (loss years) compute; NaN/inf, empty list, `discount_rate ≤ -1.0`, and `pos ∉ [0,1]` raise.
  - **`cash_runway(cash_usd, monthly_burn_usd, months_to_catalyst=None)`** — `months = cash/burn`; adds `detail["funded_past_catalyst"]` when a catalyst horizon is given. Rejects `burn ≤ 0`, `cash < 0`, NaN/inf.
  - **`pipeline_value(results)`** — sums per-asset rNPV `ToolResult.value` (added per the plan-checker so agents never sum by hand); rejects empty list and value-less results. `detail={"n_assets"}`.
  - Shared `_finite` / `_prob` boundary guards — every money number is finite by construction, never inf/NaN (Pattern 2).

## Requirements

QUANT-01 (callable tool), QUANT-02 (valuation slice), QUANT-03 (inputs snapshot on every result), OPS-04 (exhaustive edge-case TDD, tests before logic).

## TDD

- **RED** (Task 1, committed prior in `00fa99d`): `tests/test_valuation.py` — 34 tests covering div-0, negative, empty/short, NaN/inf, extreme, happy for all three tools + QUANT-03 inputs-snapshot assertions.
- **GREEN** (Task 2, `3cf8417`): implementation makes all 34 pass.

## Verification

- `.venv/bin/pytest tests/test_valuation.py -q` → **34 passed**
- `.venv/bin/pytest -q` (full suite) → **267 passed**

## Deviations from Plan

None — plan executed as written. (`pipeline_value` was already specified in the committed RED suite and the objective; implemented to match.)

## Known Stubs

None.

## Self-Check: PASSED

- src/catalyst_trader/quant/valuation.py — FOUND
- commit 3cf8417 (GREEN) — FOUND
- commit 00fa99d (RED, prior) — FOUND
