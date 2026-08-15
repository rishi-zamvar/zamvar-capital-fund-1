# Requirements: catalyst-trader

**Defined:** 2026-08-14
**Core Value:** Given an imminent biotech catalyst, produce a data-backed, portfolio-aware, hedged one-week trade recommendation the user can trust enough to approve — and get measurably better at it every week.

## v1 Requirements

### Data Integrity & Catalyst Feed (DATA)

- [x] **DATA-01**: System maintains a rolling catalyst calendar (PDUFA/AdCom curated, clinical-trial readouts via ClinicalTrials.gov v2, conferences, earnings) for the covered universe
- [x] **DATA-02**: User can inject an ad-hoc catalyst (ticker + type + date/window)
- [x] **DATA-03**: Every catalyst date is verified by a two-source rule and re-verified 48h before the event; unverifiable dates are flagged, never traded
- [x] **DATA-04**: Catalyst dates are typed as point-estimate vs. window, with uncertainty carried downstream
- [x] **DATA-05**: System flags catalysts 1–2 days out and triggers Workflow 1
- [x] **DATA-06**: System assembles + maintains the ~20-name universe from criteria (catalyst density, market cap, liquidity, therapeutic area)

### Knowledge Base (KB)

- [x] **KB-01**: SQLite graph-shaped store + sqlite-vec for playbooks, memory, base rates, analogs
- [x] **KB-02**: Every stored claim carries a citation edge; writes without provenance are rejected
- [x] **KB-03**: Analog query returns nearest past scenarios ("similar situations") with outcomes
- [x] **KB-04**: Hedge-relationship sub-store: per universe name, candidate inverse-hedge peers + mechanism + payoff-direction + citation
- [x] **KB-05**: Playbook entries are readable/queryable and surface their confidence

### Fundamental Framework & Base Rates (FRAME)

- [x] **FRAME-01**: Ingest online descriptions of fundamental-analysis frameworks and distill a concrete scoring rubric (biotech-adapted: rNPV, cash runway, trial design, endpoint credibility, regulatory precedent, pipeline concentration, management, commercial)
- [x] **FRAME-02**: Rubric weights are a tunable config the learning loop can adjust
- [x] **FRAME-03**: Clinical base-rate table (phase-transition LoA by phase/indication, prior-CRL penalty, AdCom follow-through) available to agents as data

### Deterministic Quant Tools (QUANT)

- [x] **QUANT-01**: Callable, unit-tested tool library — agents supply parameters and interpret output; no LLM arithmetic on money-critical numbers
- [x] **QUANT-02**: Tools include rNPV/pipeline valuation, cash-runway, Kelly/risk-of-ruin sizing, cointegration test, correlation/β, conditional-payoff matrix, options-implied move, IV-crush estimate, Sharpe/returns/attribution, SL/TP levels, portfolio concentration/exposure
- [x] **QUANT-03**: Every tool output records the inputs used (reproducible, auditable)

### Hedging (HEDGE)

- [ ] **HEDGE-01**: Hedge is an inverse-payoff peer (rises when target falls), typically a direct competitor for the same indication — not a merely-correlated peer
- [ ] **HEDGE-02**: Risk agent re-analyzes the hedge relationship before every trade, conditional on THIS catalyst (historical analog gaps + current landscape), producing a conditional payoff matrix
- [ ] **HEDGE-03**: Peer must be catalyst-clean over the hold window (no own PDUFA/readout/earnings/M&A)
- [ ] **HEDGE-04**: No-valid-inverse-peer fallback: flag and fall back to size-tiny or exit-before-event — never a fake hedge
- [ ] **HEDGE-05**: Dossier states residual net-long risk and which risk (idiosyncratic vs. sector) is actually covered

### Workflow 1 — Catalyst Call (CALL)

- [x] **CALL-01**: Four analysts (Clinical, Regulatory, Financial, Market) produce structured, source-cited signals
- [ ] **CALL-02**: Bull and Bear researchers build opposing cases in real context isolation
- [x] **CALL-03**: Debate manager runs bounded rounds and emits a binary directional verdict + calibrated confidence + explicit falsification/kill criteria
- [x] **CALL-04**: A fact-check verifier enforces source-quote-or-drop on every claim

### Workflow 2 — Portfolio Construction (PORT)

- [ ] **PORT-01**: Takes the week's catalyst calls and builds one recommended portfolio for the week
- [ ] **PORT-02**: Trade Builder selects the inverse-hedge peer, entry, hold-vs-exit-before-event decision, SL/TP
- [ ] **PORT-03**: 3-way Risk Committee (aggressive/conservative/neutral) sizes for survival via risk-of-ruin; the 1% target is a measured outcome, never a sizing input
- [ ] **PORT-04**: MD/PM evaluates portfolio fit (concentration, correlation to open book, weekly budget) and promotes/kills
- [ ] **PORT-05**: Emits a StrategyDossier for review

### Workflow 3 — Independent Diligence (DILIG)

- [ ] **DILIG-01**: Runs on the proposed portfolio, receiving only {ticker, catalyst, pair} — an enforced firewall from Workflow 1/2 reasoning
- [ ] **DILIG-02**: Multi-dimensional DD from raw sources (trial stats/endpoints, regulatory precedent, financials/runway, ownership/flow, options-implied move, hedge/correlation, liquidity, historical analog)
- [ ] **DILIG-03**: Synthesizer adversarially combines dimensions, rewards "no-go", and requires data-backed confidence → DiligenceDossier {go/no-go, evidence, residual risks}

### Backtest / Baseline Harness (BACK)

- [ ] **BACK-01**: Historical event set from ~1yr of earnings calendars across the universe + dateable biotech catalysts
- [ ] **BACK-02**: Layer A — mechanical strategy backtest (no LLM): deterministic pair selection + sizing + entry + SL/TP + 1-week exit → baseline distribution (win rate, avg win/loss, Sharpe, max DD) + hedge effectiveness
- [ ] **BACK-03**: Layer B — guarded agentic replay with look-ahead guardrails (web blocked/archived, point-in-time fundamentals, outcome-blind prompts); results labeled biased-optimistic
- [ ] **BACK-04**: Fill model: historical price + tunable slippage haircut; skip only halted/delisted/zero-volume/zero-quote events
- [ ] **BACK-05**: Baseline unlocks config tuning + a go/no-go gate before paper trading

### Paper Trading & Execution (EXEC)

- [ ] **EXEC-01**: Internal simulated paper-trading ledger against live quotes, tracking P&L (Layer C — true out-of-sample)
- [ ] **EXEC-02**: Go-live gate is sample-based (sufficient N), not calendar-based
- [ ] **EXEC-03**: Live execution via the official Robinhood agentic MCP (equities), only after LP approval; human gate is inviolable
- [ ] **EXEC-04**: Robinhood MCP tool surface verified via a small real-money probe before auto-execution is wired

### iOS Dashboard (IOS)

- [ ] **IOS-01**: This Week page — expected return vs. 1% benchmark, per-position thesis + kill criteria, top failure factors + mitigations, SL/TP, Sharpe/expectancy, catalyst countdown; plus in-the-moment (live P&L, both legs, distance to SL/TP)
- [ ] **IOS-02**: Historical Performance page — equity curve, per-trade outcomes, win rate, attribution, prediction-vs-realized calibration
- [ ] **IOS-03**: Playbook page — current state of the scenario playbooks/KB with confidence
- [ ] **IOS-04**: Chat with the MD (Fable GP) — LP-to-GP interrogation of positioning, rationale, risk
- [ ] **IOS-05**: Review the diligence dossier and approve/reject a trade (the human gate)
- [ ] **IOS-06**: Transport to the Claude Code host over Tailscale (ZeeChat-style shim)

### Continuous Iteration (LEARN)

- [ ] **LEARN-01**: After each catalyst resolves, score prediction vs. realized and run an LLM-judge calibrated to graded labels
- [ ] **LEARN-02**: Propose playbook/config diffs; merge only if they pass a golden-set regression replay + guardrail evals
- [ ] **LEARN-03**: Post-mortem decomposes P&L (catalyst effect vs. beta drift vs. hedge leg vs. sizing) and updates base-rate priors

### Firm Operating Model & QC (OPS)

- [ ] **OPS-01**: Position memo per trade with explicit falsification/kill criteria (authorship separated from approval)
- [ ] **OPS-02**: Pre-mortem step ("assume this lost — why?") before promotion
- [ ] **OPS-03**: Monitors/guardrails: catalyst-date, fact-check, provenance, firewall, net-long/concentration, live-position (SL/TP, countdown, paper P&L)
- [x] **OPS-04**: Full test coverage (TDD) on all new code; money-critical tools have exhaustive edge-case suites

## v2 Requirements

### Execution & Instruments (EXEC2)

- **EXEC2-01**: Options-based put hedges if/when the Robinhood MCP supports options
- **EXEC2-02**: macOS rich dashboard

## Out of Scope

| Feature | Reason |
|---------|--------|
| Shorting / options / inverse ETFs (v1) | Robinhood agentic MCP is equities-only; hedge via inverse-payoff peer |
| Real-money trading before the 1-month paper shakedown | Validate first; go-live is sample-gated |
| Non-biotech / non-life-science tickers | Universe deliberately narrow for edge |
| Intraday / HFT | Strategy horizon is one week |
| Fully autonomous trading with no human gate | Every live trade requires LP approval |
| Volume / market-impact modeling in backtest | Small size; only zero-liquidity events excluded (slippage knob kept) |
| `robin_stocks` unofficial API | ToS/ban risk on real money; use official agentic MCP |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 1 | Complete |
| DATA-02 | Phase 1 | Complete |
| DATA-03 | Phase 1 | Complete |
| DATA-04 | Phase 1 | Complete |
| DATA-05 | Phase 1 | Complete |
| DATA-06 | Phase 1 | Complete |
| KB-01 | Phase 2 | Complete |
| KB-02 | Phase 2 | Complete |
| KB-03 | Phase 2 | Complete |
| KB-04 | Phase 2 | Complete |
| KB-05 | Phase 2 | Complete |
| QUANT-01 | Phase 3 | Complete |
| QUANT-02 | Phase 3 | Complete |
| QUANT-03 | Phase 3 | Complete |
| FRAME-01 | Phase 3 | Complete |
| FRAME-02 | Phase 3 | Complete |
| FRAME-03 | Phase 3 | Complete |
| OPS-04 | Phase 3 | Complete |
| CALL-01 | Phase 4 | Complete |
| CALL-02 | Phase 4 | Pending |
| CALL-03 | Phase 4 | Complete |
| CALL-04 | Phase 4 | Complete |
| PORT-01 | Phase 5 | Pending |
| PORT-02 | Phase 5 | Pending |
| PORT-03 | Phase 5 | Pending |
| PORT-04 | Phase 5 | Pending |
| PORT-05 | Phase 5 | Pending |
| HEDGE-01 | Phase 5 | Pending |
| HEDGE-02 | Phase 5 | Pending |
| HEDGE-03 | Phase 5 | Pending |
| HEDGE-04 | Phase 5 | Pending |
| HEDGE-05 | Phase 5 | Pending |
| OPS-01 | Phase 5 | Pending |
| OPS-02 | Phase 5 | Pending |
| DILIG-01 | Phase 6 | Pending |
| DILIG-02 | Phase 6 | Pending |
| DILIG-03 | Phase 6 | Pending |
| BACK-01 | Phase 7 | Pending |
| BACK-02 | Phase 7 | Pending |
| BACK-03 | Phase 7 | Pending |
| BACK-04 | Phase 7 | Pending |
| BACK-05 | Phase 7 | Pending |
| OPS-03 | Phase 7 | Pending |
| EXEC-01 | Phase 8 | Pending |
| EXEC-02 | Phase 8 | Pending |
| LEARN-03 | Phase 8 | Pending |
| IOS-01 | Phase 9 | Pending |
| IOS-02 | Phase 9 | Pending |
| IOS-03 | Phase 9 | Pending |
| IOS-04 | Phase 9 | Pending |
| IOS-05 | Phase 9 | Pending |
| IOS-06 | Phase 9 | Pending |
| LEARN-01 | Phase 10 | Pending |
| LEARN-02 | Phase 10 | Pending |
| EXEC-03 | Phase 11 | Pending |
| EXEC-04 | Phase 11 | Pending |

**Coverage:**
- v1 requirements: 56 total
- Mapped to phases: 56
- Unmapped: 0

---
*Requirements defined: 2026-08-14*
*Last updated: 2026-08-14 after roadmap creation (traceability populated)*
