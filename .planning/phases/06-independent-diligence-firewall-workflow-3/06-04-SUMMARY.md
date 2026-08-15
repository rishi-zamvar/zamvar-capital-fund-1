---
phase: 06-independent-diligence-firewall-workflow-3
plan: 04
subsystem: diligence desk — firewalled run_diligence orchestrator (end-to-end, offline)
tags: [firewall, diligence, orchestrator, end-to-end, money-critical, tdd, offline]
requires:
  - "catalyst_trader.contracts (DiligenceInput, DiligenceDossier)"
  - "desk/diligence.py Wave-2 layer (gather_dimensions, prep seams, DILIGENCE_PARAMS, zero_liquidity)"
  - "desk/diligence.py Wave-3 layer (synthesize_verdict, MONEY_TOUCHING, _narrative, assemble_dossier, enforce_dossier)"
  - "desk.risk.validate_hedge (independent per-pair hedge re-run behind hedge_context)"
  - "tests/test_desk_diligence.py Wave-1/2/3 harness (_dd_router, _patch_dd_seam, DD_INPUT, dd_* fixtures)"
provides:
  - "desk/diligence.py::run_diligence — the firewalled Workflow-3 entry point (signature accepts ONLY DiligenceInput)"
  - "ungrounded-money hard NO-GO: a money-touching dim with no raw-data seam value cannot yield a GO"
  - "the full second desk composed end-to-end offline: quant server -> prep seams -> 8 dims -> deterministic verdict -> narrative -> cite-or-drop gate -> DiligenceDossier"
affects:
  - "Phase 7 (data-layer fetchers) supplies run_diligence's market_data (options/financials/ownership/trial/hedge/liquidity) — currently caller/test-supplied behind seams"
  - "Phase 6.7 (MD reconciliation loop) consumes the DiligenceDossier this entry point returns"
tech-stack:
  added: []
  patterns:
    - "run_desk mirror: run_diligence is a thin composition (a gather + a deterministic call + two awaits + a gate), no new logic"
    - "Firewall as a signature: the ONLY trade-facts parameter is input: DiligenceInput — a Workflow-1/2 leak is a type error, proven via typing.get_type_hints (belt-and-suspenders over the extra=forbid boundary)"
    - "Ungrounded-money hard NO-GO: MONEY_TOUCHING - set(dimension_context) - {liquidity if quote present} — a money dim with no raw-data seam value is forced NO-GO before the narrative, keeping the LLM out of the money decision (mirrors the zero-liquidity hard-fail)"
    - "market_data is the caller-supplied market context (mirrors run_portfolio's 'caller supplies the context' convention); Phase-7 fetchers fill it, tests mock it"
key-files:
  created: []
  modified:
    - "src/catalyst_trader/desk/diligence.py"
    - "tests/test_desk_diligence.py"
decisions:
  - "run_diligence signature is (conn, input: DiligenceInput, *, market_data: dict, embed=None) — the firewall is the absence of any Workflow-1/2-typed parameter, verified by test_run_diligence_signature_is_firewalled (get_type_hints disjoint from DebateVerdict/TradeProposal/StrategyDossier/RiskAssessment)"
  - "An ungrounded money dim (missing raw-data key in market_data) forces NO-GO even when its dimension fixture is a PASSING GO signal — closes the 'hallucinated finding passes' gap; the deterministic layer must not trust an agent signal for a money dim that had no grounding data"
  - "hedge/options/liquidity keys are optional-in-shape but their absence lands in ungrounded_money (or forces liquidity_zero=True) — a missing money seam is never a silent pass"
  - "params = DILIGENCE_PARAMS threaded to options_context / synthesize_verdict / assemble_dossier; kb.load_params is never called for diligence thresholds (grep-gate clean)"
metrics:
  duration: ~5min
  completed: 2026-08-15
---

# Phase 6 Plan 4: Firewalled run_diligence Orchestrator Summary

`run_diligence` — the firewalled Workflow-3 entry point that composes the whole second desk end-to-end, offline. It mirrors `run_desk`: build the quant MCP server, thread the prep seams into an 8-dimension fan-out, run the DETERMINISTIC `synthesize_verdict`, add the verdict-free opus narrative, and gate through `enforce_dossier` cite-or-drop, returning an evidence-backed `DiligenceDossier`. The firewall is proven at the signature level (the only trade-facts parameter is `input: DiligenceInput` — a Workflow-1/2 leak is a type error), and the money crux is closed end-to-end: a money-touching dimension with no raw-data seam value is forced NO-GO, so no hallucinated finding can produce a false GO. Fully offline, TDD (failing test first).

## What Was Built

**Task 1 — run_diligence orchestrator (commits 0ea6de2 impl + prior RED test commit)**
- `async def run_diligence(conn, input: DiligenceInput, *, market_data: dict, embed=None) -> DiligenceDossier`:
  1. `params = DILIGENCE_PARAMS` (the single, seed-proof threshold source — never the KB fitted-param seam).
  2. Build `dimension_context` from the prep seams — including both money dims (financials, ownership_flow) that previously got an empty string; a `None` prep is dropped (never an empty-string prompt).
  3. `liquidity_zero = zero_liquidity(md["liquidity_quote"])` (or `True` if the quote is absent).
  4. `ungrounded_money = MONEY_TOUCHING - set(dimension_context) - ({"liquidity"} if quote else set())` — the set of money dims with no raw-data grounding.
  5. `findings = await gather_dimensions(...)` (the 8-dim fan-out).
  6. `verdict = synthesize_verdict(findings, liquidity_zero=..., params=params)` — DETERMINISTIC, decided before the narrative; then `if ungrounded_money: verdict = "no_go"`.
  7. `narrative = await _narrative(findings, verdict)` — the LLM writes the story of a fixed decision.
  8. `dossier = assemble_dossier(...)` then `return await enforce_dossier(conn, dossier, signals=findings)` — cite-or-drop before return.
- Test harness: extended the shared `_dd_router` with a `SupportCheck` branch so `enforce_dossier`'s semantic gate runs offline (`supported=True`), plus `_full_market_data()` / `_mock_valid_hedge()` helpers for the end-to-end path.

**Task 2 — full-suite gate + Graphify re-index**
- Full offline suite green (see Verification). No regression from the additive orchestrator.
- Phase sign-off invariants each map to a now-passing test (see cross-check below).
- Graphify re-index: FLAGGED AS A FOLLOW-UP (see Known Follow-ups) — the executor `graphify` CLI has no `index` subcommand and there is no `graphify-out/graph.json` to update; the code-graph re-index runs through the interactive `/graphify` command, which a subagent executor cannot invoke.

## Money-Critical Invariants Enforced (test-backed)

- `run_diligence` accepts ONLY `DiligenceInput` — no parameter carries a Workflow-1/2 artifact (`test_run_diligence_signature_is_firewalled`, via `typing.get_type_hints` disjoint from DebateVerdict/TradeProposal/StrategyDossier/RiskAssessment).
- The full pipeline runs end-to-end offline and returns a `DiligenceDossier` with a deterministic verdict, 8 per-dimension entries, surviving evidence refs, and residual_risks (`test_run_diligence_end_to_end`).
- The deterministic verdict wins over the narrative through the real pipeline: a failing (grounded) financials dim yields no_go regardless of the narrative's tone (`test_run_diligence_verdict_is_deterministic`).
- Zero-liquidity is a hard NO-GO end-to-end (`test_run_diligence_zero_liquidity_no_go`).
- A money-touching dim with NO raw-data seam value forces NO-GO even though its fixture is a PASSING GO signal — no false GO from a hallucination (`test_run_diligence_money_dim_without_raw_data_is_no_go`, parametrized over financials + ownership).

## Phase Sign-Off Cross-Check (each invariant -> passing test)

- **Firewall (DILIG-01):** field-disjoint + extra=forbid (`test_contracts.py` DiligenceInput tests) + signature-firewalled (`test_run_diligence_signature_is_firewalled`).
- **Dimensions (DILIG-02):** 8 dimensions cited + one fan-out (`test_eight_dimensions_run_concurrently`), options degrade on illiquid (`test_options_dimension_degrades_on_illiquid`), hedge independent (`test_hedge_dimension_revalidates_independently`).
- **Synthesizer (DILIG-03):** deterministic asymmetry — one money dim / zero-liquidity / tie -> NO-GO (`test_one_money_dimension_failure_forces_no_go`, `test_zero_liquidity_hard_fails`, `test_ties_default_no_go`); narrative-cannot-flip (`test_llm_narrative_cannot_override_verdict`, `test_narrative_schema_is_narrative_only`); cite-or-drop + residual_risks (`test_dossier_cite_or_drop`, `test_run_diligence_end_to_end`).
- **Thresholds from params:** `test_dimension_passed_reads_params`, `test_diligence_params_survive_seeded_path`; `load_params` grep-gate clean in diligence.py.
- **No scraped-to-order path:** no execution surface in this phase (verified by absence — Phase 11 owns execution).

## Deviations from Plan

**1. [Rule 3 — grep-gate] reworded one comment to keep the `load_params` grep-gate clean**
- **Found during:** Task 1 acceptance greps.
- **Issue:** the acceptance criterion `grep -n "kb.load_params\|load_params" src/.../diligence.py` must return NOTHING, but a comment on the `params = DILIGENCE_PARAMS` line read "…NOT kb.load_params", tripping the gate.
- **Fix:** reworded to "…NOT the KB fitted-param seam". No behavior change (same discipline as 06-03's grep-gate deviation).
- **Files modified:** src/catalyst_trader/desk/diligence.py.
- **Commit:** 0ea6de2.

## Known Follow-ups

- **Graphify re-index (required, per CLAUDE.md convention):** re-index the code graph so Phase 7 navigates the current graph including `desk/diligence.py::run_diligence`, `synthesize_verdict`, and `DiligenceInput`. The executor `graphify` CLI exposes no `index` subcommand and there is no existing `graphify-out/graph.json`; the re-index must be run via the interactive `/graphify` command by the user/orchestrator. This is code-complete for Phase 6 — the re-index is a navigation-convenience follow-up, not a code gap.

## Verification

- `.venv/bin/python -m pytest tests/test_desk_diligence.py::test_run_diligence_signature_is_firewalled tests/test_desk_diligence.py::test_run_diligence_end_to_end tests/test_desk_diligence.py::test_run_diligence_verdict_is_deterministic tests/test_desk_diligence.py::test_run_diligence_zero_liquidity_no_go tests/test_desk_diligence.py::test_run_diligence_money_dim_without_raw_data_is_no_go` -> 6 passed.
- `.venv/bin/python -m pytest tests/test_desk_diligence.py -q` -> 33 passed.
- `.venv/bin/python -m pytest tests/test_desk_diligence.py tests/test_contracts.py -q` -> 78 passed.
- `.venv/bin/python -m pytest -q` -> 689 passed (683 baseline + 6 new), 2 pre-existing statsmodels ComplexWarnings (out of scope). No regression, zero live API.
- Acceptance greps: `async def run_diligence` present; `synthesize_verdict`/`enforce_dossier`/`gather_dimensions` all inside run_diligence; `financials_context`/`ownership_context`/`ungrounded_money`/`DILIGENCE_PARAMS` all wired; `load_params` grep clean; typing firewall check succeeds (DiligenceInput in hints, forbidden types disjoint).

## Requirements Closed

- **DILIG-01** (firewall — receives only {ticker, catalyst, pair}) — closed: the signature accepts ONLY DiligenceInput, proven at the type level; no code path from the diligence desk to a Workflow-1/2 artifact.
- **DILIG-02** (multi-dimensional DD from raw sources) — closed: 8 adversarial dimensions fan out with their prep-seam contexts wired end-to-end; both money dims (financials, ownership_flow) grounded to raw-data seams.
- **DILIG-03** (adversarial synthesizer -> DiligenceDossier) — closed: the deterministic verdict + verdict-immutable narrative + cite-or-drop gate compose end-to-end into an evidence-backed GO/NO-GO dossier with residual_risks.

## Notes for Downstream

- **Phase 7 (data layer):** supply `market_data` = `{"options": {"quote", "underlying_price", "days_to_event"}, "financials": {...}, "ownership": {...}, "trial": {...}, "hedge": {"entry", "exit_by_date", "analog_gaps", "prices"}, "liquidity_quote": {"bid", "volume", "oi"}}`. A MISSING money key forces NO-GO by design — the fetcher must fill every money seam for a GO to be possible.
- **Phase 6.7 (MD reconciliation):** `run_diligence` returns the `DiligenceDossier` the MD/GP reviews; the firewall stays sealed — only DD findings flow up.

## Self-Check: PASSED

- `src/catalyst_trader/desk/diligence.py` exists on disk; `run_diligence` present.
- Commits present: RED test commit + 0ea6de2 (feat run_diligence).
- SUMMARY.md written; full suite 689 passed verified.
