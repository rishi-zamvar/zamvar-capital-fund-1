---
phase: 5
slug: trade-builder-honest-hedge-ruin-avoidant-sizing-workflow-1b-2
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-15
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Detailed per-requirement validation architecture lives in `05-RESEARCH.md ## Validation Architecture`. Money-critical principle: ALL agent/desk logic is tested offline via the single `run_structured()` seam monkeypatched against recorded fixtures — **zero live API calls in the pytest suite** — and every deterministic quant tool is tested with pinned params (no magic numbers, no network).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio |
| **Config file** | pyproject.toml (existing) |
| **Quick run command** | `.venv/bin/python -m pytest -q` |
| **Full suite command** | `.venv/bin/python -m pytest` |
| **Estimated runtime** | ~35 seconds (all mocked; no network) |

> NOTE: bare `python`/`python3` are NOT on PATH — always use `.venv/bin/python` (confirmed in research).

---

## Sampling Rate

- **After every task commit:** `.venv/bin/python -m pytest -q`
- **After every plan wave:** `.venv/bin/python -m pytest`
- **Before `/gsd:verify-work`:** full suite green
- **Max feedback latency:** ~35 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| (filled by planner from `05-RESEARCH.md ## Validation Architecture`) | | | PORT-01..05, HEDGE-01..05, OPS-01, OPS-02 | unit (mocked) | `.venv/bin/python -m pytest -q` | — | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Per research, the following Wave-0 items are named (planner assigns to tasks):
- [ ] `Hedge` model + `covers` validator (idiosyncratic hedge unrepresentable at the contract boundary) — HEDGE-01/04
- [ ] `TradeProposal` extensions: `estimate_vetting: EstimateVetting`, `sl_advisory: bool`, `holds_through_catalyst: bool`
- [ ] `tests/test_kb_params.py` — param-seam (no-magic-numbers, deterministic-with-pinned-params, `load_params` seam, newer-fit-wins versioning, provenance/cite-or-drop, bootstrap-present)
- [ ] `tests/test_desk_estimate_gate.py` — estimate vetting gate (endorse path + each rejection reason + blocking-finalize)
- [ ] Bootstrap `fitted_params:<catalyst_type>` playbook rows (cited base-rates + historical gaps)

*Existing infrastructure (pytest, `run_structured` seam, in-memory `db` + `hash_embed` fixtures, quant `ToolResult`) covers everything else.*

---

## Manual-Only Verifications

*None for the offline suite. A single live smoke-run of the trade builder against a real catalyst is a nice-to-have post-verification check, not a gated test (needs ANTHROPIC_API_KEY / CC auth).*

---

## Validation Sign-Off

- [ ] Sizing has NO return-target parameter (structural — 1% cannot be a sizing input)
- [ ] `conditional_payoff` un-netted worst-cell used for hedge validation (no fake netting)
- [ ] `Hedge.covers` makes a fake idiosyncratic hedge unrepresentable (HEDGE-01/04)
- [ ] Estimator + `adaptive_sl_tp_levels` take params IN and raise on missing key (no magic numbers)
- [ ] Hold-through-binary SL is labeled gap-exposed/advisory (regime invariant)
- [ ] Estimate vetting gate blocks finalize on rejection (PORT/HEDGE audit trail)
- [ ] `select_book` cannot resize any leg above its survival size (1% is book-level only)
- [ ] All PORT-01..05, HEDGE-01..05, OPS-01, OPS-02 covered
- [ ] No live API in the test suite
- [ ] `nyquist_compliant: true` on sign-off

**Approval:** pending
