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

- [x] **HEDGE-01**: Hedge is an inverse-payoff peer (rises when target falls), typically a direct competitor for the same indication — not a merely-correlated peer
- [x] **HEDGE-02**: Risk agent re-analyzes the hedge relationship before every trade, conditional on THIS catalyst (historical analog gaps + current landscape), producing a conditional payoff matrix
- [x] **HEDGE-03**: Peer must be catalyst-clean over the hold window (no own PDUFA/readout/earnings/M&A)
- [x] **HEDGE-04**: No-valid-inverse-peer fallback: flag and fall back to size-tiny or exit-before-event — never a fake hedge
- [x] **HEDGE-05**: Dossier states residual net-long risk and which risk (idiosyncratic vs. sector) is actually covered

### Workflow 1 — Catalyst Call (CALL)

- [x] **CALL-01**: Four analysts (Clinical, Regulatory, Financial, Market) produce structured, source-cited signals
- [x] **CALL-02**: Bull and Bear researchers build opposing cases in real context isolation
- [x] **CALL-03**: Debate manager runs bounded rounds and emits a binary directional verdict + calibrated confidence + explicit falsification/kill criteria
- [x] **CALL-04**: A fact-check verifier enforces source-quote-or-drop on every claim

### Workflow 2 — Portfolio Construction (PORT)

- [x] **PORT-01**: Takes the week's catalyst calls and builds one recommended portfolio for the week
- [x] **PORT-02**: Trade Builder selects the inverse-hedge peer, entry, hold-vs-exit-before-event decision, SL/TP
- [~] **PORT-03** *(AMENDED 2026-08-15 — needs Phase-5 sizing rework, see WEEK-04)*: 3-way Risk Committee sizes as a function of BOTH the ~1%/week target AND survivability. The target DRIVES the size; the risk-of-ruin cap is a HARD CEILING the size can never cross (`size = clamp(target_implied_size, floor, survival_cap)`). Survival remains the binding constraint when the two conflict — the target never buys past the ruin cap. (Supersedes the original "1% is never a sizing input / survival-only" invariant.)
- [x] **PORT-04**: MD/PM evaluates portfolio fit (concentration, correlation to open book, weekly budget) and promotes/kills
- [x] **PORT-05**: Emits a StrategyDossier for review

### Weekly Cadence & Universe-Wide Theses (WEEK) — added 2026-08-15

- [x] **WEEK-01**: The desk runs on a WEEKLY cycle — build a portfolio, hold ~1 week, exit, rebuild the next week. A fresh portfolio every week; positions are one-week holds by default.
- [x] **WEEK-02**: A thesis runs on EVERY universe name every week, not only names with a catalyst. Thesis TYPES: (a) catalyst (existing Workflow-1), (b) mean-reversion ("dropped last week — is catching the bounce a *proven*, data-backed edge for THIS name?"), (c) continuation/momentum. Each thesis is evidence-backed with a measured historical edge (base rate for that pattern on that name/cohort) — never a hunch; cite-or-drop still holds.
- [x] **WEEK-03**: NO zero-trade weeks. Every week produces a portfolio. The survival cap is the safety valve — a weak-signal week deploys SMALLER (tighter sizing / more cash), never zero. (Supersedes the original "zero-trade weeks are allowed".)
- [x] **WEEK-04**: Sizing serves the ~1%/week target within the survival ceiling (see amended PORT-03). Winrate is fine-tuned week-over-week via the learning loop (LEARN) — the compounding edge is the moat.
- [x] **WEEK-05**: Weekly portfolio performance is monitored adaptively vs. the 1% goal; realized outcomes feed the fine-tuning loop (which thesis types / names / assumptions actually hit, and get reweighted).
- [x] **WEEK-06** *(refinement 2026-08-15)*: The weekly per-name thesis is a REFRESH of the SAME standing analysis every week — repeatable + comparable week-over-week, so the signal is the CHANGE vs the standing baseline, not a bespoke re-derivation. The refresh emits FLAGS when something trips: quantitative (a metric/threshold moves materially vs baseline — the `quant/weekly.py` layer, Phase 6.5) OR qualitative (an analyst notes a material change/concern/opportunity — the Haiku DD-replica company scanner, SCAN group / Phase 6.8). Flags route UP to the MD (monitor-by-exception on the weekly cadence); the MD decides whether to act; unactioned flags are logged, never forced. (Router = RECON-08 / Phase 6.7; qualitative producer = SCAN / Phase 6.8.)

- [x] **DILIG-01**: Runs on the proposed portfolio, receiving only {ticker, catalyst, pair} — an enforced firewall from Workflow 1/2 reasoning
- [x] **DILIG-02**: Multi-dimensional DD from raw sources (trial stats/endpoints, regulatory precedent, financials/runway, ownership/flow, options-implied move, hedge/correlation, liquidity, historical analog)
- [x] **DILIG-03**: Synthesizer adversarially combines dimensions, rewards "no-go", and requires data-backed confidence → DiligenceDossier {go/no-go, evidence, residual risks}

### MD/GP Reconciliation Loop (RECON) — added 2026-08-15

- [x] **RECON-01**: The MD/GP sits above Workflow 1 (catalyst call), Workflow 2 (portfolio) and Workflow 3 (diligence). The DiligenceDossier feeds UP to the GP, who reviews the whole picture (call + portfolio + DD) — the GP is the one integration point that sees all three (this is the SAME head-of-firm persona as the Workflow-2 PM sign-off).
- [x] **RECON-02**: If the GP flags an issue with the CATALYST CALL, he re-triggers the bull/bear debate (Workflow 1) with the specific key info DD surfaced that the debate left out; the re-run RE-REASONS (it is not handed the answer) → new verdict feeds forward into the portfolio builder.
- [x] **RECON-03**: If the GP flags an issue with the PORTFOLIO BUILD, he sends it back to the portfolio builder (Workflow 2) with the key info that was left out; the new build feeds back to DD (Workflow 3) for a fresh independent pass.
- [x] **RECON-04**: The loop is BOUNDED — iterate to a solid/converged outcome (DD clears + GP satisfied + no new material issue) or a HARD iteration cap (no infinite ping-pong). Every round is logged.
- [x] **RECON-05**: Any residual caveats after convergence/cap are relayed to the LP in the final dossier (honest "here's what we're still unsure about").
- [x] **RECON-07** *(MD authority model, 2026-08-15)*: The MD is the DECISION HUB — every workflow (incl. the intra-week monitor) proposes portfolio-impacting decisions UP to the MD, each with all supporting deliverables attached so the MD only decides. The MD escalates to the human/LP if-and-only-if a genuine blocker it can't resolve (rare); that escalation is the monitor's decision-blocker banner. Live real-money order placement retains a final human confirmation as the one safety gate (see PROJECT.md Human gate).
- [x] **RECON-06**: FIREWALL PRESERVED — DD's INPUTS stay sealed ({ticker,catalyst,pair} only, no Workflow-1/2 reasoning in). Only DD's FINDINGS flow up to the GP and back down as "missing info"; DD re-runs independently each round. The firewall is one-directional (bias-in blocked), not a total barrier.
- [x] **RECON-08** *(refinement 2026-08-15)*: The MD is the ROUTER for ALL flags, not only diligence findings — the weekly per-name refresh (WEEK-06) and (later) the intra-week monitor (MON) also emit flags UP to the MD. On a flag the MD decides whether to ACT; if so it routes to the APPROPRIATE team (Workflow 1 catalyst call / Workflow 2 portfolio builder / Workflow 3 diligence) via the same gap-not-answer re-trigger mechanism (RetriggerFlag). Unactioned flags are logged, never forced. Same bounded-loop + escalation machinery as RECON-01..07 — the reconcile input generalizes beyond a single DiligenceDossier to any flag source.

### Intra-Week Position Monitor (MON) — added 2026-08-15 (scoped now, BUILD DEFERRED per operator)

- [ ] **MON-01**: A SEPARATE, lightweight, fast workflow monitors open-position performance throughout the week (distinct from the weekly build/exit cycle).
- [ ] **MON-02**: EVENT-TRIGGERED, not continuous LLM polling — deterministic monitors (technical-indicator thresholds, a news hit on a held name) fire and hand the flagged position to the light agent group for examination.
- [ ] **MON-03**: Light + cheap — runs on lighter models (Haiku-class), can operate many times / on the fly through the day at low cost.
- [ ] **MON-04**: If the group flags that a position needs adjustment, it PROPOSES that adjustment UP to the MD (with all supporting data attached, MD-authority model) → on MD approval routes to the portfolio builder (Workflow 2). It never places orders itself.
- [ ] **MON-05**: BUILD DEFERRED — capability is scoped and roadmapped (Phase 8.5); implemented after the paper ledger (Phase 8) exists to monitor against.

**MON locked decisions (operator, 2026-08-15) + research design (`.planning/research/intra-week-monitoring.md`):**
- [ ] **MON-06 (adjustment power = DEFEND ONLY)**: intra-week the monitor may only REDUCE risk on a flagged position (trim or exit); adding/flipping waits for the next weekly build. (Research default: fixed-fraction trim, e.g. 50%, vs full exit — a build-time knob.)
- [ ] **MON-07 (react to BOTH equally)**: full trigger set — technical/price AND news/fundamentals AND risk-limit breaches. Research starter set (8 monitors): halts RSS (60s), ATR-normalized move + stop-proximity + time-prorated volume spike (5-min), EDGAR filings (10-min), tiered-keyword headlines (15-min), catalyst-date diff + book/heat checks (EOD).
- [ ] **MON-08 (cadence = triggers + periodic sweeps)**: deterministic layer fires on event triggers immediately PLUS a light periodic sweep (~30-60 min) on 5-min data; anti-whipsaw = 2-bar confirmation, 60-min cooldown, hysteresis re-arm, ≤4 wakes/day/ticker. Cost verified ~$0.70/week on Haiku.
- [ ] **MON-09 (decision routing = MD)**: every flag is a PROPOSAL to the MD with the position-card + deliverables; MD decides; MD escalates to LP only on a genuine blocker (per the MD authority model). Live-execution human confirm still applies to real money.

### Weekly Company-Vetting Scanner (SCAN) — added 2026-08-15 (Haiku DD-replica)

- [x] **SCAN-01**: The weekly per-company vetting engine is a HAIKU REPLICA of the diligence workflow (`desk/diligence.py`) — same multi-dimensional adversarial + cite-or-drop structure — run on cheap Haiku models across ALL ~20 names every week. It vets the COMPANY FORWARD for the upcoming week (not a proposed trade); output = trading OPPORTUNITIES arising from possible volatility (catalyst proximity, technical setup, news, unusual flow/vol).
- [x] **SCAN-02**: REFRESHABLE week-over-week — a persisted per-company "card" (the proper volatility/opportunity metrics) is refreshed each week; the SIGNAL is the deterministic DELTA vs last week's card (a real, material change vs baseline), not a re-derivation. Materiality thresholds reuse the intra-week anti-whipsaw thinking.
- [x] **SCAN-03**: LIGHT / not token-heavy — DETERMINISTIC-FIRST: metric deltas computed by tools (no LLM); the Haiku agentic pass wakes ONLY on a name whose deltas cross the materiality bar (monitor-by-exception — most names most weeks are a cheap deterministic "no material change" row). Composes with (does not duplicate) the deterministic `quant/weekly.py`. Escalate beyond Haiku only on genuine ambiguity.
- [x] **SCAN-04**: An opportunity flag routes UP to the MD (RECON-08); the MD routes actionable ones to the appropriate workflow to be VERIFICATION-tested (catalyst call for direction, measured-edge tools, mini-backtest — the scanner's opportunity is NEVER trusted un-verified). Verified assumptions are added to the weekly portfolio (`run_weekly`), then monitored intra-week (Phase 8.5). The opportunity flag carries the opportunity + evidence + which verification is needed (gap-not-answer discipline).

### Free-Data Ingestion Layer (INGEST) — added 2026-08-15

- [ ] **INGEST-01**: Free-data providers BUILT per `free-data-sources.md`, each behind a uniform provider interface with provenance on every datum (source_url, fetch_ts, source_grade): yfinance historical prices (primary — FMP 401s on historicals), CBOE delayed-quotes options/IV JSON, FINRA short-interest, SEC EDGAR filings, Federal Register + RTTNews PDUFA/AdCom, earnings+trial readouts.
- [ ] **INGEST-02**: Scraper discipline — rate-limited, cached at >=5-min TTL, ToS-aware (documented posture per source), graceful-degrade on outage/illiquidity (never fabricate; mark UNVERIFIED/missing).
- [ ] **INGEST-03**: The mocked seams (price bars, company card, implied-move, catalyst set) are wired to the real providers behind the SAME interfaces — zero downstream contract change.
- [ ] **INGEST-04**: Historical-ingestion path populates price_bar + catalyst + company_card stores for the seed universe over ~1-2yr, point-in-time + survivorship-aware.
- [ ] **INGEST-05**: Live shakedown — ingest the real seed universe, run Layer-A backtest + thesis_scan on real data end-to-end; edge cases logged + triaged.

### Backtest / Baseline Harness (BACK)

- [x] **BACK-01**: Historical event set from ~1yr of earnings calendars across the universe + dateable biotech catalysts
- [x] **BACK-02**: Layer A — mechanical strategy backtest (no LLM): deterministic pair selection + sizing + entry + SL/TP + 1-week exit → baseline distribution (win rate, avg win/loss, Sharpe, max DD) + hedge effectiveness
- [x] **BACK-03**: Layer B — guarded agentic replay with look-ahead guardrails (web blocked/archived, point-in-time fundamentals, outcome-blind prompts); results labeled biased-optimistic
- [x] **BACK-04**: Fill model: historical price + tunable slippage haircut; skip only halted/delisted/zero-volume/zero-quote events
- [x] **BACK-05**: Baseline unlocks config tuning + a go/no-go gate before paper trading

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

- [x] **OPS-01**: Position memo per trade with explicit falsification/kill criteria (authorship separated from approval)
- [x] **OPS-02**: Pre-mortem step ("assume this lost — why?") before promotion
- [x] **OPS-03**: Monitors/guardrails: catalyst-date, fact-check, provenance, firewall, net-long/concentration, live-position (SL/TP, countdown, paper P&L)
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
| CALL-02 | Phase 4 | Complete |
| CALL-03 | Phase 4 | Complete |
| CALL-04 | Phase 4 | Complete |
| PORT-01 | Phase 5 | Complete |
| PORT-02 | Phase 5 | Complete |
| PORT-03 | Phase 5 | Complete |
| PORT-04 | Phase 5 | Complete |
| PORT-05 | Phase 5 | Complete |
| HEDGE-01 | Phase 5 | Complete |
| HEDGE-02 | Phase 5 | Complete |
| HEDGE-03 | Phase 5 | Complete |
| HEDGE-04 | Phase 5 | Complete |
| HEDGE-05 | Phase 5 | Complete |
| OPS-01 | Phase 5 | Complete |
| OPS-02 | Phase 5 | Complete |
| DILIG-01 | Phase 6 | Complete |
| DILIG-02 | Phase 6 | Complete |
| DILIG-03 | Phase 6 | Complete |
| BACK-01 | Phase 7 | Complete |
| BACK-02 | Phase 7 | Complete |
| BACK-03 | Phase 7 | Complete |
| BACK-04 | Phase 7 | Complete |
| BACK-05 | Phase 7 | Complete |
| OPS-03 | Phase 7 | Complete |
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
