---
phase: 1
slug: data-integrity-catalyst-feed
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-14
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. The detailed per-requirement validation architecture lives in `01-RESEARCH.md` (## Validation Architecture); this file tracks its execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | pyproject.toml (Wave 0 installs) |
| **Quick run command** | `pytest -q` |
| **Full suite command** | `pytest` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest -q`
- **After every plan wave:** Run `pytest`
- **Before verification:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| (filled by planner from RESEARCH ## Validation Architecture) | | | DATA-01..06 | unit | `pytest -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] pytest + pytest-httpx + freezegun installed via pyproject
- [ ] `tests/conftest.py` — shared fixtures (live-captured CT.gov / FMP JSON fixtures)
- [ ] Fixture capture of exact FMP earnings-calendar JSON field names (research open question)

*The date-precision / uncertainty-typing tests are money-critical and must be written before logic (TDD).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Seed ~20-name universe curation | DATA-06 | Human curation task (hand-seed from a PDUFA calendar), not code | Reviewer confirms the seed universe list is populated and sourced |

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
