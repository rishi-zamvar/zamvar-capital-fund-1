# Architecture Research

**Domain:** Event-driven multi-agent biotech trading desk (Claude Code subagents + graph KB + iOS dashboard), real money
**Researched:** 2026-08-14
**Confidence:** MEDIUM-HIGH (fork target, debate mechanics, eval loop verified against primary sources; graph-DB landscape has a fresh disruption flagged below)

---

## TL;DR for the roadmap

1. **Fork target: `TauricResearch/TradingAgents`** (Apache-2.0, LangGraph). **Recommendation: BORROW THE STRUCTURE, DO NOT FORK THE CODE.** It is Python/LangGraph; this project runs on Claude Code subagents. Re-implement its proven org chart (analysts → bull/bear debate → trader → risk debate → PM) as Claude Code subagents + Markdown/JSON contracts. Lift its *state schema* and *debate-round loop* almost verbatim — those are the load-bearing, proven parts.
2. **Graph KB: DO NOT default to Kùzu.** Kùzu was **archived Oct 2025 after Apple acquired the team** — dead upstream. Use **SQLite (with a thin graph layer) for v1**, and only reach for a real graph DB (LadybugDB fork or Neo4j Community) if analog-query performance actually demands it. This is the single biggest correction to the PROJECT.md assumption.
3. **Two-pipeline independence** is enforceable by *process isolation + input firewalling*: Pipeline 2 (Diligence) never reads Pipeline 1's conclusion, only its raw inputs (ticker, catalyst, pair). This is the anti-confirmation-bias mechanism.
4. **Iteration loop = DoorDash's eval-driven pattern**: every trade produces a scored transcript; LLM-as-judge evals calibrated to your own graded outcomes; playbook + config updates gated behind a regression suite so the desk provably improves without regressing.
5. **iOS transport = your existing ZeeChat pattern** (SwiftUI ↔ HTTP/SSE shim over Tailscale). Reuse it wholesale.

---

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          iOS DASHBOARD (SwiftUI)                           │
│   KPIs · diligence dossier review · approve/reject · chat                  │
└───────────────────────────────┬────────────────────────────────────────────┘
                                 │  HTTP + SSE over Tailscale (ZeeChat pattern)
┌───────────────────────────────┴────────────────────────────────────────────┐
│                    TRANSPORT SHIM  (FastAPI on the CC host)                 │
│   /approvals · /dossier · /kpis (SSE) · /chat (SSE) · whois-auth           │
└───────────────────────────────┬────────────────────────────────────────────┘
                                 │  spawns / reads
┌───────────────────────────────┴────────────────────────────────────────────┐
│                        ORCHESTRATOR (Claude Code host)                      │
│   catalyst calendar → per-catalyst run → gate at PM → gate at DD → approval │
├────────────────────────────────────────────────────────────────────────────┤
│  PIPELINE 1 — TRADE IDENTIFIER (hedge-fund org, runs per catalyst)         │
│                                                                            │
│   ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐             │
│   │ Clinical/  │ │ Regulatory │ │ Financial  │ │ Market/    │  ANALYST     │
│   │ Scientific │ │  Analyst   │ │  Analyst   │ │ Sentiment  │  LAYER       │
│   └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘             │
│         └──────────────┴───── AnalystSignal[] ───────┘                     │
│                              ↓                                             │
│   ┌──────────┐   debate    ┌──────────┐    ┌──────────────┐               │
│   │  BULL    │◄──rounds───►│  BEAR    │──► │  MODERATOR    │  RESEARCH     │
│   │researcher│  (N loops)  │researcher│    │ (judge/synth) │  LAYER        │
│   └──────────┘             └──────────┘    └──────┬───────┘               │
│                              DebateVerdict ────────┘                       │
│                              ↓                                             │
│   ┌──────────────────────────────────────────────┐  TRADE BUILDER        │
│   │ long/long pair · entry/exit · SL/TP · ~1% size│                       │
│   └───────────────────────┬──────────────────────┘  TradeProposal        │
│                           ↓                                                │
│   ┌───────────┐  debate  ┌───────────┐  ┌───────────┐  RISK LAYER         │
│   │ AGGRESSIVE│◄────────►│CONSERVATIVE│─►│  NEUTRAL   │  (3-way, from      │
│   └───────────┘          └───────────┘  └───────────┘   TradingAgents)    │
│                              RiskAssessment ↓                              │
│   ┌──────────────────────────────────────────────┐  PORTFOLIO MGR / MD    │
│   │ single trade vs whole book · concentration ·  │  final promote/kill   │
│   │ correlation to open positions · weekly budget │                       │
│   └───────────────────────┬──────────────────────┘  StrategyDossier      │
├───────────────────────────┼────────────────────────────────────────────────┤
│                    HUMAN GATE 1 (PM promote) → PIPELINE 2                   │
├───────────────────────────┼────────────────────────────────────────────────┤
│  PIPELINE 2 — TRADE DILIGENCE (INDEPENDENT, runs on promoted trades)       │
│   Gets ONLY {ticker, catalyst, pair} — NOT P1's thesis (firewall)         │
│   trial-stats · reg-precedent · runway · ownership/SI · options-implied ·  │
│   pair-corr-validation · liquidity · historical-analog(KB) → GO / NO-GO    │
├───────────────────────────┼────────────────────────────────────────────────┤
│                    HUMAN GATE 2 (user approves on iOS) → EXECUTION          │
├────────────────────────────────────────────────────────────────────────────┤
│  EXECUTION: paper ledger (month 1) → Robinhood MCP (post-shakedown)        │
├────────────────────────────────────────────────────────────────────────────┤
│           GRAPH / EVIDENCE KB  (all layers query; provenance-tagged)       │
│   Catalyst·Drug·Company·Trial·Indication·Outcome·Trade·Playbook·Evidence   │
├────────────────────────────────────────────────────────────────────────────┤
│  ITERATION LOOP: predict → realize → score → reflect → update playbooks    │
│                  + configs, gated by regression evals (DoorDash pattern)   │
└────────────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| Orchestrator | Watch catalyst calendar; fire per-catalyst run; sequence the two pipelines + two human gates | Claude Code parent session / slash command that spawns subagents |
| Analyst subagents (×4) | Each produces one structured, **sourced** `AnalystSignal` in its dimension | Claude Code subagent, dimension-specific tools (RAG + APIs) |
| Bull / Bear researchers | Argue the trade from opposing priors using only analyst signals + KB | Two subagents alternating for N rounds |
| Moderator | Synthesize the debate into a `DebateVerdict` (thesis + confidence + dissent) | Subagent (the "research manager" in TradingAgents terms) |
| Trade Builder | Turn a verdict into a concrete `TradeProposal` (pair, prices, SL/TP, size) | Subagent + deterministic sizing helper |
| Risk debate (×3) | Aggressive/Conservative/Neutral stress the proposal → `RiskAssessment` | Three subagents (lifted from TradingAgents `risk_mgmt/`) |
| Portfolio Manager (MD) | Judge trade vs **whole book**: concentration, correlation, weekly budget → promote/kill | Subagent with read access to positions ledger |
| Diligence framework | Independent multi-dimension DD on promoted trades → GO/NO-GO | Separate subagent set, input-firewalled |
| Graph/Evidence KB | Store entities, playbooks, outcomes, and **every claim's citation**; serve analog queries | SQLite v1 → graph DB only if needed |
| Transport shim | Bridge iOS ↔ Claude Code: approvals, dossier, KPI stream, chat | FastAPI + SSE over Tailscale (ZeeChat) |
| Iteration harness | Score realized vs predicted; write reflections; propose gated config/playbook diffs | Cron/scheduled CC run + eval suite |

---

## Fork Target Analysis (Question 1)

**Repo:** https://github.com/TauricResearch/TradingAgents · **License: Apache-2.0** (commercial-use OK, permissive) · Paper: https://arxiv.org/abs/2412.20138 · Stack: **LangGraph** (Python), multi-provider LLM incl. Claude.

**Why it's the right reference (HIGH confidence — verified from repo + paper + docs):**
- Its org chart is *exactly* the hedge-fund desk PROJECT.md wants: analysts → bull/bear researcher debate → trader → risk team → portfolio manager. This is the "bull/bear debate already defined on someone's github" the user recalled.
- v0.2.4 added the things this project needs to copy: **structured-output decision agents**, **checkpoint resume**, and a **persistent decision log with outcome-grounded reflections** — i.e. it already prototypes the memory + iteration loop.
- Directory structure (verified): `tradingagents/agents/{analysts, researchers, risk_mgmt, trader, managers, utils}` + `agents/schemas.py`; `tradingagents/graph/` holds `trading_graph.py`, `setup.py`, `conditional_logic.py`.

**Verified debate + risk mechanics (lift these):**
- Debate is a **bounded loop**: `max_debate_rounds` config controls how many bull↔bear turns before a manager synthesizes. Same pattern for risk: `max_risk_discuss_rounds`.
- Risk layer is a **3-way debate**, not a single agent: **Aggressive / Conservative / Neutral** analysts argue, then PM decides. (This is richer than the "Risk Management layer" in PROJECT.md — adopt the three roles.)
- **State is a single dict** threaded through the graph. Verified keys worth copying: `market_report, sentiment_report, news_report, fundamentals_report, investment_debate_state, risk_debate_state, trader_investment_plan, investment_plan, final_trade_decision, company_of_interest, trade_date, instrument_context, past_context`. Map these onto your JSON contracts below.
- **Memory:** appends each decision to `~/.tradingagents/memory/trading_memory.md`; on next run for the same ticker it fetches realized return (raw + alpha vs SPY), generates a one-paragraph reflection, and injects recent same-ticker + cross-ticker lessons into the PM prompt. **This is your iteration loop in miniature — copy the shape, upgrade the store to the graph KB.**

### Recommendation: BORROW, don't fork (HIGH confidence)

**Fork the code = wrong.** It's a LangGraph/Python app; catalyst-trader's runtime is Claude Code subagents (user's home turf, native MCP). Forking means maintaining a LangGraph app you won't run. **Borrow the architecture**: reimplement the DAG as CC subagents with JSON contracts, and lift three concrete assets verbatim:
1. The **state schema** (rename fields for biotech: add `clinical_report`, `regulatory_report`).
2. The **bounded-debate loop** (`max_debate_rounds` + manager-synthesis pattern).
3. The **reflection-on-realized-outcome** memory pattern (upgraded into the graph KB).

**Adapting for the three PROJECT.md needs:**
- **(a) Biotech catalysts:** replace `technical`/`news` analysts with **Clinical/Scientific** + **Regulatory** analysts; keep Financial and Market/Sentiment. Feed the catalyst calendar as the run trigger.
- **(b) Persistent memory:** their flat `trading_memory.md` → your graph KB `Outcome`/`Playbook` nodes (survives, queryable by analog).
- **(c) Graph KB:** their reflections are unstructured text; yours become provenance-tagged nodes/edges (schema below).

**Alternatives considered (LOW-MEDIUM confidence, all weaker):** `Mgiri1234/TradingAgents_llm` (a copy, no advantage); generic LangGraph "financial agent" templates (no proven org chart). None beat the original. No biotech-specific catalyst multi-agent framework surfaced — that domain layer is genuinely yours to build.

---

## Pipeline 1 — Trade Identifier: structured contracts (Question 2)

Each layer's output is a JSON document; the next layer's input. This is the enforceable boundary.

**`AnalystSignal`** (one per analyst; 4 total):
```json
{
  "dimension": "clinical|regulatory|financial|market_sentiment",
  "ticker": "XYZ",
  "catalyst_id": "cat_2026_...",
  "score": -1.0,                    // bearish..bullish, calibrated
  "confidence": 0.0,                // 0..1, self-assessed
  "key_findings": [
    {"claim": "...", "evidence_ref": "ev_...", "source_url": "..."}
  ],
  "kb_analogs_queried": ["playbook_..."],   // where KB was hit
  "unknowns": ["..."]               // explicit gaps (anti-hallucination)
}
```

**`DebateVerdict`** (moderator output): `{thesis, direction, confidence, bull_strongest_point, bear_strongest_point, unresolved_dissent[], evidence_refs[]}`. Moderator MUST surface bear's strongest surviving point even when siding bull — this is a built-in confirmation-bias check.

**`TradeProposal`** (trade builder): `{target_long, hedge_long, pair_rationale, entry, exit_by_date, stop_loss, take_profit, size_pct (~1.0), expected_return_pct, kb_analogs[]}`.

**`RiskAssessment`** (post 3-way risk debate): `{downside_stress_scenarios[], hedge_correlation_estimate, correlation_source, liquidity_check, event_vol_estimate, aggressive_view, conservative_view, neutral_view, residual_risks[]}`.

**`StrategyDossier`** (PM/MD final): `{decision: promote|kill, trade: TradeProposal, portfolio_context: {concentration, corr_to_open_positions[], weekly_budget_remaining}, verdict_summary, dissent_log, all_evidence_refs[]}`.

**Where the graph KB is queried (per layer):** analysts query `similar Catalyst/Outcome analogs` for base rates; researchers pull `Playbook` nodes for this catalyst type; trade builder pulls historical `pair-correlation` edges; risk pulls `event-vol` from past analog `Outcome`s; PM reads the live positions ledger + `correlation` edges to open trades.

---

## Pipeline 2 — Trade Diligence: independence design (Question 3)

**The firewall (this is the whole point):** Pipeline 2 receives **only** `{ticker, catalyst_id, target_long, hedge_long, horizon}` — **never** the `DebateVerdict`, `StrategyDossier`, thesis, or P1 scores. It re-derives its own view from raw sources. Enforce structurally:
- Separate subagent set with its own system prompts (no "confirm the trade" framing — framing is "find reasons this fails").
- Its input contract literally omits P1 conclusions; orchestrator strips them.
- Runs as a distinct process/session so no shared conversation context leaks.

**DD dimensions → GO/NO-GO** (each emits sourced findings + a pass/concern/fail):
| Dimension | What it checks | Primary sources |
|-----------|----------------|-----------------|
| Trial stats/endpoints | Powering, primary endpoint, p-value history, prior readouts | ClinicalTrials.gov, publications |
| Regulatory precedent | Analogous PDUFA/AdComm outcomes for the mechanism/indication | FDA calendars, precedent in KB |
| Financials/runway | Cash, burn, months-of-runway through catalyst | 10-Q/10-K, filings |
| Ownership/short interest | SI %, institutional flows, crowding | Exchange SI reports, filings |
| Options-implied move | Market's priced-in move vs your thesis | Options chain (read) |
| Pair-correlation validation | Does the hedge long actually co-move? (real, recent β/corr) | Price history |
| Liquidity | ADV, spread, can ~1% size enter/exit cleanly | Quote/volume data |
| Historical analog | Nearest past `Catalyst→Outcome` in KB + its realized result | Graph KB |

**Output `DiligenceDossier`:** `{verdict: go|no_go, per_dimension: [...], red_flags[], strongest_disconfirming_evidence, all_evidence_refs[]}`. A single dimension = `fail` on a money-touching check (liquidity, runway-through-catalyst, broken pair correlation) forces `no_go` regardless of others.

**Why this beats "just run P1 twice":** independence comes from *different inputs + adversarial framing*, not different models. Confirmation bias is an information-flow problem; the firewall is the fix.

---

## Graph Knowledge Base Schema (Question 4)

### Entities (nodes)
`Company`, `Drug`, `Indication`, `Trial` (with `phase`), `Catalyst` (type: PDUFA/readout/conference/earnings; date), `Outcome` (realized: pass/fail, price move, alpha), `Trade` (the pair, sizing, result), `Playbook` (a reusable scenario strategy), `EvidenceSource` (URL, retrieved-at, snippet-hash), `Prediction` (what an agent said, with confidence).

### Edges
```
Company    -[:DEVELOPS]->        Drug
Drug       -[:TARGETS]->         Indication
Drug       -[:TESTED_IN]->       Trial
Trial      -[:HAS_PHASE]->       TrialPhase
Catalyst   -[:ABOUT]->           Drug | Company | Trial
Catalyst   -[:RESULTED_IN]->     Outcome
Trade      -[:PLACED_ON]->       Catalyst
Trade      -[:USED_PLAYBOOK]->   Playbook
Trade      -[:REALIZED]->        Outcome
Prediction -[:MADE_BY]->         (agent/layer)
Prediction -[:ABOUT]->           Catalyst
ANY_CLAIM  -[:CITES]->           EvidenceSource     // provenance edge, mandatory
Catalyst   -[:ANALOG_OF {sim}]-> Catalyst           // analog links, weighted
```

### Provenance (the "point to why" requirement — non-negotiable)
Every stored claim node carries a **mandatory `:CITES` edge to an `EvidenceSource`** (url + retrieved-at + snippet hash + optional quote). A claim with no `EvidenceSource` is a schema violation — write path rejects it. This is what lets any dashboard number drill down to its source. `Prediction` nodes also carry the confidence and the agent that made it, so post-mortems can attribute misses.

### "Similar past scenarios" (analog query)
Two-tier, cheapest-that-works first:
1. **Structured match (v1):** filter `Catalyst` by `{type, phase, indication_class, market_cap_bucket}` → traverse to `Outcome`. Pure SQL/Cypher, deterministic, explainable. Covers most of the need.
2. **Semantic match (add when tier-1 too sparse):** embed a catalyst-context string, ANN search for nearest catalysts, then verify with tier-1 filters. Store embeddings alongside nodes.
Return analogs *with their realized `Outcome` and evidence refs* so downstream agents cite base rates, not vibes.

### Storage engine decision (IMPORTANT — corrects PROJECT.md)
PROJECT.md assumes **Kùzu embedded**. **Kùzu's GitHub was archived Oct 2025 after Apple acquired the team** (verified: BetaKit, 9to5Mac, ArcadeDB, gdotv). Upstream is dead; only community forks (e.g. LadybugDB) remain, unproven longevity. **For real money you should not build the memory core on an abandoned engine.**

| Option | Verdict | When |
|--------|---------|------|
| **SQLite + edge/adjacency tables + a few recursive CTEs** | **v1 default** | The graph is ~20 tickers × dozens of catalysts/yr — thousands of nodes, not millions. SQL handles analog filtering + provenance trivially; you already ship SQLite everywhere. Add `sqlite-vec` for tier-2 embeddings. |
| **Neo4j Community (server)** | If multi-hop analog queries get genuinely painful | Mature, Cypher, not going anywhere. Cost = running a server. |
| **LadybugDB (Kùzu fork)** | Only if you *need* embedded + Cypher + it proves maintained | Watch adoption; don't bet the money-path on it yet. |
| **Kùzu upstream** | **Do not use** | Archived/abandoned. |

Recommendation: **start SQLite, keep the schema graph-shaped** (nodes/edges as tables) so migrating to Neo4j later is mechanical if you ever need it. `ponytail: SQLite graph, upgrade to Neo4j only if multi-hop analog queries measurably slow.`

---

## Continuous-Iteration / Self-Improvement Loop (Question 5)

Modeled on **DoorDash's "platform for building and evolving agents"** (verified via their Ask DoorDash engineering series + broader eval-driven-agent literature). Their load-bearing ideas, mapped here:

1. **Every run emits a transcript** — DoorDash captures user inputs, agent responses, tool calls, tool outputs per session. Here: persist each catalyst run as a `Prediction` bundle (all layer outputs + evidence refs + confidences).
2. **Score at realization** — one week later, realize the `Outcome` (price move, alpha vs SPY/XBI, hit SL/TP?). Compute per-layer accuracy: did clinical analyst call the readout? was implied-move estimate right? was the pair correlation real?
3. **LLM-as-judge, calibrated to graded labels** — DoorDash's evals are LLM-judges *calibrated against human-reviewed labels*. Here: judge each layer's reasoning quality against the realized outcome; calibrate the judge against a small set of your own hand-graded trades so scores are trustworthy.
4. **Reflection → playbook update** — write a `Playbook` diff: "PDUFA + prior-CRL + crowded-short → base rate X, add caution Y." Store as a versioned `Playbook` node with evidence.
5. **Config tuning, gated** — propose changes (debate rounds, analyst weightings, sizing rules) but **never auto-apply to the money path without passing a regression suite**.

### Where evals/regression tests live (the anti-regression guarantee)
- A **golden set** of past catalyst runs with known outcomes lives in the repo (`evals/golden/`). Any config/prompt/playbook change must be replayed against it.
- **Guardrail evals** (DoorDash term) run every trade: "every claim has an EvidenceSource," "no trade exceeds weekly budget," "hedge correlation is real and recent." A guardrail failure blocks promotion.
- **Regression gate:** a change ships only if it improves (or holds) golden-set score AND passes all guardrails. This is what makes "provably gets better without regressing" true rather than aspirational.

```
predict (run) → store Prediction+evidence
     ↓  (1 week)
realize Outcome → score vs prediction (per layer)
     ↓
LLM-judge (calibrated) → reflection
     ↓
propose Playbook/config diff
     ↓
REPLAY on golden set + guardrails ──fail──► reject diff
     ↓ pass
apply → next runs use updated playbooks/configs
```

---

## Evidence & Anti-Hallucination Architecture (Question 6)

Real money ⇒ ungrounded assertions are the top risk. Four enforced layers:

1. **Tool-grounded retrieval only.** Analysts assert from tool/RAG outputs, not memory. Each `key_finding` must carry an `evidence_ref`. No source → the finding is dropped at the schema boundary.
2. **Citation-required structured output.** The JSON contracts above make `evidence_ref` a required field. This is enforced by validation, not by asking nicely.
3. **Calibrated confidence + explicit unknowns.** Every signal carries `confidence` and an `unknowns[]` list. Overconfidence gets punished in the iteration loop (calibration tracked over time), which pressures honest confidence.
4. **Verifier/fact-checker agent.** A dedicated subagent runs before each human gate: samples claims in the dossier, re-checks the cited source actually supports the claim (snippet-hash match / re-fetch), flags any unsupported or stale (>N-day) evidence. This is the guardrail eval made agentic.

**Where guardrails sit:** at **every layer boundary** (schema validation on each contract) and as a **hard gate before each human approval** (verifier + budget/liquidity/correlation checks). Diligence Pipeline 2 is itself a structural anti-hallucination mechanism (independent re-derivation).

---

## iOS ↔ Claude Code Transport (Question 7)

**Reuse the ZeeChat pattern wholesale** (your existing SwiftUI ↔ Claude Code bridge over Tailscale — proven in production).

```
SwiftUI app ──HTTPS/Tailscale──► FastAPI shim on CC host ──► Claude Code sessions
   ▲                                    │
   └────────── SSE streams ◄────────────┘   (KPIs live, chat tokens, approval prompts)
```

- **Transport:** FastAPI (or your existing dispatch chat router) on the CC host, bound on the Tailscale interface, whois/bearer auth (ZeeChat v2.1 already does whois auth + FaceID gate — reuse).
- **Approvals:** shim exposes `/approvals` (pending dossiers) + `POST /approvals/{id}` (approve/reject). A promoted trade parks in a pending queue; the app polls/receives an SSE push; user approves → orchestrator proceeds to execution. Mirrors your DISPATCH-WAKE pattern.
- **Chat:** `/chat` SSE relays tokens to/from the running agents (exact ZeeChat mechanism).
- **Live KPIs:** `/kpis` SSE pushes P&L, per-position status, week-expected-return as the paper ledger updates. Every KPI value links back to its evidence/computation for drill-down.
- **Dossier review:** `/dossier/{trade_id}` returns the `StrategyDossier` + `DiligenceDossier` with evidence refs rendered as tappable sources.

`ponytail: reuse ZeeChat's shim; add trading routes, don't build new transport.`

---

## Recommended Project Structure

```
catalyst-trader/
├── agents/                     # Claude Code subagent definitions (prompts + contracts)
│   ├── analysts/               # clinical, regulatory, financial, market_sentiment
│   ├── researchers/            # bull, bear, moderator
│   ├── trade_builder/
│   ├── risk/                   # aggressive, conservative, neutral
│   ├── portfolio_manager/
│   ├── diligence/              # INDEPENDENT DD dimension agents (own prompts)
│   └── verifier/               # fact-checker / guardrail agent
├── contracts/                  # JSON schemas for every inter-layer document
├── kb/                         # graph KB: SQLite schema, write-path (provenance-enforcing), analog queries
├── orchestrator/               # calendar watcher, run sequencer, gate logic, positions ledger
├── execution/                  # paper ledger (v1) → Robinhood MCP adapter (later)
├── evals/                      # golden set, LLM-judge, guardrail checks, regression runner
├── transport/                  # FastAPI/SSE shim (ZeeChat-derived)
├── ios/                        # SwiftUI dashboard
└── .planning/
```

**Rationale:** folders mirror the org chart so a new agent = a new prompt+contract in one place. `contracts/` is separate because the schemas are the enforceable boundaries (both pipelines + evals depend on them). `kb/` centralizes the provenance-enforcing write path so no agent can bypass citation rules.

---

## Architectural Patterns

### Pattern 1: Bounded adversarial debate with a synthesizer
**What:** N alternating bull/bear turns, then a moderator emits a verdict that must name the losing side's strongest surviving point. (Lifted from TradingAgents `max_debate_rounds` + research manager.)
**When:** the research + risk layers.
**Trade-offs:** + surfaces disconfirming evidence structurally; − costs tokens per round (cap N low, 2–3).

### Pattern 2: Input-firewalled independent verification
**What:** Pipeline 2 gets raw inputs, never P1's conclusion; adversarial "find the failure" framing.
**When:** any second-opinion stage on a money-touching decision.
**Trade-offs:** + real independence, kills confirmation bias; − duplicates some retrieval work (acceptable for real money).

### Pattern 3: Provenance-enforced write path
**What:** the KB rejects any claim node lacking a `:CITES → EvidenceSource` edge.
**When:** all KB writes.
**Trade-offs:** + every number is drill-down-able; − agents must always retrieve before asserting (that's the feature).

### Pattern 4: Eval-gated self-improvement
**What:** config/playbook diffs must pass a golden-set replay + guardrails before touching the live path.
**When:** the iteration loop.
**Trade-offs:** + provable non-regression; − need to maintain the golden set (cheap vs the alternative: silent drift on real money).

---

## Data Flow

### Per-catalyst run
```
Catalyst (1-2 days out)
   ↓ orchestrator spawns
4× AnalystSignal ──► Bull/Bear debate ──► DebateVerdict
   ↓
TradeProposal ──► 3-way Risk debate ──► RiskAssessment
   ↓
StrategyDossier ──► [PM promote?] ──► HUMAN GATE 1
   ↓ promoted (raw inputs only)
DiligenceDossier ──► [GO?] ──► HUMAN GATE 2 (iOS approve)
   ↓ approved
Execution (paper ledger → Robinhood MCP)
   ↓ (1 week)
Outcome ──► iteration loop ──► KB + gated config/playbook update
```

Every arrow is a validated JSON contract; every claim inside carries evidence refs into the KB.

---

## Scaling Considerations

The scale here is **tiny** (~20 tickers, a handful of catalysts/week) — the constraint is **correctness and cost**, not throughput.

| Scale | Adjustment |
|-------|-----------|
| v1 (paper, ~20 names) | SQLite KB, sequential per-catalyst runs, cap debate rounds. Fine. |
| More names / more catalysts | Parallelize independent catalyst runs; still SQLite. |
| Analog queries slow | Add `sqlite-vec` (tier-2), then Neo4j only if multi-hop truly hurts. |

**First bottleneck:** LLM token cost per run (many subagents × debate rounds), not DB. Fix: cap rounds, cache retrievals per run, use cheaper models for analysts / strongest model for PM + verifier.

---

## Anti-Patterns

### Anti-Pattern 1: Forking the LangGraph codebase
**What people do:** `git fork TradingAgents`, then fight Python/LangGraph on a Claude Code project.
**Why wrong:** you'd maintain a runtime you don't use.
**Instead:** borrow the org chart + state schema + debate loop; build on CC subagents.

### Anti-Pattern 2: Building the KB on Kùzu because a doc said "embedded graph"
**What people do:** adopt Kùzu per the original assumption.
**Why wrong:** archived Oct 2025 (Apple acquihire) — abandoned upstream, on a real-money system.
**Instead:** SQLite graph-shaped v1; Neo4j Community if you outgrow it.

### Anti-Pattern 3: "Independent" DD that sees P1's thesis
**What people do:** pass the full dossier to the DD agents.
**Why wrong:** it just rubber-stamps — the confirmation bias you were trying to remove.
**Instead:** firewall inputs to `{ticker, catalyst, pair}` + adversarial framing.

### Anti-Pattern 4: Ungated self-improvement on the money path
**What people do:** let the loop auto-apply prompt/config changes.
**Why wrong:** silent regression on real capital.
**Instead:** golden-set replay + guardrails gate every diff.

### Anti-Pattern 5: Uncited agent assertions
**What people do:** agents state numbers from memory.
**Why wrong:** hallucinated financials/trial stats → real losses; can't answer "why."
**Instead:** citation-required schemas + verifier agent + provenance-enforced KB.

---

## Integration Points

### External Services
| Service | Integration | Notes |
|---------|-------------|-------|
| Robinhood MCP | Execution (post-shakedown) | **Verify tool surface** — PROJECT.md flags options/shorting unconfirmed. Long/long pairs assume equities buy/sell only. |
| ClinicalTrials.gov / FDA | Clinical + regulatory retrieval | Primary evidence sources; cite retrieved-at. |
| Filings / quotes / options data | Financial, liquidity, options-implied, pair-corr | Read-only; feed evidence refs. |
| Anthropic (Claude via CC) | Agent runtime | Native to CC; strongest model on PM + verifier. |

### Internal Boundaries
| Boundary | Communication | Notes |
|----------|---------------|-------|
| Layer → layer (P1) | Validated JSON contract | Schema = the boundary; drop uncited claims. |
| P1 → P2 | Firewalled subset only | No thesis leakage. |
| Agents → KB | Provenance-enforcing write path | Reject claims without EvidenceSource. |
| CC host → iOS | HTTP + SSE over Tailscale | ZeeChat pattern; whois auth. |
| Iteration loop → live config | Only via eval gate | No direct writes to money-path config. |

---

## Build Order (Question 8 — dependency-ordered for the roadmap)

1. **Contracts + KB skeleton.** Define the JSON schemas and the SQLite graph schema with the provenance-enforcing write path. *Everything downstream depends on these.*
2. **Catalyst calendar + universe.** Orchestrator that builds the ~20-name universe and flags catalysts 1–2 days out. (Feeds every run.)
3. **Analyst layer (×4).** Sourced `AnalystSignal` producers with their retrieval tools. Testable in isolation against the schema.
4. **Research debate + moderator.** Bounded bull/bear loop → `DebateVerdict`. (Borrow TradingAgents loop.)
5. **Trade builder + 3-way risk + PM.** `TradeProposal` → `RiskAssessment` → `StrategyDossier` with promote/kill against a (stub) positions ledger.
6. **Pipeline 2 (independent DD).** Firewalled, adversarial → `DiligenceDossier`. Depends on contracts + KB analogs.
7. **Verifier + guardrails.** Fact-checker agent + hard gate checks before approvals.
8. **Paper ledger.** Internal sim execution + P&L against live quotes (month-1 shakedown target).
9. **Transport shim + iOS dashboard.** ZeeChat-derived; approvals + dossier + KPI SSE + chat. (Needs dossiers + ledger to show.)
10. **Iteration loop + evals.** Golden set, LLM-judge, regression gate, playbook/config update. (Needs realized outcomes → last.)
11. **Robinhood MCP execution.** Only after the 1-month paper shakedown proves out + tool surface verified.

Rationale: schemas/KB first (everything binds to them) → data feed → producers bottom-up through the org chart → independent DD → safety gates → execution sim → UI → self-improvement (needs outcomes to exist) → real money last (hard prerequisite: paper proof + human gate).

---

## Sources

- TradingAgents repo (structure, license Apache-2.0, memory, LangGraph): https://github.com/TauricResearch/TradingAgents — HIGH
- TradingAgents paper: https://arxiv.org/abs/2412.20138 — HIGH
- TradingAgents docs (roles, debate, risk team, PM): https://tauricresearch.github.io/TradingAgents/ — HIGH
- TradingAgents `graph/trading_graph.py` (state dict, conditional debate loop, checkpointing): https://github.com/TauricResearch/TradingAgents/tree/main/tradingagents — HIGH
- DoorDash — Building & Evolving Agents (eval harness, LLM-as-judge calibrated to labels, guardrail evals, tracing): https://careersatdoordash.com/blog/building-ask-doordash-part-four-a-platform-for-building_and_evolving_agents/ — MEDIUM (fetch was 403; synthesized from search excerpt + DoorDash Assistant overview)
- DoorDash Assistant engineering overview: https://careersatdoordash.com/blog/building-doordash-assistant-an-engineering-overview/ — MEDIUM
- Kùzu archived after Apple acquisition (Oct 2025): https://betakit.com/apple-strikes-deal-to-acquire-canadian-database-software-startup-kuzu/ · https://9to5mac.com/2026/02/11/kuzu-database-company-joins-apples-list-of-recent-acquisitions/ — HIGH
- Kùzu legacy / community forks (LadybugDB) + embedded-graph landscape: https://gdotv.com/blog/kuzu-legacy-embedded-graph-database-landscape/ · https://arcadedb.com/blog/neo4j-alternatives-in-2026-a-fair-look-at-the-open-source-options/ — MEDIUM
- Kùzu vs Neo4j (Cypher, embedded, perf): https://docs.kuzudb.com/cypher/difference/ · https://thedataquarry.com/blog/embedded-db-2/ — MEDIUM
- iOS transport pattern: user's ZeeChat (SwiftUI + Tailscale + HTTP/SSE shim, whois auth, FaceID) — HIGH (project precedent)

---
*Architecture research for: event-driven multi-agent biotech trading desk*
*Researched: 2026-08-14*
