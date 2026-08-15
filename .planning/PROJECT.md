# Zamvar Capital — Fund 1

<sub>codename: catalyst-trader · repo: zamvar-capital-fund-1</sub>

## What This Is

An event-driven trading system for a curated universe of ~20 life-science / biotech stocks. 1–2 days before a major catalyst (FDA PDUFA date, clinical-trial readout, conference presentation, earnings), a layered multi-agent research desk (running as Claude Code subagents) analyzes the firm, the drug, and likelihood indicators, debates bull vs. bear, and produces a recommended one-week portfolio: long/long pairs (a target long hedged by a correlated peer long) sized toward a ~1%/week return. Approved candidates pass through a second, independent due-diligence agent framework before going live. An iOS dashboard surfaces curated KPIs and lets the user review the diligence dossier and approve/reject trades, talking directly to the running Claude Code instances. The system learns continuously via a graph knowledge base of scenario playbooks and outcomes.

## Core Value

Given an imminent biotech catalyst, produce a data-backed, portfolio-aware, hedged one-week trade recommendation the user can trust enough to approve — and get measurably better at it every week.

## Requirements

### Validated

(None yet — ship to validate)

### Active

<!-- Hypotheses until shipped and validated. Grouped by area; formalized in REQUIREMENTS.md. -->

**Hedging — inverse-payoff peer (the most important part of the bet)**
- [ ] The hedge is a peer that RISES when the target FALLS — typically a direct competitor for the same indication/market (target's failure = competitor's gain). NOT a merely-correlated peer.
- [ ] Hedge-relationship database in the KB: for each universe name, candidate inverse-hedge peers + mechanism (`Company —COMPETES_ON{indication}→ Company`, payoff-direction sign) + citation
- [ ] Risk-management agent RE-ANALYZES the hedge relationship before every trade, during trade building: re-confirm the peer pays off inversely on THIS specific catalyst (historical analog gaps + current competitive landscape), compute the conditional payoff matrix (target ↑/↓ × peer ↑/↓)
- [ ] No-valid-inverse-peer fallback: when no peer reliably rises on the target's decline (e.g. positive-read-through catalysts that lift the whole class), the agent flags it and falls back to size-tiny or exit-before-event — never a fake hedge
- [ ] Upside cost of hedging is accepted as a given (not optimized against) — the objective is reliably capturing ~1%/week of portfolio net of the hedge; size to combined worst-case

**Data ingestion — options-implied move + hard-to-API data (dedicated human-like web-scraper agent)**
- [ ] Options-implied move / IV term-structure IS obtainable — not a dead gap. Sources: Robinhood read endpoints, external options-chain data, and a **dedicated web-scraper agent that interacts as a human** to pull data that has no clean API (PDUFA/AdCom dates, conference schedules, options chains, short interest). Data-layer capability feeding BOTH the Phase-5 move estimator (behind its pluggable `implied_move` source seam) AND Phase-6 diligence (which already needs options-implied move).
- [ ] The estimator/desk NEVER hard-depend on scraped data: the in-house historical-gap distribution is the always-available offline core; scraped options data enriches when present. Build the seam first (Phase 5), the scraper as its own data-layer component.
- [ ] Scraper discipline: rate-limited, ToS-aware, cached at ≥5-min cadence (latency is not critical), provenance-tagged (every scraped datum carries its source URL + fetch timestamp → cite-or-drop holds).
- [ ] **Optimized local store for fast/easy query + pull** — the cache the desk/tools/dashboard read from must be structured for cheap lookups (indexed by ticker + as-of timestamp + catalyst, columnar/append-friendly where it helps time-series pulls), so "get the point-in-time data for ticker X as of date D" is a trivial indexed query, not a scan. Extends the Phase-1 SQLite store; add indices/materialized views over raw provider tables rather than a new DB.
- [ ] **DEFERRED / TODO (user-flagged 2026-08-15):** make the data-gathering path FASTER + MORE DETERMINISTIC later. Current free ~5-min/EOD cadence is acceptable for the week-hold horizon, so this is an optimization pass, not a blocker — revisit after the backtest baseline. Candidates: parallel/async fetchers, a fixed-schedule deterministic pull job, precomputed as-of snapshots.

**Quant tool/skill library (deterministic analysis — agents never do the math)**
- [ ] Any analysis the desk does repeatedly is a deterministic tool/skill the agents call with parameters, then interpret the output — no LLM arithmetic on money-critical numbers
- [ ] Tool set spans: rNPV / pipeline valuation, cash-runway, Kelly / risk-of-ruin position sizing, pair correlation + beta, options-implied move, IV-crush estimate, Sharpe / returns / performance attribution, stop-loss & take-profit levels, portfolio concentration + exposure, phase-transition / catalyst base-rate lookups
- [ ] Each tool is unit-tested and versioned; outputs carry the inputs used (reproducible, auditable)

**Knowledge & framework**
- [ ] Ingest online descriptions of stock fundamental-analysis frameworks and distill a scoring rubric the agents apply
- [ ] Graph knowledge base storing scenario playbooks + past catalyst outcomes, queryable by analog ("similar situations")
- [ ] Continuous-iteration loop: score each realized outcome vs. prediction, feed back into playbooks + configs (DoorDash-agentic-framework-inspired)
- [ ] **Assumptions are the moat, not the models.** The deterministic tools (rNPV, Kelly, implied-move, cointegration) are commodities every desk has — the edge is the ASSUMPTIONS fed into them (P(positive), the analog set, per-catalyst-type gap distributions, drift/vol parameters) and fine-tuning them over time. So assumptions are FIRST-CLASS objects: every estimate records its explicit assumption set (cited, versioned via the KB playbook `confidence` column), and each is CALIBRATED against realized outcomes (Brier score on P(positive); error of estimated-vs-realized gap), with post-trade ATTRIBUTION naming which assumption was wrong on a loss. The LEARN loop refits the assumptions from that calibration signal — that accumulating, calibrated assumption library IS the proprietary moat.

**Universe & catalyst feed**
- [ ] System builds + maintains the ~20-name universe from criteria (catalyst density, market cap, liquidity, therapeutic area)
- [ ] Rolling catalyst calendar (auto: PDUFA / trial readouts / conferences / earnings) + manual ad-hoc catalyst injection
- [ ] Flags catalysts 1–2 days out for the covered universe

**Pipeline 1 — Catalyst Call (binary yes/no + confidence, runs once per catalyst)**
- [ ] Analyst layer (flat fan-out): Clinical/Scientific, Regulatory, Financial, Market/Sentiment analysts produce structured, source-cited signal
- [ ] Bull vs. Bear debate (borrowed TradingAgents pattern: bounded rounds + manager synthesis; real context isolation so it's not fake consensus)
- [ ] Output: a BINARY directional verdict (positive vs. negative catalyst) + calibrated confidence + explicit falsification/kill criteria. Pure prediction — no positioning, no sizing here.

**Pipeline 2 — Portfolio Construction (positioning → the week's portfolio, runs on the set of calls)**
- [ ] Takes all of the week's catalyst calls and builds ONE recommended portfolio for the week
- [ ] Trade Builder: per tradeable call, select the inverse-hedge peer (from the hedge DB), set entry, the hold-through-vs-exit-before-event decision, SL/TP
- [ ] Risk Management (3-way debate: aggressive/conservative/neutral): re-analyze the inverse-hedge relationship per trade + conditional payoff matrix, size for survival / risk-of-ruin (1% is a measured outcome, never a sizing input), liquidity + event-vol
- [ ] Independent diligence firewall: validates from RAW sources (not Pipeline-1's thesis) — trial stats/endpoints, regulatory precedent, financials/runway, ownership/short interest, options-implied move, historical analog from KB — anti-confirmation-bias
- [ ] MD / PM (the GP): portfolio-level fit (concentration, correlation to open book, weekly budget) → promote/kill → emits the week's strategy dossier for LP approval

**Backtest / baseline harness (runs before the paper month)**
- [ ] Historical event set from ~1yr of earnings calendars across the universe (dense, precisely-dated → statistically meaningful N), plus dateable biotech catalysts
- [ ] Layer A — Mechanical strategy backtest (no LLM): apply deterministic pair-selection + ~1% sizing + entry 1–2d pre-event + SL/TP + 1-week exit against historical prices → baseline distribution (win rate, avg win/loss, Sharpe, max DD) and hedge-effectiveness (how often the peer leg offsets the target leg)
- [ ] Layer B — Guarded agentic replay: run the real agent pipeline on historical catalysts with look-ahead guardrails (web blocked/archived-only, point-in-time fundamentals, outcome-blind prompts); score predicted direction+confidence vs realized; results labeled biased-optimistic (LLM memorization leaks)
- [ ] Fill model: fill at historical price around the event with a tunable slippage haircut; skip an event only if halted/delisted/zero-volume/zero-quote (volume caps ignored by design)
- [ ] **Simulate DATA-GATHERING timing + point-in-time availability (user-flagged 2026-08-15):** the backtest must replay only data that would ACTUALLY have been available at decision time given our free-source lag + fetch cadence — no look-ahead on data we couldn't have had live (e.g. delayed options quotes, bi-monthly short interest, EOD calibration). Add a tunable **data-latency knob** alongside the slippage knob so we can stress how stale-data degrades the edge. This keeps the baseline honest about the real free-data pipeline, not an idealized instant feed.
- [ ] Baseline unlocks config tuning (sizing, SL/TP, entry timing) and a go/no-go gate before paper trading

**Execution**
- [ ] Month 1: internal simulated paper-trading ledger against live quotes, tracking P&L — the true out-of-sample test (Layer C)
- [ ] After shakedown: auto-execute equities buy/sell via Robinhood MCP, only after user approval

**iOS dashboard (LP↔GP model — user is the LP; the MD is a Fable agent acting as GP/head of the firm)**
- [ ] **This Week** page — current week's strategy: expected return vs the 1% benchmark, one-line thesis + kill criteria per position, top failure factors + mitigations, SL/TP, Sharpe/expectancy, catalyst countdown; plus the in-the-moment view (live P&L, per-position status for both legs, distance to SL/TP). Curated, not overwhelming.
- [ ] **Historical Performance** page — realized track record: equity curve, per-trade outcomes, win rate, attribution, prediction-vs-realized calibration
- [ ] **Playbook** page — current state of the scenario playbook / knowledge base (what the firm has learned, active playbooks and their confidence)
- [ ] **Chat with the MD** — talk to the Fable "GP" agent that manages all trades: ask why a trade was taken, current positioning, risk, rationale — LP-to-GP interrogation
- [ ] Review the diligence dossier and approve/reject a trade (the human gate)
- [ ] The MD/GP persona is the SAME role as Pipeline-1's final portfolio-manager sign-off — one head-of-firm identity that both gates trades and answers to the LP

### Out of Scope

- Shorting / options / inverse ETFs — Robinhood agentic MCP is equities-only; hedging is done with a long inverse-payoff peer (a competitor that rises when the target falls)
- Real-money trading before the 1-month paper shakedown proves out — validate first
- Non-biotech / non-life-science tickers — universe is deliberately narrow for edge
- Intraday / HFT — the strategy horizon is one week
- Volume / market-impact modeling in the backtest — trading size is small; only zero-volume/zero-liquidity events are excluded (a tunable slippage haircut is kept)
- Fully autonomous trading with no human gate — every live trade requires user approval

## Context

- **Multi-agent orchestration** is the user's home turf (existing Mac↔PC Claude Code fleet, Dispatch bus, ZeeChat iOS bridge). This system runs as Claude Code subagents and leans on that experience.
- **iOS app precedent:** ZeeChat (SwiftUI, Tailscale bridge to Claude Code) is the pattern for the dashboard's transport.
- **Base framework to fork:** an existing bull/bear debate multi-agent trading repo (TradingAgents-style) — research picks the specific one to fork + adapt for continuous adaptation and memory.
- **DoorDash agentic-frameworks paper** is a reference for making the system self-iterating (eval loops, config tuning over time).
- **KPIs must be researched, not invented** — design the dashboard from what a trader actually wants to see, curated to avoid overload.

## Constraints

- **Execution broker**: Robinhood MCP — assumed equities buy/sell + read only (no options/shorting confirmed yet; research to verify the real tool surface). Long/long pairs work within this.
- **Tech stack**: Claude Code subagents for the agent desk; graph KB leaning embedded (Kùzu) over a Neo4j server unless research says otherwise; iOS = SwiftUI over a Tailscale bridge to the Claude Code host.
- **Return target**: ~1% per week, one-week holds — the objective the strategy and sizing optimize toward.
- **Human gate**: no live trade without explicit user approval; DD pipeline is a hard prerequisite to going live.
- **Paper-first**: 1 month simulated before any real capital.
- **Domain risk**: money-touching + biotech binary events — full rigor (research + plan-check + verifier) is on.
- **Simplicity + readability**: production-ready, but the simplest codebase that works — the user must be able to read and understand it end-to-end. Efficient, minimal dependencies, boring over clever. This never comes at the cost of insight quality: simplify the code, not the analysis.
- **Test coverage**: every new module ships with a full test suite (TDD — tests before logic), exhaustive edge cases, especially on money-critical deterministic tools. No new code without tests.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Hedge = inverse-payoff peer (rises when target falls), not a correlated peer | Only a competitor whose stock gains on the target's failure actually hedges an idiosyncratic binary; maintained as a DB, re-validated per trade by the Risk agent; fallback to tiny-size/exit when none exists | — Pending |
| Two separate pipelines (Identifier → Diligence) | Independent DD on approved trades reduces confirmation bias from the identifier | — Pending |
| Graph KB for playbooks + memory | Analog querying ("similar past scenarios") is naturally a graph problem | — Pending |
| Fork an existing debate framework vs. build from scratch | Reuse proven bull/bear debate structure; adapt for memory + biotech | — Pending |
| Internal sim ledger for paper trading | No external paper broker dependency; simplest path to a 1-month shakedown | — Pending |
| Claude Code subagents as the agent runtime | Matches user's existing fleet expertise + native MCP access | — Pending |
| Deterministic analysis as callable tools, not LLM math | Real money — no hallucinated arithmetic; reproducible, testable, auditable financial models | — Pending |
| Backtest = mechanical (trustworthy) + guarded agentic (optimistic) + paper (true OOS) | LLM memorization + web results leak past outcomes; only mechanical stats and the forward paper month are look-ahead-free | — Pending |
| Earnings calendar as primary backtest event set | Dense + precisely dated → large N for a meaningful baseline; drug catalysts layered in where dateable | — Pending |
| iOS-first dashboard | Approve-on-the-go; reuse ZeeChat's Tailscale-to-Claude-Code pattern | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-08-14 after Phase 1 (Data Integrity & Catalyst Feed) — DATA-01..06 validated; verified catalyst feed + point-in-time universe shipped, 179 tests green. Carry-forward: real seed-universe + PDUFA data curation (templates shipped).*
