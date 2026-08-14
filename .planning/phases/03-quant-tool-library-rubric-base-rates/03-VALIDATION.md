---
phase: 3
slug: quant-tool-library-rubric-base-rates
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-14
---

# Phase 3 — Validation Strategy

> Detailed per-requirement validation architecture lives in `03-RESEARCH.md` (## Validation Architecture + the per-tool edge-case matrix). This file tracks its execution. OPS-04 (exhaustive edge-case TDD on money-critical math) is the primary quality lever this phase.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | pyproject.toml (existing) |
| **Quick run** | `pytest -q` |
| **Full suite** | `pytest` |
| **Estimated runtime** | ~25 seconds |

## Sampling Rate

- After every task commit: `pytest -q`
- After every wave: `pytest`
- Before verification: full suite green
- Max feedback latency: 30 seconds

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Command | Status |
|---------|------|------|-------------|-----------|---------|--------|
| (filled by planner from RESEARCH ## Validation Architecture + edge-case matrix) | | | QUANT/FRAME/OPS | unit | `pytest -q` | ⬜ pending |

## Wave 0 Requirements

- [ ] `statsmodels` added to deps (for cointegration — Engle-Granger/Johansen)
- [ ] `ToolResult` model (frozen, extra=forbid, carries inputs snapshot) established before tools use it

## Edge-Case Matrix (OPS-04 — every money tool)

Each tool's RED suite MUST cover: division-by-zero, negative/zero inputs, empty/short series, NaN, extreme values, and the happy path — written before the tool's logic.

## Manual-Only Verifications

*None — all quant tools + rubric + base-rate loading have automated verification.*

## Validation Sign-Off

- [ ] Every tool ships an exhaustive edge-case suite written before its logic (OPS-04)
- [ ] Every tool output records its exact inputs (QUANT-03)
- [ ] Rubric weights load from tunable config; Σweights≈1 validated (FRAME-01/02)
- [ ] Base-rate table loads + is citable (FRAME-03)
- [ ] `nyquist_compliant: true` set on sign-off

**Approval:** pending
