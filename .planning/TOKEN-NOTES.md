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
| Plan-checker (re-check) | (pending) |
| Execution + verify | (pending) |

**Cumulative (measured, so far): ~902,656 subagent tokens**

## Per-Phase Retrospective (filled at each phase close)

### Phase 1 — (pending phase completion)
- Observation: planning round-trip (planner 139k + checker 122k + revision) is the dominant cost this phase; research 109k.
- Levers to apply next phase: graphify online (biggest), narrower per-phase research, tighter files_to_read.
