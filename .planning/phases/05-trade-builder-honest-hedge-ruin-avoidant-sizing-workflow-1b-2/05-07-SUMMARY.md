---
phase: 05-trade-builder-honest-hedge-ruin-avoidant-sizing-workflow-1b-2
plan: 07
subsystem: desk
tags: [portfolio, select-book, pm-promote-kill, memo, pre-mortem, risk-reconciliation, PORT-01, PORT-04, PORT-05, HEDGE-05, OPS-01, OPS-02]

# Dependency graph
requires:
  - phase: 05 (05-01)
    provides: StrategyDossier + PortfolioContext + TradeProposal(+Hedge) contracts
  - phase: 05 (05-04)
    provides: risk.assess → RiskAssessment carrying recommended_size_pct + validated Hedge object
  - phase: 05 (05-06)
    provides: builder.build → preliminary TradeProposal (size/hedge overwritten by reconciliation)
  - phase: 03
    provides: quant.concentration (Herfindahl heat cap) + quant.exposure (gross Σ|w|, net Σw)
  - phase: 04
    provides: desk.runtime.run_structured seam + run_desk composition pattern
provides:
  - "desk/portfolio.py::select_book(candidates, open_book, weekly_budget, heat_cap, target_weekly=0.01) — aggregate-to-~1% by SELECTION only, never resizing a leg above survival size"
  - "desk/portfolio.py::author_memo / author_pre_mortem / pm_decide — memo + pre-mortem authored in SEPARATE run_structured calls preceding the opus PM decision (author ≠ approver, OPS-01/02)"
  - "desk/portfolio.py::Candidate + _which_risk_covered + PositionMemo/PreMortem/PMDecision schemas"
  - "desk/orchestrator.py::run_portfolio — Workflow-1b entry point: builder → risk → RECONCILE → select_book → PM over the week's verdicts"
affects: [phase-06 diligence firewall reads the promoted StrategyDossier; phase-08 real open-book ledger replaces the stub]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "select_book is the ONE new portfolio math tool — a thin greedy selector composing quant.concentration/exposure; 1% is a book-level SELECTION outcome, never a leg sizing input"
    - "RECONCILE step (BLOCKER-1): proposal.model_copy(update={size_pct: risk.recommended_size_pct, hedge: risk.hedge}) right after risk.assess and BEFORE select_book — the builder's preliminary size/hedge are never promoted; validate_hedge is NOT re-called (single validation lives on risk.hedge)"
    - "Narrow LLM schemas (PositionMemo/PreMortem/PMDecision) mirror builder.BuilderNarrative — the model authors prose only; trade/size/hedge/residual/coverage are assembled deterministically and can't be injected"
    - "which_risk_covered derived from validated + payoff_direction + instrument (NOT a trusted `covers` string) — an unvalidated/None hedge can never surface as covering the idiosyncratic binary (HEDGE-05)"
    - "Author ≠ approver enforced structurally: memo + pre-mortem are distinct run_structured calls preceding pm_decide (opus); tested by recording seam call order (OPS-01/02)"

key-files:
  created:
    - src/catalyst_trader/desk/portfolio.py
    - tests/fixtures/agent_responses/position_memo.json
    - tests/fixtures/agent_responses/pre_mortem.json
    - tests/fixtures/agent_responses/pm_dossier.json
  modified:
    - src/catalyst_trader/desk/orchestrator.py
    - tests/test_desk_portfolio.py

key-decisions:
  - "run_portfolio takes the week's work as BUNDLED items ({verdict, catalyst, entry, risk_inputs}) rather than bare DebateVerdicts — the desk has no price/analog feed this phase, so the caller supplies the per-leg market context builder.build + risk.assess need (deviation, Rule 3 — same class as 05-06's carry-forward `entry`)"
  - "PM run_structured returns a narrow PMDecision (verdict_summary/dissent_log/all_evidence_refs) and the StrategyDossier is assembled in code — the LLM never authors trade/size/hedge/residual (mirrors builder.BuilderNarrative; pm_dossier.json is a PMDecision fixture, not a full dossier)"
  - "which_risk_covered is re-derived from validated+payoff_direction+instrument, not read off Hedge.covers — defensive HEDGE-05 guarantee that an unvalidated shape can never report idiosyncratic coverage"
  - "PortfolioContext.corr_to_open_positions is [] this phase — the open-book stub carries weights only (no price history), so per-position correlation can't be computed until the Phase-8 ledger; documented, not stubbed-and-hidden"
  - "residual_net_long is computed over the promoted book (exposure(promoted_weights).detail.net) and disclosed on every dossier — the book-level HEDGE-05 residual"

requirements-completed: [PORT-01, PORT-04, PORT-05, HEDGE-05, OPS-01, OPS-02]

# Metrics
duration: 22min
completed: 2026-08-15
---

# Phase 5 Plan 7: Portfolio Layer + Workflow-1b Entry Point Summary

**`desk/portfolio.py` + `run_portfolio` turn the week's `DebateVerdict`s into one recommended portfolio: each verdict is built into a preliminary `TradeProposal`, risk-assessed, then RECONCILED so the promoted trade carries the Risk Committee's ruin-capped `recommended_size_pct` and its validated `Hedge` object (never the builder's preliminary estimate — BLOCKER-1); `select_book` aggregates the survivable legs toward ~1% by SELECTION only (never resizing a leg above its survival size, zero-trade weeks valid); the PM promotes/kills on concentration/exposure/budget after a position memo + pre-mortem authored in SEPARATE run_structured calls (author ≠ approver); the dossier discloses residual net-long (gross ≥ |net|) and which risk is actually covered (from the reconciled hedge).**

## Performance

- **Duration:** ~22 min
- **Completed:** 2026-08-15
- **Tasks:** 3 (each TDD RED→GREEN)
- **Files:** 4 created, 2 modified

## Accomplishments
- `select_book(candidates, open_book, weekly_budget, heat_cap, target_weekly=0.01)` — the ONE new portfolio math tool: greedy inclusion by `expected_move/size` under the weekly budget + a `concentration` heat cap over the COMBINED (promoted + open) book. Provably never resizes a leg above its survival size (selection only); returns the promoted subset + aggregate `Σ(size_pct·expected_move)`; empty promote = a valid zero-trade week.
- `author_memo` + `author_pre_mortem` + `pm_decide` — the memo (with kill_criteria + coverage + residual) and the pre-mortem ("assume it lost — why") are authored in run_structured calls SEPARATE from and BEFORE the opus PM decision (author ≠ approver, OPS-01/02). Narrow LLM schemas; the StrategyDossier's trade/size/hedge/residual/coverage are assembled in code.
- `_which_risk_covered` derives coverage from `validated + payoff_direction + instrument` (idiosyncratic only for a validated −1 equity peer, sector_beta for an inverse_etf, else none) — an unvalidated/None hedge can never claim idiosyncratic coverage (HEDGE-05).
- `run_portfolio(conn, embed, verdicts, open_book)` — the Workflow-1b entry point mirroring `run_desk`: builder.build → risk.assess → **RECONCILE** (`model_copy(update={size_pct, hedge})`) → select_book → memo/pre-mortem → PM. The reconciliation is the BLOCKER-1 fix: the promoted trade carries the Risk Committee's authoritative size + validated hedge, not the builder's preliminary values. `validate_hedge` is NOT re-called (single validation lives on `risk.hedge`).
- Zero-trade week (all builds return None) returns `[]` cleanly; all-kill (nothing clears budget/heat) returns kill dossiers — both valid successes, not errors.
- 22 offline tests (quant + KB real, all run_structured seams monkeypatched); full suite **627 → 649 green**, zero regression, zero live API.

## Task Commits

1. **Task 1: select_book selector (aggregate to ~1% by selection; never resize above survival)** — `e3a7750` (test RED) → `fdc8a0d` (feat GREEN)
2. **Task 2: PM pass + memo + pre-mortem (author ≠ approver) → StrategyDossier** — `3919c24` (test RED) → `f0028b5` (feat GREEN)
3. **Task 3: run_portfolio orchestrator (builder → risk → RECONCILE → select_book → PM)** — `01ecc49` (test RED) → `b4a599f` (feat GREEN)

## Files Created/Modified
- `src/catalyst_trader/desk/portfolio.py` — `Candidate`, `select_book`, `PositionMemo`/`PreMortem`/`PMDecision`, `_which_risk_covered`, `author_memo`, `author_pre_mortem`, `pm_decide` + prompt helpers.
- `src/catalyst_trader/desk/orchestrator.py` — `run_portfolio` (the reconcile + composition) added; `run_desk` untouched.
- `tests/test_desk_portfolio.py` — 22 offline tests (select_book aggregate/no-resize/heat/zero-trade; memo/pre-mortem separation; residual + gross≥|net|; coverage mapping; reconciliation of size + hedge; zero-trade + all-kill).
- `tests/fixtures/agent_responses/{position_memo,pre_mortem,pm_dossier}.json` — the three PM-seam fixtures.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `run_portfolio` takes BUNDLED work items, not bare verdicts**
- **Found during:** Task 3 (composing builder.build + risk.assess).
- **Issue:** The plan signature `run_portfolio(conn, embed, verdicts, open_book)` implies bare `DebateVerdict`s, but `builder.build` needs `(catalyst, entry)` and `risk.assess` needs `(catalyst, p_loss, gap, analog_gaps, prices)` — none of which a desk with no live price/analog feed can invent this phase.
- **Fix:** Each element of `verdicts` is a work-item dict bundling the verdict with its market context (`{verdict, catalyst, entry, risk_inputs}`). Same class as 05-06's carry-forward `entry`; the caller supplies market inputs, the composition can't fabricate them. Acceptance grep `async def run_portfolio(` still holds.
- **Files modified:** src/catalyst_trader/desk/orchestrator.py
- **Committed in:** b4a599f

**2. [Rule 3 - Blocking] PM run_structured returns a narrow PMDecision; the dossier is assembled in code**
- **Found during:** Task 2.
- **Issue:** The plan sketch had `pm_decide` return a `StrategyDossier` from run_structured then overwrite deterministic fields — but StrategyDossier requires a full `trade` (TradeProposal) + `portfolio_context` the LLM must not author, and the fixture would have to be a complete valid dossier.
- **Fix:** `pm_decide`'s run_structured call returns a narrow `PMDecision` (verdict_summary/dissent_log/all_evidence_refs); the StrategyDossier is built in code with the deterministic trade/size/hedge/residual/coverage/memo/pre-mortem/kill_criteria. This mirrors the already-shipped `builder.BuilderNarrative` pattern (money numbers never authored by the model) and keeps `pm_dossier.json` a small PMDecision fixture.
- **Files modified:** src/catalyst_trader/desk/portfolio.py
- **Committed in:** f0028b5

---

**Total deviations:** 2 auto-fixed (both blocking, plumbing/consistency). No scope change — the money-critical invariants (reconcile-before-select, 1%-by-selection-never-resize, author≠approver, residual disclosure, honest coverage) are all met exactly as specified.

## Known Stubs
- `PortfolioContext.corr_to_open_positions = []` — the open-book is a stub shape this phase (`{ticker, weight, catalyst_id}`, per RESEARCH Open Q2); with no per-position price history there is no correlation to compute. The real ledger + price feed arrive in Phase 8, which will populate this. Documented, not hidden — the concentration/exposure/budget constraints that actually gate promotion this phase are all live and real.

## Issues Encountered
One test-side bug (asserted `c.weight` instead of `c.book_weight()` in the heat-cap test) caught on the first GREEN run and fixed immediately; production code was correct.

## User Setup Required
None.

## Next Phase Readiness
- `run_portfolio` is the Workflow-1b entry point Phase-6 (independent diligence firewall) consumes: it reads the promoted `StrategyDossier` (with its reconciled trade, residual disclosure, memo, pre-mortem, kill_criteria) and validates from RAW sources.
- Carry-forward for Phase 8: replace the open-book stub (`{ticker, weight, catalyst_id}`) with the real position ledger + a price feed, which unlocks `corr_to_open_positions` and combined-book correlation in the PM pass.
- Graphify re-index (CONVENTIONS.md) is a `/graphify`-command flow, not a CLI subcommand — pending a manual `/graphify` run to refresh `graphify-out/` after this phase's code.
- No blockers.

---
*Phase: 05-trade-builder-honest-hedge-ruin-avoidant-sizing-workflow-1b-2*
*Completed: 2026-08-15*

## Self-Check: PASSED

All created/modified files exist on disk; all six task commits (e3a7750, fdc8a0d, 3919c24, f0028b5, 01ecc49, b4a599f) present in history. Full suite 649 green (627 existing + 22 new), zero live API; all acceptance-criteria greps pass.
