# Roadmap: catalyst-trader

## Overview

Build a real-money, event-driven biotech-catalyst trading desk bottom-up, in strict dependency order so that money-critical foundations are hardened before any agent cleverness runs on top of them. First the ground truth: a two-source-verified catalyst feed and point-in-time universe (a wrong date is a total loss). Then the enforceable boundaries: JSON contracts between agent layers and a provenance-enforcing knowledge base (no claim without a citation). Then deterministic quant tools and a scoring rubric so agents interpret math rather than do it. On that base, Workflow 1 (Catalyst Call) predicts direction, Workflow 2 (Portfolio Construction) builds an honestly-hedged, ruin-avoidant portfolio, and Workflow 3 (Independent Diligence) firewalls a second opinion. A verifier plus mechanical/agentic backtest proves the strategy honestly, a paper ledger provides the true out-of-sample test, and an iOS dashboard puts the human approval gate in the user's pocket. A gated continuous-iteration loop makes the desk measurably better each week, and only then — behind a statistically meaningful paper proof and a real tool-surface probe — does live Robinhood execution get wired in.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Data Integrity & Catalyst Feed** - Two-source-verified catalyst calendar + point-in-time ~20-name universe (nothing downstream trusts an unverified date) (completed 2026-08-14)
- [x] **Phase 2: Contracts + Knowledge-Base Skeleton** - Validated JSON contracts between agent layers + provenance-enforcing SQLite/sqlite-vec KB (completed 2026-08-14)
- [x] **Phase 3: Quant Tool Library + Rubric & Base-Rates** - Deterministic, unit-tested money tools + biotech scoring rubric + clinical base rates (completed 2026-08-15)
- [x] **Phase 4: Analyst Desk + Bull/Bear Debate (Workflow 1a)** - Four sourced analysts + bounded adversarial debate → binary directional verdict (completed 2026-08-15)
- [ ] **Phase 5: Trade Builder, Honest Hedge & Ruin-Avoidant Sizing (Workflow 1b/2)** - Inverse-payoff peer selection, risk-of-ruin sizing, 3-way risk debate, PM promote/kill → StrategyDossier
- [ ] **Phase 6: Independent Diligence Firewall (Workflow 3)** - Input-firewalled adversarial second opinion → GO/NO-GO DiligenceDossier
- [ ] **Phase 6.5: Weekly Strategy Correction** - Sizing amendment (target-within-survival-cap), NO zero-trade weeks, universe-wide weekly thesis engine (catalyst + mean-reversion + continuation, each with a measured edge), weekly build/exit/monitor cadence — reworks Phase-5 sizing before any backtest
- [ ] **Phase 6.7: MD/GP Reconciliation Loop** - GP integrates catalyst-call + portfolio + diligence; bounded iterative re-trigger of Workflow 1 or 2 with DD's missing info until convergence/cap; residual caveats → LP; firewall preserved
- [ ] **Phase 6.8: Weekly Company-Vetting Scanner (Haiku DD-Replica)** - Haiku replica of the diligence workflow vetting each company forward for the week; refreshable week-over-week deltas (company card), monitor-by-exception (deterministic-first, cheap); surfaces volatility opportunities → MD routes to verification → weekly portfolio → intra-week monitor
- [x] **Phase 6.9: Free-Data Ingestion Layer** *(added 2026-08-15, completed 2026-08-16)* - Multi-source free-data pipeline built + wired + shakedown-tested on real data (1002 tests, 100% coverage, ≥2-source cross-check live-proven). Live shakedown found + fixed 3 real bugs; honest result = plumbing works but backtest is vacuous until catalysts are curated (open blocker). Coverage gaps → 6.10.
- [x] **Phase 6.10: Always-On Data Daemon, Coverage Expansion & Quality Monitor** *(added 2026-08-16, completed 2026-08-16)* - Wrap the 6.9 foundation in a constantly-running launchd daemon (stateless run_cycle + gap-detector + self-heal + raw-snapshot lake); add the gap-filler free sources (SEC XBRL fundamentals/float via edgartools, FRED macro/rates/VIX); upgrade price cross-check to N-source median; surface data-health to the monitor. FREE + accuracy-first, $0.
- [ ] **Phase 6.11: EDGAR-8K PDUFA Autopopulation (+ Robinhood data, gated)** *(added 2026-08-16)* - Build our OWN PDUFA/AdCom source from SEC 8-K/PR filings (authoritative, free, provenance-native, tunable) — verifies as a single authoritative source (DATA-03 amendment) → tradeable PDUFA without a paid tracker; + Robinhood pluggable data adapter (quotes/portfolio) design + probe-plan gated on MCP connection
  - **Plans:** 4 plans in 3 waves
    - [x] 06.11-01-PLAN.md — providers/pdufa_edgar.py core: efts CIK-filtered discovery + deterministic regex extraction (no-LLM-dates/cite-or-drop) + single-source "SEC EDGAR" self-verifying Catalyst emit [PDUFA-EDGAR-01/02/03]
    - [x] 06.11-02-PLAN.md — wire pdufa_edgar onto the daemon path (ingest._fetch_catalysts + registry + CADENCE) + verify-synergy integration test [PDUFA-EDGAR-04]
    - [x] 06.11-03-PLAN.md — Robinhood degrade-to-None MCP-tool data adapter (quotes_rt/portfolio) + registry slots + gated 7-step probe-plan doc [RH-DATA-01; RH-DATA-02/03 deferred]
    - [ ] 06.11-04-PLAN.md — operator-directed LIVE verification: real efts + IMNM/CAPR 8-K -> extract->verify->tradeable proof + human-verify gate [PDUFA-EDGAR-04 live-close]
- [ ] **Phase 7: Verifier/Guardrails + Backtest Harness** - Fact-check verifier + runtime monitors + mechanical (Layer A) and guarded-agentic (Layer B) backtests
- [ ] **Phase 8: Paper Ledger, Attribution & Post-Mortem (Layer C)** - Simulated ledger vs live quotes + P&L attribution + post-mortem into the KB
- [ ] **Phase 8.5: Intra-Week Position Monitor** *(BUILD DEFERRED)* - Light/fast Haiku agent group, event-triggered by deterministic monitors (TA thresholds/news), flags positions → routes adjustment back to portfolio builder; no order placement
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
**Plans**: 4 plans (3 waves)
- [x] 02-01-PLAN.md — sqlite-vec + migration 003 (kb_node/kb_edge/kb_vec) + deterministic embedder (Wave 1)
- [x] 02-02-PLAN.md — Six pydantic inter-layer contracts with strict boundary rejection (Wave 1)
- [x] 02-03-PLAN.md — Provenance-enforced atomic KB claim write-path (Wave 2)
- [x] 02-04-PLAN.md — Analog query + hedge sub-store + playbook store (Wave 3)

### Phase 3: Quant Tool Library + Rubric & Base-Rates
**Goal**: Agents never do money arithmetic — they call deterministic, reproducible, exhaustively-tested tools and interpret the output against a concrete rubric.
**Depends on**: Phase 2
**Requirements**: QUANT-01, QUANT-02, QUANT-03, FRAME-01, FRAME-02, FRAME-03, OPS-04
**Success Criteria** (what must be TRUE):
  1. A callable, versioned tool library covers rNPV/pipeline valuation, cash-runway, Kelly/risk-of-ruin sizing, cointegration test, correlation/β, conditional-payoff matrix, options-implied move, IV-crush, Sharpe/returns/attribution, SL/TP levels, and portfolio concentration/exposure
  2. Every tool output records the exact inputs used (reproducible and auditable), and every tool ships with an exhaustive edge-case test suite written before its logic (TDD)
  3. A biotech-adapted scoring rubric (rNPV + cash runway + trial design + endpoint credibility + regulatory precedent + pipeline concentration + management + commercial) exists as tunable config the learning loop can later adjust
  4. A clinical base-rate table (phase-transition LoA by phase/indication, prior-CRL penalty, AdCom follow-through) is loaded and citable by agents as data
**Plans**: 8 plans (3 waves)
- [x] 03-01-PLAN.md — Dependency (statsmodels) + ToolResult reproducibility contract (Wave 1)
- [x] 03-02-PLAN.md — Valuation: rNPV + cash-runway, TDD (Wave 2)
- [x] 03-03-PLAN.md — Sizing: Kelly/fractional-Kelly/risk-of-ruin/SL-TP, TDD (Wave 2)
- [x] 03-04-PLAN.md — Pairs: cointegration (statsmodels) + correlation/β + conditional-payoff, TDD (Wave 2)
- [x] 03-05-PLAN.md — Options (implied-move/IV-crush) + Portfolio (concentration/exposure), TDD (Wave 2)
- [x] 03-06-PLAN.md — Performance: Sharpe/Sortino/returns/attribution (explicit periods_per_year), TDD (Wave 2)
- [x] 03-07-PLAN.md — Rubric (tunable JSON) + clinical base-rate table (cited CSV), TDD (Wave 2)
- [x] 03-08-PLAN.md — Wire import surface + library-wide inputs-snapshot invariant + coverage gate + phase report/TOKEN-NOTES (Wave 3)

### Phase 4: Analyst Desk + Bull/Bear Debate (Workflow 1a)
**Goal**: For a flagged catalyst, produce a binary directional verdict with calibrated confidence and explicit kill criteria — pure prediction, no positioning.
**Depends on**: Phase 3
**Requirements**: CALL-01, CALL-02, CALL-03, CALL-04
**Success Criteria** (what must be TRUE):
  1. Four analyst subagents (Clinical, Regulatory, Financial, Market) each emit a structured, source-cited AnalystSignal
  2. Bull and Bear researchers build opposing cases in real context isolation, and the debate manager runs bounded rounds emitting a DebateVerdict that names the losing side's strongest point
  3. The verdict is binary (positive vs. negative catalyst) with calibrated confidence and explicit falsification/kill criteria, and contains no sizing or positioning
  4. A fact-check verifier enforces source-quote-or-drop on every claim before the verdict is finalized
**Plans**: 7 plans (3 waves)
- [x] 04-01-PLAN.md — Extend DebateVerdict: binary direction + required kill_criteria (CALL-03 contract)
- [x] 04-02-PLAN.md — Async foundation: claude-agent-sdk + run_structured() SDK seam + evidence_ref mint/resolve + fixture harness
- [x] 04-03-PLAN.md — Quant/KB tools as an in-process SDK MCP server (analysts interpret, never compute)
- [x] 04-04-PLAN.md — Analyst layer: 4 dimension prompts + run_analyst → source-cited AnalystSignal (CALL-01)
- [x] 04-05-PLAN.md — Bounded, isolated bull/bear debate + moderator → binary grounded verdict (CALL-02/03)
- [x] 04-06-PLAN.md — Fact-check verifier: deterministic source-quote-or-drop + gated semantic check (CALL-04)
- [x] 04-07-PLAN.md — run_desk orchestrator (concurrent analysts → debate → verifier) + .claude/agents role defs

### Phase 5: Trade Builder, Honest Hedge & Ruin-Avoidant Sizing (Workflow 1b/2)
**Goal**: Turn the week's calls into ONE portfolio whose hedges genuinely offset the binary and whose sizing is built for survival, not a return target.
**Depends on**: Phase 4
**Requirements**: PORT-01, PORT-02, PORT-03, PORT-04, PORT-05, HEDGE-01, HEDGE-02, HEDGE-03, HEDGE-04, HEDGE-05, OPS-01, OPS-02
**Success Criteria** (what must be TRUE):
  1. The Trade Builder selects an inverse-payoff peer (competitor that rises when the target falls, cointegration-validated and catalyst-clean over the hold window), sets entry, the hold-through-vs-exit-before-event decision, and advisory-only SL/TP
  2. The Risk agent re-analyzes each hedge conditional on THIS catalyst and emits a conditional payoff matrix; when no valid inverse peer exists it flags and falls back to size-tiny or exit-before-event — never a fake hedge
  3. A 3-way Risk Committee (aggressive/conservative/neutral) sizes for survival via risk-of-ruin/fractional-Kelly on a -70% downside gap, with the 1% target treated strictly as a measured outcome and zero-trade weeks allowed
  4. Each trade ships a position memo with explicit kill criteria and a documented pre-mortem, authored separately from approval, and the MD/PM promotes/kills against the live book → StrategyDossier stating residual net-long risk and which risk is actually covered
**Plans**: 7 plans (4 waves)
- [x] 05-01-PLAN.md — Contract extensions: Hedge + EstimateVetting + extended TradeProposal/RiskAssessment/StrategyDossier (Wave 1)
- [x] 05-02-PLAN.md — Quant tools: catalyst_move_estimate (events.py) + adaptive_sl_tp_levels, param-driven, TDD (Wave 1)
- [x] 05-03-PLAN.md — KB model-fit param seam: kb.load_params + cited bootstrap fitted_params per catalyst type (Wave 1)
- [x] 05-04-PLAN.md — desk/risk.py: size_for_survival + honest per-catalyst hedge validation + 3-way committee (Wave 2)
- [x] 05-05-PLAN.md — Estimate vetting gate: verifier.enforce_estimate (cite-or-drop + consistency + blocking) (Wave 2)
- [x] 05-06-PLAN.md — desk/builder.py: DebateVerdict → TradeProposal estimated-move construction + vetting (Wave 3)
- [x] 05-07-PLAN.md — desk/portfolio.py select_book + PM/memo/pre-mortem + run_portfolio orchestrator (Wave 4)

### Phase 6: Independent Diligence Firewall (Workflow 3)
**Goal**: A structurally isolated second desk tries to kill the trade from raw sources — a real four-eyes check, not a rubber stamp.
**Depends on**: Phase 5
**Requirements**: DILIG-01, DILIG-02, DILIG-03
**Success Criteria** (what must be TRUE):
  1. The diligence pipeline runs in a separate session receiving only {ticker, catalyst, pair} with adversarial framing — Workflow 1/2 reasoning is provably never passed in
  2. Multi-dimensional DD is performed from raw sources (trial stats/endpoints, regulatory precedent, financials/runway, ownership/flow, options-implied move, hedge/correlation re-validation, liquidity, historical analog)
  3. A synthesizer adversarially combines dimensions, rewards "no-go", and emits a DiligenceDossier {go/no-go, evidence, residual risks} where a single failing money-touching dimension forces NO-GO
**Plans**: 4 plans (4 waves)
- [x] 06-01-PLAN.md — DiligenceInput firewall contract + residual_risks + offline test harness/fixtures (Wave 1)
- [x] 06-02-PLAN.md — 8 adversarial DD dimensions + options degradation + independent hedge re-validation (Wave 2)
- [x] 06-03-PLAN.md — Deterministic NO-GO synthesizer + verdict-immutable narrative + enforce_dossier cite-or-drop (Wave 3)
- [x] 06-04-PLAN.md — run_diligence firewalled orchestrator + end-to-end (Wave 4)

### Phase 6.5: Weekly Strategy Correction
**Goal**: Implement the operator's 2026-08-15 strategy correction so the whole desk runs the way it actually should — before any backtest measures it.
**Depends on**: Phase 5 (sizing/portfolio), Phase 4 (analyst desk, reused by the thesis engine)
**Requirements**: PORT-03 (amended), WEEK-01, WEEK-02, WEEK-03, WEEK-04, WEEK-05
**Success Criteria** (what must be TRUE):
  1. Sizing is a function of BOTH the ~1%/week target AND survivability: `size = clamp(target_implied_size, floor, survival_cap)`, survival is a HARD ceiling never crossed (test-enforced). Reworks Phase-5 `size_for_survival`/`select_book`; keeps the risk-of-ruin cap intact; adds a no-regression test.
  2. NO zero-trade weeks: every week produces a book; a weak-signal week deploys smaller (survival cap), never zero. The old "zero-trade allowed" path is removed/inverted with a test.
  3. Universe-wide weekly thesis engine: a thesis on EVERY name every week — catalyst (reuse Workflow-1), mean-reversion (dropped-last-week → measured bounce edge for THIS name/cohort), continuation/momentum — each with a cited historical base rate, cite-or-drop enforced. Reuses the analyst-desk + KB base-rate machinery; agents interpret, deterministic tools compute the edge.
  4. Weekly build/exit/monitor cadence: a weekly runner builds → (one-week hold) → exit → rebuild; weekly performance recorded vs the 1% goal, feeding the LEARN loop (Phase 10).
**Design (research-backed, `weekly-thesis-engine.md` + `weekly_reversal_check.py`)**: the edges are REAL ONLY WHEN CONDITIONED (Savor 2012, verified: info-moves drift, no-info moves reverse). Measured on our own data (18 biotechs, weekly 2016–2026): −5/−10% drops bounce ~54–55% vs 51.3% base (~+1% edge); −15% weeks = 48.8% negative-median FALLING KNIFE (a hard veto, not a bounce); up-week continuation ~50% (coin flip unconditionally — real only via PEAD/news-drift or high-turnover per Medhat–Schmeling 2022). New surface = ONE module `quant/weekly.py` (3 tools: reversal base-rate, continuation base-rate, deterministic drop-classifier reusing `correlation_beta`), beta-binomial shrinkage mirroring the estimator's `uncertainty_widened` seam, tradeability bar (edge ≥2pts, n≥30, mean >2× cost, CI>0 — honest expectation: only 2–4 cells survive). Statistical legs are SINGLE-LEG (hedge logic stays catalyst-only, reuse Phase-5 size-tiny fallback). **No-zero-trade-weeks reconciled honestly**: never force a failing cell — a weak week is a DEFENSIVE book (SGOV/BIL + tiny XBI anchors) with dossier language stating so. Measurement trap flagged: base-rate window must equal execution window; survivorship bias in the sanity table noted. 7 PM knobs deferred to plan-time (exit anchor, defensive instrument, thresholds, sleeve cap, −15% hard veto, shortlist k, backtest go/no-go) — all with research defaults.
**Plans**: 4 plans (3 waves)
- [x] 06.5-01-PLAN.md — Price-bars store (GATING) + weekly params row (Wave 1)
- [x] 06.5-02-PLAN.md — Sizing target-within-survival-cap + no-zero-trade defensive select_book (Wave 1)
- [x] 06.5-03-PLAN.md — quant/weekly.py thesis engine: classify_drop + weekly_base_rate + thesis_scan (Wave 2)
- [x] 06.5-04-PLAN.md — Weekly runner (run_weekly) + run_portfolio target/defensive threading + WEEK-05 record seam (Wave 3)

### Phase 6.7: MD/GP Reconciliation Loop
**Goal**: Wire the MD/GP as the firm's decision hub — integrate the catalyst call, the portfolio build, and independent diligence, run a bounded iterative reconciliation to converge on a decision, and escalate to the LP only on a genuine blocker.
**Depends on**: Phase 4 (catalyst call / bull-bear debate — re-triggerable), Phase 5 (portfolio builder — re-triggerable), Phase 6 (diligence dossier feeds up)
**Requirements**: RECON-01, RECON-02, RECON-03, RECON-04, RECON-05, RECON-06, RECON-07, RECON-08 (+ WEEK-06 weekly-refresh flag emit)
**Research**: `.planning/research/md-reconciliation-loop.md` (IC/PM process, bounded-loop convergence, decision-packet contents, escalation criteria)
**Success Criteria** (what must be TRUE):
  1. MD authority model: every workflow's output is a PROPOSAL to the MD with a full decision packet attached (catalyst verdict + kill criteria, portfolio + survival/sizing math, DD go/no-go + residual risks, conditional payoff, pre-mortem) so the MD is purely deciding. The MD has final say (test-enforced routing: no trade decision bypasses the MD).
  2. Reconciliation: MD flags a catalyst-call issue → re-triggers Workflow-1 debate carrying the SPECIFIC gap DD surfaced (not the answer; debate re-reasons) → new verdict → portfolio builder. MD flags a portfolio issue → back to Workflow-2 with the missing info → new build → back to DD for a fresh independent pass.
  3. Bounded loop: iterate to convergence (DD clears + no new material issue + MD satisfied) OR a hard round cap; every round logged; no infinite ping-pong (test: cap enforced, convergence exits early).
  4. Firewall preserved: DD's INPUTS stay sealed ({ticker,catalyst,pair}); only DD FINDINGS flow up to the MD and back down as "missing info"; DD re-runs independently each round (test: no Workflow-1/2 artifact reaches DD's input).
  5. Residual caveats after convergence/cap are relayed to the LP in the final dossier; the MD escalates to the LP (→ monitor blocker banner) only on a genuine unresolvable blocker.
**Design (research-backed, `md-reconciliation-loop.md`)**: almost entirely REUSE — new surface = `desk/md.py::reconcile` (~150 lines, orchestrator shape) + 2 contracts (`MDDecision`, `RetriggerFlag` with `extra="forbid"` encoding gap-not-answer in the type system, mirroring `DiligenceInput`) + an `extra_context` param on `debate.run`/`builder.build` (pattern already in `diligence.build_dimension_prompt`) + a deterministic cross-check sheet (no LLM, pre-computes inter-workflow inconsistencies). Loop control: round cap = 3 (PE 2–3-touch norm); re-open only on MATERIAL new info; re-trigger payload = fact + why-material, never the answer; "unmoved with rebuttal" = valid convergence; same-issue-class oscillation → forced PASS; per-round immutable log. "The MD can always PASS" is the de-escalation valve. Decision packet maps onto existing contracts (DebateVerdict/StrategyDossier/RiskAssessment/DiligenceDossier + OPS-01/02 memo+pre-mortem); LP summary GENERATED FROM the decision record. 6 PM-confirmation knobs deferred to plan-time (cap size, oscillation→PASS, refresh scope, MD-vs-pm_decide as two judgment points, enter-at-cap-with-priced-residuals, escalation transport pre-Phase-9) — all have research defaults.
**Plans**: 4 plans (2 waves)
- [x] 06.7-01-PLAN.md — Contracts: RetriggerFlag + WeeklyFlag (gap-not-answer firewalls) + MDDecision + ReconciliationRound (Wave 1)
- [x] 06.7-02-PLAN.md — extra_context re-trigger plumbing on debate.run/builder.build (+ orchestrator pass-through) with byte-for-byte no-regression; DD firewall untouched (Wave 1)
- [x] 06.7-03-PLAN.md — Deterministic no-LLM cross_check consistency sheet across WF-1/2/3 (Wave 1)
- [x] 06.7-04-PLAN.md — reconcile bounded loop + general flag router (act-or-log, mock-tested) + escalation blocker-file + LP summary (Wave 2)

### Phase 6.8: Weekly Company-Vetting Scanner (Haiku DD-Replica)
**Goal**: A cheap, refreshable weekly scan of every universe company — deterministic flaggers surface who's worth a look, then a Haiku analyst does a KB/playbook-backed once-over to find what's of interest THIS coming week to explore and build into the weekly portfolio.
**Depends on**: Phase 6 (DD workflow to replicate), Phase 6.5 (quant/weekly.py + price store + run_weekly), Phase 6.7 (MD router receives the opportunity flags)
**Requirements**: SCAN-01, SCAN-02, SCAN-03, SCAN-04 (+ WEEK-06 qualitative producer)
**Research**: `.planning/research/weekly-company-scanner.md` (Haiku DD-replica structure, week-over-week company card + deltas, low-token monitor-by-exception, opportunity routing)
**Success Criteria** (what must be TRUE):
  1. TWO-STAGE, cheap-first: STAGE 1 = deterministic flaggers built ONLY from data we actually have (bars_asof price/vol, catalyst calendar days-to-event, FMP runway, CBOE IV/expected-move, FINRA short interest, EDGAR filings, quant/weekly.py) — each a computable week-over-week delta vs a persisted company card with a materiality threshold. Most names most weeks = a cheap "no material change" row (monitor-by-exception).
  2. STAGE 2 = on a material flag, a HAIKU analyst does a once-over WITH full KB + playbook access (kb.analog_query + kb.query_playbooks) to determine, for THAT company THIS week, what is of interest, whether it's a real explorable opportunity, and the specific thesis to verify — interpreting (cite-or-drop), never doing arithmetic. Replicates the DD workflow's adversarial + cite-or-drop discipline on Haiku.
  3. REFRESHABLE: a persisted per-company card (the proper volatility/opportunity metrics) is refreshed weekly; the signal is the real DELTA vs last week, comparable and reproducible, not a re-derivation.
  4. LIGHT: deterministic delta layer costs ~nothing; the Haiku pass fires only on flagged names; documented weekly cost estimate; composes with (does not duplicate) quant/weekly.py.
  5. Opportunity flags route UP to the MD (RECON-08) → routed to VERIFICATION (catalyst call / measured edge / mini-backtest — never trusted un-verified) → verified assumptions added to the weekly portfolio (run_weekly) → monitored intra-week (Phase 8.5). Opportunity-flag contract carries the opportunity + evidence + which verification is needed (gap-not-answer).
**Plans**: 3 plans (3 waves)
- [x] 06.8-01-PLAN.md — Foundations: migration 006 company_card/scan_flag store + ScanInput/OpportunityFlag contracts (Wave 1)
- [x] 06.8-02-PLAN.md — Deterministic Stage-1: SCAN_PARAMS + build_card (no-recompute) + delta_card (F1-F13 transitions, latching/hysteresis/tier gate) (Wave 2)
- [x] 06.8-03-PLAN.md — Stage-2 Haiku once-over (one pass, cite-or-drop) + to_weekly_flag routing to the MD (zero md.py change) (Wave 3)

### Phase 6.9: Free-Data Ingestion Layer
**Goal**: Turn the fully-researched free-data sources into actually-built providers/scrapers, wire them to the mocked seams across the desk, and ingest real history — so the backtest, scanner, and monitor run on REAL data, not fixtures.
**Depends on**: Phase 1 (providers/store pattern), Phase 6.5 (price_bar store), Phase 6.8 (company_card), Phase 7 (backtest consumes it)
**Requirements**: INGEST-01, INGEST-02, INGEST-03, INGEST-04, INGEST-05
**Research**: `.planning/research/free-data-sources.md` (all sources verified-live + ToS posture) + `weekly-company-scanner.md` (flag-source map) + `intra-week-monitoring.md` (trigger sources)
**Success Criteria** (what must be TRUE):
  1. Free-data providers are BUILT per research, each behind a uniform provider interface with provenance on every datum (source_url, fetch_ts, source_grade): a MULTI-SOURCE price cascade (Alpha Vantage → Tiingo → yfinance → Nasdaq, ranked/cross-checked, RAW/unadjusted; Stooq registered-but-IP-blocked; FMP 401 on historicals — confirmed), CBOE delayed-quotes options/IV JSON, FINRA short-interest, SEC EDGAR filings, Federal Register + RTTNews PDUFA/AdCom, Nasdaq/CT.gov earnings+trial readouts.
  2. Scraper discipline enforced: rate-limited, cached at >=5-min TTL, ToS-aware (documented posture per source), graceful-degrade when a source is down/illiquid (never fabricate — mark UNVERIFIED/missing).
  3. The mocked seams built in Phases 6.5/6.8/7 (price bars, company card, implied-move, catalyst set) are wired to these real providers behind the SAME interfaces — no downstream contract change.
  4. A historical-ingestion path populates the price_bar + catalyst + company_card stores for the seed universe over ~1-2yr, point-in-time + survivorship-aware.
  5. LIVE SHAKEDOWN (the phase's own verification): ingest the real seed universe, then run Layer-A backtest + thesis_scan on the ingested data end-to-end; every edge case / divergence-from-synthetic is logged and triaged (real data stress-tests every system built so far).
**Plans**: 8 plans (5 waves)
- [x] 06.9-01-PLAN.md — Network foundation: settings (sec_user_agent + alpha_vantage/tiingo keys) + conftest text loader + _http base (cache/rate-limit/retry/UA/degrade) (Wave 1)
- [x] 06.9-02-PLAN.md — Store+price foundation: migration 007 (source_grade+agreeing_sources) + upsert_bars kwargs + shared Friday week_end anchor helper (Wave 1)
- [x] 06.9-03-PLAN.md — Price sources: yfinance+Nasdaq (always-on) + Alpha Vantage+Tiingo (keyed) + disabled Stooq — all RAW, Friday-anchored (Wave 2)
- [x] 06.9-04-PLAN.md — options_cboe (implied-move seam + iv=0 gate) + finra (short interest, settlementDate EQUAL filter) (Wave 2)
- [x] 06.9-05-PLAN.md — edgar (seen_accessions/live_shelf, SEC UA) + pdufa (Federal Register GREEN + RTTNews YELLOW → list[Catalyst]) (Wave 2)
- [x] 06.9-06-PLAN.md — prices.py cascade: PRICE_PROVIDERS registry + get_weekly_bars cross-check/fallback (0.5% tol, divergence log, never impute) (Wave 3)
- [x] 06.9-07-PLAN.md — ingest.py: assemble_raw (the seam) + historical loop (idempotent, point-in-time, survivorship) + seam/historical integration tests (Wave 4)
- [x] 06.9-08-PLAN.md — scripts/shakedown.py LIVE run (INGEST-05) + test_shakedown_offline wiring gate (Wave 5)

### Phase 6.10: Always-On Data Daemon, Coverage Expansion & Quality Monitor
**Goal**: Turn the on-demand 6.9 providers into our own FREE data-gathering pipeline that runs constantly — a warm, always-fresh, self-healing store — and close the two coverage gaps (fundamentals/float, macro regime). Accuracy over speed; $0 forever.
**Depends on**: Phase 6.9 (provider foundation, store write-paths, cascade/cross-check, cache/degrade base)
**Requirements**: PIPE-01, PIPE-02, PIPE-03, PIPE-04, PIPE-05, PIPE-06, PIPE-07, PIPE-08, PIPE-09, PIPE-10
**Research**: `.planning/research/free-data-pipeline.md` (ecosystem survey, proxy verdict, OpenBB adopt-vs-mirror, daemon architecture)
**Success Criteria** (what must be TRUE):
  1. A constantly-running launchd daemon executes a stateless `run_cycle()` on an accuracy-first cadence, appending to a growing historical archive; launchd is the supervisor/crash-recovery, store idempotency is the resumability (re-runs never duplicate).
  2. Self-healing: a gap-detector finds missing name-weeks / stale sources and auto-re-fetches; dead-source detection fails over through the ranked cascade; the cycle resumes cleanly after a crash.
  3. Coverage expansion (the gap-fillers): SEC XBRL fundamentals/float/cash-runway via `edgartools` (MIT, keyless — replaces + upgrades the hand-rolled edgar.py) and FRED macro/rates/VIX (free key, ~20-line httpx provider). Both free, provenance-tagged, degrade-safe.
  4. Accuracy upgrade: the price cross-check moves from 2-source-agree to N-source median/majority-vote with divergence flagged; raw response snapshots are archived (keyed by source/ticker/fetch_ts) for audit + re-parse.
  5. Data-health surfaced to the live monitor (`.monitor/data_health.json` → monitor tab): per-need freshness, staleness, cross-source divergence, source-health; alerts on degradation.
  6. OpenBB is MIRRORED not adopted (AGPL + 50-dep weight); Stooq stays disabled (route-around, no proxies). Whole design stays $0.
**Plans**: 7 plans (4 waves)
- [x] 06.10-01-PLAN.md — edgartools fundamentals/float provider: replace edgar.py (CIK-internal), keep seen_accessions/live_shelf, add cash_runway_months/shares_outstanding (Wave 1)
- [x] 06.10-02-PLAN.md — FRED macro/rates/VIX provider (env-first key, degrade-to-skip) (Wave 1)
- [x] 06.10-03-PLAN.md — raw-snapshot lake in _http (data/raw + re-parse + prune) + get_text json_body transport (Wave 1)
- [x] 06.10-04-PLAN.md — N-source median cross-check + split/bad-tick/stale detectors in prices.py (Wave 1)
- [x] 06.10-05-PLAN.md — coverage fixes: FINRA NDJSON parse + Nasdaq earnings FMP-fallback (Wave 2)
- [x] 06.10-06-PLAN.md — daemon: registry + run_cycle/cadence + detect_gaps/backfill/failover + data_health.json + monitor tab + launchd (Wave 3)
- [ ] 06.10-07-PLAN.md — live --once operator shakedown: >=2-source median live + GREEN-key doc + catalyst debug ($0) (Wave 4)

### Phase 7: Verifier/Guardrails + Backtest Harness
**Goal**: Prove the strategy honestly against history and stand up the runtime safety gates before any capital — real or simulated — is at stake.
**Depends on**: Phase 6.5 (backtest must measure the corrected strategy: weekly cadence, target-within-cap sizing, no-zero-trade, universe-wide theses)
**Requirements**: BACK-01, BACK-02, BACK-03, BACK-04, BACK-05, OPS-03
**Success Criteria** (what must be TRUE):
  1. Runtime monitors/guardrails are active and enforced: catalyst-date freshness, fact-check, provenance, Workflow-3 firewall, net-long/concentration caps, and there is no path from scraped content to an order
  2. A historical event set is built from ~1yr of universe earnings calendars plus dateable biotech catalysts, point-in-time and including delisted names
  3. Layer A mechanical backtest (no LLM) runs deterministic pair selection + sizing + entry + SL/TP + 1-week exit with a pessimistic fill model (far-side + gap-open on held-through events), producing a baseline distribution (win rate, avg win/loss, Sharpe, max DD) and hedge-effectiveness stats
  4. Layer B guarded agentic replay runs the real pipeline with look-ahead guardrails (web blocked/archived, point-in-time fundamentals, outcome-blind prompts) and its results are labeled biased-optimistic
  5. The baseline unlocks config tuning and produces an explicit go/no-go gate before paper trading
**Plans**: 5 plans (3 waves)
- [x] 07-01-PLAN.md — 4 new baseline metrics (max_drawdown/win_rate/avg_win_loss/hedge_effectiveness) in performance.py, TDD (Wave 1)
- [x] 07-02-PLAN.md — Backtest data foundation: synthetic-history fixture + events.py (point-in-time survivorship-free event set, BACK-01) + fill.py (pessimistic gap-open + slippage + data-latency effective_asof, BACK-04) (Wave 1)
- [x] 07-03-PLAN.md — desk/guardrails.py: fail-closed pre-trade runtime gate aggregating the shipped OPS-03 invariants (Wave 1)
- [x] 07-04-PLAN.md — backtest/engine.py: Layer A deterministic weekly loop (NO run_desk) + base-rate direction proxy + baseline distribution, BACK-02 (Wave 2)
- [x] 07-05-PLAN.md — backtest/layerb.py (guarded replay + biased_optimistic label + sample/drop-log, BACK-03) + backtest/gate.py (sample-based go/no-go, BACK-05) (Wave 3)

### Phase 8: Paper Ledger, Attribution & Post-Mortem (Layer C)
**Goal**: Run the full desk forward against live quotes for the true out-of-sample test, and learn from every resolved trade.
**Depends on**: Phase 7
**Requirements**: EXEC-01, EXEC-02, LEARN-03
**Success Criteria** (what must be TRUE):
  1. An internal simulated ledger prices positions against live quotes, tracks P&L per leg, and uses pessimistic fills consistent with the Phase 7 backtest
  2. Each resolved trade produces a P&L attribution decomposing catalyst effect vs. beta drift vs. hedge leg vs. sizing, plus a good-decision/bad-luck post-mortem written into the KB and updating base-rate priors
  3. The go-live gate is sample-based (sufficient catalyst count / statistical significance), never calendar-based
**Plans**: TBD

### Phase 8.5: Intra-Week Position Monitor (BUILD DEFERRED)
**Goal**: A light, fast, event-triggered watchdog on the open book through the week — monitor by exception, defend on genuine trouble, propose adjustments up to the MD. Cheap enough to run all day.
**Depends on**: Phase 8 (paper ledger — live positions to monitor), Phase 6.7 (MD decision hub receives the proposals)
**Requirements**: MON-01, MON-02, MON-03, MON-04, MON-05, MON-06, MON-07, MON-08, MON-09, MON-10
**Research**: `.planning/research/intra-week-monitoring.md` (monitor-by-exception, 8-trigger starter set, position-card, anti-whipsaw, ~$0.70/week on Haiku) + `.planning/research/free-intraday-prices.md` (free 15-min intraday feed — CBOE-already-fetched + yfinance 15m batch, MON-10)
**Operator-locked decisions**: DEFEND-ONLY (trim/exit, MON-06) · react to BOTH technicals+news+risk (MON-07) · triggers + periodic sweeps (MON-08) · every flag is a proposal to the MD (MON-09) · intraday feed = free 15-min, monitor-only, isolated from the weekly store/backtest (MON-10)
**Success Criteria** (what must be TRUE):
  1. A deterministic monitor layer (no LLM) runs the 8-trigger starter set — halts RSS (~60s), ATR-normalized move + stop-proximity + volume spike (5-min), EDGAR filings (10-min), tiered-keyword headlines (15-min), catalyst-date diff + book/heat checks (EOD) — plus a periodic light sweep; fires only on breach (monitor by exception).
  2. On a trigger, a light Haiku-class agent examines the flagged position from a pre-written position-card (~1-2K tokens) and decides hold / trim / exit — DEFEND-ONLY (never add/flip intra-week). Deterministic tools compute; agent interprets; cite-or-drop.
  3. Anti-whipsaw enforced: 2-bar confirmation, ~60-min cooldown, hysteresis re-arm, ≤4 wakes/day/ticker; verified cost profile ~$0.70/week (vs ~$35/week for naive continuous polling).
  4. Any adjustment is a PROPOSAL to the MD with the position-card + evidence attached (MD authority model); on MD approval it routes to the portfolio builder; the monitor never places orders and never bypasses the MD.
  5. BUILD DEFERRED — scoped + researched now; implemented after Phase 8 exists to monitor against.
**Plans**: TBD (planner) — build deferred per operator

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
| 1. Data Integrity & Catalyst Feed | 0/6 | Complete    | 2026-08-14 |
| 2. Contracts + KB Skeleton | 0/TBD | Complete    | 2026-08-14 |
| 3. Quant Tool Library + Rubric & Base-Rates | 0/8 | Complete    | 2026-08-15 |
| 4. Analyst Desk + Bull/Bear Debate | 0/TBD | Complete    | 2026-08-15 |
| 5. Trade Builder, Hedge & Sizing | 0/7 | Not started | - |
| 6. Independent Diligence Firewall | 0/4 | Planned | - |
| 7. Verifier/Guardrails + Backtest Harness | 0/5 | Planned | - |
| 8. Paper Ledger, Attribution & Post-Mortem | 0/TBD | Not started | - |
| 9. iOS Dashboard + Approval Gate | 0/TBD | Not started | - |
| 10. Continuous-Iteration Loop | 0/TBD | Not started | - |
| 11. Robinhood MCP Live Execution | 0/TBD | Not started | - |
