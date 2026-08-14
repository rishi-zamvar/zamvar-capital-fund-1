# catalyst-trader

## What This Is

An event-driven trading system for a curated universe of ~20 life-science / biotech stocks. 1–2 days before a major catalyst (FDA PDUFA date, clinical-trial readout, conference presentation, earnings), a layered multi-agent research desk (running as Claude Code subagents) analyzes the firm, the drug, and likelihood indicators, debates bull vs. bear, and produces a recommended one-week portfolio: long/long pairs (a target long hedged by a correlated peer long) sized toward a ~1%/week return. Approved candidates pass through a second, independent due-diligence agent framework before going live. An iOS dashboard surfaces curated KPIs and lets the user review the diligence dossier and approve/reject trades, talking directly to the running Claude Code instances. The system learns continuously via a graph knowledge base of scenario playbooks and outcomes.

## Core Value

Given an imminent biotech catalyst, produce a data-backed, portfolio-aware, hedged one-week trade recommendation the user can trust enough to approve — and get measurably better at it every week.

## Requirements

### Validated

(None yet — ship to validate)

### Active

<!-- Hypotheses until shipped and validated. Grouped by area; formalized in REQUIREMENTS.md. -->

**Knowledge & framework**
- [ ] Ingest online descriptions of stock fundamental-analysis frameworks and distill a scoring rubric the agents apply
- [ ] Graph knowledge base storing scenario playbooks + past catalyst outcomes, queryable by analog ("similar situations")
- [ ] Continuous-iteration loop: score each realized outcome vs. prediction, feed back into playbooks + configs (DoorDash-agentic-framework-inspired)

**Universe & catalyst feed**
- [ ] System builds + maintains the ~20-name universe from criteria (catalyst density, market cap, liquidity, therapeutic area)
- [ ] Rolling catalyst calendar (auto: PDUFA / trial readouts / conferences / earnings) + manual ad-hoc catalyst injection
- [ ] Flags catalysts 1–2 days out for the covered universe

**Pipeline 1 — Trade Identifier (layered analyst desk, runs per catalyst)**
- [ ] Analyst layer: Clinical/Scientific, Regulatory, Financial, Market/Sentiment analysts produce structured signal
- [ ] Research/debate layer: Bull vs. Bear researchers debate (adapted from a forked TradingAgents-style GitHub framework)
- [ ] Trade Builder: constructs the concrete long/long pair, entry/exit, stop-loss/take-profit, ~1% sizing
- [ ] Risk Management layer: stresses downside, hedge-correlation validity, liquidity, event-vol
- [ ] Portfolio Manager (MD, final): evaluates the single trade against the whole current portfolio → promote or kill
- [ ] Emits a strategy dossier for review

**Pipeline 2 — Trade Diligence (runs on approved trades)**
- [ ] Independent multi-dimensional DD: trial statistics/endpoints, regulatory precedent, financials/runway, ownership/short interest, options-implied move, pair-correlation validation, liquidity, historical analog from graph KB
- [ ] Produces a data-backed go/no-go before the trade goes live

**Execution**
- [ ] Month 1: internal simulated paper-trading ledger against live quotes, tracking P&L
- [ ] After shakedown: auto-execute equities buy/sell via Robinhood MCP, only after user approval

**iOS dashboard**
- [ ] Curated (not overwhelming) KPI set researched from a trader's POV: this-week expected return, live P&L, Sharpe of current strategy, total return, top failure factors + mitigations, stop-loss/take-profit, per-position status — the 1-week picture AND the in-the-moment picture
- [ ] Review the diligence dossier and approve/reject a trade
- [ ] Chat interface to the running Claude Code agents

### Out of Scope

- Shorting / inverse ETFs — Robinhood constraint; hedging is done via long/long correlated pairs
- Real-money trading before the 1-month paper shakedown proves out — validate first
- Non-biotech / non-life-science tickers — universe is deliberately narrow for edge
- Intraday / HFT — the strategy horizon is one week
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

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Long/long correlated pairs for hedging | Robinhood can't short; a correlated peer long approximates a hedge | — Pending |
| Two separate pipelines (Identifier → Diligence) | Independent DD on approved trades reduces confirmation bias from the identifier | — Pending |
| Graph KB for playbooks + memory | Analog querying ("similar past scenarios") is naturally a graph problem | — Pending |
| Fork an existing debate framework vs. build from scratch | Reuse proven bull/bear debate structure; adapt for memory + biotech | — Pending |
| Internal sim ledger for paper trading | No external paper broker dependency; simplest path to a 1-month shakedown | — Pending |
| Claude Code subagents as the agent runtime | Matches user's existing fleet expertise + native MCP access | — Pending |
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
*Last updated: 2026-08-14 after initialization*
