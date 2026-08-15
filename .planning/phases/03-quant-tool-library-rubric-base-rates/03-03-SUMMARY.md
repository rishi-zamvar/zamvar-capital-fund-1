---
phase: 03-quant-tool-library-rubric-base-rates
plan: 03
subsystem: quant
tags: [sizing, kelly, risk-of-ruin, sl-tp, survival, tdd, money-critical]
requires: [QUANT-01, "03-01 ToolResult"]
provides: [QUANT-02 sizing slice, "kelly()", "fractional_kelly()", "risk_of_ruin()", "sl_tp_levels()"]
affects: ["Phase 5 Risk Committee (sizes trades)", "Plan 08 __init__ re-export surface"]
tech-stack:
  added: []
  patterns:
    - "pure-python stdlib math only"
    - "validate-at-boundary raise ValueError (never emit inf/NaN)"
    - "deterministic streak-probability DP (no RNG)"
    - "ToolResult inputs snapshot (QUANT-03)"
key-files:
  created:
    - src/catalyst_trader/quant/sizing.py
  modified: []
  committed-prior:
    - tests/test_sizing.py
decisions:
  - "risk_of_ruin has NO return-target parameter — structural (not just tested) guarantee sizing can never be coupled to the 1%/week target"
  - "risk_of_ruin is a two-step deterministic model: bankroll recurrence -> loss_length, then exact streak-probability DP over n_trades (no Monte Carlo)"
  - "loss_length counting is bounded by n_trades: a ruinous streak that cannot fit the horizon -> ruin probability 0.0 (also caps the loop)"
  - "Kelly clamps negative edge to 0 (no edge = no bet); win_frac and loss_frac both required > 0"
  - "sl_tp_levels sets advisory+reason only when holds_through_catalyst=True (gap jumps the stop)"
metrics:
  duration: 4min
  completed: 2026-08-15
---

# Phase 3 Plan 03: Sizing Tools Summary

Survival-first position sizing — asymmetric Kelly / fractional-Kelly, a deterministic (no-RNG) risk-of-ruin over a −70% binary downside, and SL/TP levels that self-flag as advisory-only when held through a catalyst. The arithmetic itself is the guardrail: nothing here can be scaled toward the 1%/week return target.

## What shipped

- `src/catalyst_trader/quant/sizing.py` (~200 lines, stdlib `math` only):
  - **`kelly(p_win, win_frac, loss_frac)`** — `f* = p_win/loss_frac − (1−p_win)/win_frac`, clamped `<0 → 0`. On the −70%-binary poor-odds case `kelly(0.30, 0.40, 0.70)` f* is negative → returns 0.0 (honestly tiny, never inflated). Raises on `loss_frac≤0`, `win_frac≤0`, `p_win∉[0,1]`, NaN/inf.
  - **`fractional_kelly(kelly_fraction, fraction=0.25)`** — `value = fraction · kelly_fraction`; rejects negative `fraction`, NaN/inf.
  - **`risk_of_ruin(p_loss, size_pct, gap=0.70, ruin_drawdown=0.5, n_trades=52)`** — Step 1 iterates `bankroll *= (1 − size_pct·gap)` to find `loss_length` (consecutive −gap×size hits to breach `ruin_drawdown`); `max_survivable = loss_length − 1` in `detail`. Step 2 runs an exact DP over `n_trades` tracking the current loss-streak, accumulating the probability a ruinous run occurs. Deterministic → identical calls return identical values; monotonically non-decreasing in `size_pct`; `size_pct=1.0` → ruin ≈ 1.0. **No return-target parameter by construction.** Raises on `size_pct∉(0,1]`, `gap∉(0,1]`, `ruin_drawdown∉(0,1]`, `p_loss∉[0,1]`, `n_trades≤0`, NaN.
  - **`sl_tp_levels(entry, sl_pct, tp_pct, holds_through_catalyst=False)`** — `stop=entry·(1−sl_pct)`, `target=entry·(1+tp_pct)`, `value = reward_risk = tp_pct/sl_pct`. When `holds_through_catalyst`, `detail={"advisory": True, "reason": "gap jumps stop..."}`. Rejects `sl_pct≤0` (R:R div-0), negative `tp_pct`, `entry≤0`, NaN/inf.
  - Shared `_finite` / `_prob` boundary guards (mirrors `valuation.py`).

## Requirements

QUANT-01 (callable tool), QUANT-02 (sizing slice), QUANT-03 (inputs snapshot on every result), OPS-04 (exhaustive edge-case TDD, tests before logic). PITFALLS #2 (advisory SL) and #5 (survival-not-target sizing) encoded as tested arithmetic.

## TDD

- **RED** (Task 1, `acd337a`): `tests/test_sizing.py` — 35 test functions (50 cases with parametrization) covering div-0, negative, zero, NaN/inf, extreme, happy for all four tools; the structural `risk_of_ruin` no-return-target signature assertion; ruin monotonicity + determinism; small-Kelly-on-−70%-binary; advisory-flag; QUANT-03 inputs snapshots. Failed at collection (module absent).
- **GREEN** (Task 2, `c6f1b92`): implementation makes all 50 pass.

## Verification

- `.venv/bin/pytest tests/test_sizing.py -q` → **50 passed**
- `.venv/bin/pytest -q` (full suite) → **317 passed**

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Self-Check: PASSED

- src/catalyst_trader/quant/sizing.py — FOUND
- commit acd337a (RED) — FOUND
- commit c6f1b92 (GREEN) — FOUND
