---
phase: 03-quant-tool-library-rubric-base-rates
plan: 06
subsystem: quant
tags: [performance, sharpe, sortino, cumulative-return, attribution, freq-footgun, tdd]
requires:
  - catalyst_trader.quant.result.ToolResult
  - numpy
provides:
  - "performance.sharpe() → ToolResult (annualized, REQUIRED periods_per_year, ddof=1)"
  - "performance.sortino() → ToolResult (annualized, downside semideviation)"
  - "performance.cumulative_return() → ToolResult (∏(1+r)-1)"
  - "performance.attribution() → ToolResult (components reconciled to total)"
affects:
  - "Phase 8 paper-ledger EOD P&L + attribution"
  - "Phase 8 weekly performance metrics (Sharpe/Sortino on the sim ledger)"
  - "iOS dashboard Historical Performance page (Sharpe, attribution)"
tech_stack:
  added: []
  patterns:
    - "numpy-backed tools returning ToolResult with verbatim inputs snapshot; pandas kept out of the API (Pattern 3)"
    - "Boundary validation raises ValueError on out-of-domain input (Pattern 2), never inf/NaN"
    - "freq footgun cured by making periods_per_year a REQUIRED argument (no silent annualization default)"
key_files:
  created:
    - src/catalyst_trader/quant/performance.py
    - tests/test_performance.py
  modified: []
decisions:
  - "periods_per_year is a REQUIRED arg on sharpe + sortino — the deliberate cure for the vectorbt/quantstats silent-annualization footgun (tested: 252 == 52 × √(252/52))"
  - "Sortino denominator = target semideviation √mean(min(excess−mar,0)²) over ALL observations — handles a single downside point cleanly and zeroes to a raise when nothing is below mar"
  - "attribution reconciliation tolerance = math.isclose(rel_tol=1e-6, abs_tol=1e-9); a decomposition that doesn't add up raises rather than emitting a number"
metrics:
  duration: 4min
  completed: 2026-08-15
  tasks: 2
  files: 2
---

# Phase 3 Plan 6: Performance + Attribution Tools Summary

Hand-rolled numpy performance tools — annualized Sharpe/Sortino with a REQUIRED `periods_per_year` (the freq footgun made an explicit, tested caller decision), compounded cumulative return, and P&L attribution that reconciles named components to a total — each returning a versioned `ToolResult` with a verbatim inputs snapshot, TDD'd with a RED-first edge-case suite whose headline proves 252-daily and 52-weekly books produce correctly √(252/52)-scaled Sharpe from the same returns.

## What Was Built

- **`quant/performance.py`** — four tools:
  - `sharpe(returns, periods_per_year, risk_free=0.0)` — mean(excess)/std(excess, ddof=1)·√ppy; raises on <2 points, NaN, or zero volatility.
  - `sortino(returns, periods_per_year, mar=0.0, risk_free=0.0)` — same numerator, denominator = downside target semideviation; raises on zero downside deviation.
  - `cumulative_return(returns)` — ∏(1+r)−1; a −100% period computes to −1.0 (wipeout, not a crash); raises on empty/NaN.
  - `attribution(components, total)` — reconciles Σcomponents to total within 1e-6 rel tolerance, else raises; `detail` carries components + residual.
- **RED-first suite** (`tests/test_performance.py`, 24 tests) — freq-footgun 52-vs-252 scaling assertion (Sharpe + Sortino), zero-vol / empty / single-point / NaN guards on every tool, cumulative wipeout, attribution sum-to-total tolerance, and QUANT-03 `.inputs`-snapshot (periods_per_year recorded) for all four tools.

## Verification

- `pytest tests/test_performance.py -q` → 24 passed.
- `pytest -q` → 391 passed (2 pre-existing statsmodels/numpy ComplexWarnings from test_pairs.py, out of scope).

## Deviations from Plan

None - plan executed exactly as written.

## Requirements Closed

- **QUANT-01** — tools versioned (`_VERSION = "1.0.0"`), callable, unit-tested.
- **QUANT-02** — Sharpe/Sortino/returns/attribution performance slice.
- **QUANT-03** — every tool returns a `ToolResult` with a verbatim inputs snapshot including `periods_per_year` (reproducible/auditable).
- **OPS-04** — exhaustive RED-first edge-case suite written before the logic; the 52-vs-252 freq-footgun case is the headline.

## Self-Check: PASSED
