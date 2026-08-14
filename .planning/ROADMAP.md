# Roadmap: catalyst-trader

## Overview

Build a real-money, event-driven biotech-catalyst trading desk bottom-up, in strict dependency order so that money-critical foundations are hardened before any agent cleverness runs on top of them. First the ground truth: a two-source-verified catalyst feed and point-in-time universe (a wrong date is a total loss). Then the enforceable boundaries: JSON contracts between agent layers and a provenance-enforcing knowledge base (no claim without a citation). Then deterministic quant tools and a scoring rubric so agents interpret math rather than do it. On that base, Workflow 1 (Catalyst Call) predicts direction, Workflow 2 (Portfolio Construction) builds an honestly-hedged, ruin-avoidant portfolio, and Workflow 3 (Independent Diligence) firewalls a second opinion. A verifier plus mechanical/agentic backtest proves the strategy honestly, a paper ledger provides the true out-of-sample test, and an iOS dashboard puts the human approval gate in the user's pocket. A gated continuous-iteration loop makes the desk measurably better each week, and only then — behind a statistically meaningful paper proof and a real tool-surface probe — does live Robinhood execution get wired in.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Data Integrity & Catalyst Feed** - Two-source-verified catalyst calendar + point-in-time ~20-name universe (nothing downstream trusts an unverified date)
- [ ] **Phase 2: Contracts + Knowledge-Base Skeleton** - Validated JSON contracts between agent layers + provenance-enforcing SQLite/sqlite-vec KB
- [ ] **Phase 3: Quant Tool Library + Rubric & Base-Rates** - Deterministic, unit-tested money tools + biotech scoring rubric + clinical base rates
- [ ] **Phase 4: Analyst Desk + Bull/Bear Debate (Workflow 1a)** - Four sourced analysts + bounded adversarial debate → binary directional verdict
- [ ] **Phase 5: Trade Builder, Honest Hedge & Ruin-Avoidant Sizing (Workflow 1b/2)** - Inverse-payoff peer selection, risk-of-ruin sizing, 3-way risk debate, PM promote/kill → StrategyDossier
- [ ] **Phase 6: Independent Diligence Firewall (Workflow 3)** - Input-firewalled adversarial second opinion → GO/NO-GO DiligenceDossier
- [ ] **Phase 7: Verifier/Guardrails + Backtest Harness** - Fact-check verifier + runtime monitors + mechanical (Layer A) and guarded-agentic (Layer B) backtests
- [ ] **Phase 8: Paper Ledger, Attribution & Post-Mortem (Layer C)** - Simulated ledger vs live quotes + P&L attribution + post-mortem into the KB
- [ ] **Phase 9: iOS Dashboard + Approval Gate** - SwiftUI two-view dashboard, dossier review, approve/reject gate, chat-to-MD over Tailscale
- [ ] **Phase 10: Continuous-Iteration Loop** - Predict→realize→score→propose-diff, gated behind golden-set regression + walk-forward evals
- [ ] **Phase 11: Robinhood MCP Live Execution** - Live equities behind the human gate, after paper proof + a real tool-surface probe (strictly last)

## Phase Details

### Phase 1: Data Integrity & Catalyst Feed
**Goal**: The system always knows what catalyst is coming, when, and how sure it is — with no date ever originating from an LLM's memory.
**Depends on**: Nothing (first phase)
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06
**Success Criteria** (what must be TRUE):
  1. A rolling catalyst calendar auto-populates from ClinicalTrials.gov v2 + earnings feeds and merges hand-curated PDUFA/AdCom entries for the covered universe
  2. Every catalyst date carries an uncertainty type (firm/window/soft), a two-source verification record, and a `last_verified` stamp; unverifiable dates are flagged and excluded from trading
  3. A catalyst is re-verified within 48h of the event and, when 1–2 days out, triggers Workflow 1
  4. The ~20-name universe is assembled point-in-time from explicit criteria (catalyst density, market cap, liquidity, therapeutic area) and includes delisted names for later backtesting
  5. The user can inject an ad-hoc catalyst (ticker + type + date/window) and it flows through the same verification rules
**Plans**: 6 plans (4 waves)
- [x] 01-01-PLAN.md — Project skeleton, SQLite schema, pydantic models, live fixtures (Wave 1)
- [x] 01-02-PLAN.md — Money-critical date-precision + uncertainty classifier, TDD (Wave 2)
- [x] 01-03-PLAN.md — CT.gov v2 + FMP earnings providers with attached provenance (Wave 3)
- [x] 01-04-PLAN.md — Atomic write-path, two-source verify gate, curated PDUFA loader, ad-hoc CLI (Wave 3)
- [x] 01-05-PLAN.md — Idempotent daily refresh, 48h re-verify, T-2 trigger seam, launchd (Wave 4)
- [x] 01-06-PLAN.md — Point-in-time universe builder + data-curation checkpoint (Wave 4)

### Phase 2: Contracts + Knowledge-Base Skeleton
**Goal**: Every inter-layer message and every stored claim has an enforced shape and a citation — the anti-hallucination spine everything else binds to.
**Depends on**: Phase 1
**Requirements**: KB-01, KB-02, KB-03, KB-04, KB-05
**Success Criteria** (what must be TRUE):
  1. Pydantic-validated JSON schemas exist for AnalystSignal, DebateVerdict, TradeProposal, RiskAssessment, StrategyDossier, and DiligenceDossier, and malformed payloads are rejected at the boundary
  2. A SQLite graph-shaped KB (Company/Drug/Trial/Catalyst/Outcome/Trade/Playbook/EvidenceSource nodes + edges) plus sqlite-vec exists; a claim written without a `:CITES → EvidenceSource` edge is rejected as a schema violation
  3. An analog query returns nearest past scenarios with their outcomes, filtered structurally then ranked semantically
  4. A hedge-relationship sub-store holds, per universe name, candidate inverse-payoff peers with mechanism, payoff-direction sign, and citation
  5. Playbook entries are queryable and surface their confidence
**Plans**: TBD

### Phase 3: Quant Tool Library + Rubric & Base-Rates
**Goal**: Agents never do money arithmetic — they call deterministic, reproducible, exhaustively-tested tools and interpret the output against a concrete rubric.
**Depends on**: Phase 2
**Requirements**: QUANT-01, QUANT-02, QUANT-03, FRAME-01, FRAME-02, FRAME-03, OPS-04
**Success Criteria** (what must be TRUE):
  1. A callable, versioned tool library covers rNPV/pipeline valuation, cash-runway, Kelly/risk-of-ruin sizing, cointegration test, correlation/β, conditional-payoff matrix, options-implied move, IV-crush, Sharpe/returns/attribution, SL/TP levels, and portfolio concentration/exposure
  2. Every tool output records the exact inputs used (reproducible and auditable), and every tool ships with an exhaustive edge-case test suite written before its logic (TDD)
  3. A biotech-adapted scoring rubric (rNPV + cash runway + trial design + endpoint credibility + regulatory precedent + pipeline concentration + management + commercial) exists as tunable config the learning loop can later adjust
  4. A clinical base-rate table (phase-transition LoA by phase/indication, prior-CRL penalty, AdCom follow-through) is loaded and citable by agents as data
**Plans**: TBD

### Phase 4: Analyst Desk + Bull/Bear Debate (Workflow 1a)
**Goal**: For a flagged catalyst, produce a binary directional verdict with calibrated confidence and explicit kill criteria — pure prediction, no positioning.
**Depends on**: Phase 3
**Requirements**: CALL-01, CALL-02, CALL-03, CALL-04
**Success Criteria** (what must be TRUE):
  1. Four analyst subagents (Clinical, Regulatory, Financial, Market) each emit a structured, source-cited AnalystSignal
  2. Bull and Bear researchers build opposing cases in real context isolation, and the debate manager runs bounded rounds emitting a DebateVerdict that names the losing side's strongest point
  3. The verdict is binary (positive vs. negative catalyst) with calibrated confidence and explicit falsification/kill criteria, and contains no sizing or positioning
  4. A fact-check verifier enforces source-quote-or-drop on every claim before the verdict is finalized
**Plans**: TBD

### Phase 5: Trade Builder, Honest Hedge & Ruin-Avoidant Sizing (Workflow 1b/2)
**Goal**: Turn the week's calls into ONE portfolio whose hedges genuinely offset the binary and whose sizing is built for survival, not a return target.
**Depends on**: Phase 4
**Requirements**: PORT-01, PORT-02, PORT-03, PORT-04, PORT-05, HEDGE-01, HEDGE-02, HEDGE-03, HEDGE-04, HEDGE-05, OPS-01, OPS-02
**Success Criteria** (what must be TRUE):
  1. The Trade Builder selects an inverse-payoff peer (competitor that rises when the target falls, cointegration-validated and catalyst-clean over the hold window), sets entry, the hold-through-vs-exit-before-event decision, and advisory-only SL/TP
  2. The Risk agent re-analyzes each hedge conditional on THIS catalyst and emits a conditional payoff matrix; when no valid inverse peer exists it flags and falls back to size-tiny or exit-before-event — never a fake hedge
  3. A 3-way Risk Committee (aggressive/conservative/neutral) sizes for survival via risk-of-ruin/fractional-Kelly on a -70% downside gap, with the 1% target treated strictly as a measured outcome and zero-trade weeks allowed
  4. Each trade ships a position memo with explicit kill criteria and a documented pre-mortem, authored separately from approval, and the MD/PM promotes/kills against the live book → StrategyDossier stating residual net-long risk and which risk is actually covered
**Plans**: TBD

### Phase 6: Independent Diligence Firewall (Workflow 3)
**Goal**: A structurally isolated second desk tries to kill the trade from raw sources — a real four-eyes check, not a rubber stamp.
**Depends on**: Phase 5
**Requirements**: DILIG-01, DILIG-02, DILIG-03
**Success Criteria** (what must be TRUE):
  1. The diligence pipeline runs in a separate session receiving only {ticker, catalyst, pair} with adversarial framing — Workflow 1/2 reasoning is provably never passed in
  2. Multi-dimensional DD is performed from raw sources (trial stats/endpoints, regulatory precedent, financials/runway, ownership/flow, options-implied move, hedge/correlation re-validation, liquidity, historical analog)
  3. A synthesizer adversarially combines dimensions, rewards "no-go", and emits a DiligenceDossier {go/no-go, evidence, residual risks} where a single failing money-touching dimension forces NO-GO
**Plans**: TBD

### Phase 7: Verifier/Guardrails + Backtest Harness
**Goal**: Prove the strategy honestly against history and stand up the runtime safety gates before any capital — real or simulated — is at stake.
**Depends on**: Phase 6
**Requirements**: BACK-01, BACK-02, BACK-03, BACK-04, BACK-05, OPS-03
**Success Criteria** (what must be TRUE):
  1. Runtime monitors/guardrails are active and enforced: catalyst-date freshness, fact-check, provenance, Workflow-3 firewall, net-long/concentration caps, and there is no path from scraped content to an order
  2. A historical event set is built from ~1yr of universe earnings calendars plus dateable biotech catalysts, point-in-time and including delisted names
  3. Layer A mechanical backtest (no LLM) runs deterministic pair selection + sizing + entry + SL/TP + 1-week exit with a pessimistic fill model (far-side + gap-open on held-through events), producing a baseline distribution (win rate, avg win/loss, Sharpe, max DD) and hedge-effectiveness stats
  4. Layer B guarded agentic replay runs the real pipeline with look-ahead guardrails (web blocked/archived, point-in-time fundamentals, outcome-blind prompts) and its results are labeled biased-optimistic
  5. The baseline unlocks config tuning and produces an explicit go/no-go gate before paper trading
**Plans**: TBD

### Phase 8: Paper Ledger, Attribution & Post-Mortem (Layer C)
**Goal**: Run the full desk forward against live quotes for the true out-of-sample test, and learn from every resolved trade.
**Depends on**: Phase 7
**Requirements**: EXEC-01, EXEC-02, LEARN-03
**Success Criteria** (what must be TRUE):
  1. An internal simulated ledger prices positions against live quotes, tracks P&L per leg, and uses pessimistic fills consistent with the Phase 7 backtest
  2. Each resolved trade produces a P&L attribution decomposing catalyst effect vs. beta drift vs. hedge leg vs. sizing, plus a good-decision/bad-luck post-mortem written into the KB and updating base-rate priors
  3. The go-live gate is sample-based (sufficient catalyst count / statistical significance), never calendar-based
**Plans**: TBD

### Phase 9: iOS Dashboard + Approval Gate
**Goal**: The user (LP) can see the week's strategy, interrogate the MD, and approve or reject trades from their phone — the human gate lives here.
**Depends on**: Phase 8
**Requirements**: IOS-01, IOS-02, IOS-03, IOS-04, IOS-05, IOS-06
**Success Criteria** (what must be TRUE):
  1. A This Week page shows expected return vs. the 1% benchmark, per-position thesis + kill criteria, top failure factors + mitigations, advisory SL/TP (never a fictitious bounded loss), Sharpe/expectancy, and catalyst countdown, plus the in-the-moment live P&L for both legs and distance to SL/TP
  2. A Historical Performance page shows the equity curve, per-trade outcomes, win rate, attribution, and prediction-vs-realized calibration; a Playbook page shows the current scenario playbooks/KB state with confidence
  3. The user can review the DiligenceDossier with tappable evidence and approve or reject a trade — the inviolable human gate
  4. The user can chat with the MD (Fable GP) to interrogate positioning, rationale, and risk, over a FastAPI/SSE Tailscale shim reusing the ZeeChat transport pattern
**Plans**: TBD
**UI hint**: yes

### Phase 10: Continuous-Iteration Loop
**Goal**: The desk gets measurably better every week — but can never quietly overfit or reward-hack the money path.
**Depends on**: Phase 9
**Requirements**: LEARN-01, LEARN-02
**Success Criteria** (what must be TRUE):
  1. After each catalyst resolves, prediction-vs-realized is scored by an LLM-judge calibrated to hand-graded labels
  2. The loop proposes playbook/config diffs, and a diff merges to the money path only if it passes a golden-set regression replay plus guardrail/walk-forward evals against a frozen holdout
  3. No config or playbook diff can auto-apply to the live/paper money path without passing the gate
**Plans**: TBD

### Phase 11: Robinhood MCP Live Execution
**Goal**: Execute real equities trades behind the human gate — only after paper proof and a verified tool surface.
**Depends on**: Phase 10
**Requirements**: EXEC-03, EXEC-04
**Success Criteria** (what must be TRUE):
  1. The official Robinhood agentic MCP tool surface is verified via a small real-money probe (order types, read shapes, error semantics, OAuth flow) before any auto-execution logic is written
  2. Live equities buy/sell execute only after explicit LP approval — the human gate is inviolable and there is a fail-safe halt on API breakage plus a documented manual-execution fallback
  3. Orders use limit-order discipline (no market orders on illiquid names) and PDT enforcement state is re-verified against the actual account at go-live
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Integrity & Catalyst Feed | 0/6 | Planned | - |
| 2. Contracts + KB Skeleton | 0/TBD | Not started | - |
| 3. Quant Tool Library + Rubric & Base-Rates | 0/TBD | Not started | - |
| 4. Analyst Desk + Bull/Bear Debate | 0/TBD | Not started | - |
| 5. Trade Builder, Hedge & Sizing | 0/TBD | Not started | - |
| 6. Independent Diligence Firewall | 0/TBD | Not started | - |
| 7. Verifier/Guardrails + Backtest Harness | 0/TBD | Not started | - |
| 8. Paper Ledger, Attribution & Post-Mortem | 0/TBD | Not started | - |
| 9. iOS Dashboard + Approval Gate | 0/TBD | Not started | - |
| 10. Continuous-Iteration Loop | 0/TBD | Not started | - |
| 11. Robinhood MCP Live Execution | 0/TBD | Not started | - |
