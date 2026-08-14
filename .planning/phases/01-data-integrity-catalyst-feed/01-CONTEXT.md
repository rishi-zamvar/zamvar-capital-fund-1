# Phase 1: Data Integrity & Catalyst Feed - Context

**Gathered:** 2026-08-14
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

The system always knows what catalyst is coming, when, and how sure it is — with no date ever originating from an LLM's memory. Delivers the verified rolling catalyst calendar and the point-in-time ~20-name universe that everything downstream trusts.

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
All implementation choices are at Claude's discretion — discuss phase was skipped per user setting. Use the ROADMAP phase goal, success criteria, PROJECT.md constraints, and the STACK decisions in CLAUDE.md (ClinicalTrials.gov API v2 for trial readouts, FMP earnings calendar, hand-curated PDUFA/AdCom table, httpx + pydantic, SQLite) to guide decisions.

Hard constraints from PROJECT.md that bind this phase:
- No catalyst date may originate from an LLM's memory — every date comes from a named external source.
- Two-source verification + `last_verified` stamp + uncertainty typing (firm/window/soft) on every date; unverifiable dates are flagged and excluded from trading.
- Full test coverage / TDD — tests before logic; money-critical date handling gets exhaustive edge cases.
- Simplicity + readability: simplest production-ready implementation, minimal dependencies.

</decisions>

<code_context>
## Existing Code Insights

Greenfield — no application code yet. This is the first implementation phase. Establish the project's Python package layout, dependency management (pyproject), test harness (pytest), and data-provider client conventions here, since later phases build on them.

</code_context>

<specifics>
## Specific Ideas

Success criteria to satisfy (from ROADMAP):
1. Rolling calendar auto-populates from ClinicalTrials.gov v2 + earnings feeds, merged with hand-curated PDUFA/AdCom entries for the covered universe.
2. Every catalyst date carries an uncertainty type (firm/window/soft), a two-source verification record, and a `last_verified` stamp; unverifiable dates are flagged and excluded from trading.
3. A catalyst is re-verified within 48h of the event and, when 1–2 days out, triggers Workflow 1.
4. The ~20-name universe is assembled point-in-time from explicit criteria (catalyst density, market cap, liquidity, therapeutic area) and includes delisted names for later backtesting.
5. The user can inject an ad-hoc catalyst (ticker + type + date/window) and it flows through the same verification rules.

</specifics>

<deferred>
## Deferred Ideas

None — discuss phase skipped.

</deferred>
