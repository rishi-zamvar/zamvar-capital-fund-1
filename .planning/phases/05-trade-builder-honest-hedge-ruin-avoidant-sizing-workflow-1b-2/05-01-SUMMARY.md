---
phase: 05-trade-builder-honest-hedge-ruin-avoidant-sizing-workflow-1b-2
plan: 01
subsystem: contracts
tags: [contracts, honest-hedge, estimate-gate, workflow-1b]
requires: [contracts (Phase-2), DebateVerdict (Phase-4)]
provides:
  - Hedge model (honest-hedge abstraction, options-ready)
  - EstimateVetting model (estimate-gate verdict)
  - extended TradeProposal / RiskAssessment / StrategyDossier
affects:
  - src/catalyst_trader/contracts/__init__.py
tech-stack:
  added: []
  patterns:
    - "structural unrepresentability via field_validator reading info.data (cross-field)"
    - "options-ready enum member + one guard (put_option legal, not executable)"
key-files:
  created: []
  modified:
    - src/catalyst_trader/contracts/__init__.py
    - tests/test_contracts.py
decisions:
  - "Hedge.covers validator makes a fake idiosyncratic hedge raise at model_validate — money-safety is structural, not prompt-caught (HEDGE-01/04)"
  - "inverse_etf (LABD) can only ever be sector_beta; put_option is a legal-but-unpromotable enum member (options-ready, not options-executed)"
  - "RiskAssessment carries the validated Hedge OBJECT (hedge: Hedge | None), distinct from hedge_valid: bool, so 05-07 can reconcile it onto the promoted proposal (BLOCKER-1)"
metrics:
  duration: 3min
  completed: 2026-08-15
  tasks: 2
  files: 2
---

# Phase 05 Plan 01: Contract Extensions (Honest Hedge + Estimate Gate) Summary

Extended the Phase-2 contract module with the structural `Hedge` abstraction, the `EstimateVetting`
model, and the Workflow-1b fields on `TradeProposal`, `RiskAssessment`, and `StrategyDossier` —
making the honest-hedge money-safety guarantees unrepresentable-if-illegal at the pydantic boundary
rather than prompt-caught.

## What Shipped

- **`Hedge`** — `instrument` (equity_peer / inverse_etf / put_option), `ticker`, `payoff_direction`,
  `validated`, `covers` (idiosyncratic / sector_beta / none), `mechanism`, `conditional_worst`. A
  `@field_validator("covers")` reading `info.data` enforces three invariants at `model_validate`:
  only a `validated` inverse (`payoff_direction == -1`) peer may claim `idiosyncratic`; an
  `inverse_etf` (LABD) may never claim `idiosyncratic` (sector_beta only); a `put_option` always
  raises (architected, not executable in v1).
- **`EstimateVetting`** — `verdict` (endorse / reject), `input_refs`, `dropped_inputs`, `reasons`,
  `uncertainty_widened`.
- **`TradeProposal`** — replaced `hedge_long: str` with `hedge: Hedge | None` (None = HEDGE-04
  fallback); added `holds_through_catalyst`, `catalyst_id`, `direction`, `estimate_vetting`,
  `sl_advisory`. stop_loss/take_profit noted advisory when `sl_advisory`.
- **`RiskAssessment`** — added `conditional_payoff_matrix`, `conditional_worst`, `hedge: Hedge | None`
  (the OBJECT, BLOCKER-1), `hedge_valid`, `recommended_size_pct`, `ruin_at_size`.
- **`StrategyDossier`** — added `residual_net_long`, `which_risk_covered`, `position_memo`,
  `pre_mortem`, non-empty `kill_criteria` (validator mirrors DebateVerdict).

## Tasks

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Hedge + EstimateVetting models with structural validators | a74d2b6 | contracts/__init__.py, tests/test_contracts.py |
| 2 | Extend TradeProposal, RiskAssessment, StrategyDossier | fd8b34a | contracts/__init__.py, tests/test_contracts.py |

## Verification

- `.venv/bin/python -m pytest tests/test_contracts.py -q` → 41 passed.
- `.venv/bin/python -m pytest -q` → 516 passed (no regression; 18 new contract tests).
- Structural invariants enforced at the boundary: fake idiosyncratic hedge (unvalidated / co-move),
  LABD-idiosyncratic, and promoted put_option all raise; the `hedge=None` fallback is representable;
  `RiskAssessment` round-trips both a Hedge object and None.

## Deviations from Plan

None — plan executed exactly as written. (Both tasks followed TDD: failing test → model → green.)

## Known Stubs

None. All fields are typed carriers consumed by downstream 05-* plans (builder, risk, portfolio,
estimate gate); no hardcoded/placeholder values introduced.

## Self-Check: PASSED

- FOUND: src/catalyst_trader/contracts/__init__.py (class Hedge, class EstimateVetting, extended models)
- FOUND: tests/test_contracts.py (Hedge/EstimateVetting/extension tests)
- FOUND commit: a74d2b6
- FOUND commit: fd8b34a
