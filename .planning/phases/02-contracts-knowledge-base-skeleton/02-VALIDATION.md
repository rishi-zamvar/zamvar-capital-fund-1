---
phase: 2
slug: contracts-knowledge-base-skeleton
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-14
---

# Phase 2 — Validation Strategy

> Per-phase validation contract. Detailed per-requirement validation architecture lives in `02-RESEARCH.md` (## Validation Architecture); this file tracks its execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
| **Config file** | pyproject.toml (existing) |
| **Quick run command** | `pytest -q` |
| **Full suite command** | `pytest` |
| **Estimated runtime** | ~20 seconds |

---

## Sampling Rate

- **After every task commit:** `pytest -q`
- **After every plan wave:** `pytest`
- **Before verification:** full suite green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| (filled by planner from RESEARCH ## Validation Architecture) | | | KB-01..05 | unit | `pytest -q` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red*

---

## Wave 0 Requirements

- [ ] `sqlite-vec` added to pyproject deps + `db.connect()` loads the extension
- [ ] deterministic hash embedder fixture (no network/ML) for KB analog tests

---

## Manual-Only Verifications

*None — all Phase 2 behaviors (contract validation, provenance rejection, analog KNN, hedge/playbook edges) have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Provenance-rejection invariant has an explicit failing-path test
- [ ] `nyquist_compliant: true` set on sign-off

**Approval:** pending
