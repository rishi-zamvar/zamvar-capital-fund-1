---
phase: 6
slug: independent-diligence-firewall-workflow-3
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-15
---

# Phase 6 — Validation Strategy

> Per-phase validation contract. Detailed per-requirement architecture lives in `06-RESEARCH.md ## Validation Architecture`. Money-critical principle: ALL agent/desk logic is tested offline via the single monkeypatched `run_structured()` seam (role-router pattern from `test_desk_orchestrator.py`); providers mocked / raw values passed in — **zero live API calls in the pytest suite**. The FIREWALL is enforced by types (pydantic `extra="forbid"`), proven by a field-disjointness test, not a runtime check.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio (`asyncio_mode="auto"`) |
| **Config file** | pyproject.toml (existing) |
| **Quick run command** | `.venv/bin/python -m pytest tests/test_desk_diligence.py -x` |
| **Full suite command** | `.venv/bin/python -m pytest -q` |
| **Estimated runtime** | ~35 seconds (all mocked; no network) |

> `.venv/bin/python` only — bare `python`/`python3` are NOT on PATH.

---

## Sampling Rate

- **After every task commit:** `.venv/bin/python -m pytest -q`
- **After every wave:** full suite
- **Before verification:** full suite green (expect ~649 baseline + new)
- **Max feedback latency:** ~35 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| (filled by planner from `06-RESEARCH.md ## Validation Architecture` — 12 named tests: DILIG-01 firewall ×3, DILIG-02 dimensions ×3, DILIG-03 synthesizer ×6) | | | DILIG-01/02/03 | unit (mocked) | `.venv/bin/python -m pytest -q` | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `contracts.DiligenceInput` (`extra="forbid"`, `{ticker, catalyst, pair?}`; `pair` is a bare ticker str, never a Hedge object)
- [ ] `DiligenceDossier.residual_risks: list[str] = []` (one-line extension)
- [ ] `tests/test_desk_diligence.py` (new) — firewall + dimensions + synthesizer
- [ ] 8 dimension `AnalystSignal` fixtures + a `run_structured` role-router (copy `test_desk_orchestrator.py::_router`)
- [ ] additions to `tests/test_contracts.py` (DiligenceInput rejection + field-disjointness)

*Existing infra (pytest, run_structured seam, in-memory db + hash_embed, quant ToolResult, provider mocks) covers everything else.*

---

## Manual-Only Verifications

*None for the offline suite. A single live smoke-run of the diligence desk against a real catalyst is a nice-to-have post-verification check (needs ANTHROPIC_API_KEY / CC auth), not a gated test.*

---

## Validation Sign-Off

- [ ] **Firewall (DILIG-01):** `DiligenceInput` field set is DISJOINT from DebateVerdict/TradeProposal/StrategyDossier/RiskAssessment field names (test-enforced); `extra="forbid"` raises `ValidationError` on a stray Workflow-1/2 field; `run_diligence` signature only accepts `DiligenceInput`.
- [ ] **Dimensions (DILIG-02):** 8 dimensions each emit a source-cited `AnalystSignal`; each reuses the confirmed existing tool/provider/KB call; all offline (mock/value-in); options dim degrades on illiquid names (illiquid ≠ hard fail; only zero-liquidity is).
- [ ] **Synthesizer (DILIG-03):** deterministic `synthesize_verdict` — any money-touching dimension failing forces NO-GO; GO requires all money dims data-backed; ties → NO-GO; LLM writes narrative only (verdict overwritten via model_copy).
- [ ] `enforce_dossier` cite-or-drop gate mirrors verifier's two-stage shape (reuses `evidence` primitives; does NOT call the DebateVerdict-typed `verifier.enforce`).
- [ ] `dimension_passed` thresholds read from params (missing-key-raises), no hardcoded literals.
- [ ] No path from raw/scraped content to an order (no execution in this phase).
- [ ] All DILIG-01/02/03 covered; no live API in the suite.
- [ ] `nyquist_compliant: true` on sign-off.

**Approval:** pending
