---
phase: 03-quant-tool-library-rubric-base-rates
plan: 05
subsystem: quant
tags: [options, portfolio, implied-move, iv-crush, concentration, exposure, tdd]
requires:
  - catalyst_trader.quant.result.ToolResult
provides:
  - "options.implied_move() → ToolResult (straddle + IV method)"
  - "options.iv_crush() → ToolResult (post-event + baseline path)"
  - "portfolio.concentration() → ToolResult (HHI + max abs weight)"
  - "portfolio.exposure() → ToolResult (gross Σ|w| + net Σw)"
affects:
  - "Phase 5 sizing/risk (implied-move magnitude prior, gross-exposure risk)"
  - "Phase 6 diligence (implied-move + IV-crush as DD inputs)"
tech_stack:
  added: []
  patterns:
    - "Pure-python (math only) tools returning ToolResult with verbatim inputs snapshot"
    - "Boundary validation raises ValueError on out-of-domain input (Pattern 2), never inf/NaN"
key_files:
  created:
    - src/catalyst_trader/quant/options.py
    - src/catalyst_trader/quant/portfolio.py
    - tests/test_options.py
    - tests/test_portfolio.py
  modified: []
decisions:
  - "implied_move: straddle method wins when both methods' inputs supplied (model-free, preferred)"
  - "gross exposure uses abs so two longs report 2× (PITFALLS #1 honest-net-long framing), net surfaced separately in detail"
  - "concentration max_weight uses abs magnitude so a large short leg counts as concentration"
metrics:
  duration: 4min
  completed: 2026-08-15
  tasks: 3
  files: 4
---

# Phase 3 Plan 5: Options + Portfolio Tools Summary

Options context tools (implied-move via straddle or IV method, IV-crush via post-event or baseline path) and portfolio tools (Herfindahl concentration + gross/net exposure), all pure-python, each returning a versioned `ToolResult` with a verbatim inputs snapshot, TDD'd with an exhaustive RED-first edge-case suite (div-0, negative, NaN/inf, empty, extreme, happy).

## What Was Built

- **`quant/options.py`** — `implied_move()` computes the market's implied % move as a magnitude prior for the downside gap: straddle `(call_mid + put_mid) / underlying_price` (preferred, model-free) or IV `iv · sqrt(days/365)`. `iv_crush()` = `pre − (post or baseline)`. Both are context/sizing inputs, never directional P&L (PITFALLS #10).
- **`quant/portfolio.py`** — `concentration()` = Herfindahl Σwᵢ² + max abs single-name weight; `exposure()` = gross Σ|wᵢ| + net Σwᵢ. Gross uses abs so two longs show 2× — the honest long/long framing (PITFALLS #1).
- **Two RED-first suites** (28 tests) covering every applicable edge column in the 03-RESEARCH.md matrix, plus QUANT-03 `.inputs`-snapshot assertions for all four tools.

## Verification

- `pytest tests/test_options.py tests/test_portfolio.py -q` → 28 passed.
- `pytest -q` → 367 passed (2 pre-existing statsmodels ComplexWarnings in test_pairs.py, out of scope).

## Deviations from Plan

None - plan executed exactly as written.

## Requirements Closed

- **QUANT-01** — tools versioned (`_VERSION = "1.0.0"`).
- **QUANT-02** — options (implied-move, IV-crush) + portfolio (concentration, exposure) slices.
- **QUANT-03** — every tool returns a `ToolResult` with a verbatim inputs snapshot (reproducible/auditable).
- **OPS-04** — exhaustive RED-first edge-case suites written before the logic.

## Self-Check: PASSED
