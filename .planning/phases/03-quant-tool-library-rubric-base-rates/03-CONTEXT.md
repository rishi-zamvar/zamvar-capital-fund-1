# Phase 3: Quant Tool Library + Rubric & Base-Rates - Context

**Gathered:** 2026-08-14
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

Agents never do money arithmetic — they call deterministic, reproducible, exhaustively-tested tools and interpret the output against a concrete rubric. Delivers: the callable quant-tool library, the biotech scoring rubric (tunable config), and the clinical base-rate table.
</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
Discuss skipped. Follow ROADMAP success criteria, PROJECT.md (deterministic-tools principle), CLAUDE.md, and research/FEATURES.md (rNPV rubric + base rates like ~7.9% Phase-I LoA, ~28% prior-CRL penalty) + PITFALLS.md (risk-of-ruin sizing, IV-crush, hedge conditional payoff).

Hard constraints:
- No LLM arithmetic on money-critical numbers — these tools ARE the arithmetic layer; agents only supply parameters and interpret output.
- Every tool output records the exact inputs used (reproducible, auditable).
- TDD with EXHAUSTIVE edge cases, tests before logic (OPS-04) — money-critical: division-by-zero, negative inputs, empty series, extreme values, partial data.
- Rubric weights are a tunable config the learning loop (Phase 10) can adjust — do not hardcode.
- Base rates are data (a citable table), not magic numbers in code.
- Simplicity + minimal deps: prefer numpy/statsmodels/scipy already implied; cointegration via statsmodels (Engle-Granger/Johansen); Sharpe/returns via a lean calc or quantstats/empyrical (CLAUDE.md notes quantstats, avoid vectorbt's freq footgun).
</decisions>

<code_context>
## Existing Code Insights

**Graphify LIVE + freshly re-indexed.** Navigate via `graphify explain <symbol>` / `graphify path A B` / the graphify skill — do NOT re-read the src/ tree. Reuse: `models.py` / `contracts/` (pydantic patterns for tool input/output records), `kb.py` (base-rate table can live as cited KB nodes or a loaded data table + provenance), `db.py` (migration runner if base rates persist). Tools live in a new `quant/` (or `tools/`) module; each returns a result object carrying its inputs.
</code_context>

<specifics>
## Specific Ideas

Success criteria (from ROADMAP):
1. Callable, versioned tool library: rNPV/pipeline valuation, cash-runway, Kelly/risk-of-ruin sizing, cointegration test, correlation/β, conditional-payoff matrix, options-implied move, IV-crush, Sharpe/returns/attribution, SL/TP levels, portfolio concentration/exposure.
2. Every tool output records exact inputs (reproducible); exhaustive edge-case test suite written before logic (TDD).
3. Biotech scoring rubric (rNPV + cash runway + trial design + endpoint credibility + regulatory precedent + pipeline concentration + management + commercial) as tunable config.
4. Clinical base-rate table (phase-transition LoA by phase/indication, prior-CRL penalty, AdCom follow-through) loaded + citable as data.
</specifics>

<deferred>
## Deferred Ideas

None — discuss phase skipped.
</deferred>
