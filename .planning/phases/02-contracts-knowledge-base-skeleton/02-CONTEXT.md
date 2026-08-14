# Phase 2: Contracts + Knowledge-Base Skeleton - Context

**Gathered:** 2026-08-14
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

Every inter-layer message and every stored claim has an enforced shape and a citation — the anti-hallucination spine everything else binds to. Delivers: Pydantic JSON contracts between the agent layers, and a provenance-enforced SQLite (graph-shaped) + sqlite-vec knowledge base with analog query, hedge-relationship sub-store, and playbook store.
</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
Discuss skipped. Follow ROADMAP success criteria, PROJECT.md, CLAUDE.md STACK decisions (SQLite + sqlite-vec; pydantic v2; borrow contract shapes from research/ARCHITECTURE.md's JSON contracts section). Build on Phase 1's existing SQLite store (`src/catalyst_trader/store.py`, `db.py`, migrations) — extend the same DB file, do not create a parallel store.

Hard constraints:
- Provenance enforced at the KB write path: a claim node without a `:CITES → EvidenceSource` edge is rejected (schema violation), mirroring Phase 1's no-LLM-date invariant.
- Contracts are pydantic-validated; malformed payloads rejected at the boundary.
- Full test coverage / TDD — tests before logic.
- Simplicity + readability; minimal deps (sqlite-vec is the only new one).
</decisions>

<code_context>
## Existing Code Insights

**Graphify code graph is LIVE (706 nodes / 1155 edges).** Navigate the existing codebase via the graph (`graphify explain <symbol>`, `graphify path A B`, or the graphify skill) — do NOT re-read the `src/` tree. Reuse from Phase 1: `store.py` (atomic insert + provenance pattern), `db.py` (migration runner — add migration 003+), `models.py` (pydantic patterns, DateType enum, source/provenance model), `providers/base.py` (ProviderRecord). The KB extends the same SQLite DB and migration chain.
</code_context>

<specifics>
## Specific Ideas

Success criteria (from ROADMAP):
1. Pydantic-validated JSON schemas for AnalystSignal, DebateVerdict, TradeProposal, RiskAssessment, StrategyDossier, DiligenceDossier; malformed payloads rejected.
2. SQLite graph-shaped KB (Company/Drug/Trial/Catalyst/Outcome/Trade/Playbook/EvidenceSource nodes + edges) + sqlite-vec; a claim without a `:CITES → EvidenceSource` edge is rejected.
3. Analog query returns nearest past scenarios with outcomes — structural filter then semantic (vector) rank.
4. Hedge-relationship sub-store: per universe name, candidate inverse-payoff peers + mechanism + payoff-direction sign + citation.
5. Playbook entries queryable and surface their confidence.
</specifics>

<deferred>
## Deferred Ideas

None — discuss phase skipped.
</deferred>
