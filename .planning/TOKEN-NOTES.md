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

### Phase 5 — Trade Builder, Honest Hedge & Ruin-Avoidant Sizing (CLOSED)
| Agent | Tokens |
|-------|--------|
| Planner | 180,090 |
| Plan-checker (2 blockers → revised) | 153,230 |
| Revision planner | 150,259 |
| Plan-checker (re-check, PASSED) | 143,470 |
| Executor 05-01 (contracts) | 85,571 |
| Executor 05-02 (quant tools) | 111,601 |
| Executor 05-03 (param seam) | 87,840 |
| Executor 05-04 (risk committee) | 142,900 |
| Executor 05-05 (vetting gate) | 123,144 |
| Executor 05-06 (builder) | 202,807 |
| Executor 05-07 (portfolio) | 164,832 |
| Verifier | 132,509 |
| **Phase 5 subtotal** | **~1,678,000** |

**Cumulative build (measured, so far): ~6,773,000 subagent tokens (+ P5 ~1,678,000).**

### Phase 6 — Independent Diligence Firewall (Workflow 3) (CLOSED)
| Agent | Tokens |
|-------|--------|
| Researcher | 128,179 |
| Planner | 157,289 |
| Plan-checker (3 blockers → revised) | 152,272 |
| Revision planner | 136,813 |
| Plan-checker (re-check, PASSED) | 108,061 |
| Executor 06-01 (firewall contract) | 99,742 |
| Executor 06-02 (8 DD dimensions + candidate_peer) | 154,672 |
| Executor 06-03 (deterministic synthesizer) | 130,574 |
| Executor 06-04 (firewalled orchestrator) | 132,633 |
| Verifier | 140,406 |
| **Phase 6 subtotal** | **~1,340,000** |

**Cumulative build (measured, so far): ~8,113,000 subagent tokens (+ P6 ~1,340,000).**

### Phase 6.5 — Weekly Strategy Correction (CLOSED)
| Agent | Tokens |
|-------|--------|
| Researcher | 132,830 |
| Planner | 189,722 |
| Plan-checker (1 blocker → revised) | 133,809 |
| Revision planner | 97,486 |
| Plan-checker (re-check, PASSED) | 80,822 |
| Executor 06.5-01 (price store + weekly params) | 94,004 |
| Executor 06.5-02 (cap-safe sizing + defensive select_book) | 97,701 |
| Executor 06.5-03 (quant/weekly.py thesis engine) | 154,258 |
| Executor 06.5-04 (weekly runner + sleeve cap + WEEK-05) | 220,712 |
| Verifier | 126,222 |
| **Phase 6.5 subtotal** | **~1,328,000** |

**Cumulative build (measured, so far): ~9,441,000 subagent tokens (+ P6.5 ~1,328,000).**

### Phase 6.7 — MD/GP Reconciliation Loop (CLOSED)
| Agent | Tokens |
|-------|--------|
| Researcher | 123,374 |
| Planner | 207,665 |
| Plan-checker (2 blockers → revised) | 130,670 |
| Revision planner | 123,210 |
| Plan-checker (re-check, PASSED) | 108,168 |
| Executor 06.7-01 (4 contracts) | 94,440 |
| Executor 06.7-02 (extra_context plumbing) | 124,195 |
| Executor 06.7-03 (cross_check) | 109,165 |
| Executor 06.7-04 (reconcile loop + router + escalation) | 172,000 |
| Verifier | 126,279 |
| **Phase 6.7 subtotal** | **~1,319,000** |

**Cumulative build (measured, so far): ~10,760,000 subagent tokens (+ P6.7 ~1,319,000). Crossed 10M.**

### Phase 6.8 — Weekly Company-Vetting Scanner (Haiku DD-Replica) (CLOSED)
| Agent | Tokens |
|-------|--------|
| Researcher | 134,767 |
| Planner | 166,182 |
| Plan-checker (1 blocker → revised) | 105,908 |
| Revision planner | 89,759 |
| Plan-checker (re-check, PASSED) | 78,621 |
| Executor 06.8-01 (card store + contracts) | 90,072 |
| Executor 06.8-02 (deterministic flaggers + delta_card) | 138,528 |
| Executor 06.8-03 (Haiku once-over + routing) | 185,760 |
| Verifier | 103,408 |
| **Phase 6.8 subtotal** | **~1,093,000** |

**Cumulative build (measured, so far): ~11,853,000 subagent tokens (+ P6.8 ~1,093,000).**

### Phase 7 — Verifier/Guardrails + Backtest Harness (CLOSED)
| Agent | Tokens |
|-------|--------|
| Researcher | 141,602 |
| Planner | 186,548 |
| Plan-checker (2 blockers → revised) | 132,533 |
| Revision planner | 150,944 |
| Plan-checker (re-check, PASSED) | 109,560 |
| Executor 07-01 (4 metrics) | 106,298 |
| Executor 07-02 (event set + fill + latency) | 142,529 |
| Executor 07-03 (guardrail gate) | 103,394 |
| Executor 07-04 (Layer A engine) | 201,816 |
| Executor 07-05 (Layer B + gate) | 155,422 |
| Verifier | 111,400 |
| **Phase 7 subtotal** | **~1,542,000** |

**Cumulative build (measured, so far): ~13,395,000 subagent tokens (+ P7 ~1,542,000).**

### Phase 7 Retrospective
- **Spend:** ~1.54M — the most expensive phase (5 plans, a whole new `backtest/` package). 07-04 (Layer A engine) was priciest at 202k (the deterministic weekly-loop re-expression is genuinely intricate).
- **Plan-check earned its cost a 7th straight money phase — and this was the sharpest catch yet:** two SILENT look-ahead leaks that the specified tests would have passed — `tradeable_catalysts` has no `as_of` guard (a catalyst verified AFTER the simulated week would be visible), and the direction proxy read `trigger`/`drop_class` off a catalyst thesis row where they're null (→ crash or coin-flip). Both are exactly the failure modes a backtest exists to prevent; both were invisible to TDD. This is the strongest evidence yet for keeping plan-check on for money phases.
- **The "already-a-free-seam" pattern held again:** Layer B "web blocked" was free (desk already web-free); the 4 metrics were numpy (no quantstats/empyrical dep). Research surfacing these kept the phase from ballooning.
- Directives carried forward: research MUST verify assumed guards actually exist in source (the tradeable_catalysts miss was a research-premise error the plan-check caught); plan-check ON for money phases (7/7); graph re-index each code phase (now 2844 nodes).

### Phase 6.8 Retrospective
- **Spend:** ~1.09M — the cheapest agentic phase, thanks to the "routing is free" research finding (reconcile already ingested WeeklyFlags → zero md.py work) and heavy pattern-mirroring (card store cloned the 6.5 price store).
- **Plan-check earned its cost a 6th straight money phase:** caught the write-before-delta latch-persistence bug — silent (no unit test on hand-built dicts would fail), broke SCAN-02 week-over-week replayability, contradicted a locked CONTEXT decision. Fix = reorder + a 2-week DB round-trip regression test. This class of bug (cross-plan sequencing that unit tests miss) is the single strongest argument for keeping plan-check on.
- **Verifier caught a shadowed duplicate test name** — a real coverage hole (one intended test never ran). Fixed at close. Verifiers reading actual test collection, not just names, matters.
- Directives carried forward: research must surface "free seam" reuse (biggest cost saver); plan-check ON for money phases (6/6 caught real blockers); graph re-index each code phase (now 2593 nodes).

### Phase 6.7 Retrospective
- **Spend:** ~1.32M, in line with the other agentic phases. Reuse-heavy (the research verdict was "almost entirely reuse") kept executors lean; 06.7-04 (capstone loop) was the priciest at 172k.
- **Plan-check earned its cost a 5th straight money phase:** caught 2 real blockers — `cross_check`'s 3-arg signature couldn't reach `catalyst_id` (DebateVerdict has no such field) or `min_tradeable_size` for two of its six checks. Fix = widen the signature, thread from `reconcile`. TDD would have hit a NameError only at execution; the check caught it at plan time.
- **The MD hub came online cleanly** because the firewall/gap-not-answer discipline was a TYPE fact (extra="forbid" contracts) rather than a runtime check — same technique as the Phase-5 fake-hedge and Phase-6 DiligenceInput invariants. This pattern (make the dangerous state unrepresentable) has now paid off across 3 money phases.
- Directives carried forward: reuse-vs-new + signature-reachability audit in research/plan-check; plan-check ON for money phases; graph re-index each code phase (now 2478 nodes).

### Phase 6.5 Retrospective
- **Spend:** ~1.33M — in line with P6. The 06.5-04 executor was the priciest (~221k): the weekly runner threads target + sleeve-cap + defensive + WEEK-05 across run_portfolio, the most integration-heavy single plan of the phase.
- **Plan-check earned its cost again (4th money phase):** caught the missing statistical-sleeve budget cap — a real risk-control gap (efficient mean-reversion legs could crowd out the catalyst moat + uncapped cost drag). All 6 money invariants otherwise confirmed sound on first pass — the research's reuse-vs-new verdict + the gating price-store catch kept execution clean.
- **The gating catch (no price store) was the phase MVP:** research verified the OHLCV store was absent BEFORE planning, so it became Wave-1 gating instead of an execution-time blocker. Reinforces: research reads actual code/data state, not assumptions.
- Directives carried forward: reuse-vs-new + data-dependency audit in research; plan-check ON for money phases; graph-first nav (re-indexed 2215→2361 nodes).

### Phase 6 Retrospective
- **Spend:** ~1.34M — cheaper than P5 (~1.68M) despite similar complexity: the reuse-vs-new verdict came in RESEARCH (not discovered during execution), so executors were lean (99k-155k). Firewall-as-a-type (vs a runtime check) kept the contract work tiny.
- **Plan-check earned its cost a 3rd straight money phase:** caught 3 real blockers (2 ungroundable money dims → false-GO risk; diligence params on the wrong load path → KeyError on the seeded steady state; hedge re-validation validating the wrong peer). All would have passed tests green. TDD structurally can't catch data-grounding/wiring gaps — keep plan-check ON.
- **Graphify re-index** done post-phase (incremental AST merge, 2081→2215 nodes). Executor CLI has no index subcommand — must run via the interpreter directly (documented).
- Directives carried to 6.5+: reuse-vs-new verdict up front (biggest cost lever); plan-check stays on for money phases; `.venv/bin/python -m pytest`; graph-first nav.

### Out-of-band research (user-requested, NOT in the build total)
Fable/Opus researchers this session, tracked separately: inverse-instruments, disease-competitor-pairs, single-leg-microstructure, free-data-sources, intra-week-monitoring, weekly-thesis-engine, md-reconciliation-loop. Several hundred k each; they inform scope but aren't build tokens.
> NOTE: research was done OUT-OF-BAND before planning (5 Fable/Opus researchers: inverse-instruments, disease-pairs, microstructure, free-data, + phase-5 research), tracked separately from the build total per the OOB convention.

### Phase 5 Retrospective
- **Spend:** ~1.68M — the most expensive phase yet. Split: planning round-trip (planner 180k + checker 153k + revision 150k + re-check 143k = ~627k) ≈ execution (7 executors ~919k) + verify 132k.
- **The plan-check round-trip earned its cost decisively (again):** it caught 2 real money-critical blockers by tracing data end-to-end — (1) Risk Committee's ruin-capped size + validated Hedge never reconciled onto the promoted trade (would silently promote the builder's un-vetted size), (2) hold-vs-exit used raw EV instead of the locked expected-log-growth (a ruin-risk regression on fat-tailed binaries). Both would have passed all tests green. TDD alone would NOT have caught either — they're wiring/fidelity gaps, not unit-logic bugs. **Keep plan-check on for every money phase.**
- **Executor spend crept up** (05-06 builder 202k, 05-04 risk 142k) — the judgment-heavy desk modules with many reused symbols cost more even with Graphify. The reuse-vs-new verdicts in RESEARCH kept net-new code minimal (1 tool + 1 extension + 1 selector + 1 seam + 1 gate sibling + 3 desk modules), which is the main lever that stopped it ballooning further.
- **Sequential-on-main execution** (not parallel-worktree) was a deliberate choice for the money path — clean linear git history, no worktree-merge risk, no fan-out overload. Cost: wall-clock. Worth it here.

### Directives carried to Phase 6+ (append to research/planner/executor prompts)
1. **Graphify re-index BEFORE Phase-6 planning** — Phase 5 added ~10 new symbols (quant/events.py, desk/risk.py, desk/builder.py, desk/portfolio.py, orchestrator run_portfolio, verifier.enforce_estimate, kb.load_params). Re-index via the `/graphify` skill so Phase-6 agents navigate the current graph, not a Phase-4-era one.
2. **Reuse-vs-new verdict up front** — the biggest cost-controller in P5 was RESEARCH deciding reuse-vs-rebuild against ACTUAL signatures before planning. Do this in every phase's research.
3. **Plan-check stays ON for money phases** — it caught what TDD structurally cannot (cross-plan wiring + model-fidelity).
4. Prior directives still hold: graph-first navigation, narrow per-phase research, tight files_to_read, `.venv/bin/python -m pytest` (bare python NOT on PATH), checker on Sonnet.

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

### Phase 6.9 — Free-Data Ingestion Layer (CLOSED 2026-08-16)
- **Spend: ~1.73M tokens** (build). Split:
  - Research: base 129k + price-cascade addendum 101k = **230k**
  - Planning round-trip: planner 163k + plan-check 150k + revision 140k + re-check 84k = **537k** (2 money blockers caught + fixed + re-verified — the round-trip earned it AGAIN, 8th straight money phase)
  - Execution: 8 plans (60+75+78+122+124+72+138+243k) = **912k** + yfinance shakedown-fix 54k = **966k**
- **The shakedown was the biggest single line (243k)** and the highest-value: it ran 5 live network passes, caught 2 money-critical crashes (null-close, ETF asset-class) AND exposed the single-source collapse + vacuous backtest that offline tests structurally could not. Real-data verification is worth its cost on a money path.
- **Cross-phase honesty win:** the offline suite was GREEN while the live cascade was single-source — because a fake fixture (flat columns) didn't match real yfinance (MultiIndex). Lesson recorded: **provider fixtures must mirror the real upstream response shape**, or offline-green masks a live break. The yfinance-fix RED test now reproduces the exact live bug offline.
- **Levers that held cost down:** store-is-the-seam finding (zero downstream contract change → no desk rewrites); reuse-vs-new verdict up front (thin plumbing over already-built machinery); Graphify graph-first navigation; `.venv/bin/python` discipline.
- **Out-of-band forward research (NOT in the 1.73M build total, tracked separately):** free-data-pipeline ecosystem 101k + free-intraday-prices 127k = **228k** — these scoped Phase 6.10 + 8.5 (edgartools/FRED/daemon; intraday monitor feed). User-requested, so bucketed apart to keep the build/Graphify metric clean.
- **Cumulative build ≈ 15.1M** (was ~13.4M after Phase 7) + ~0.23M forward-research bucket.

### Directives carried to Phase 6.10+ (append to agent prompts)
1. **Provider/HTTP fixtures MUST mirror the real upstream shape** (MultiIndex columns, NDJSON, whatever the live source actually returns) — the yfinance MultiIndex bug shipped offline-green because the fake was flat. When adding a provider, capture a REAL response snapshot as the fixture.
2. **Prefer live-verified real-data checks at phase close** for data-touching phases — the shakedown found what 1002 offline tests could not.
3. Prior directives still hold: Graphify re-index before planning (done — graph re-indexed at 6.9 close), reuse-vs-new verdict up front, narrow per-phase research, tight files_to_read, plan-check ON for money phases, `.venv/bin/python -m pytest`, sequential-on-main execution.

### Phase 6.10 — Always-On Data Daemon, Coverage Expansion & Quality Monitor (CLOSED 2026-08-16)
- **Spend: ~1.51M tokens** (build). Split:
  - Planning round-trip: planner 158k + plan-check 118k + revision 101k = **377k** (1 blocker [SourceOrigin provenance] + 3 warnings caught; I skipped the formal re-check as a risk-calibrated call since fixes were localized + TDD-guarded — held).
  - Execution: 7 plans — 01 edgartools 112k + 02 FRED 71k + 03 _http lake 76k + 04 median 88k + 05 FINRA/Nasdaq 98k + 06 daemon 149k = 594k; **07 live daemon shakedown ~540k** (3 executor resumes).
- **The dominant, avoidable cost was Plan 07 (~540k).** The executor repeatedly LAUNCHED the ~18-min live daemon and its turn timed out mid-run 3×, re-diagnosing/re-running each time (each resume re-read context + re-watched). It DID earn value — found + fixed 3 real daemon bugs live (run_cycle crash, FINRA content-negotiation, data_health single-source reporting gap) — but the babysitting pattern tripled the cost.
- **NEW DIRECTIVE (long-running live steps):** an executor must NOT babysit a multi-minute live process. Pattern: executor LAUNCHES the process in background + writes a completion signal (file/PID), then RETURNS; the ORCHESTRATOR owns the wait (background `until` watch) and re-engages the executor (SendMessage) only once the signal fires, to build the report. I applied this mid-phase (killed the redundant 3rd daemon run, closed from results in hand) — bake it into the plan for any live-verification task (Phase 8 paper ledger, Phase 11 live exec).
- **Result quality was HIGH:** cross-check 0→99.6% live (the headline multi-source win), no-CIK 21→0, FINRA degrades 21→0, Nasdaq earnings fallback $0. The live shakedown remains the highest-value verification for data phases.
- **Cumulative build ≈ 16.6M** (was ~15.1M after 6.9).

### Phase 6.11 — Own PDUFA Source from SEC 8-K (CLOSED 2026-08-16)
- **Spend: modest** (4 lean plans; no plan-check round-trip re-run needed — additive-provider risk was low, TDD-guarded). Execution dominated by the two provider plans (01 pdufa_edgar ~build + tests, 02 daemon wiring, 03 RH adapter, 04 the live shakedown ~ this run).
- **The 6.9/6.10 directive PAID OFF verbatim.** "Provider fixtures MUST mirror the real upstream shape" was honored — the 8-K fixtures were real-HTML-shaped (tag-split keyword/date), so the HTML→text-normalize-before-regex step was designed against the true trap. Result: the live extractor ran clean on real efts + real 8-K exhibits on the FIRST real run — **zero normalization miss, zero degrade, zero rate-limit, zero pdufa_edgar.py fix.** The offline-green/live-broken gap that bit Phase 6.9 (yfinance MultiIndex) did NOT recur. This is the payoff of capturing real upstream shape as the fixture.
- **The live shakedown stayed cheap this time** (~90s run, not the multi-minute daemon of 6.10) — so the 6.10 "don't babysit long-running live steps" directive wasn't stressed, but the executor still ran the live step once, in-hand, no resumes.
- **Only 2 fixes, both script-level + pre-commit** (pit_ok compared against the non-persisted published_date; review-count undercounted on idempotent re-run) — caught by reading the first run's output critically, not by a second agent. Cheap.
- **Headline result:** tradeable PDUFA catalysts **0 → 6** live (IMNM, CAPR, BBIO×2, DYN, PRAX) — clearing the single blocker that gated both 6.9 and 6.10 closes. 13 ambiguous/multi-date filings correctly routed to the human-review CSV.

### Directives carried to Phase 7+ (append to agent prompts)
1. **Capture a REAL upstream response snapshot as the provider fixture** — proven twice now (yfinance bug shipped offline-green in 6.9; pdufa_edgar ran clean live in 6.11 *because* the fixture was real-HTML-shaped). Non-negotiable for any new data/provider path.
2. **Prefer live-verified real-data checks at phase close** for data/money-touching phases (the shakedown remains the highest-value verification; 6.9/6.10/6.11 all agree).
3. **Don't babysit multi-minute live processes** (6.10 lesson): launch + signal + return; orchestrator owns the wait. (Not stressed in 6.11's fast run, but stands.)
4. Prior directives still hold: Graphify graph-first, reuse-vs-new verdict up front, narrow per-phase research, tight files_to_read, plan-check ON for money phases, `.venv/bin/python -m pytest`, sequential-on-main execution, no-LLM-dates / cite-or-drop on any date-bearing extraction.
