# Token Ledger & Optimization Notes

> Running tally of subagent token spend (measured from each agent's reported `subagent_tokens` on completion) + per-phase optimization directives fed forward into later phases' agent prompts. Excludes the orchestrator (main-loop) tokens, which aren't reported per-call.

## Directives (READ THIS — applies to all future agents)

1. **Query the code graph, don't re-read the tree.** Graphify (code knowledge graph, MCP + `explore` command) is being installed. From Phase 2 onward, agents MUST use the graph to locate symbols/callers/imports instead of grepping or reading whole files. Read only the specific files the graph points to.
2. **Reuse settled research.** Project-level STACK/ARCHITECTURE/PITFALLS/SUMMARY are done — do NOT re-research settled decisions. Per-phase research must be narrow (only the phase's new unknowns).
3. **Trim `files_to_read`.** Give each agent only the files it needs. Don't pass the whole `.planning/` tree when CONTEXT + the specific research section suffice.
4. **Prefer the codebase map over raw source** for orientation once it exists.
5. **Right-size models.** Checker on Sonnet (done). Pure-infrastructure phase checks may use Haiku.

## Running Tally (subagent tokens)

### Project setup
| Agent | Tokens |
|-------|--------|
| Research — Features | 61,888 |
| Research — Stack | 67,292 |
| Research — Architecture | 56,047 |
| Research — Pitfalls | 55,085 |
| Research synthesizer | 108,135 |
| Roadmapper | 71,130 |
| **Subtotal** | **419,577** |

### Phase 1 — Data Integrity & Catalyst Feed
| Agent | Tokens |
|-------|--------|
| Researcher | 108,962 |
| Planner | 139,062 |
| Plan-checker | 122,844 |
| Revision planner | 112,211 |
| Plan-checker (re-check) | 119,586 |
| Executor 01-01 | 109,211 |
| Executor 01-02 | 86,869 |
| Executor 01-03 | 124,032 |
| Executor 01-04 | 114,150 |
| Executor 01-05 | 155,138 |
| Executor 01-06 | 118,843 |
| Verifier | 133,453 |
| **Phase 1 subtotal** | **~1,444,361** |

**Cumulative (measured, so far): ~1,863,938 subagent tokens (project 419,577 + Phase 1 1,444,361)**

## Per-Phase Retrospective

### Phase 1 — Data Integrity & Catalyst Feed (CLOSED)
- **Spend:** ~1.44M tokens. Split: planning round-trip (research→plan→check→revise→re-check) ~603k; execution (6 plans) ~708k; verify 133k.
- **Earned its cost:** the plan-check round-trip caught a real money-critical blocker (date_type persistence) that tests would not have. Keep plan-check on.
- **Levers now active for Phase 2+:**
  1. **Graphify LIVE** (706 nodes / 1155 edges indexed). Every Phase 2 agent MUST query the graph (`graphify explain/path` or the skill) to locate code instead of reading src/ files. This is the biggest lever — Phase-1 executors each re-read overlapping src/ files (~110-155k each).
  2. **Narrow per-phase research** — project STACK/ARCH are settled; Phase 2 research should only cover the KB/contracts specifics, not re-derive the stack.
  3. **Tighter files_to_read** — pass the graph + the 2-3 specific files, not the whole src tree.
- **Directive carried to Phase 2 prompts:** "Graphify graph is built — use `graphify explain <symbol>` / `graphify path A B` / the graphify skill to navigate; read only the files the graph points to. Do not re-read the src/ tree."

## Per-Phase Retrospective (filled at each phase close)

### Phase 1 — (pending phase completion)
- Observation: planning round-trip (planner 139k + checker 122k + revision) is the dominant cost this phase; research 109k.
- Levers to apply next phase: graphify online (biggest), narrower per-phase research, tighter files_to_read.
