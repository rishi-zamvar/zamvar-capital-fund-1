# Phase 4: Analyst Desk + Bull/Bear Debate (Workflow 1a) - Context

**Gathered:** 2026-08-14
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped via workflow.skip_discuss)

<domain>
## Phase Boundary

For a flagged catalyst, produce a BINARY directional verdict (positive vs. negative catalyst) with calibrated confidence and explicit falsification/kill criteria — pure prediction, no sizing or positioning. This is the FIRST agentic pipeline: four analyst agents + a bull/bear debate → a DebateVerdict, all source-grounded. Positioning/sizing is Phase 5; this phase stops at the call.
</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion
Discuss skipped. Follow ROADMAP success criteria + PROJECT.md (evidence-grounded, cite-or-drop, no LLM math) + CLAUDE.md STACK: **Claude Agent SDK (Python)** for headless/scheduled orchestration (catalyst T-2 trigger can't rely on an interactive session), sharing `.claude/agents/` role defs; **borrow TradingAgents' structure** (bounded debate loop + manager synthesis + reflect-on-outcome memory) but re-express as our own agents — do NOT vendor its LangGraph runtime. Structured outputs via the Phase-2 `contracts` models (AnalystSignal, DebateVerdict).

Hard constraints:
- **Agents never do money arithmetic** — analysts CALL the Phase-3 quant tools (rNPV, base-rate lookups, implied-move, etc.) and interpret; they never compute.
- **Every claim is source-cited or dropped** — a fact-check verifier enforces this before the verdict finalizes (mirrors the KB provenance invariant at the reasoning layer).
- **Bull and Bear reason in REAL context isolation** — not fake consensus; the debate must be able to name the losing side's strongest point.
- **Subagents can't nest** (SDK constraint) → the desk is a FLAT orchestrator→analyst fan-out, not deep nesting.
- Binary verdict + calibrated confidence + explicit kill/falsification criteria. NO sizing/positioning (that's Phase 5).
- Full TDD; agent logic tested with mocked/recorded LLM responses so tests stay deterministic + offline.
</decisions>

<code_context>
## Existing Code Insights

**Graphify LIVE + fresh.** Navigate via `graphify explain <symbol>` / the graphify skill — do NOT re-read the src/ tree. This phase consumes what Phases 1–3 built: `contracts/` (AnalystSignal, DebateVerdict shapes), `kb.py` (analog query + base-rate/cited claims), `quant/` (tools the analysts call: base_rate, rnpv, implied_move, etc.), the catalyst feed (`calendar/`, `store.py`) that flags the catalyst to analyze. Add a new agent-orchestration module (e.g. `desk/` or `agents/`) + `.claude/agents/*.md` role defs. Test agent behavior with recorded/mocked model outputs (no live API in the suite).
</code_context>

<specifics>
## Specific Ideas

Success criteria (from ROADMAP):
1. Four analyst subagents (Clinical, Regulatory, Financial, Market) each emit a structured, source-cited AnalystSignal.
2. Bull and Bear researchers build opposing cases in real context isolation; the debate manager runs bounded rounds and emits a DebateVerdict that names the losing side's strongest point.
3. The verdict is binary (positive vs. negative) with calibrated confidence + explicit falsification/kill criteria; no sizing/positioning.
4. A fact-check verifier enforces source-quote-or-drop on every claim before the verdict is finalized.
</specifics>

<deferred>
## Deferred Ideas

None — discuss phase skipped. (Trade construction, hedge selection, sizing = Phase 5.)
</deferred>
