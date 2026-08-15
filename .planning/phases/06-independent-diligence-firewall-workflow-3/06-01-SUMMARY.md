---
phase: 06-independent-diligence-firewall-workflow-3
plan: 01
subsystem: contracts + diligence-desk test harness
tags: [firewall, contracts, diligence, tdd, offline-harness]
requires:
  - "catalyst_trader.contracts (AnalystSignal, DebateVerdict, TradeProposal, StrategyDossier, RiskAssessment, DiligenceDossier)"
provides:
  - "DiligenceInput contract (the firewall boundary, DILIG-01)"
  - "DiligenceDossier.residual_risks field"
  - "tests/test_desk_diligence.py offline harness (_dd_router, _patch_dd_seam, DD_DIMENSIONS, MONEY_DIMS, DD_INPUT)"
  - "8 locked-key dimension AnalystSignal fixtures + dd_narrative fixture"
affects:
  - "Waves 2-4 (dimensions, synthesizer, orchestrator) build on this harness + these locked keys"
tech-stack:
  added: []
  patterns:
    - "Firewall as a pydantic + type-signature property (extra='forbid' makes Workflow-1/2 fields unrepresentable) — the Hedge.covers move applied to the input boundary"
    - "One-seam offline test recipe: monkeypatch the single run_structured seam with a role-routing fake; lazy-import the not-yet-existent desk module inside the patch helper"
key-files:
  created:
    - "tests/test_desk_diligence.py"
    - "tests/fixtures/agent_responses/dd_trial_stats_signal.json"
    - "tests/fixtures/agent_responses/dd_regulatory_signal.json"
    - "tests/fixtures/agent_responses/dd_financials_signal.json"
    - "tests/fixtures/agent_responses/dd_ownership_flow_signal.json"
    - "tests/fixtures/agent_responses/dd_options_move_signal.json"
    - "tests/fixtures/agent_responses/dd_hedge_revalidation_signal.json"
    - "tests/fixtures/agent_responses/dd_liquidity_signal.json"
    - "tests/fixtures/agent_responses/dd_historical_analog_signal.json"
    - "tests/fixtures/agent_responses/dd_narrative.json"
  modified:
    - "src/catalyst_trader/contracts/__init__.py"
    - "tests/test_contracts.py"
decisions:
  - "catalyst stays a raw dict on DiligenceInput (not the Catalyst model) to keep the firewall boundary minimal — bare facts only"
  - "pair is str | None (bare peer ticker) — a Hedge object as pair is rejected at model_validate, so no Workflow-2 hedge reasoning can cross the firewall"
  - "_dd_router validates the narrative fixture against the schema the caller passes (schema.model_validate) rather than importing/naming the Wave-3 narrative model — keeps the harness decoupled from the not-yet-existent model name"
metrics:
  duration: ~5min
  completed: 2026-08-15
---

# Phase 6 Plan 1: Diligence Firewall Foundation Summary

The firewall boundary contract (`DiligenceInput`), the one-line `DiligenceDossier.residual_risks` extension, and the shared offline diligence test harness (role-router + 8 locked-key dimension fixtures + narrative fixture) — the Wave-1 foundation every downstream diligence plan builds on. The firewall is enforced as a pydantic property (`extra="forbid"` + field-disjointness), not a runtime check: a leaked Workflow-1/2 field is a `ValidationError`, not a policy violation.

## What Was Built

**Task 1 — DiligenceInput firewall contract + residual_risks (TDD, commit e4c3c2c)**
- `DiligenceInput(extra="forbid", {ticker: str, catalyst: dict, pair: str | None = None})` in `contracts/__init__.py`. `catalyst` is a raw dict (bare facts), `pair` is a bare peer ticker.
- `DiligenceDossier.residual_risks: list[str] = []` (one-line extension, mirrors `RiskAssessment.residual_risks`).
- 4 TDD tests in `test_contracts.py`: field-disjointness from the union of DebateVerdict/TradeProposal/StrategyDossier/RiskAssessment; rejection of `thesis`/`direction`/`Hedge`-as-pair; valid minimal (pair defaults None, bare ticker validates); residual_risks accepted + defaults to [].

**Task 2 — offline diligence harness + fixtures (commit 1147c44)**
- `tests/test_desk_diligence.py`: `DD_DIMENSIONS` (8 locked keys), `MONEY_DIMS` (5-key money-touching subset), `DD_INPUT`, `_dd_router` (role-routing fake run_structured), `_patch_dd_seam` (lazy-imports `desk.diligence` inside the helper so the file imports cleanly before Wave 2 creates the module), and a `test_dd_fixtures_are_valid_signals` smoke test.
- 8 `dd_<dim>_signal.json` fixtures (default = a passing GO set: money dims score >= 0, confidence >= 0.6, each with a resolved `tool:` evidence_ref) + `dd_narrative.json` (with a deliberately GO-flipping "FATAL" red-flag bait for the Wave-3 "narrative cannot flip verdict" test).

## Deviations from Plan

None - plan executed exactly as written.

One in-spirit choice worth noting (not a deviation): the plan's `_dd_router` narrative branch suggested `getattr` on the diligence module to resolve the narrative model. Since the router already receives `schema` as an argument, it validates the recorded narrative via `schema.model_validate(...)` — no import of / name-coupling to the not-yet-existent module, satisfying the same "imports cleanly now" constraint more directly.

## Requirements Progressed

- DILIG-01 (independent firewall boundary) — the structural boundary contract is in place and test-enforced.
- DILIG-03 (diligence dossier shape) — residual_risks added.

## Verification

- `.venv/bin/python -m pytest tests/test_contracts.py -q` → 45 passed.
- `.venv/bin/python -m pytest tests/test_desk_diligence.py -q` → smoke test passed.
- `.venv/bin/python -m pytest -q` → 654 passed (649 baseline + 4 contract + 1 harness). No regression. (2 pre-existing statsmodels ComplexWarnings, out of scope.)

## Notes for Downstream (Waves 2-4)

- The 8 dimension keys in `DD_DIMENSIONS` and the 5-key `MONEY_DIMS` are LOCKED — reuse verbatim.
- `desk/diligence.py` (Wave 2) must expose a `run_structured` seam (mirroring `desk.runtime.run_structured`) for `_patch_dd_seam` to patch.
- Wave 3's synthesizer should assert its own MONEY_TOUCHING frozenset equals `MONEY_DIMS`.
- The recorded dimension set is deliberately a GO set; the narrative fixture carries GO-flipping bait for the "narrative cannot flip a deterministic verdict" guard.

## Self-Check: PASSED

- All created/modified files exist on disk (contracts, harness, 8 signal fixtures + narrative).
- Both commits present: e4c3c2c (Task 1), 1147c44 (Task 2).
- `class DiligenceInput` + `residual_risks` present in contracts.
