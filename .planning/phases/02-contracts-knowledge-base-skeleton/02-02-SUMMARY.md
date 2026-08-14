---
phase: 02-contracts-knowledge-base-skeleton
plan: 02
subsystem: contracts
tags: [pydantic, contracts, validation, anti-hallucination]
requires:
  - phase: 01-data-integrity-catalyst-feed
    provides: "models.py field_validator + _at_least_one_source citation-boundary pattern"
provides:
  - "catalyst_trader.contracts module: AnalystSignal, DebateVerdict, TradeProposal, RiskAssessment, StrategyDossier, DiligenceDossier (+ KeyFinding, PortfolioContext)"
  - "extra='forbid' + bounded score/confidence + required non-empty evidence_ref at every inter-layer boundary"
  - "composite contracts with typed nested sub-contracts (StrategyDossier embeds TradeProposal + PortfolioContext)"
affects:
  - analysts (AnalystSignal producers)
  - debate/moderator (DebateVerdict)
  - trade-builder (TradeProposal)
  - risk (RiskAssessment)
  - portfolio-manager (StrategyDossier)
  - diligence (DiligenceDossier)
tech-stack:
  added: []
  patterns: ["pydantic v2 ConfigDict(extra='forbid') strict-boundary contract", "Field bounds for money-path ranges", "field_validator citation-required (mirrors Phase-1 _at_least_one_source)", "Literal for verdict enums", "typed nested sub-contracts in composites"]
key-files:
  created:
    - src/catalyst_trader/contracts/__init__.py
    - tests/test_contracts.py
  modified: []
key-decisions:
  - "extra='forbid' on all 8 models — LLM-hallucinated keys rejected at model_validate, not silently accepted"
  - "PortfolioContext extracted as its own extra='forbid' submodel so StrategyDossier's nested dict is itself strictly validated"
  - "DiligenceDossier.per_dimension kept as list[dict] (skipped a DimensionResult submodel) — no downstream field access yet; add typed model when a DD consumer needs it"
patterns-established:
  - "Strict-boundary contract: model_config = ConfigDict(extra='forbid') + Field bounds + field_validator on evidence"
  - "Citation-at-the-boundary: evidence_ref = Field(min_length=1) + non-empty key_findings validator = contract-side half of KB-02"
requirements-completed: [KB-02]
duration: ~3min
completed: 2026-08-14
---

# Phase 2 Plan 02: Inter-Layer Contracts Summary

**Six pydantic v2 inter-layer contracts (AnalystSignal, DebateVerdict, TradeProposal, RiskAssessment, StrategyDossier, DiligenceDossier) with `extra="forbid"`, bounded score/confidence, and a required non-empty evidence_ref — the anti-hallucination spine at every agent message boundary.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-08-14T22:07:57Z
- **Completed:** 2026-08-14T22:12:00Z
- **Tasks:** 2 (TDD)
- **Files modified:** 2 (both created)

## Accomplishments

- All six inter-layer contracts implemented in `contracts/__init__.py`, each with `ConfigDict(extra="forbid")` — an unknown/hallucinated key is rejected by `model_validate`.
- Citation-at-the-boundary enforced: `KeyFinding.evidence_ref = Field(min_length=1)` + a `key_findings` validator requiring ≥1 sourced finding (the contract-side half of KB-02, mirroring Phase-1's `_at_least_one_source`).
- Money-path ranges bounded: `score` ∈ [-1, 1], `confidence` ∈ [0, 1] — out-of-range values rejected.
- Composites validate their nested contracts: `StrategyDossier` embeds a typed `TradeProposal` + `PortfolioContext` (a malformed nested trade is rejected); `StrategyDossier.decision` / `DiligenceDossier.verdict` are `Literal` enums.

## Task Commits

1. **Task 1: RED — malformed-payload rejection suite** — `34f956f` (test)
2. **Task 2: GREEN — six pydantic contracts** — `5cd9fb7` (feat)

_TDD: RED (failing suite, module absent) → GREEN (contracts implemented, 20 tests pass). No refactor needed — code was minimal on first pass._

## Files Created/Modified

- `src/catalyst_trader/contracts/__init__.py` — the six contracts + `KeyFinding` + `PortfolioContext`, all `extra="forbid"`.
- `tests/test_contracts.py` — good-payload validation + malformed-payload rejection (extra key, empty evidence_ref, empty key_findings, out-of-range score/confidence, bad Literal, malformed nested trade) for all six.

## Decisions Made

- **`PortfolioContext` as its own `extra="forbid"` submodel** rather than an inline `dict` — so the nested portfolio block is itself strictly validated, not a permissive dict.
- **`DiligenceDossier.per_dimension` kept as `list[dict]`** — no downstream consumer reads its fields yet; a typed `DimensionResult` submodel is a later add when a DD reader needs it (ponytail: don't pre-structure).

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Contracts are importable from `catalyst_trader.contracts` and ready for every downstream layer (analysts → debate → trade builder → risk → PM → diligence).
- Full suite green: `.venv/bin/pytest -q` → **208 passed** (188 prior + 20 new contract tests). No regression.
- Plans 02-03 (KB claim write-path / provenance) and 02-04 remain in this phase.

## Self-Check: PASSED

Both created files present; both task commits (34f956f, 5cd9fb7) in history.

---
*Phase: 02-contracts-knowledge-base-skeleton*
*Completed: 2026-08-14*
