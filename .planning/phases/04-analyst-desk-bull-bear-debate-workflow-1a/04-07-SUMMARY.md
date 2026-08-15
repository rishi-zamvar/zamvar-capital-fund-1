---
phase: 04-analyst-desk-bull-bear-debate-workflow-1a
plan: 07
subsystem: desk
tags: [orchestrator, workflow-1a, call-01, call-02, call-03, call-04, asyncio-gather, agent-defs, tdd]
requires:
  - "desk.tools.build_quant_server (Plan 03)"
  - "desk.analysts.run_analyst + PROMPTS (Plan 04)"
  - "desk.debate.run + Argument (Plan 05)"
  - "desk.verifier.enforce + VerdictUnsupportedError (Plan 06)"
  - "desk.MAX_ROUNDS + contracts.DebateVerdict (Plans 01/02)"
provides:
  - "desk.orchestrator.run_desk(conn, catalyst) -> DebateVerdict — the Workflow-1a public entry"
  - "desk.orchestrator.DIMENSIONS + ALLOWED_TOOLS (the mcp__quant__* fan-out surface)"
  - ".claude/agents/*.md — 8 human-readable/interactive-CC role-def parity docs"
affects:
  - "Phase 5 (sizing/positioning consumes the finalized DebateVerdict)"
  - "Later scheduling/trigger layer (calls run_desk headless at catalyst T-2)"
tech-stack:
  added: []
  patterns:
    - "Thin async composition: asyncio.gather flat fan-out of the 4 analysts, then two sequential awaits (debate -> verifier)"
    - "Signals threaded into verifier.enforce so kb: refs resolve; the whole pipeline stays offline via the one run_structured seam"
    - ".claude/agents defs are parity docs — Python prompt is the source of truth (RESEARCH Pitfall 2, no nested SDK subagents)"
key-files:
  created:
    - src/catalyst_trader/desk/orchestrator.py
    - tests/test_desk_orchestrator.py
    - .claude/agents/analysts/clinical.md
    - .claude/agents/analysts/regulatory.md
    - .claude/agents/analysts/financial.md
    - .claude/agents/analysts/market_sentiment.md
    - .claude/agents/researchers/bull.md
    - .claude/agents/researchers/bear.md
    - .claude/agents/researchers/moderator.md
    - .claude/agents/verifier/verifier.md
  modified: []
decisions:
  - "run_desk threads signals=signals into verifier.enforce (the plan's bare enforce(conn, verdict) example) so kb:-cited claims can run the quote-substring gate — correct wiring, not new logic"
  - "DIMENSIONS derives from analysts.PROMPTS keys and ALLOWED_TOOLS lists the mcp__quant__* surface explicitly — one source of dimensions, no per-call-site drift"
  - "Concurrency proven two ways: an asyncio.gather spy (exactly one fan-out of 4) plus four distinct dimension prompts issued"
  - "Role defs use Claude Code subagent frontmatter (name/description/model) so the same files are usable interactively; each carries a Python-is-source-of-truth banner"
metrics:
  duration: 9min
  completed: 2026-08-15
  tasks: 2
  files: 11
---

# Phase 04 Plan 07: run_desk Orchestrator + Agent Role Defs Summary

The Workflow-1a assembly: `desk.orchestrator.run_desk(conn, catalyst)` wires the pieces from Plans 03-06 into one end-to-end pipeline — build the quant/KB MCP server, fan the four dimension analysts out concurrently via `asyncio.gather`, run the bounded bull/bear/moderator debate over their signals, then gate the verdict through source-quote-or-drop before returning a finalized `DebateVerdict`. Plus 8 `.claude/agents/*.md` role-def parity docs mirroring the canonical Python prompts.

## What was built

**Task 1 — `run_desk` orchestrator (TDD).** A thin async composition, no new business logic:

1. `srv = {"quant": build_quant_server(conn)}` — the one in-process MCP server wrapping both quant and KB tools.
2. `signals = await asyncio.gather(*[run_analyst(dim, catalyst, mcp_servers=srv, allowed_tools=ALLOWED_TOOLS) for dim in DIMENSIONS])` — 4 concurrent, isolated analyst sessions.
3. `verdict = await debate.run(signals, catalyst, rounds=MAX_ROUNDS)` — bounded bull/bear/moderator.
4. `return await verifier.enforce(conn, verdict, signals=signals)` — source-quote-or-drop before finalize.

Every role call routes through the single `desk.runtime.run_structured` seam, so the whole desk runs offline under test.

**Task 2 — 8 role-def `.md` files.** `.claude/agents/analysts/{clinical,regulatory,financial,market_sentiment}.md` (sonnet), `researchers/{bull,bear}.md` (sonnet), `researchers/moderator.md` (opus), `verifier/verifier.md` (opus). Each mirrors its canonical Python prompt + hard constraints (analysts CALL `mcp__quant__*` and cite / never compute; moderator emits binary verdict + kill_criteria + names the losing side; verifier enforces source-quote-or-drop), with a banner stating Python is the source of truth (SDK path is Python-driven, RESEARCH Pitfall 2).

## Tests

`tests/test_desk_orchestrator.py` — a role-routing `run_structured` fake (dispatches on schema + prompt content, returns the recorded fixtures from Plans 04/05/06) drives the whole pipeline:

- `test_run_desk_end_to_end` — 4 analysts -> debate -> verifier returns a finalized verdict (binary direction, non-empty kill_criteria, both strongest points, surviving evidence_refs). Exercises CALL-01..04 together.
- `test_analysts_run_concurrently` — an `asyncio.gather` spy proves exactly one fan-out of four awaitables + four distinct dimension prompts.
- `test_verifier_gates_run_desk` — a verdict whose refs all fail structural resolution raises `VerdictUnsupportedError` (no unsupported verdict returned; no opus semantic call spent).

Full suite: **498 passed** (2 pre-existing statsmodels complex-cast warnings in `test_pairs`, out of scope). No live API anywhere.

## Deviations from Plan

**None functionally.** One clarification the plan left implicit: the plan's interface line showed `verifier.enforce(conn, verdict)`, but `enforce` takes `*, signals=None` (Plan 06) and needs the signals to run the quote-substring gate on `kb:` refs. `run_desk` passes `signals=signals` — this is correct wiring, not added logic. (Not tracked as a deviation rule; it's the intended composition.)

## Requirements

- **CALL-01** (analysts call quant/KB tools + cite, never compute) — wired: `run_analyst` fan-out threaded to `build_quant_server` + `ALLOWED_TOOLS`.
- **CALL-02** (context-isolated debate) — wired: `debate.run` over the shared signals.
- **CALL-03** (binary grounded verdict + kill criteria) — wired: moderator `DebateVerdict`.
- **CALL-04** (source-quote-or-drop finalize gate) — wired: `verifier.enforce` before return.

## Notes for the phase-close step

- Graphify re-index (per CONVENTIONS "re-index after every code-producing phase") is a phase-level task — orchestrator/verifier should run it after this last plan.
- Phase-completion HTML report (`docs/phase-reports/phase-04-report.html`) + TOKEN-NOTES retrospective are the mandatory phase-close conventions, handled at phase close, not in this plan.

## Known Stubs

None. `run_desk` is fully wired end-to-end; no placeholder data paths. The `.claude/agents/*.md` files are intentional parity docs (not executable stubs) — the SDK pipeline runs from Python.

## Self-Check: PASSED

All 10 created files verified present; all 3 task commits (9e7d02a, 5dfd2ea, a8d2e23) verified in git log.
