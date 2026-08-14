# Feature Research

**Domain:** Event-driven / biotech-catalyst trading desk (multi-agent Claude Code system + iOS dashboard)
**Researched:** 2026-08-14
**Confidence:** MEDIUM-HIGH (base rates HIGH; fund-operating-cadence MEDIUM — synthesized from credible sources, some is generalized practice not audited fact)

> This document has two halves. **Part A** is the deep domain research the five research questions asked for (operating model, fundamental rubric, edge indicators, dashboard KPIs, hedging) — this is the load-bearing material for requirements. **Part B** is the standard FEATURES categorization (table stakes / differentiators / anti-features / MVP) that the roadmap consumes. Read A to justify B.

---

# PART A — Domain Research

## A1. How a real event-driven desk operates → mapped to agent roles

The user wants the **operating model of a real fund mirrored**. Below is the synthesized model with each element mapped to a system deliverable or agent. Confidence is MEDIUM: the *existence* of these artifacts is well-documented; the exact hourly cadence varies by fund and is partly professional folklore, so treat cadence as a sensible default, not gospel.

### Deliverable cadence around a catalyst

| When | Deliverable | Owner (real fund) | Maps to (this system) | Confidence |
|------|-------------|-------------------|------------------------|------------|
| T-5 to T-2 days | **Pre-catalyst investment memo** — thesis, variant perception, base rate, valuation, catalyst path, **falsification/kill criteria**, risk/reward | Analyst → PM | Analyst layer + Trade Builder output → strategy dossier | MEDIUM |
| T-2 to T-1 days | **Position-sizing memo** — sizing vs. conviction, portfolio fit, correlation to existing book, Kelly/vol-scaled size toward ~1%/wk | PM | Portfolio Manager agent | MEDIUM |
| T-1 day | **Risk report / pre-mortem** — "assume this trade lost, why?"; downside scenarios, liquidity, event-vol, hedge validity | Risk officer | Risk Management layer + explicit pre-mortem step | MEDIUM |
| T-1 day | **IC review / four-eyes sign-off** — independent challenge before capital commits | Investment Committee / CIO | Pipeline 2 (independent Diligence) + human approval gate | MEDIUM |
| Intraday of event | **Morning note / positioning update** | PM / trader | Dashboard "in-the-moment" view + agent chat | MEDIUM |
| T+0 / T+1 (post-event) | **EOD P&L + attribution** — what drove the move, was thesis right for the right reason | PM / risk | Attribution report → graph KB | MEDIUM |
| After close-out | **Post-mortem** — realized vs. predicted, update base rates & playbooks | Analyst + PM | Continuous-iteration loop → graph KB | MEDIUM |

Sources: [Daloopa — hedge fund investment memo](https://daloopa.com/blog/hedge-fund-investment-memo-example), [Stanford/Addepar — investment memos & decision-making](https://longterminvesting.stanford.edu/sites/g/files/sbiybj23856/files/media/file/addepar-investment-memos-and-decision-making.pdf), [Aurum — event-driven hedge fund primer](https://www.aurum.com/wp-content/uploads/Aurum-Insight-Sep-24-Event-driven-hedge-fund-primer.pdf).

### Accountability chain (who is accountable for what)

Real desks run a **linear escalation with independent challenge**:

`Analyst (owns the thesis & data) → PM (owns sizing & portfolio fit & the P&L) → Risk (owns downside/limits, can veto) → IC/CIO (final capital authority)`

The critical property is **separation of authorship from approval** — the person who writes the thesis is not the person who green-lights capital. This is exactly what the PROJECT's two-pipeline design (Identifier → independent Diligence) reproduces, and it's the single most important structural feature to preserve. Maps cleanly:

- **Analyst layer** (Clinical/Regulatory/Financial/Sentiment) = analysts, own the structured signal.
- **Bull/Bear debate** = built-in devil's advocate / red-team (funds explicitly use red teams — [Daloopa](https://daloopa.com/blog/hedge-fund-investment-memo-example)).
- **Trade Builder** = constructs the concrete trade.
- **Risk Management agent** = risk officer with **veto power** (must be a real gate, not advisory).
- **Portfolio Manager agent** = PM, portfolio-level promote/kill.
- **Diligence pipeline (Pipeline 2)** = IC/four-eyes — independent, cannot see the Identifier's reasoning to avoid anchoring.
- **Human approval on iOS** = CIO final sign-off. Non-negotiable per constraints.

### Quality control mechanisms (how funds prevent bad decisions)

Every one of these is documented practice and each maps to a concrete feature:

1. **Position memo with explicit falsification/kill criteria.** The thesis must state *what would prove it wrong* and *what price/data invalidates it* — this is the antidote to confirmation bias and the hook for automated stop logic. (Base-rate/outside-view discipline: [Mauboussin base rates](https://hedgefundalpha.com/education/michael-mauboussin-the-base-rate-book/).)
2. **Pre-mortem** — imagine the trade failed, work backward. Formal debiasing technique. ([Pre-mortem, Wikipedia](https://en.wikipedia.org/wiki/Pre-mortem); [Mauboussin/Morgan Stanley on inversion](https://www.morganstanley.com/articles/behavioral-finance-q-a)).
3. **Red-team / devil's advocate** — a dedicated bear case, structurally required, not optional.
4. **Base-rate anchoring (outside view)** — every thesis must cite the historical base rate (e.g., "Phase III oncology → approval ~57% for large pharma, ~40% broad") before the inside-view narrative.
5. **Checklists / four-eyes review** — standardized DD checklist so nothing is skipped under time pressure.
6. **IC vote** — a decision that requires assent, with the risk gate able to veto.

### Performance attribution & post-mortems (how they learn)

Attribution should decompose the P&L: catalyst-outcome effect vs. market/beta drift vs. the hedge leg vs. sizing. Post-mortem asks the Mauboussin question: *was the process good regardless of outcome?* (good decision / bad luck vs. bad decision / good luck). This feeds the **graph KB continuous-iteration loop** — each realized outcome updates the base-rate priors and the scenario playbooks. Attribution frameworks for event-driven: [Wolf Financial](https://wolf.financial/blog/event-driven-hedge-fund-positioning-alternative-investment), [Aurum primer](https://www.aurum.com/wp-content/uploads/Aurum-Insight-Sep-24-Event-driven-hedge-fund-primer.pdf).

---

## A2. Fundamental-analysis scoring rubric — adapted for clinical-stage biotech

Classic DCF/earnings **do not apply** to pre-revenue biotech. The industry-standard method is **risk-adjusted NPV (rNPV)**: probability-weight projected cash flows at each phase gate, discount at 15–40% (higher = earlier stage), with clinical risk captured in the *probability weights*, not the discount rate. Confidence HIGH — this is explicitly "the gold standard." ([rNPV — Healthcare IB guide](https://ibinterviewquestions.com/guides/healthcare-investment-banking/risk-adjusted-npv-biotech-valuation), [Toptal biotech valuation](https://www.toptal.com/management-consultants/valuation/biotech-valuation), [BiopharmaVantage 2026 guide](https://www.biopharmavantage.com/pharma-biotech-valuation-best-practices)).

Below is a **concrete, applicable scoring rubric** the agents can apply. Weights are a defensible starting point — they are the *tunable config* the continuous-iteration loop should adjust over time; do not treat them as final truth.

| # | Factor | What it measures | How to score (0–10) | Suggested weight | Data source |
|---|--------|------------------|---------------------|------------------|-------------|
| 1 | **Probability of Success (PoS) at the catalyst gate** | Base-rate LoA for this phase × indication, adjusted for biomarker use | Anchor to BIO/Biomedtracker base rate (see A3), adjust ±for trial-specific factors | **20%** | BIO base rates |
| 2 | **Cash runway** | Months of cash at current burn vs. time to catalyst & beyond | 10 if >24mo & funded past readout; 0 if raise needed before catalyst (dilution risk) | **15%** | 10-Q, cash & burn |
| 3 | **Trial design quality** | Randomized/controlled? powered? endpoint pre-specified? realistic effect size? | See A2b checklist | **15%** | Protocol, ClinicalTrials.gov |
| 4 | **Endpoint credibility** | Hard clinical endpoint (OS) vs. surrogate; is surrogate validated (Prentice criteria)? | 10 = validated hard endpoint; low = unvalidated novel surrogate | **12%** | FDA surrogate table, literature |
| 5 | **Regulatory precedent** | Has FDA approved on this endpoint/pathway before? prior CRL? special designations (BTD, Fast Track)? | 10 = clean precedent + designations; penalize prior CRL heavily | **12%** | FDA, prior labels |
| 6 | **Pipeline value / asset concentration** | rNPV of lead vs. diversification; single-asset binary risk | 10 = multiple shots; 0 = one-asset company | **10%** | rNPV model |
| 7 | **Management & sponsor track record** | Prior approvals, prior trial conduct, credibility of guidance | 10 = team with prior approvals; low = first-timers / history of misses | **8%** | Bios, filing history |
| 8 | **Competitive / commercial context** | Market size, competition, standard of care, reimbursement | scaled | **8%** | Market research |

**Composite score = Σ(factor × weight)**, output 0–100, with the PoS factor also surfaced *separately* because it's the single dominant driver of a binary catalyst.

### A2b. Trial-design & endpoint quality mini-checklist (feeds factors 3 & 4)

- Randomized + controlled (vs. single-arm)? Placebo/active comparator?
- Primary endpoint **pre-specified and single** (not fished from many)?
- **Statistically powered** — is the enrolled N adequate for the assumed effect size? Underpowered = red flag.
- Effect size assumption realistic vs. prior art (over-optimistic powering is a classic failure signal)?
- Endpoint = hard clinical (OS, PFS) or **surrogate**? If surrogate, is it FDA-recognized/validated (Prentice: correlated with AND captures the treatment effect on the true outcome)?
- Biomarker-selected population? (raises PoS — see A3).

Sources: [FDA surrogate endpoint resources](https://www.fda.gov/drugs/development-resources/surrogate-endpoint-resources-drug-and-biologic-development), [Surrogate endpoints — ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0895435623003402), [Choosing primary endpoints — ScienceDirect](https://www.sciencedirect.com/science/article/pii/S2451865419302480).

---

## A3. Biotech catalyst edge indicators (objective likelihood signals)

These are the **sourced, objective factors** that separate this system from "vibes." Confidence HIGH on the base rates (peer-reviewed / BIO), MEDIUM on the market-microstructure signals (documented but noisy).

### Base rates — the outside view (HIGH confidence)

| Metric | Value | Source |
|--------|-------|--------|
| Overall LoA from Phase I, all indications (2011–2020) | **7.9%** | [BIO/Biomedtracker 2011–2020](https://www.readkong.com/page/clinical-development-success-rates-and-contributing-factors-6942827) |
| Phase II → Phase III advancement (biggest hurdle) | **28.9%** | BIO 2011–2020 |
| Typical phase PoS (rule-of-thumb) | Ph1 ~10–15%, Ph2 ~25–35%, Ph3 ~50–65%, Filed ~85–90% | [Healthcare IB guide](https://ibinterviewquestions.com/guides/healthcare-investment-banking/risk-adjusted-npv-biotech-valuation) |
| Oncology LoA from Phase I (lowest of all areas) | **~3.4%** | [Oxford Biostatistics](https://academic.oup.com/biostatistics/article/20/2/273/4817524) |
| Large-pharma oncology transitions (1990–2005) | Ph1→2 76.8%, Ph2→3 59.4%, Ph3→appr 57.1% | Oxford Biostatistics |
| **Biomarker-selected programs** | Higher success at *every* phase | BIO 2011–2020 |
| Success rates 2014–2023 vs. prior | **Falling** | [Citeline](https://insights.citeline.com/IV154612/Why-Are-Clinical-Development-Success-Rates-Falling/) |

### Regulatory-event signals (HIGH/MEDIUM)

| Signal | Predictive value | Source |
|--------|------------------|--------|
| **Prior CRL on the asset** | Reduces approval probability by **~28%** | [BiopharmaWatch](https://www.biopharmawatch.com/blog/biotech-catalyst-trading-hedge-funds-insiders-fda-decisions) |
| **Positive AdCom vote** | FDA follows AdCom majority of the time; ~90% of AdCom-supported applications approved | [RTTNews](https://www.rttnews.com/amp/3670522/fda-advisory-committee-meetings-how-they-work-and-why-biotech-stocks-move.aspx) |
| Special designations (BTD, Fast Track, Priority Review) | Signal FDA engagement / unmet need | FDA |

### Market-microstructure signals (MEDIUM — noisy, corroborating not deciding)

| Signal | What it tells you | Caveat | Source |
|--------|-------------------|--------|--------|
| **Options implied move** | Market's expected % move on the event; compare to historical actual moves to spot over/underpricing | The market's own base rate — use as a sanity check on our PoS, not as ground truth | [MarketChameleon](https://marketchameleon.com/Reports/biotech-stock-catalysts), [Merlintrader](https://www.merlintrader.com/) |
| **Unusual options activity** (call buying pre-PDUFA) | Possible informed positioning | "Not foolproof — informed traders are wrong regularly" | [BiopharmaWatch](https://www.biopharmawatch.com/blog/biotech-catalyst-trading-hedge-funds-insiders-fda-decisions) |
| **Insider transactions** (Form 4, 2-day reporting) | Real-time view of insider conviction | Buys more informative than sells | BiopharmaWatch |
| **Short interest** | Bearish positioning / squeeze potential | High SI = crowded, cuts both ways | Benzinga |
| **PDUFA run-up** | Stocks tend to rise **20–40%** in the 4–8 wks pre-decision | Creates a "sell-the-news" risk our 1-wk hold must respect | [Dan Sfera](https://dansfera.com/pdufa-explained), [Merlintrader](https://www.merlintrader.com/runup-biotech-26/) |
| Single-day catalyst move magnitude | **40–200%+** either direction | This is why hedging + sizing discipline is existential | [BiopharmaWatch](https://www.biopharmawatch.com/blog/how-to-invest-in-biotech-stocks-beginners-guide-fda-approvals-clinical-trials-pdufa-dates) |

**Implication for the system:** the edge is *combining* the base rate (outside view) with the trial-specific and market-microstructure signals, and being explicit when they disagree. A single-asset Phase III oncology name with a prior CRL and no AdCom support is a base-rate death sentence regardless of the narrative.

---

## A4. iOS dashboard KPIs (curated, from a trader's POV)

Guiding principle from the research: a dashboard should **answer one question in ~10 seconds** and not overwhelm. Split into two views the user explicitly wants — the **1-week strategy picture** and the **in-the-moment picture**. Confidence MEDIUM (KPIs synthesized from trading-dashboard best-practice sources; adapted to this event-driven horizon). Sources: [TradeZella — 8 KPIs that matter](https://www.tradezella.com/blog/trading-dashboard), [tradewiththepros — performance metrics](https://tradewiththepros.com/trading-performance-metrics/), [JournalPlus](https://journalplus.co/learn/guides/trading-performance-dashboard-guide/).

### View 1 — The 1-week strategy picture (per approved trade / book)

The **handful that matter**:
1. **Expected return this week** vs. the ~1% target (the objective).
2. **Position thesis, one line** + the **falsification/kill criteria** (why we're in, what kills it).
3. **Top 2–3 failure factors + mitigations** (from the pre-mortem).
4. **Stop-loss / take-profit levels** and the reward:risk ratio.
5. **Sharpe of current strategy / expectancy** (risk-adjusted, not raw return).
6. **Catalyst date + type** (what event, when).

### View 2 — The in-the-moment picture (live)

1. **Live P&L** (today + open-position unrealized).
2. **Per-position status** (target leg + hedge leg, both).
3. **Distance to SL / TP** (how close to either boundary — the single most-glanced number intraday).
4. **Catalyst countdown** (time to event).
5. **Total return / equity curve** (am I improving, flat, or worse — the 10-second question).

**Anti-KPI note:** do NOT surface win-rate-by-time-of-day, trade frequency, commissions, or the full 8-metric journal grid — those are for a day-trader reviewing a high-frequency journal, not a 1-week event-driven approver. Curate ruthlessly.

---

## A5. Hedging via long/long correlated pairs (the hard constraint)

Robinhood MCP is long-only (no shorting), so the "hedge" is a **second long in a correlated peer**. This is a genuine approximation and must be treated honestly — it is NOT a true market-neutral hedge. Confidence: HIGH on the cointegration methodology; the long/long *reframing* is a real limitation to flag.

**What a valid correlated peer hedge requires:**
- **Cointegration, not just correlation.** Correlation is a short-term return relationship; cointegration is a long-term *price* equilibrium whose spread mean-reverts. Cointegration is the property that makes pair relationships tradeable. ([Hudson & Thames](https://hudsonthames.org/an-introduction-to-cointegration/), [Groww](https://groww.in/blog/pair-trading-strategy)).
- **Validation tests:** Engle-Granger and/or Johansen to confirm cointegration and get the hedge ratio (beta). ([arXiv pairs-trading](https://arxiv.org/pdf/2211.07080)).
- **Sector/idiosyncratic-risk logic:** the peer long neutralizes *sector/market* moves (rate cycles, sector sentiment) but does NOT neutralize the *idiosyncratic catalyst* — which is intentional; the catalyst is our alpha. The hedge is meant to strip out the beta you're not paid to take.

**The critical caveat the sources flag directly:** in biotech, **peers can diverge violently on single-name M&A or their own FDA events** — "close pairs in high-M&A sectors (biotech) should be closed before earnings/rumor periods." So the hedge peer must itself be **catalyst-clean** over the hold window (no PDUFA/readout/earnings of its own). Validating that the hedge leg has no competing catalyst is a first-class DD step. ([Groww pairs-trading](https://groww.in/blog/pair-trading-strategy)).

**Honest framing for requirements:** long/long with a catalyst-clean cointegrated peer reduces sector beta and dampens drawdown, but two longs are still net long — a sector-wide crash hurts both. This bounds how much "hedge" is really being bought and should be stated in the dossier, not oversold.

---

# PART B — Feature Categorization (for roadmap)

## Feature Landscape

### Table Stakes (must-have to be a credible desk)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Catalyst calendar (auto PDUFA/readout/conference/earnings + manual injection) | No catalyst feed = no system | MEDIUM | Aggregate free calendars (RTTNews, BiopharmaWatch); manual override for ad-hoc |
| ~20-name curated universe builder | Edge comes from narrow, deep coverage | MEDIUM | Criteria: catalyst density, mkt cap, liquidity, therapeutic area |
| Layered analyst desk (Clinical/Reg/Financial/Sentiment) | Mirrors real fund analyst layer | HIGH | Core of Pipeline 1 |
| Bull/Bear debate (red-team built in) | Structural devil's advocate = QC | MEDIUM | Fork TradingAgents-style repo |
| **Fundamental scoring rubric (rNPV + A2 factors)** | The objective, sourced core; anti-vibes | HIGH | Priority. Weights = tunable config |
| **Base-rate anchoring on every thesis** | Outside view is the #1 debiaser; sourced | LOW-MED | Cite BIO LoA per phase/indication |
| Position memo w/ **explicit falsification/kill criteria** | Real funds require it; hooks stop logic | LOW | Text + machine-readable SL/TP triggers |
| Pre-mortem step | Documented debiasing technique | LOW | One agent pass, imagine failure |
| Independent Diligence pipeline (four-eyes, no anchoring) | Separation of authorship from approval | HIGH | Pipeline 2; must not see Pipeline 1 reasoning |
| Risk agent with **real veto** | Risk officer accountability | MEDIUM | A gate, not advisory |
| Trade Builder (long/long pair, entry/exit, SL/TP, ~1% size) | The actual deliverable | MEDIUM | Sizing toward 1%/wk target |
| **Cointegration-validated hedge peer + catalyst-clean check** | A valid pair must be cointegrated & event-free | MEDIUM | Engle-Granger/Johansen; verify peer has no own catalyst |
| Human approval gate (iOS) | Hard constraint; CIO sign-off | LOW | No live trade without it |
| Paper-trading sim ledger vs. live quotes (Month 1) | Validate before real money | MEDIUM | Internal ledger, no external broker |
| iOS dashboard — 2 views (1-week + in-the-moment) w/ curated KPIs | The user's window into the desk | MEDIUM | See A4; curate ruthlessly |
| Post-trade attribution + post-mortem | How funds learn; feeds KB | MEDIUM | Realized vs. predicted, good/bad decision framing |

### Differentiators (competitive advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Graph KB of scenario playbooks + outcomes, queryable by analog** | "Similar past situations" = compounding edge; naturally a graph | HIGH | Kùzu embedded per PROJECT |
| **Continuous-iteration loop** (score outcome vs. prediction → tune rubric weights & playbooks) | System gets measurably better weekly; the core value | HIGH | DoorDash-agentic eval-loop inspired |
| Options-implied-move sanity check vs. our PoS | Cross-check our model against the market's own base rate | MEDIUM | Flag when we disagree with the tape |
| Insider (Form 4) + short-interest + unusual-options corroboration | Objective microstructure signals layered on base rate | MEDIUM | Corroborating, weighted low (noisy) |
| Chat directly to running agents from iOS | Interrogate the reasoning, not just read a verdict | MEDIUM | Reuse ZeeChat Tailscale bridge |
| Portfolio-aware promote/kill (PM agent evaluates trade vs. whole book) | Real PM behavior; avoids correlated stacking | MEDIUM | Correlation to existing positions |
| Prior-CRL / AdCom-history flags baked into scoring | Sourced, high-signal regulatory factors | LOW-MED | ~28% CRL penalty, AdCom follow-rate |

### Anti-Features (deliberately NOT build)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Shorting / inverse ETFs / options | "Proper" hedging | Robinhood constraint; also adds unbounded-loss + assignment complexity on binary events | Long/long cointegrated pairs (A5) |
| Fully autonomous live trading | "Let it run" | Binary biotech = 40–200% single-day moves; real money | Hard human approval gate every live trade |
| Intraday / HFT signals | More activity = more edge (myth) | Strategy horizon is 1 week; adds infra + noise | 1-week holds only |
| Kitchen-sink dashboard (all 8+ journal KPIs) | "See everything" | Overwhelms; violates the 10-second rule | Curated 2-view KPI set (A4) |
| DCF / P/E on pre-revenue biotech | Standard equity valuation | Meaningless with no earnings; false precision | rNPV (A2) |
| Non-biotech tickers | Broader universe | Dilutes the domain edge that justifies the whole thesis | Narrow ~20-name life-science universe |
| Trusting a single narrative / "story" pick | Compelling stories sell | Inside-view bias; ignores base rates | Mandatory base-rate anchor + bear case |
| Neo4j server for the KB | "Real" graph DB | Ops overhead for a single-user system | Embedded Kùzu (per PROJECT) |
| Treating long/long as a true hedge in reporting | Sounds safe | Two longs are net long; oversells protection | State residual net-long risk in dossier |

## Feature Dependencies

```
Catalyst calendar + Universe builder
    └──requires──> Analyst desk (Pipeline 1)
                       └──requires──> Fundamental rubric (rNPV + A2) + Base rates (A3)
                       └──requires──> Bull/Bear debate + Pre-mortem
                           └──requires──> Trade Builder (pair + SL/TP + sizing)
                               └──requires──> Cointegration hedge validation + catalyst-clean check
                                   └──requires──> Risk agent (veto)
                                       └──requires──> Portfolio Manager (portfolio-aware)
                                           └──requires──> Diligence pipeline (Pipeline 2, independent)
                                               └──requires──> iOS approval gate
                                                   └──requires──> Paper sim ledger (Month 1)
                                                       └──requires──> Attribution + post-mortem
                                                           └──enhances──> Graph KB
                                                               └──enhances──> Continuous-iteration loop
                                                                   └──feeds back into──> Fundamental rubric weights

Graph KB ──enhances──> Analyst desk (analog retrieval)
Diligence pipeline ──conflicts──> sharing Pipeline 1 reasoning (must stay independent to avoid anchoring)
```

### Dependency Notes

- **Rubric + base rates before the desk:** analysts need the scoring framework and base-rate priors to produce structured signal. Build A2/A3 early.
- **Hedge validation before Risk:** the Risk agent can't assess hedge validity until the cointegration + catalyst-clean check exists.
- **Graph KB is an enhancer, not a blocker:** the desk works without it; the KB makes it *compound*. Ship the desk, then the KB, then the iteration loop.
- **Diligence MUST stay independent:** if Pipeline 2 sees Pipeline 1's reasoning, the four-eyes value collapses into anchoring. Enforce isolation.

## MVP Definition

### Launch With (v1) — the credible paper desk
- [ ] Catalyst calendar + ~20-name universe — no input, no system
- [ ] Analyst desk + Bull/Bear debate — the core reasoning engine
- [ ] Fundamental rubric (rNPV + A2) + base-rate anchoring — the objective spine
- [ ] Position memo w/ falsification criteria + pre-mortem — QC
- [ ] Trade Builder + cointegration hedge validation + catalyst-clean check — the deliverable
- [ ] Risk agent (veto) + Portfolio Manager — accountability chain
- [ ] Independent Diligence pipeline — four-eyes
- [ ] iOS dashboard (2 curated views) + approval gate + agent chat — the user's window
- [ ] Paper sim ledger vs. live quotes — validate before real money
- [ ] Attribution + post-mortem — closes the loop

### Add After Validation (v1.x)
- [ ] Graph KB analog retrieval — trigger: enough logged outcomes to query (~dozens of trades)
- [ ] Continuous-iteration weight-tuning loop — trigger: KB populated + attribution proving/disproving weights
- [ ] Microstructure corroboration (Form 4 / short interest / unusual options) — trigger: base desk trusted
- [ ] Robinhood MCP auto-execute (post human approval) — trigger: 1-month paper shakedown passes

### Future Consideration (v2+)
- [ ] Options-implied-move model as a second independent PoS estimator — defer until base model validated
- [ ] Multi-catalyst / multi-position portfolio optimization — defer until single-trade flow proven

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Fundamental rubric (rNPV + A2) + base rates | HIGH | MEDIUM | P1 |
| Analyst desk + Bull/Bear debate | HIGH | HIGH | P1 |
| Position memo + falsification + pre-mortem | HIGH | LOW | P1 |
| Cointegration hedge validation + catalyst-clean | HIGH | MEDIUM | P1 |
| Risk veto + PM portfolio-aware gate | HIGH | MEDIUM | P1 |
| Independent Diligence pipeline | HIGH | HIGH | P1 |
| iOS 2-view dashboard + approval gate | HIGH | MEDIUM | P1 |
| Paper sim ledger + attribution/post-mortem | HIGH | MEDIUM | P1 |
| Graph KB analog retrieval | HIGH | HIGH | P2 |
| Continuous-iteration weight-tuning | HIGH | HIGH | P2 |
| Microstructure corroboration signals | MEDIUM | MEDIUM | P2 |
| Robinhood auto-execute | MEDIUM | MEDIUM | P2 |
| Options-implied-move PoS model | MEDIUM | HIGH | P3 |

## Competitor / Reference Analysis

| Feature | Retail biotech tools (BiopharmaWatch, Merlintrader) | Real event-driven fund | Our approach |
|---------|------------------------------------------------------|------------------------|--------------|
| Catalyst calendar | Yes (their core) | Internal | Reuse public feeds + manual injection |
| Base rates | Rarely surfaced | Core to IC | First-class, cited, per phase/indication |
| Falsification/kill criteria | No | Standard in memos | Mandatory, machine-readable → SL |
| Independent DD / four-eyes | No | Yes (IC) | Pipeline 2, isolated |
| Learning loop | No | Post-mortems, informal | Graph KB + automated weight tuning |
| Hedging | Options (retail) | Long/short | Long/long cointegrated (constraint) |

## Sources

- [BIO/Biomedtracker — Clinical Development Success Rates 2011–2020](https://www.readkong.com/page/clinical-development-success-rates-and-contributing-factors-6942827) — base rates (HIGH)
- [Oxford Biostatistics — Estimation of clinical trial success rates](https://academic.oup.com/biostatistics/article/20/2/273/4817524) — oncology transitions (HIGH)
- [Citeline — Why success rates are falling](https://insights.citeline.com/IV154612/Why-Are-Clinical-Development-Success-Rates-Falling/) (HIGH)
- [rNPV — Healthcare IB guide](https://ibinterviewquestions.com/guides/healthcare-investment-banking/risk-adjusted-npv-biotech-valuation) — valuation method (HIGH)
- [Toptal — Biotech valuation best practices](https://www.toptal.com/management-consultants/valuation/biotech-valuation) (HIGH)
- [BiopharmaVantage — 2026 pharma/biotech valuation guide](https://www.biopharmavantage.com/pharma-biotech-valuation-best-practices) (MEDIUM)
- [FDA — Surrogate endpoint resources](https://www.fda.gov/drugs/development-resources/surrogate-endpoint-resources-drug-and-biologic-development) (HIGH)
- [Surrogate endpoints — ScienceDirect](https://www.sciencedirect.com/science/article/pii/S0895435623003402) (HIGH)
- [BiopharmaWatch — hedge funds & insiders around FDA decisions](https://www.biopharmawatch.com/blog/biotech-catalyst-trading-hedge-funds-insiders-fda-decisions) — CRL penalty, insider/options (MEDIUM)
- [RTTNews — FDA AdCom meetings & stock moves](https://www.rttnews.com/amp/3670522/fda-advisory-committee-meetings-how-they-work-and-why-biotech-stocks-move.aspx) — AdCom follow-rate (MEDIUM)
- [Dan Sfera — PDUFA explained / run-up](https://dansfera.com/pdufa-explained) (MEDIUM)
- [MarketChameleon — biotech catalysts / implied move](https://marketchameleon.com/Reports/biotech-stock-catalysts) (MEDIUM)
- [Aurum — Event-driven hedge fund primer](https://www.aurum.com/wp-content/uploads/Aurum-Insight-Sep-24-Event-driven-hedge-fund-primer.pdf) — operating model, attribution (MEDIUM)
- [Wolf Financial — event-driven positioning](https://wolf.financial/blog/event-driven-hedge-fund-positioning-alternative-investment) (MEDIUM)
- [Daloopa — hedge fund investment memo example](https://daloopa.com/blog/hedge-fund-investment-memo-example) — memo structure, red teams (MEDIUM)
- [Stanford/Addepar — investment memos & decision-making](https://longterminvesting.stanford.edu/sites/g/files/sbiybj23856/files/media/file/addepar-investment-memos-and-decision-making.pdf) (MEDIUM)
- [Pre-mortem — Wikipedia](https://en.wikipedia.org/wiki/Pre-mortem) (MEDIUM)
- [Mauboussin — The Base Rate Book](https://hedgefundalpha.com/education/michael-mauboussin-the-base-rate-book/) — outside view (MEDIUM)
- [Morgan Stanley — Mauboussin behavioral finance Q&A](https://www.morganstanley.com/articles/behavioral-finance-q-a) (MEDIUM)
- [TradeZella — Trading dashboard: 8 KPIs](https://www.tradezella.com/blog/trading-dashboard) (MEDIUM)
- [tradewiththepros — Trading performance metrics](https://tradewiththepros.com/trading-performance-metrics/) (MEDIUM)
- [Hudson & Thames — Cointegration for pairs trading](https://hudsonthames.org/an-introduction-to-cointegration/) (HIGH)
- [Groww — Pair trading strategy](https://groww.in/blog/pair-trading-strategy) — biotech pair caveat (MEDIUM)
- [arXiv — Cointegration pairs trading (Indian market)](https://arxiv.org/pdf/2211.07080) — Engle-Granger/Johansen (MEDIUM)

---
*Feature research for: event-driven biotech-catalyst multi-agent trading desk*
*Researched: 2026-08-14*
