# Phase 6: Independent Diligence Firewall (Workflow 3) - Context

**Gathered:** 2026-08-15
**Status:** Ready for planning
**Mode:** Auto-generated (autonomous run; decisions locked from PROJECT.md + ROADMAP success criteria)

<domain>
## Phase Boundary

A structurally isolated SECOND desk that tries to KILL a promoted trade from RAW sources — a real four-eyes check, not a rubber stamp. Takes a promoted trade's minimal facts, runs independent multi-dimensional due diligence, and emits a GO/NO-GO `DiligenceDossier`. Stops at the dossier for the human gate — NO live execution (Phase 11), NO re-use of Workflow-1/2 (Phase 4/5) reasoning.
</domain>

<decisions>
## Implementation Decisions (LOCKED — from ROADMAP success criteria + PROJECT.md DILIG + Fund constraints)

### 1. The FIREWALL is the crux (DILIG-01) — enforced structurally, not by convention
- `run_diligence` accepts ONLY a minimal `DiligenceInput` (e.g. `{ticker, catalyst, pair?}`) — a NEW contract that STRUCTURALLY CANNOT carry Workflow-1/2 reasoning (no DebateVerdict, no TradeProposal, no bull/bear notes, no thesis). Mirror the Phase-5 discipline where a fake hedge was made unrepresentable at the pydantic boundary: here the leak is made unrepresentable by the input type + the absence of any code path from the diligence desk to Workflow-1/2 artifacts.
- Adversarial FRAMING in every dimension prompt: the diligence desk's job is to find reasons this trade FAILS, from scratch.
- TEST-ENFORCED: a test proves the diligence agents never receive any Workflow-1/2 field (the input type can't hold it) — the "provably never passed in" success criterion.

### 2. Multi-dimensional DD from RAW sources (DILIG-02) — reuse the desk pattern; agents interpret, tools compute
Each dimension is an analyst-style agent producing a SOURCE-CITED signal (reuse `desk/analysts.py` flat async fan-out + the single `run_structured` seam; agents NEVER do money arithmetic — deterministic tools compute). Dimensions (each maps to raw sources already available or free):
- **Trial stats / endpoints** → ClinicalTrials.gov v2 provider (existing).
- **Regulatory precedent** → base rates + KB analogs (existing) + FDA/Federal Register free sources (data-layer).
- **Financials / runway** → FMP provider (existing) + `quant.cash_runway` / `pipeline_value`.
- **Ownership / flow / short interest** → FINRA free Query API + SEC EDGAR (data-layer).
- **Options-implied move** → the CBOE free delayed-quotes feed behind the pluggable `implied_move` SOURCE SEAM (from Phase 5); DD dimension takes the value IN / via a mockable provider so it's offline-testable, degrades gracefully when a name has illiquid options.
- **Hedge / correlation re-validation** → REUSE `desk/risk.validate_hedge` + `quant.conditional_payoff` / `cointegration` (independent re-run, not trusting Workflow-2's result).
- **Liquidity** → quote/volume checks (only zero-liquidity is a hard fail, per Fund design).
- **Historical analog** → `kb.analog_query` (existing).

### 3. Adversarial synthesizer (DILIG-03) — asymmetric, rewards NO-GO
- Combines the dimensions and is DELIBERATELY ASYMMETRIC: a SINGLE failing money-touching dimension forces NO-GO (easy to kill, hard to clear). GO requires data-backed confidence across all money dimensions.
- Emits `DiligenceDossier {go_no_go, evidence, residual_risks}` (contract exists from Phase 2 — extend only if a field is missing, mirroring the Phase-4/5 contract-extension precedent).
- Cite-or-drop enforced (REUSE `desk/verifier` machinery): an uncited diligence claim is dropped; a NO-GO or GO must be evidence-backed.

### 4. Reuse discipline (biggest cost lever — honor the research reuse-vs-new verdict)
REUSE: `desk/analysts.py` pattern, `run_structured` seam, `desk/verifier` (cite-or-drop), quant tools (`cash_runway`, `pipeline_value`, `conditional_payoff`, `cointegration`, `implied_move`, liquidity), providers (clinicaltrials, fmp), `kb.analog_query`, `desk/risk.validate_hedge`, the `DiligenceDossier` contract. NEW: `contracts.DiligenceInput` (the firewall boundary), `desk/diligence.py` (the dimensions + adversarial synthesizer), a `run_diligence` orchestrator entry point. Query the Graphify graph (freshly re-indexed) to locate reuse targets — do NOT re-read the src/ tree.

### 5. Offline + money-safety
Fully offline: monkeypatch `run_structured`; mock providers / pass raw data in; zero live API in pytest. No path from scraped/raw content to an order (there is no execution in this phase at all). Full TDD (tests before logic, `.venv/bin/python -m pytest` — bare python NOT on PATH).
</decisions>

<code_context>
## Existing Code Insights

**Graphify LIVE + fresh (re-indexed 2026-08-15, 2081 nodes incl. all Phase-5 symbols).** Navigate via `graphify explain <symbol>` / the graphify skill — do NOT re-read the src/ tree. Reuse: `desk/` (analysts flat fan-out, run_structured seam, verifier cite-or-drop, orchestrator patterns — the diligence desk mirrors the analyst desk), `desk/risk.validate_hedge` (independent hedge re-validation), `quant/` (cash_runway, pipeline_value, conditional_payoff, cointegration, implied_move), `providers/` (clinicaltrials, fmp), `kb.analog_query`, `contracts/` (DiligenceInput is NEW; DiligenceDossier EXISTS — extend if a field is missing). New module: `desk/diligence.py` + a `run_diligence` entry point.
</code_context>

<specifics>
## Specific Ideas

Success criteria (from ROADMAP):
1. Diligence pipeline runs in a separate session receiving only {ticker, catalyst, pair} with adversarial framing — Workflow 1/2 reasoning provably never passed in (firewall).
2. Multi-dimensional DD from raw sources (the 8 dimensions above).
3. Adversarial synthesizer rewards "no-go", requires data-backed confidence, emits DiligenceDossier {go/no-go, evidence, residual risks}; a single failing money-touching dimension forces NO-GO.

Requirement IDs: DILIG-01, DILIG-02, DILIG-03.
</specifics>

<deferred>
## Deferred Ideas
- Runtime guardrails / monitors (catalyst freshness, provenance, firewall enforcement at runtime, net-long caps, no-scraped-to-order) — Phase 7 (OPS-03).
- The actual web-scraper / free-data fetcher build (CBOE, FINRA, Federal Register ingestion) — data-layer component; this phase consumes the values behind seams and mocks them in tests.
- Live order placement — Phase 11.
</deferred>
