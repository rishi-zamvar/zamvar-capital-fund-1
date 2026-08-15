---
phase: 07-verifier-guardrails-backtest-harness
plan: 03
subsystem: guardrails
tags: [guardrails, fail-closed, pre-trade-gate, ops-03, firewall, cite-or-drop, concentration, web-free, reuse]

# Dependency graph
requires:
  - phase: 01-data-integrity-catalyst-feed
    provides: calendar.verify.is_tradeable (the single tradeable gate — catalyst-date freshness/verification)
  - phase: 03-quant-tool-library-rubric-base-rates
    provides: quant.portfolio.concentration (Herfindahl net-long/concentration math)
  - phase: 04-analyst-desk-bull-bear-debate-workflow-1a
    provides: desk/verifier.py::enforce/enforce_estimate (cite-or-drop enforcers), desk/orchestrator.py::ALLOWED_TOOLS (web-free mcp__quant__* only)
  - phase: 06-independent-diligence-firewall-workflow-3
    provides: contracts.DiligenceInput (extra="forbid" WF-3 firewall), desk/diligence.py::enforce_dossier/ALLOWED_TOOLS
provides:
  - src/catalyst_trader/desk/guardrails.py — the thin FAIL-CLOSED pre-trade runtime gate aggregating the 5 shipped OPS-03 pre-trade invariants + a frozen GuardrailReport
  - check_guardrails(*, candidates, weights, heat_cap) -> GuardrailReport (AND-over-checks; None/missing input = violation)
  - assert_guardrails(...) -> raises GuardrailViolation on a blocked book (hard-stop for call sites)
affects: [08-paper-ledger, 08.5-intra-week-monitor, pipeline-pre-trade-gate]

# Tech tracking
tech-stack:
  added: []  # pydantic (already present) only — NO new dependency; all invariants reused, not re-implemented
  patterns:
    - "The gate is a pure aggregator: one boolean helper per invariant, AND over all five (mirrors diligence.synthesize_verdict's deterministic money-owner shape) — a False on ANY check blocks"
    - "FAIL-CLOSED by construction: every invariant helper try/excepts to False and treats None/missing input as a violation, never a skipped check"
    - "ALLOWED_TOOLS is read LIVE off the orchestrator/diligence module objects at call time (not import-bound) so a smuggled web tool is caught + tests can monkeypatch it"
    - "GuardrailReport is a frozen (extra='forbid') pydantic model — the verdict cannot be mutated after the fact, so a caller can't flip a block to a pass"

key-files:
  created:
    - src/catalyst_trader/desk/guardrails.py
    - tests/test_guardrails.py
  modified: []

decisions:
  - "guardrails.py AGGREGATES the shipped invariants (is_tradeable, concentration, DiligenceInput firewall, enforce* enforcers, web-free ALLOWED_TOOLS) into ONE tested runtime gate — it re-implements NONE of them (research verdict: ~all reuse)"
  - "dd_firewall_sealed verifies the TOP-LEVEL firewall ONLY: DiligenceInput.catalyst is a raw dict, so extra='forbid' does not deep-seal keys smuggled inside it; the docstring/test document this scope limitation and cross-reference 07-05's outcome-blind catalyst projection as the Layer-B nested-key safeguard"
  - "Scope split (research open-Q3, LOCKED): Phase 7 = pre-trade/pipeline guardrails only; live-position monitors (SL/TP, catalyst countdown, paper P&L) need a ledger and are deferred to Phase 8/8.5 — documented in the module docstring + a ponytail note"
  - "no_scrape_to_order asserts (not assumes) the desk is web-free: both orchestrator + diligence ALLOWED_TOOLS must be disjoint from a _WEB_TOOL_DENYLIST (web/fetch/http/browser/scrape)"

# Metrics
metrics:
  duration: 8min
  tasks: 2
  files: 2
  completed: 2026-08-15
---

# Phase 7 Plan 3: Verifier Guardrails Runtime Gate Summary

A thin fail-closed pre-trade runtime gate (`desk/guardrails.py`) that aggregates the five already-shipped OPS-03 pre-trade invariants — catalyst-date freshness, cite-or-drop/provenance, the Workflow-3 firewall (top-level), net-long/concentration caps, and no-path-from-scraped-content-to-an-order — into one `check_guardrails` / `assert_guardrails` gate that blocks on ANY violation and re-implements nothing.

## What Was Built

- **`check_guardrails(*, candidates, weights, heat_cap) -> GuardrailReport`** — runs the five invariants and returns a frozen report `{passed, checks, violations}`. `passed` is the AND over `checks`; a missing/None input for any invariant is a violation, never a skipped check.
- **`assert_guardrails(...)`** — the raising wrapper; raises `GuardrailViolation` on a blocked book for call sites that must hard-stop, returns the report on pass.
- **`GuardrailReport`** — frozen pydantic model (`extra="forbid"`, `frozen=True`) so the verdict can't be mutated after the fact.
- **Six-plus tests** (`tests/test_guardrails.py`), one enforced-and-fails-closed test per invariant + the raising wrapper + a frozen-model guard; all offline.

The five aggregated invariants (all reuse):
1. `catalyst_fresh` — every candidate's catalyst passes `calendar.verify.is_tradeable`.
2. `cite_or_drop_present` — `verifier.enforce` / `enforce_estimate` / `diligence.enforce_dossier` are importable + callable.
3. `dd_firewall_sealed` — `DiligenceInput` has `extra="forbid"` AND its top-level field set is disjoint from the WF-1/2 artifacts (`DebateVerdict` ∪ `TradeProposal`).
4. `concentration_within_cap` — `concentration(weights).value` and the net-long book weight are `<= heat_cap`.
5. `no_scrape_to_order` — both desks' `ALLOWED_TOOLS` are disjoint from the web-tool denylist.

## Deviations from Plan

None - plan executed exactly as written.

## Firewall-depth scope note

`dd_firewall_sealed` proves the **top-level** firewall only. `DiligenceInput.catalyst` is a raw `dict` (contracts/__init__.py L195), so `extra="forbid"` does not deep-seal keys smuggled inside that nested dict. The module docstring, the check's docstring, and `test_guardrail_dd_firewall_field_disjoint` all state this scope limitation and cross-reference **07-05's outcome-blind catalyst projection** as the Layer-B nested-key safeguard. The test includes an explicit assertion that a key smuggled inside the nested `catalyst` dict *passes* here — documenting the gap so it is never mistaken for full sealing.

## Deferred (documented, not built)

Live-position monitors — stop-loss / take-profit tracking, catalyst countdown, paper P&L — are the other half of OPS-03. They need a ledger and ride with **Phase 8** (paper ledger) / **Phase 8.5** (intra-week monitor), per research open-Q3 (LOCKED). Documented in the module docstring + a `# ponytail:` note; this gate is pre-trade/pipeline only.

## Verification

- `.venv/bin/python -m pytest tests/test_guardrails.py -x -q` — 7 passed.
- `.venv/bin/python -m pytest -q` — 892 passed (885 prior + 7 new), zero regression.
- Clean offline import confirmed: `from catalyst_trader.desk.guardrails import check_guardrails, assert_guardrails` exits 0.
- fail-closed test present: any single check failing → `passed=False` and `assert_guardrails` raises `GuardrailViolation`.

## Known Stubs

None.

## Self-Check: PASSED

All created files exist; both task commits (003dc1e test/RED, 2fb5122 feat/GREEN) present.
