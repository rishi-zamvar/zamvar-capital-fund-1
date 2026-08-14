# Project Research Summary

**Project:** catalyst-trader
**Domain:** Event-driven biotech-catalyst trading system — multi-agent research desk (Claude Code subagents) + graph-shaped knowledge base + iOS approval dashboard + real-money Robinhood equities execution
**Researched:** 2026-08-14
**Confidence:** MEDIUM-HIGH (execution path, fork target, and financial base rates HIGH; exact library versions and RH MCP tool surface LOW/UNVERIFIED)

## Executive Summary

This is a real-money system, so the research is opinionated and corrects two load-bearing assumptions in PROJECT.md before any code is written. First: **Robinhood shipped an official Agentic Trading MCP (2026-05-27)** with a segregated agent account and localhost OAuth — exactly this project's local-Mac, equities-only, human-gated scope. Use it; never build execution on `robin_stocks` or any unofficial wrapper (ToS/ban risk on real money). Second: **Kùzu is dead** — the company was acquired by Apple in Oct 2025 and the upstream repo was archived. The knowledge base should be **SQLite kept graph-shaped (nodes/edges as tables) + `sqlite-vec`** for analog similarity search, escalating to a real graph DB only if multi-hop queries measurably hurt at the ~20-ticker scale this project actually has.

The recommended build is to **borrow, not fork, `TauricResearch/TradingAgents`** (Apache-2.0): lift its state schema, its bounded bull/bear debate loop, its 3-way risk debate (Aggressive/Conservative/Neutral), and its reflect-on-realized-outcome memory pattern — but re-implement the org chart as flat Claude Code subagents (subagents cannot nest, so the design is orchestrator → analyst/researcher/risk fan-out, not deep hierarchy) rather than fighting LangGraph. The two-pipeline design (Identifier → independent Diligence) is architecturally sound and maps to real hedge-fund practice (separation of authorship from approval); its value depends entirely on a genuine **information firewall** — Pipeline 2 must receive only `{ticker, catalyst, pair}` and adversarial framing, never Pipeline 1's thesis, or the "independent" check just rubber-stamps. Provenance must be enforced at the KB write path (no claim without a `:CITES → EvidenceSource` edge) and a verifier/fact-checker agent must run before every human gate — this is the anti-hallucination spine for a domain (biotech binaries) where a single fabricated p-value or stale PDUFA date is a total-loss event.

The single biggest risk is not technical, it's conceptual: **the design's own long/long "hedge" does not hedge the idiosyncratic binary event it's meant to protect against.** A correlated peer long often rallies (not falls) when a name fails its trial, so two longs on a catalyst is 2x conditional-long exposure dressed as a hedge, not risk reduction. Combined with three other total-loss-capable pitfalls — stop-losses that gap straight through on binary events, a fixed 1%/week return target that (if used as a sizing input rather than a measured outcome) drives martingale-style ruin, and a wrong/stale catalyst date that alone can be a total loss — the roadmap must put **data-integrity/catalyst-feed rigor and honest risk sizing before any agent cleverness**, and must gate the self-improvement loop behind walk-forward evals so it can't quietly overfit or reward-hack on real capital.

## Key Findings

### Recommended Stack

See `.planning/research/STACK.md` for full detail. Headline: **official Robinhood Agentic Trading MCP** for execution (segregated account, per-trade notifications, equities-only beta — a near-perfect scope match), **Claude Agent SDK (Python)** for headless/scheduled orchestration (native MCP + structured outputs; subagents cannot nest, forcing a flat orchestrator→fan-out design), **SQLite + `sqlite-vec`** for the knowledge base (not Kùzu — archived upstream), **ClinicalTrials.gov API v2 + FMP + Polygon** for data (no free PDUFA API exists — that calendar must be hand-curated), and **SwiftUI + FastAPI/SSE over Tailscale**, reusing the ZeeChat transport pattern wholesale.

**Core technologies:**
- Robinhood Agentic Trading MCP (official) — live equities buy/sell + read — only ToS-safe execution path; localhost OAuth fits this local-Mac deployment exactly. **HIGH**
- Claude Agent SDK (Python) — headless orchestration runtime for T-2 catalyst-triggered runs — native MCP + structured outputs; **subagents cannot nest** → flat orchestrator→analyst fan-out, not deep hierarchy. **HIGH** (feature set) / LOW (exact version)
- SQLite + `sqlite-vec` — knowledge base substrate: scenario playbooks, outcomes, provenance, analog similarity search — zero-ops, plenty for ~20 tickers × dozens of catalysts/yr; no ANN index yet but brute-force is fine at this scale. **MEDIUM**
- ClinicalTrials.gov v2 (trial dates, HIGH) + FMP (fundamentals/earnings calendar, MEDIUM-HIGH) + Polygon (options IV, MEDIUM) — no free/authoritative PDUFA API exists anywhere; PDUFA/AdCom dates must be a **manually-maintained, two-source-verified table**.
- TauricResearch/TradingAgents (Apache-2.0) — fork *source for structure only*: bull/bear debate, 3-way risk team, reflect-on-outcome memory. **HIGH**
- SwiftUI + Swift Charts (iOS dashboard) + FastAPI/SSE over Tailscale (transport) — direct reuse of the proven ZeeChat pattern. **HIGH**

**Do not use:** `robin_stocks`/unofficial RH wrappers (ban risk), Kùzu upstream (archived), Neo4j server (ops overhead for one user), yfinance as a decision-critical source, vectorbt for the paper ledger (wrong tool + `freq` footgun).

### Expected Features

See `.planning/research/FEATURES.md` for the full domain research (real fund operating cadence, rNPV scoring rubric, base-rate edge indicators, dashboard KPIs, hedging mechanics) — that document is load-bearing for REQUIREMENTS.md, not just a features list.

**Must have (table stakes):**
- Catalyst calendar (auto PDUFA/readout/conference/earnings + manual injection) + ~20-name curated universe
- Layered analyst desk (Clinical/Regulatory/Financial/Sentiment) + bull/bear debate (built-in red team)
- Fundamental scoring rubric: **rNPV** (the industry-standard method for pre-revenue biotech — DCF/P-E do not apply) + base-rate anchoring cited on every thesis (BIO/Biomedtracker LoA: overall Phase I→approval 7.9%, Phase II→III 28.9%, oncology from Phase I ~3.4%)
- Position memo with explicit falsification/kill criteria + a pre-mortem step (documented debiasing techniques from real funds)
- Independent Diligence pipeline (four-eyes, no anchoring) + Risk agent with a real veto + Portfolio Manager (promote/kill vs whole book)
- Cointegration-validated (not merely correlated) hedge peer + a check that the peer is itself catalyst-clean over the hold window
- Human approval gate (iOS) — non-negotiable; paper-trading sim ledger vs live quotes for Month 1; iOS dashboard with two curated views (1-week strategy picture + in-the-moment live picture); post-trade attribution + post-mortem

**Should have (differentiators):**
- Graph-shaped KB of scenario playbooks + outcomes queryable by analog
- Continuous-iteration loop (score realized vs predicted → tune rubric weights/playbooks), DoorDash-eval-pattern inspired
- Options-implied-move as a cross-check on the desk's own probability-of-success estimate
- Chat directly to running agents from iOS (reuse ZeeChat)

**Defer (v2+):**
- Options-implied-move as an independent second PoS model, multi-catalyst portfolio optimization — defer until the single-trade flow and base desk are proven
- Microstructure corroboration (Form 4 insider, short interest, unusual options activity) — low-signal/noisy, add once base desk is trusted

### Architecture Approach

See `.planning/research/ARCHITECTURE.md` for full contracts, KB schema, and build order. **Borrow, don't fork, TradingAgents**: reimplement its DAG (analysts → bull/bear debate → trade builder → 3-way risk debate → PM) as Claude Code subagents with validated JSON contracts at every layer boundary, since subagents can't nest — the orchestrator sequences a flat fan-out, not a hierarchy. Pipeline 2's independence is enforced structurally (input firewall + adversarial framing + separate process/session), not merely by prompt instruction. The KB is provenance-enforcing at the write path: any claim node lacking a `:CITES → EvidenceSource` edge is a schema violation and is rejected, so every dashboard number is drill-down-able to its source.

**Major components:**
1. Orchestrator — watches the catalyst calendar, fires per-catalyst runs, sequences both pipelines and both human gates
2. Pipeline 1 (Trade Identifier) — 4 analyst subagents → bounded bull/bear debate + moderator → Trade Builder → 3-way risk debate (Aggressive/Conservative/Neutral) → Portfolio Manager promote/kill → `StrategyDossier`
3. Pipeline 2 (Trade Diligence) — independent, input-firewalled (`{ticker, catalyst, pair}` only), 8-dimension DD → `DiligenceDossier` GO/NO-GO
4. Graph/Evidence KB (SQLite, graph-shaped) — entities/edges + mandatory provenance + two-tier analog query (structured filter first, semantic/ANN second)
5. Iteration harness — predict → realize outcome → LLM-judge (calibrated to hand-graded labels) → reflection → playbook/config diff → **golden-set regression replay + guardrail evals gate before any diff touches the money path**
6. Transport shim + iOS dashboard — FastAPI/SSE over Tailscale, direct ZeeChat-pattern reuse, for approvals/dossier/KPIs/chat
7. Execution — paper ledger (Month 1) → Robinhood MCP adapter (only after shakedown + tool-surface verification)

### Critical Pitfalls

See `.planning/research/PITFALLS.md` for the full set (14 pitfalls, ranked). The first four are **total-loss-capable and, as PROJECT.md is currently written, three of them are baked into the design**:

1. **Long/long is not a hedge for a binary single-name event, and can double the loss.** Correlation is a sector/beta relationship measured in normal markets; it is exactly the relationship that breaks on idiosyncratic catalyst days — a competing peer often *rallies* on a name's failure. Two correlated longs is 2x conditional-long exposure, not risk reduction. **Fix:** require the Risk layer to model the pair's payoff *conditional on the catalyst outcome* (using historical analog gaps, not unconditional daily correlation); size to the combined worst case; treat "close before the event" as the default, holding-through as the exception; if a peer long is kept, justify it as conviction, not hedge.
2. **Stop-losses do not survive a binary gap.** Biotech catalysts gap overnight/pre-market straight through any stop (real 2025-26 examples: -72%, -70%+ single-day moves); a stop fills at the next print. **Fix:** default to exiting before the event opens; if holding through is ever allowed, the only real control is position size sized for a -70%-or-worse outcome, and the stop-loss field must be labeled advisory-only in the dossier and dashboard — never shown as a bounded-loss number.
3. **A wrong or stale catalyst date is a total loss.** PDUFA dates are deadlines that move; trial readouts are guided *windows*, not dates; LLMs will confidently hallucinate a plausible-but-wrong date from training data. **Fix:** two-source rule (at least one primary: company IR/FDA/ClinicalTrials.gov) for every catalyst date, an explicit uncertainty type (`firm`/`window`/`soft`), a `last_verified` freshness stamp re-checked within 48h of any trade, and dates must never originate from an LLM's parametric memory.
4. **Chasing a fixed 1%/week maximizes risk of ruin.** ~1%/week ≈ 68%/yr compounded on the highest-variance event class in equities; if the target is used to *derive* size (rather than measured as an outcome), losses force size-up-to-recover — the classic ruin path, and short loss streaks are statistically routine even at healthy base rates. **Fix:** size for survival via risk-of-ruin / fractional-Kelly on the position's downside gap (assume -70%), hard per-event and portfolio caps, and treat 1%/week strictly as a measured outcome, never a sizing input; explicitly allow zero-trade weeks.

Also high-severity and roadmap-relevant: prompt injection via scraped web content (no path from scraped content to an order, ever — the human gate is the hard line); the paper-to-live gap (a 1-month sample is statistically meaningless for binary events, and mid/last-quote fills make paper P&L systematically too rosy — fill pessimistically, gate go-live on catalyst *count* not calendar time); look-ahead/survivorship bias in the universe and backtest (build point-in-time, include delisted names); and Robinhood's unofficial-API fragility being entirely sidestepped by using the official MCP, but its collar/rejection/halt behavior around volatile events must still be assumed and handled with limit orders + a manual fallback.

## Implications for Roadmap

Based on combined research, the dependency-correct build order (from ARCHITECTURE.md's Build Order section, cross-checked against PITFALLS.md's "fix data integrity first" and FEATURES.md's dependency graph) is:

### Phase 1: Data Integrity & Catalyst Feed
**Rationale:** A wrong/stale catalyst date is a total-loss pitfall (#3) and every downstream layer depends on it — this must be built and hardened *before* any agent logic, not bolted on later.
**Delivers:** ~20-name universe builder (point-in-time, catalyst density/liquidity/therapeutic-area criteria), rolling catalyst calendar (ClinicalTrials.gov v2 auto + FMP earnings auto + hand-curated PDUFA/AdCom with two-source verification and freshness stamps), catalyst uncertainty typing (`firm`/`window`/`soft`).
**Addresses:** Universe & catalyst feed requirements (FEATURES.md table stakes).
**Avoids:** Pitfall 3 (wrong catalyst date), Pitfall 8 (survivorship/look-ahead bias — build point-in-time from day one), Pitfall 11 (corporate actions/reverse splits corrupting data silently).

### Phase 2: Contracts + Knowledge-Base Skeleton
**Rationale:** Every inter-layer JSON contract and the provenance-enforcing KB write path are the enforceable boundaries everything else binds to (ARCHITECTURE.md Build Order step 1).
**Delivers:** JSON schemas for `AnalystSignal`/`DebateVerdict`/`TradeProposal`/`RiskAssessment`/`StrategyDossier`/`DiligenceDossier`; SQLite graph-shaped schema (Company/Drug/Trial/Catalyst/Outcome/Trade/Playbook/EvidenceSource nodes, mandatory `:CITES` edges) with `sqlite-vec` for analog similarity.
**Uses:** SQLite + sqlite-vec (STACK.md), pydantic for schema enforcement.
**Implements:** Provenance-enforced write path (ARCHITECTURE.md Pattern 3) — the anti-hallucination spine.

### Phase 3: Quant Tool Library + Rubric/Base-Rates
**Rationale:** Analysts need deterministic tools and the scoring framework before they can produce structured, sourced signal; this is also the "no LLM arithmetic on money" constraint from PROJECT.md.
**Delivers:** rNPV/cash-runway/Kelly-sizing/correlation-beta/options-implied-move/Sharpe/base-rate-lookup as unit-tested, versioned, reproducible tools; the rNPV+8-factor scoring rubric (A2 in FEATURES.md) as tunable config; BIO/Biomedtracker base rates loaded and citable.
**Addresses:** "Quant tool/skill library" and "Knowledge & framework" requirements.
**Avoids:** Pitfall 4 (LLM hallucinated statistics) via a deterministic sanity-gate on every extracted number.

### Phase 4: Analyst Desk + Bull/Bear Debate (Pipeline 1, part 1)
**Rationale:** Bottom-up through the org chart — analysts before debate before trade construction.
**Delivers:** 4 analyst subagents producing sourced `AnalystSignal`s; bounded bull/bear debate loop + moderator (borrowed from TradingAgents' `max_debate_rounds` pattern) producing `DebateVerdict` that must name the losing side's strongest point.
**Uses:** Claude Agent SDK subagents, TauricResearch/TradingAgents state-schema/debate-loop pattern (borrowed, not forked).
**Implements:** ARCHITECTURE.md Pattern 1 (bounded adversarial debate with synthesizer).

### Phase 5: Trade Builder + Honest Sizing + 3-Way Risk + Portfolio Manager (Pipeline 1, part 2)
**Rationale:** Cannot construct a trade correctly until the pair-hedge honesty problem (Pitfall 1) and ruin-avoidant sizing (Pitfall 5) are solved as first-class design, not an afterthought.
**Delivers:** `TradeProposal` with cointegration-validated (Engle-Granger/Johansen), catalyst-clean hedge peer; risk-of-ruin/fractional-Kelly sizing (1%/week as measured output, never sizing input); 3-way risk debate (Aggressive/Conservative/Neutral, borrowed from TradingAgents' risk_mgmt); Portfolio Manager promote/kill against the live book (concentration, correlation to open positions, weekly budget).
**Addresses:** Trade Builder + Risk Management + Portfolio Manager requirements.
**Avoids:** Pitfall 1 (fake hedge), Pitfall 5 (ruin from fixed-return sizing), Pitfall 2 (stop-loss labeled advisory-only for any held-through position).

### Phase 6: Independent Diligence Pipeline (Pipeline 2)
**Rationale:** Depends on the contracts/KB (Phase 2) and produces a real second opinion only if structurally isolated from Pipeline 1 — the whole point of the two-pipeline design.
**Delivers:** Separate subagent set with adversarial ("find reasons this fails") framing, input-firewalled to `{ticker, catalyst, pair}` only, 8-dimension DD (trial stats, regulatory precedent, financials/runway, ownership/SI, options-implied move, pair-correlation re-validation, liquidity, historical analog) → `DiligenceDossier` GO/NO-GO with a single failing money-touching dimension forcing NO-GO.
**Uses:** Graph KB analog queries.
**Avoids:** Pitfall 4 (laundered confirmation bias if independence isn't structurally enforced).

### Phase 7: Verifier/Guardrails + Backtest Harness
**Rationale:** Safety gates and empirical validation before any capital simulation. Backtest must exist before the paper month to set config baselines and prove the fill/hedge assumptions honestly.
**Delivers:** Fact-checker/verifier subagent (re-checks cited claims before each human gate); Layer A mechanical backtest (deterministic, no LLM, ~1yr earnings + dateable biotech catalysts, point-in-time universe including delisted names, pessimistic fill model — far side of spread + gap-open fills on held-through events); Layer B guarded agentic replay (look-ahead-blocked, labeled biased-optimistic).
**Avoids:** Pitfall 6 (prompt injection — no scrape→order path), Pitfall 7 (paper-to-live gap — pessimistic fills modeled here first), Pitfall 8 (look-ahead/survivorship).

### Phase 8: Paper Ledger, Attribution & Post-Mortem (Layer C)
**Rationale:** The true out-of-sample test; needs the full pipeline and backtest baseline to be meaningful.
**Delivers:** Internal sim ledger vs live quotes, pessimistic-fill-consistent with Phase 7; performance attribution (catalyst effect vs beta drift vs hedge leg vs sizing) and post-mortem (good-decision/bad-luck framing) feeding the KB.
**Addresses:** Execution (Month 1) + attribution/post-mortem requirements.
**Avoids:** Pitfall 7 (go-live gated on catalyst *count*/statistical significance, not calendar time — a month is a plumbing shakedown, not proof of edge).

### Phase 9: iOS Dashboard + Approval Gate
**Rationale:** Needs dossiers and a live ledger to display; reuses an already-proven transport (ZeeChat), so this is low-research, high-confidence integration work once upstream data exists.
**Delivers:** SwiftUI two-view dashboard (1-week strategy picture + in-the-moment live picture) with curated KPIs (FEATURES.md A4), dossier review with tappable evidence, approve/reject gate, chat to running agents — over the FastAPI/SSE-over-Tailscale shim.
**Uses:** SwiftUI + Swift Charts, FastAPI/SSE, ZeeChat pattern (STACK.md, ARCHITECTURE.md).
**Avoids:** Pitfall 2's dashboard corollary — never display a fictitious bounded loss for a held-through position.

### Phase 10: Continuous-Iteration Loop
**Rationale:** Needs realized outcomes to exist — genuinely last. This is also the most seductive failure surface (overfitting/reward-hacking on real capital), so it must ship gated from day one.
**Delivers:** Predict→realize→score→reflect→propose-diff pipeline; golden-set regression replay + guardrail evals; walk-forward evaluation with a frozen holdout; config/playbook diffs never auto-apply to the money path without passing the gate.
**Addresses:** Continuous-iteration loop requirement (DoorDash-pattern).
**Avoids:** Pitfall 13 (learning-loop overfit/leak/reward-hack).

### Phase 11: Robinhood MCP Live Execution
**Rationale:** Absolute last — hard prerequisite is the paper shakedown proving out on a statistically meaningful sample, plus the official MCP's real tool surface must be probed/verified first (Robinhood does not publish request/response specs).
**Delivers:** Live equities buy/sell behind the inviolable human-approval gate, limit-order discipline (no market orders on illiquid names), fail-safe halt on API breakage, manual-execution fallback documented, PDT enforcement re-verified at go-live time (SEC eliminated the $25k PDT minimum 2026-06-04 but brokers have until 2027-10-20 to implement — don't assume Robinhood has yet).
**Uses:** Official Robinhood Agentic Trading MCP (STACK.md).
**Avoids:** Pitfall 9 (unofficial-API fragility, sidestepped by the official MCP but its collars/halts still apply), Pitfall 12 (PDT regime-change trap), Pitfall 14 (compliance framing — single-user, human-gated, public-data-only).

### Phase Ordering Rationale

- **Data integrity first, always:** a wrong catalyst date is a total-loss pitfall with no downstream mitigation — every other phase implicitly trusts Phase 1's output, so it cannot be revisited later without invalidating everything built on top.
- **Contracts/KB before any agent logic:** the provenance-enforcing write path and JSON schemas are the enforceable boundaries both pipelines and the eval loop depend on (ARCHITECTURE.md explicitly orders this second).
- **Honest risk/sizing is inline with Trade Builder, not a later hardening pass:** Pitfalls 1 and 5 are structural design flaws in PROJECT.md as currently written — fixing them after the fact would mean re-architecting sizing and pair-selection logic that other phases (Diligence, backtest, paper ledger) already assume is correct.
- **Diligence must stay isolated by construction, so it's built as its own phase** after Pipeline 1 is stable, with an explicit input-firewall requirement carried into its phase scope from day one — not bolted on.
- **Execution (real money) is strictly last,** gated behind a statistically meaningful paper result and MCP tool-surface verification — this mirrors PROJECT.md's own "paper-first" constraint and the pitfalls research's strongest warning (a 1-month calendar gate is not the same as a sample-size gate).
- **The iteration loop is deliberately last-but-one:** it needs realized outcomes to exist, and shipping it gated (golden-set replay + guardrails) from the start avoids Pitfall 13 entirely rather than retrofitting safety onto an already-mutating loop.

### Research Flags

Phases likely needing deeper research during planning (`/gsd:research-phase`):
- **Phase 1 (Data Integrity & Catalyst Feed):** PDUFA/AdCom data landscape has no clean free API (STACK.md); needs a spike into which commercial tracker (if any, e.g. BPIQ) is worth the budget vs pure hand-curation.
- **Phase 5 (Trade Builder + Sizing + Risk):** cointegration validation methodology (Engle-Granger/Johansen) and conditional-on-catalyst payoff modeling for pairs is domain-specific quant work with real-money consequences — verify the exact statistical approach before implementation.
- **Phase 11 (Robinhood MCP Live Execution):** exact tool surface, request/response schemas, order types, rate limits, and the connection/OAuth flow into the Claude Agent SDK are all explicitly UNVERIFIED per STACK.md — Robinhood does not publish specs; expect a probing spike that costs a small amount of real money before building against it.

Phases with standard, well-documented patterns (can likely skip deep research-phase):
- **Phase 4 (Analyst Desk + Bull/Bear Debate):** TradingAgents' debate-loop and state-schema patterns are verified from primary sources (repo, paper, docs) — largely a direct port to Claude Code subagents.
- **Phase 9 (iOS Dashboard):** direct reuse of the user's own proven ZeeChat transport pattern — established, not novel.
- **Phase 2 (Contracts + KB Skeleton):** SQLite graph-shaped schema + sqlite-vec is a standard, well-documented pattern at this scale.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Execution path (official RH MCP) and KB substrate correction (Kùzu dead) are HIGH-confidence, source-verified findings. Exact library versions (claude-agent-sdk, sqlite-vec, quantstats) are LOW/unverified — pin at build time. |
| Features | MEDIUM-HIGH | Base rates (BIO/Biomedtracker, Oxford Biostatistics, FDA surrogate-endpoint guidance) are HIGH — peer-reviewed/regulatory sources. Fund operating-cadence and dashboard-KPI research is MEDIUM — documented practice generalized from credible secondary sources, not audited fact. |
| Architecture | MEDIUM-HIGH | Fork-target analysis, debate mechanics, and eval-loop pattern verified against primary sources (repo, paper, docs). The graph-DB landscape correction (Kùzu archived) is a fresh, HIGH-confidence disruption caught in research. |
| Pitfalls | HIGH (finance/domain) / MEDIUM (LLM-specific) | Finance/domain pitfalls (hedge mechanics, stop-loss gapping, PDT rules, base rates) rest on well-established exchange rules and documented real-world catalyst-day price action. LLM-specific mitigations (prompt injection, hallucination, debate independence) are active-research areas with fewer settled patterns. |

**Overall confidence:** MEDIUM-HIGH — high enough to roadmap with confidence on structure and sequencing; several real-money-critical items are explicitly flagged UNVERIFIED and must be resolved before their respective phases ship, not deferred silently.

### Gaps to Address

- **Robinhood MCP exact tool surface + schemas** (order types, read shapes, error semantics) — UNVERIFIED; plan a small-money probing spike as part of Phase 11 before any auto-execution logic is written.
- **Robinhood MCP connection URL + OAuth flow into Claude Agent SDK/CC MCP config** — UNVERIFIED; source directly from Robinhood's support article at build time.
- **PDT rule enforcement timing on the specific agentic account type** (cash vs margin) — the $25k minimum was eliminated by SEC/FINRA 2026-06-04 but brokers have until 2027-10-20 to implement; verify Robinhood's actual enforcement state at go-live, don't assume the headline change applies yet.
- **Rate limits** on the RH MCP and on the FMP tier (Starter = 20GB/30d) for the intended polling cadence — UNVERIFIED.
- **FMP short-interest endpoint availability** on the chosen tier — UNVERIFIED; FINRA bulk files are the confirmed fallback.
- **PDUFA/AdCom data-source budget decision** (pure hand-curation vs a paid tracker like BPIQ) — deferred to Phase 1 planning; no clean free API exists.
- **Exact library versions** (claude-agent-sdk, sqlite-vec, quantstats/empyrical-reloaded, quantstats maintenance status in 2026) — pin at build time, verify quantstats isn't stale before depending on it for the attribution phase.

## Sources

### Primary (HIGH confidence)
- Robinhood — "Now Open to Agents" newsroom + agentic-trading product page — official MCP launch, segregated account, equities-only beta
- ClinicalTrials.gov API v2 (NLM bulletin) — free REST/JSON trial registry
- TauricResearch/TradingAgents repo + arXiv paper 2412.20138 + docs — verified org chart, debate loop, state schema, memory pattern
- BetaKit / 9to5Mac — Kùzu Inc. acquired by Apple (Oct 2025), upstream repo archived
- BIO/Biomedtracker Clinical Development Success Rates 2011-2020; Oxford Biostatistics (oncology transitions) — base-rate PoS figures
- FDA surrogate endpoint resources; ScienceDirect surrogate-endpoint literature — endpoint credibility criteria
- FINRA Regulatory Notice 26-10 / SEC Rule 4210 amendment — PDT $25k minimum elimination and broker implementation deadline
- Robinhood support articles + market-volatility overview PDF — order collars, rejections, halts
- Real 2025-26 binary-event price action (GlycoMimetics, Karyopharm) — documented gap magnitudes

### Secondary (MEDIUM confidence)
- Austin Starks review of RH agentic MCP — observed tool list, no-paper-mode, localhost-only OAuth (single third-party review)
- FMP docs/pricing, Polygon options/IV docs — fundamentals/options data tiers and licensing
- sqlite-vec repo + performance benchmarks — embedded vector search, no-ANN caveat at current scale
- DoorDash engineering blog (Building & Evolving Agents) — eval-loop pattern (fetch was 403; synthesized from search excerpts and overview post)
- Daloopa / Stanford-Addepar / Aurum — hedge-fund investment memo structure, event-driven operating cadence (generalized practice, not audited)
- BiopharmaWatch, RTTNews, Dan Sfera, MarketChameleon — regulatory-event and market-microstructure signals (CRL penalty, AdCom follow-rate, PDUFA run-up)
- Hudson & Thames, Groww, arXiv 2211.07080 — cointegration methodology for pairs trading, including the biotech-specific caveat that correlated peers must be catalyst-clean
- OWASP LLM01:2025, Unit 42, arXiv AutoRedTrader/TradeTrap — prompt injection and LLM hallucination risk in trading agents

### Tertiary (LOW confidence)
- Vela-Engineering/kuzu community fork — unproven longevity, only relevant if multi-hop graph queries ever become necessary
- LadybugDB and other Kùzu-successor forks — early-stage, watch adoption before considering
- Exact claude-agent-sdk / sqlite-vec / quantstats current version numbers — not verified, pin at build time

---
*Research completed: 2026-08-14*
*Ready for roadmap: yes*
