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

### Phase 2 — Contracts + Knowledge-Base Skeleton (CLOSED)
| Agent | Tokens |
|-------|--------|
| Researcher (narrow + graph-first) | 91,089 |
| Planner | 131,689 |
| Plan-checker (passed first try — no revision) | 115,394 |
| Executor 02-01 | 77,214 |
| Executor 02-02 | 100,514 |
| Executor 02-03 | 90,227 |
| Executor 02-04 | 103,847 |
| Verifier | 76,347 |
| **Phase 2 subtotal** | **~786,321** |

### Phase 3 — Quant Tool Library + Rubric & Base-Rates (CLOSED)
| Agent | Tokens |
|-------|--------|
| Researcher (narrow + graph-first) | 118,981 |
| Planner | 134,369 |
| Plan-checker (passed, 2 warnings folded into exec) | 112,013 |
| Executor 03-02 | 76,279 |
| Executor 03-03 | 91,075 |
| Executor 03-04 | 90,370 |
| Executor 03-05 | 70,189 |
| Executor 03-06 | 86,823 |
| Executor 03-07 | 105,352 |
| Executor 03-08 | 103,524 |
| Verifier | 97,658 |
| (+ 03-01 executor + 03-02 first run: stalled on battery-sleep, ~120k partial, re-run to completion) | ~120,000 |
| **Phase 3 subtotal** | **~1,207,000** |

**Cumulative build (measured, so far): ~3,857,000 subagent tokens (project 419,577 + P1 1,444,361 + P2 786,321 + P3 ~1,207,000)**

### Phase 4 — Analyst Desk + Bull/Bear Debate (CLOSED)
| Agent | Tokens |
|-------|--------|
| Researcher | 110,852 |
| Planner | 129,896 |
| Plan-checker (1 blocker → revised) | 105,078 |
| Revision planner | 74,868 |
| Plan-checker (re-check) | 89,600 |
| Executor 04-01 | 67,452 |
| Executor 04-02 | 106,009 |
| Executor 04-03 | 98,868 |
| Executor 04-04 | 82,361 |
| Executor 04-05 | 79,242 |
| Executor 04-06 | 90,101 |
| Executor 04-07 | 106,422 |
| Verifier | 97,387 |
| **Phase 4 subtotal** | **~1,238,000** |

**Cumulative build (measured, so far): ~5,095,000 subagent tokens (project 419,577 + P1 1,444,361 + P2 786,321 + P3 ~1,207,000 + P4 ~1,238,000)**

> Executor avg holding ~90k across P2-P4 with Graphify live (vs ~118k P1) — steady ~23% executor-token saving. Plan-check caught a real money-critical blocker in P4 (silent CALL-04 hole) — the round-trip keeps earning its cost.

### Out-of-band research (user-requested, NOT in the build total above)
Fable universe + pairs-discovery agents (event studies, FMP/yfinance metrics). Tracked separately so they don't distort the build/Graphify metric. Several hundred k tokens; the first universe run's fan-out mass-stalled (battery sleep) and was re-run as a single sequential agent.

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
