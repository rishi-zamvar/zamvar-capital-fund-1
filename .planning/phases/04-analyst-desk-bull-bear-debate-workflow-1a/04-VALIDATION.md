---
phase: 4
slug: analyst-desk-bull-bear-debate-workflow-1a
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-14
---

# Phase 4 — Validation Strategy

> Detailed per-requirement validation architecture lives in `04-RESEARCH.md`. This file tracks execution. Key testability principle: ALL agent logic is tested offline via a single `run_structured()` seam monkeypatched against recorded JSON fixtures — **zero live API calls in the pytest suite.**

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio (Wave 0) |
| **Quick run** | `pytest -q` |
| **Full suite** | `pytest` |
| **Estimated runtime** | ~30 seconds (all mocked; no network) |

## Sampling Rate
- After every task commit: `pytest -q`
- After every wave: `pytest`
- Before verification: full suite green
- Max feedback latency: 30 seconds

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Command | Status |
|---------|------|------|-------------|-----------|---------|--------|
| (filled by planner from RESEARCH ## Validation Architecture) | | | CALL-01..04 | unit (mocked) | `pytest -q` | ⬜ pending |

## Wave 0 Requirements
- [ ] `pytest-asyncio` added to dev deps
- [ ] `DebateVerdict` extended: `kill_criteria: list[str]` (non-empty validator) + `direction: Literal["positive","negative"]` (enforces binary CALL-03)
- [ ] `run_structured()` SDK seam + recorded-fixture harness (the offline test boundary)
- [ ] `evidence_ref` format standardized so the verifier can resolve claims against the KB

## Manual-Only Verifications
*None for the offline suite. (A single live smoke-run of the desk against a real catalyst is a nice-to-have post-verification check, not a gated test — needs ANTHROPIC_API_KEY / CC auth.)*

## Validation Sign-Off
- [ ] Four analysts each emit a source-cited AnalystSignal (CALL-01)
- [ ] Bull/Bear run in isolated sessions; debate manager names the losing side's strongest point (CALL-02)
- [ ] Verdict is binary + calibrated confidence + kill criteria, no positioning (CALL-03)
- [ ] Fact-check verifier enforces source-quote-or-drop (CALL-04)
- [ ] No live API in the test suite
- [ ] `nyquist_compliant: true` on sign-off

**Approval:** pending
