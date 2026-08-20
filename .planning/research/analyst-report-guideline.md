# Binary-Catalyst Analyst Report Guideline

**Zamvar Capital — Fund 1 Strategy**
**Scope:** How to analyze a single drug ahead of a binary FDA/clinical catalyst (a PDUFA approval decision or a pivotal trial readout).
**Purpose:** A repeatable REPORT GUIDELINE + one-pager TEMPLATE for each of four analytical lenses, so an AI analyst desk produces consistent, deep, data-rich, **plain-language** analysis every time.

---

## 0. How to use this document

The desk analyzes every binary catalyst through **four lenses**, each producing one one-pager:

1. **CLINICAL / SCIENTIFIC** — reasons like a physician-scientist. *Is the data real and strong enough to approve?*
2. **REGULATORY** — reasons like FDA regulatory counsel. *Will the FDA say yes, and in what form?*
3. **FINANCIAL** — reasons like a biotech CFO. *Can the company survive to the event, and what is the asset worth?*
4. **MARKET / POSITIONING** — reasons like an event-driven PM. *What's already priced in, and is the setup skewed?*

Each lens template below has the same three parts:
- **(A) Section structure** — fixed headers, in order. Same every time.
- **(B) Data-point checklist** — the specific quantitative slots each section must fill, and **where each is sourced**.
- **(C) Framework** — the heuristics that turn the data into a judgment (a probability, a valuation, an asymmetry call).

**Every lens ends with a one-line BOTTOM LINE and a probability or valuation number.** The four one-pagers then roll up into a single thesis (see §6).

**Non-negotiable house style: the Plain-Language Standard (§5).** Read it first. Every number gets context; every term gets defined in-line the first time; every section leads with the "so what."

---

## 1. LENS 1 — CLINICAL / SCIENTIFIC

> Framing rule underneath everything: **"Met its primary endpoint" can describe a practice-changing result or a statistically significant sliver no payer will reimburse — telling the difference is the whole job.** The topline press release is a curated sponsor summary; the real story is in the trial design, the full dataset, and the FDA review documents.

### (A) Section structure — in order

1. **Bottom Line** (1 sentence: is the science real + strong enough to approve, and the key risk)
2. **Disease & Unmet Need**
3. **Mechanism of Action (MoA) & Scientific Rationale**
4. **Trial Design & Statistical Plan**
5. **Endpoints** (primary/secondary hierarchy; surrogate vs. clinical)
6. **Efficacy Result — Effect Size WITH CONTEXT**
7. **Safety & Tolerability**
8. **Prior-Data Consistency** (Phase 2 → Phase 3; cross-trial)
9. **Key Scientific Risk & Probability of Success (PoS)**

### (B) Checklist + sourcing

**Disease & Unmet Need**
- [ ] Incidence & prevalence (US + ex-US); addressable sub-population after line-of-therapy and biomarker gating — *Source: SEER / CDC / WHO / GLOBOCAN; verify company deck framing, don't accept it*
- [ ] Current standard of care (SoC) and its benchmark numbers (median OS/PFS, response rate, key toxicities) — *Source: NCCN / ESMO / ASCO guidelines + the SoC's own pivotal trial*
- [ ] Severity of unmet need: is SoC curative, life-extending, or palliative? Untreated mortality/morbidity
- [ ] Line of therapy targeted (1L = bigger market and higher bar than 3L+)

**Mechanism of Action & Rationale**
- [ ] Target, modality (small molecule / mAb / ADC / cell / gene therapy), pathway
- [ ] Is the target *genetically validated* (human genetics / knockout) or only associational?
- [ ] Class read-through: have other drugs on this target/pathway succeeded or failed? — *Source: PubMed, competitor trial history*
- [ ] Selection-biomarker strategy? (**programs with a selection biomarker succeed at higher rates at every phase**)

**Trial Design & Statistical Plan** — *Source: ClinicalTrials.gov (authoritative pre-specification record incl. history tab), the Statistical Analysis Plan, FDA briefing docs, journal supplement*
- [ ] **n =** (randomized), randomization ratio (1:1, 2:1)
- [ ] Control arm: **placebo vs. active SoC** (beating SoC is a far higher bar than beating placebo)
- [ ] Blinding: double-blind > single-blind > open-label (open-label inflates subjective endpoints)
- [ ] Powering: pre-specified alpha (usually two-sided 0.05), power (usually 80–90%), and **the effect size the trial was designed to detect**
- [ ] Superiority vs. non-inferiority (and the NI margin)
- [ ] Interim analyses / adaptive features / alpha-spending plan
- [ ] Enrollment criteria (how sick / how selected the population)

**Endpoints** — *Source: ClinicalTrials.gov original-vs-current, FDA "Clinical Trial Endpoints" guidance, FDA "Table of Surrogate Endpoints," briefing docs*
- [ ] Primary endpoint + its rung in the evidence ladder: **Overall Survival (OS) > Progression-Free Survival (PFS) > Response Rate (ORR)**
- [ ] Is the primary a **validated surrogate** (OK for traditional approval) or only **"reasonably likely to predict benefit"** (the accelerated-approval standard, weaker)?
- [ ] Key secondaries — alpha-controlled (in the testing hierarchy) or merely descriptive?
- [ ] **Any endpoint change vs. original registration** — a late primary swap is a major red flag
- [ ] Is the endpoint clinically meaningful (does an MCID — minimal clinically important difference — exist) or just measurable?

**Efficacy — Effect Size WITH CONTEXT** (the analytic core) — *Source: topline PR (incomplete) → ASCO/ASH/AACR/ESMO abstracts → journal + supplement → FDA briefing docs (most complete, includes FDA's own reanalysis)*
- [ ] **Point estimate + 95% CI + p-value** for the primary. The CI width tells you precision; the p only tells you the effect is probably real.
- [ ] Time-to-event: **Hazard Ratio (HR)** + absolute median gain (months). Context benchmarks:
  - HR **0.65, tight CI** = strong, precise signal
  - HR **0.85, CI approaching 1.0** = statistically significant but commercially underwhelming
  - **ASCO set HR = 0.80 as the *weakest* acceptable design target** in oncology; HR > 0.80 is a "relatively small" benefit
  - ASCO meaningful-benefit bar: **≥20% relative OS increase or ~2.5–6 months** absolute; ESMO-MCBS grades 4–5 = meaningful (non-curative setting)
- [ ] Binary outcomes: report **Relative Risk Reduction (RRR)** AND **Absolute Risk Reduction (ARR)** AND **Number Needed to Treat (NNT = 1/ARR)**. RRR alone is the classic spin vehicle: a 50% RRR on a 2%→1% event rate is a 1% ARR, NNT = 100.
- [ ] Surrogate→clinical translation risk (e.g., PFS HR predicts OS HR moderately-to-strongly; ORR predicts OS only weakly, r ≈ 0.47)

**Safety & Tolerability** — *Source: FDA briefing docs + journal safety tables (topline PRs routinely under-disclose safety)*
- [ ] **Discontinuation rate due to AEs** (cleanest tolerability proxy), treatment vs. control
- [ ] Serious adverse event (SAE) rate and deaths, balanced arm-vs-arm
- [ ] Grade 3–4 AE rate; specific dose-limiting or organ toxicities
- [ ] Any signal that would trigger a **boxed warning, REMS, or narrower label**

**Prior-Data Consistency** — *Source: prior ClinicalTrials.gov + prior publications; BIO/Biomedtracker base rates*
- [ ] Does the Phase 3 effect match or shrink from Phase 2? (Regression to the mean: Phase 2 effects usually shrink; a Phase 3 matching a suspiciously strong Phase 2 deserves scrutiny.)
- [ ] Consistency across subgroups, geographies, prior trials
- [ ] Base-rate anchor: **Phase 3 → approval ≈ 50–52% overall, ~37% oncology** (see Lens 3 §4 for full BIO numbers)

**Key Scientific Risk & PoS**
- [ ] The single biggest scientific reason this fails (underpowering, surrogate won't translate, safety, unblinded subjective endpoint, multiplicity)
- [ ] PoS estimate, base-rate-anchored then adjusted
- [ ] What the full-data reveal (conference / FDA docs) could still change

### (C) Framework — "will the data support approval / is the science real?"

- **Statistical vs. clinical significance.** A p-value says the effect is probably real, not that it's big enough to matter. Judge magnitude against an MCID / field benchmark / payer bar. Always demand point estimate + 95% CI + absolute magnitude together.
- **Endpoint hierarchy as evidence ladder.** OS > PFS > ORR. A PFS win with an OS miss complicates label + reimbursement. An unvalidated surrogate only supports accelerated approval (with a confirmatory-trial string attached).
- **Multiplicity / alpha-spend.** A "significant" secondary tested *after* the primary failed, with no multiplicity correction, is not confirmatory.
- **Subgroup vs. ITT — the single biggest red flag.** Trust the intent-to-treat primary. Distrust a subgroup unless it was pre-specified, biologically rational, and backed by a significant *interaction test*. Red flags: overall non-significant but one subgroup "positive"; no interaction test; the winning subgroup conveniently equals a commercial population; "benefit was driven by…". Post-hoc subgroups are hypothesis-generating only.
- **Missing data / dropout bias.** Differential dropout biases results (informative censoring). Per-protocol analyses that beat ITT are a spin signal — ITT is the honest denominator.
- **Spin tactics to flag:** RRR without ARR/NNT; per-protocol instead of ITT; late endpoint changes; "numerically improved / trended toward" (= missed significance); leading on a secondary because the primary failed; topline PR omitting CIs and safety.
- **Design-vs-result stress test.** Barely clearing significance on a trial powered for a *large* effect = the drug underperformed its own design, even if "positive."

---

## 2. LENS 2 — REGULATORY

> The vote is advisory, the letter is binary, and the label is where an "approval" can still be a loss. Handicap **three outcomes, not two**: clean approval, approval crippled by a boxed warning / REMS / narrow label, and a Complete Response Letter (CRL = FDA's formal "not in this form" rejection).

### (A) Section structure — in order

1. **Bottom Line** (1 sentence + the numeric Probability of Approval)
2. **Application Mechanics** (BLA/NDA, review designation, clock, PDUFA date, resubmission class)
3. **Review Division & Posture**
4. **The Regulatory Question** (the benefit-risk issue; prior CRL deficiency & whether addressed)
5. **Advisory Committee (AdCom) Analysis**
6. **Label / REMS / Post-Marketing Risk**
7. **Precedent & Base Rates**
8. **Probability of Approval (PoA) + Scenario/Payoff Map**

### (B) Checklist + sourcing

**Application Mechanics** — *Source: company 8-K / PR (PDUFA date, designations, filing acceptance); Drugs@FDA (accessdata.fda.gov/scripts/cder/daf) for approval history & prior action letters; FDA.gov expedited-program pages*
- [ ] **Application type:** BLA (biologic — antibodies, cell/gene therapy, vaccines; filed under the PHS Act) vs. NDA (small-molecule; §505(b)(1) or 505(b)(2)). Same PDUFA clock either way.
- [ ] **Review designation & clock:** Priority Review = FDA acts within **6 months** of filing; Standard = **10 months** of filing. Clock starts at *filing* (~60 days post-submission), so calendar time from submission ≈ 8 / 12 months.
- [ ] **PDUFA goal date** (a target, NOT a legal deadline — FDA misses/extends routinely)
- [ ] Submission date + filing acceptance (Day-60 "Filed" letter; a Refuse-to-File is an early red flag)
- [ ] Expedited tags: Breakthrough, Fast Track, Accelerated Approval, Orphan (each nudges base rates up)
- [ ] **Resubmission class (if post-CRL):** Class 1 (minor — labeling/safety) → **2-month** goal; Class 2 (substantive — new data/reinspection) → **6-month** goal; FDA assigns class within 30 days
- [ ] Late-cycle amendments / clock extensions (a major amendment adds 3 months — common near-PDUFA surprise)

**Review Division & Posture**
- [ ] Which OND division owns it (Oncology/OCE, Neurology, Cardio-Renal, Psychiatry…)
- [ ] Division track record: recent CRL rate, how often it convenes AdComs, public skepticism on this endpoint/class
- [ ] Named division director / reviewer posture where knowable from prior decisions

**The Regulatory Question** — *Source: FDA briefing docs, FDA guidances, company 8-K/earnings*
- [ ] The specific benefit-risk issue (efficacy magnitude, endpoint acceptability, single-trial vs. two-trial evidence, surrogate validity)
- [ ] **Prior CRL deficiency itemized:** (a) clinical/efficacy, (b) safety, (c) CMC/manufacturing, or (d) facility inspection — this drives resubmission odds
- [ ] Has each deficiency been addressed? (new trial? new data cut? plant re-inspected?)
- [ ] Manufacturing/inspection status (an unresolved Form 483 is a frequent silent CRL cause, independent of the data) — *Source: FDA inspection database / FOIA + company disclosure*

**AdCom Analysis** — *Source: FDA Advisory Committee Calendar (fda.gov/advisory-committees) + Federal Register; briefing docs on the FDA meeting-materials page (posted ~2 business days pre-meeting)*
- [ ] **Is an AdCom scheduled?** (No AdCom on a controversial drug = usually positive; a newly-scheduled AdCom on a "clean" drug = negative tell)
- [ ] Committee identity + **exact voting-question wording** (framing predicts outcome)
- [ ] Briefing-doc read: read **FDA's book first**, the executive summary / benefit-risk conclusion — that's where reviewers telegraph their leaning

**Label / REMS / Post-Marketing** — *Source: Drugs@FDA labels, FDA REMS public dashboard, IntuitionLabs boxed-warning analysis*
- [ ] Boxed-warning risk (can gut the commercial thesis even on approval)
- [ ] REMS requirement (restricted distribution/monitoring — "approvable only with REMS" is a real gate)
- [ ] Narrower-than-sought label / subpopulation restriction risk
- [ ] Accelerated-approval confirmatory-trial obligation + withdrawal risk

**Precedent & Base Rates**
- [ ] Nearest **approved** analog in the class/division and its label
- [ ] Nearest **CRL'd/rejected** analog and why
- [ ] This division's AdCom concordance history

### (C) Framework — handicapping the PoA

**AdCom mechanics (the numbers to know):**
- The vote is **non-binding** — the committee advises, FDA decides.
- **88% overall FDA-AdCom concordance, 298 votes, 2010–2021** (JAMA Network Open). Broken out: FDA followed *positive* votes ~97% (initial approvals) but *negative* votes only ~67% — i.e., it approved over a "no" vote about a third of the time.
- **A split (non-consensus) vote is the single biggest predictor of FDA going its own way.** Unanimous votes carry far more weight. In 2010–2021, FDA approved 4 of 5 *tied*-vote drugs.
- **2025 regime shift — flag loudly:** FDA went *against* its AdCom on 3 of 7 (43%) meetings in 2025 vs. ~16% discordance across 2020–2024, and held far fewer AdComs. The historical 88% prior is materially weaker under the current FDA.

**Base rates (with sources):**
- First-cycle approval: CDER approved **46/55 (84%)** novel drugs first-cycle in 2023
- PDUFA on-time: **89%** of 2023 approvals met the goal date (target 90% under PDUFA VII)
- **CRL → eventual approval ≈ 40% overall**, but deficiency-dependent: **labeling-driven ~85%+**, **safety-driven ~40%**
- Whole-pipeline LOA from Phase 1: small-molecule NME **5.7%**, biologics **9.1%** (BIO 2011–2020); a Phase-3 asset at PDUFA is far higher (~50%)

**The PoA build:**
1. **Anchor** on a base rate for the designation (practitioner heuristic priors: NDA standard ≈85%, NDA priority ≈90%, orphan ≈93% — treat as priors, not gospel).
2. **Apply modifiers:** prior CRL ≈ −28% (worse if safety-driven); AdCom on a controversial file = haircut; negative FDA briefing-doc tone = often the biggest single same-week revision; unresolved manufacturing = haircut; strong single pivotal + unmet need + biomarker = boost. In 2025+, widen the error bar.
3. **Cross-check against precedent** — the nearest same-division analog overrides a generic base rate.
4. **Convert to a scenario/payoff map**, not one number: P(clean approve), P(approve with boxed warning/REMS/narrow label), P(CRL). *The PoA is only useful paired with the payoff* — 70% PoA on a 2x-up/0.4x-down setup is a very different trade from the same PoA on a 1.3x/0.2x setup.

---

## 3. LENS 3 — FINANCIAL

> Answers two questions: **Can this company survive to and past the event without a gun-to-head raise?** and **What is the risk-adjusted value of the asset the event de-risks?** Counter-intuitive core: **more cash is not always a good sign** — raising a big cushion *into* a catalyst can signal low internal confidence.

### (A) Section structure — in order

1. **Bottom Line** (1 sentence: solvency through the catalyst + rNPV vs. current market cap)
2. **Balance Sheet & Liquidity**
3. **Burn Rate & Cash Runway** (the runway-vs-catalyst test)
4. **Capital Structure & Dilution**
5. **Financing History & Structure**
6. **Insider & Institutional Activity**
7. **Asset Valuation — rNPV Build**
8. **Scenario Value & Signal Synthesis**

### (B) Checklist + sourcing

**Balance Sheet & Liquidity** — *Source: latest 10-Q/10-K balance sheet; 8-K if a raise closed after quarter-end*
- [ ] Cash & equivalents ($M); short- + long-term marketable securities ($M); **total liquidity** = sum
- [ ] Debt: term/venture-debt principal, rate, maturity, **covenants** (minimum-cash covenants can force a raise *before* the stated runway ends)
- [ ] Convertible notes: face, conversion price, maturity
- [ ] Restricted cash (exclude from runway)

**Burn Rate & Cash Runway** — *Source: 10-Q/10-K cash-flow statement (operating activities) + MD&A liquidity section*
- [ ] Net cash used in operations (TTM + latest quarter)
- [ ] **Quarterly net burn** = avg of last 2–4 quarters; normalize out one-timers (milestones, upfronts, restructuring)
- [ ] Expected burn step-up (a Phase 3 win precedes a commercial build → burn accelerates)
- [ ] **Runway (months)** = total liquidity ÷ (quarterly net burn ÷ 3)
- [ ] **Runway-vs-catalyst test:** does runway extend *past* the catalyst, and by how many months of cushion? (<6–9 mo = dilution clock is live; healthy pre-catalyst = 18–24 mo; <2 quarters cushion = high risk of a raise *into* the event / overhang)
- [ ] Management's own "runway into [period]" guidance — compare to your independent calc

**Capital Structure & Dilution** — *Source: 10-Q cover (as-of date) + equity footnotes; S-1/S-3/424B for offering counts*
- [ ] Basic shares outstanding (+ cover as-of date); options/RSUs/warrants/convert-underlying → **fully diluted count**
- [ ] Warrant overhang: strikes + expiries (in-the-money warrants = near-term dilution + selling pressure)
- [ ] Dilution trajectory: shares at each of last 4–8 quarter-ends → annualized dilution %
- [ ] Pre-funded warrants (economically shares; sit outside the basic count)

**Financing History & Structure** (each raise, last ~3 yrs) — *Source: 8-K (+ securities purchase agreement exhibit), S-1/S-3/424B, ATM sales agreement*
- [ ] Date, gross + net proceeds
- [ ] **Vehicle:** ATM / marketed follow-on / registered direct / **PIPE** / convertible / venture debt / royalty monetization
- [ ] **Pricing vs. market:** premium or discount to prior close / trailing VWAP, and the discount %
  - ATM: sells *at market* (no baked-in discount) — cheapest, most flexible, caps velocity
  - Marketed follow-on: modest discount (~5–10%)
  - **PIPE: negotiated 5–15% discount**; PIPEs were ~87% of 2025 biotech follow-on volume
  - **Distressed tell:** deep discount + warrant coverage + warrants struck *below* market = weak hand
- [ ] Investor quality: brand-name crossover/specialist funds (RA, Baker, Deep Track, Perceptive) vs. anonymous/retail
- [ ] Is an ATM facility *in place and undrawn*? (a live ATM = latent dilution the market prices as overhang)

**Insider & Institutional Activity** — *Source: Form 4 / Form 144 (EDGAR); 13F quarterly; 13D/13G (>5%)*
- [ ] Form 4 buys vs. sells (last 6–12 mo): share counts, prices, who (CEO/CFO/director/10% holder)
- [ ] **10b5-1 vs. discretionary flag:** a checkbox + footnote marks a Rule 10b5-1 (pre-scheduled) plan trade
  - **10b5-1 automatic *sales*** = pre-scheduled → **low signal**
  - **Discretionary open-market *buys* (code "P")** = **high-conviction signal**, especially CEO/CFO into a catalyst
  - Watch a *newly adopted* 10b5-1 plan set to fire post-readout (ambiguous-to-negative)
  - Codes: **P** = open-market buy, **S** = open-market sale, **A** = grant, **M** = option exercise, **F** = tax-withhold (M/F/A ≈ near-zero signal)
- [ ] 13F/13D changes from biotech specialist funds (accumulation into the event = corroborating conviction)

**Asset Valuation — rNPV Build** — *Source: epi from CDC/WHO/SEER; pricing/comps from analog launches; costs from 10-K R&D*
- [ ] **Addressable population** — bottom-up: epidemiology → diagnosed % → treated/line-eligible % → biomarker-positive haircut → treatable population (epi-prevalence to commercially-addressable is routinely a 60–80% shrink)
- [ ] Peak market penetration % (share at peak; e.g. ~30%)
- [ ] Net price/patient/year = list minus gross-to-net (rebates/discounts)
- [ ] **Peak sales** = treatable pop × penetration × net price (× ex-US uplift, often +50–100% of US)
- [ ] **Probability of Success (PoS/LoA)** — cumulative from current phase to approval (see §4)
- [ ] Launch curve — ramp yrs 1–5, peak yrs 5–10 (specialty/rare peaks in 3–4 yrs; broad primary-care 8–10 yrs)
- [ ] Patent / Loss-of-Exclusivity date — post-LoE: small molecules lose 80–90% within ~2 yrs, biologics retain 60–70%
- [ ] Remaining dev + commercialization costs by phase
- [ ] **Discount rate** — typically **10–12%** (large pharma 8–10%, mid-cap biotech 10–15%, early/pre-revenue 15–20%). *Clinical risk goes in the PoS weights, NOT the discount rate* — that separation is the whole point of rNPV.

### (C) Framework — rNPV + resilience

**rNPV formula:**
> **rNPV = Σ_t [ (Cash Flow_t × Cumulative PoS_t) ÷ (1 + r)^t ]**

Clinical risk sits in the cumulative-PoS multiplier at each node; `r` covers only time-value/financial risk.

**Worked example** (Phase-2 oncology asset, illustrative):
Peak-sales build (US): NSCLC incidence ~235,000/yr → diagnosed ~223,000 → line-eligible ~40% = 89,000 → biomarker-positive ~25% = 22,000 → peak penetration ~30% = **6,600 patients** × **$150,000 net price** = **~$990M US peak** → +50% ex-US = **~$1.5B global peak.** Discounting the probability-weighted cash-flow stream (cumulative PoS from Phase 2 ≈ 20%, r ≈ 8–11%) through LoE yields an rNPV on the order of **~$900M**. (Textbook Phase-1 case, Alacrita: $5M/$20M/$50M phase costs, $100M/yr profit for 10 yrs, 11% rate → rNPV ≈ $200M.) *Swap in the target's real numbers — these outputs are illustrative.*

**PoS / Likelihood-of-Approval benchmarks** — BIO + Informa (Biomedtracker) + QLS, *"Clinical Development Success Rates and Contributing Factors, 2011–2020"* (12,728 phase transitions):
- Phase 1→2: **52.0%** · Phase 2→3: **28.9%** (the hardest gate) · Phase 3→filing: **57.8%** · Filing→approval: **90.6%**
- **Overall LOA from Phase 1: 7.9%** → a Phase-3 asset is ~**50–52%** likely to be approved (0.578 × 0.906)
- By area (Phase-1 LOA): **Oncology 5.3% (lowest)**, **Hematology highest** (~2–3× oncology), rare/orphan above average
- By modality: biologics **9.1%** vs. small-molecule NME **5.7%**; selection-biomarker programs higher at every phase

**How financing choices signal conviction:**
- Raising a large cushion *right before* a binary catalyst can signal *low* confidence — if management believed the readout would re-rate the stock up, they'd wait and raise after at a higher price.
- Undrawn ATM used opportunistically at market = healthy. Deep-discount PIPE + warrant coverage + below-market strikes, announced late = weak hand. PIPE led by brand-name specialists at a modest discount = validation (smart money did diligence).
- Insider **buying (code P)** into a catalyst is the cleanest positive tell. Insider **selling** is mostly noise if 10b5-1.
- **Synthesis rule:** cross the runway-vs-catalyst test with financing structure and insider direction. Best case = runway comfortably past the event + insiders buying + no raise needed. Worst = <2 quarters cushion + a deep-discount PIPE just closed + a new 10b5-1 sale plan.

---

## 4. LENS 4 — MARKET / POSITIONING

> The current price is a probability-weighted blend of the two post-event scenarios. The job: extract the **market's implied odds**, compare to your fundamental odds, and judge whether the setup is skewed — and whether **positioning (flows) or fundamentals (the outcome)** will drive the move.

### (A) Section structure — in order

1. **Bottom Line** (1 sentence: what's priced in vs. our view + the asymmetry call)
2. **Catalyst Definition & Timeline**
3. **Pre-Event Price Action / Drift** (the run-up)
4. **Options-Implied / Expected Move**
5. **Volatility Structure & IV-Crush Setup**
6. **"What's Priced In" — Implied Probability Decomposition**
7. **Short Interest & Squeeze Setup**
8. **Float & Ownership / 13F Concentration**
9. **Sell-Side Sentiment & Revisions**
10. **Historical Analogs**
11. **Positioning / Risk-Reward Asymmetry Synthesis**

### (B) Checklist + sourcing

**Pre-Event Price Action** — *Source: exchange price feed / charting*
- [ ] % move over trailing 4w/8w/3m/6m (the PDUFA run-up typically starts 4–8 weeks out)
- [ ] % move vs. sector (XBI/IBB) — idiosyncratic or beta?
- [ ] Distance from 52-wk high/low; volume trend (accumulation vs. distribution)
- [ ] Short-covering component of the run-up (reconcile with §7 so you don't double-count demand)

**Options-Implied / Expected Move** — *Source: options chains (Bloomberg OMON, broker chain, MarketChameleon)*
- [ ] **ATM straddle price** for the first expiry *after* the event
- [ ] **Expected move % = ATM straddle ÷ stock price**; binary-refine to **0.85 × straddle**, or **(ATM straddle + first OTM strangle)/2**, or weighted **0.6×ATM + 0.3×1st-strangle + 0.1×2nd-strangle**
- [ ] Implied ± bound in dollars
- [ ] Implied move vs. realized moves of the analog class (the trade thesis lives here)

**Volatility Structure & IV-Crush** — *Source: IV analytics (MarketChameleon, ORATS, SpotGamma, LiveVol)*
- [ ] Current event-month ATM IV (biotech pre-binary IV routinely >100%, sometimes >150%)
- [ ] Post-event IV estimate (back-month / historical baseline, often ≤40%) → the crush
- [ ] IV rank / percentile vs. own 1-yr history; term structure (front vs. back = event premium); put/call skew
- [ ] Break-even after crush: does a "right-direction" bet still lose to vol collapse?

**"What's Priced In" — Implied Probability** — *Source: options chain + sell-side/analog scenario targets*
- [ ] Approval target Z, rejection/CRL target Y, current price X
- [ ] **Implied P(approval) = (X − Y) ÷ (Z − Y)** → compare to your fundamental P → the edge

**Short Interest & Squeeze** — *Source: FINRA/exchange bi-monthly (twice a month, ~7-trading-day lag) for the official print; ORTEX / S3 for daily estimates + borrow*
- [ ] Short interest as **% of float** (>20% high, >30% very high)
- [ ] **Days-to-cover = shares short ÷ avg daily volume** (>5 meaningful, >7 aggressive)
- [ ] **Cost-to-borrow** annualized % (>30% notable, >80% severe); utilization %; hard-to-borrow?
- [ ] SI trend into the event

**Float & Ownership** — *Source: 13F (EDGAR), Bloomberg HDS, Form 4*
- [ ] Free float + float % of shares; institutional ownership %
- [ ] Top-10 holder concentration; specialist-fund presence; insider ownership %
- [ ] 13F change last quarter (crowdedness)

**Sell-Side Sentiment** — *Source: consensus aggregators (Bloomberg, FactSet, MarketScreener)*
- [ ] Rating distribution (Buy/Hold/Sell); consensus + high/low target + **dispersion** (wide = disagreement)
- [ ] % upside to consensus; revision direction (1m/3m)
- [ ] Are targets probability-weighted or single-scenario? (biotech targets often the latter — flag it)

**Historical Analogs** — *Source: event databases + own backtest of prior PDUFA/readout reactions*
- [ ] 3–5 comparable catalysts; implied move going in vs. **realized 1-day move**; outcome + asymmetry
- [ ] Lesson: high consensus P(approval) → small move on approval (priced in), catastrophic on CRL (not priced in)

### (C) Framework — event-driven positioning

**Implied probability ("priced in"):**
> **X = p·Z + (1 − p)·Y**  →  **p = (X − Y) ÷ (Z − Y)**

Worked: X = $30, approval Z = $50, CRL Y = $12 → p = 18/38 = **47%** implied. If your clinical read is 70%, the long is cheap; if 30%, it's rich.

**Expected move — two formulas:**
- From the straddle: expected move % = ATM straddle ÷ stock (e.g. $9 straddle on $200 stock = 4.5%)
- From IV: 1-s.d. move % = IV × √(days/365) (e.g. 120% IV, 5 days = 14.0%)

**IV crush — why direction alone doesn't save you:** Pre-binary IV (say 80–150%) collapses to ~30–40% overnight once uncertainty resolves. Worked: $100 stock, $8 straddle (8% implied), IV 80%. Stock rises 5% on approval but IV crushes to 32% → the next-day straddle is ~$4–5. **The buyer was right on direction and still lost.** To win owning premium, realized move must *exceed* implied move. Selling premium harvests the crush but carries the full binary tail.

**Short-squeeze setup:** SI >20–30% of float + days-to-cover >5–7 + cost-to-borrow >30–80% + a positive binary catalyst. Forced-covering odds rise ~3× when DTC >5 *and* CTB >30% together. Some of the run-up is short-covering, not new longs.

**Asymmetry synthesis:**
- Expected value: **EV = P(app)×Upside% + P(rej)×Downside%** (e.g. 0.60×80% + 0.40×−60% = **+24%**). Positive EV *and* fundamental P above the market-implied p = favorably skewed long.
- Size to conviction (specialist convention): very-high (P≥70%) 3–5% of book; high (50–70%) 1.5–3%; moderate (30–50%) 0.5–1.5%; speculative (<30%) 0.25–0.5%.
- **Positioning vs. fundamentals test:** if the stock has run 30–40% and implied p already exceeds your fundamental p, the move is *positioning-driven and priced in* — asymmetry has decayed (exit before the date or hedge). If implied p is *below* your fundamental p and shorts are crowded, asymmetry favors holding through (or the squeeze). Expression: run-up/positioning trades buy 6–8w out and exit 1–2w before the date (harvest ~20–40%, avoid the binary); hold-through/fundamentals trades take the binary (+50–200% on approval vs. −40–80% on CRL).

---

## 5. THE PLAIN-LANGUAGE STANDARD (house style — applies to all four lenses)

Non-jargon is the product. Three rules, enforced on every sentence:

1. **Define every technical term in-line the first time it appears.** "Hazard ratio (the risk of the bad event in the treated group divided by the control group; below 1.0 = benefit)". Not "HR 0.72."
2. **Every number gets context — good/bad, vs. what benchmark.** Never a bare number. "HR 0.85 — a 15% risk reduction, which is *below* the ~20%+ oncology bodies consider clearly meaningful."
3. **Lead with the bottom-line "so what," then the evidence.** Each section opens with the conclusion; the data supports it, not the reverse.

Supporting rules: spell out absolute *and* relative (RRR + ARR + NNT together); flag when a number is an estimate vs. a hard filing figure; convert probabilities to plain odds ("~1 in 13"); state the source inline when it's load-bearing.

### Before / after examples (real biotech-catalyst sentences)

**Example 1 — clinical (HR/CI)**
- ❌ *Jargon:* "Treatment met its primary endpoint of PFS with a statistically significant hazard ratio of 0.85 (95% CI 0.74–0.98, p=0.03)."
- ✅ *Plain + data-rich:* "The drug delayed cancer growth, but modestly — it cut the risk of the disease worsening by about 15% versus the control arm. The result barely cleared the statistical bar (the confidence range nearly touched 'no effect'), and a 15% reduction sits *below* the ~20%+ level oncology bodies call clearly meaningful. It slowed progression; it has not yet shown people live longer."

**Example 2 — clinical (relative-risk spin)**
- ❌ *Jargon:* "The therapy reduced the relative risk of major cardiovascular events by 50% (p<0.001)."
- ✅ *Plain + data-rich:* "Events fell from 2% to 1% — a real but small absolute drop of 1 percentage point. You'd treat about 100 patients to prevent one event (number-needed-to-treat ≈ 100). The '50%' is technically true but makes a 1-in-100 benefit sound larger than it is."

**Example 3 — regulatory (AdCom + label)**
- ❌ *Jargon:* "A split AdCom vote against approval materially elevates CRL probability, though the label carries boxed-warning risk even in an approve scenario."
- ✅ *Plain + data-rich:* "The FDA's outside expert panel voted no — but only narrowly, and a divided vote is exactly the setup where the FDA most often overrides the panel (it followed 'no' votes only ~67% of the time historically). Even if approved, the bigger danger is a boxed warning — the FDA's strongest safety label — which can wreck sales. So 'approved' isn't automatically a win. Model three outcomes, not two."

**Example 4 — financial (insider signal)**
- ❌ *Jargon:* "Recent insider transactions reflect routine portfolio management under pre-established trading arrangements."
- ✅ *Plain + data-rich:* "The CFO's 40,000-share sale was a pre-scheduled automatic sale (a 10b5-1 plan set up 8 months ago) — low signal. The read that matters: the CEO *bought* 25,000 shares on the open market at $9 last month, a discretionary purchase into the catalyst — the strongest conviction tell in the filings."

**Example 5 — market (IV crush)**
- ❌ *Jargon:* "Vol is bid into the print with a fat straddle; watch the crush on the back-month."
- ✅ *Plain + data-rich:* "Options price a **±14% move** on the decision (the $8 straddle on a $100 stock, implied volatility 120%). Even if the stock rises 5% on approval, that volatility collapsing from ~120% to ~40% would leave a bought straddle worth roughly half — so you only profit owning options if the stock moves *more than 14%*."

---

## 6. ROLL-UP — the single thesis

After the four one-pagers, the desk emits one combined view:
- **Fundamental P(approval)** = reconciled Clinical × Regulatory read (the two lenses that estimate the same probability from different angles — they should agree or the disagreement is itself the finding).
- **Market-implied P(approval)** from Lens 4 → the **edge** = fundamental − implied.
- **Payoff map:** upside (approval, adjusted for label risk from Lens 2) vs. downside (CRL), sized against the rNPV and current market cap from Lens 3.
- **Solvency gate** from Lens 3: if the company can't clear the event without a distressed raise, the setup is contaminated regardless of the science.
- **Expression** from Lens 4: hold-through (fundamentals) vs. run-up (positioning), sized to conviction.
- **BOTTOM LINE:** direction, conviction, size, and the one thing that would change the view.

---

## 7. SCHEMA — how an AI agent emits this

Each one-pager maps to a structured object. The guideline above is the human-readable contract; this is the machine-readable shape. (JSON sketch — implement per fields, not verbatim.)

```json
{
  "ticker": "string",
  "catalyst": {
    "type": "PDUFA | pivotal_readout",
    "date": "YYYY-MM-DD",
    "drug": "string",
    "indication": "string"
  },
  "clinical": {
    "bottom_line": "string",
    "disease_unmet_need": { "prevalence": 0, "soc": "string", "unmet_need_severity": "string" },
    "moa": { "target": "string", "modality": "string", "genetically_validated": true, "selection_biomarker": true },
    "trial_design": { "n": 0, "randomization": "1:1", "control": "placebo | active_SoC", "blinding": "double | single | open", "alpha": 0.05, "power": 0.9, "powered_effect": "string" },
    "endpoints": { "primary": "string", "ladder_rung": "OS | PFS | ORR", "surrogate_status": "validated | reasonably_likely", "endpoint_changed_vs_registration": false, "key_secondaries": [] },
    "efficacy": { "point_estimate": 0, "ci_low": 0, "ci_high": 0, "p_value": 0, "hr": 0, "absolute_gain": "string", "arr": 0, "rrr": 0, "nnt": 0, "context_vs_benchmark": "string" },
    "safety": { "ae_discontinuation_pct": 0, "sae_pct": 0, "deaths": 0, "grade34_pct": 0, "boxed_warning_risk": "low|med|high" },
    "prior_consistency": "string",
    "key_scientific_risk": "string",
    "pos_estimate": 0.0
  },
  "regulatory": {
    "bottom_line": "string",
    "application": { "type": "BLA | NDA", "review": "priority | standard", "clock_months": 6, "pdufa_date": "YYYY-MM-DD", "resubmission_class": null, "expedited_tags": [] },
    "division": { "name": "string", "posture": "string" },
    "regulatory_question": "string",
    "prior_crl": { "exists": false, "deficiency_type": "clinical|safety|CMC|inspection", "addressed": true },
    "adcom": { "scheduled": false, "committee": "string", "voting_question": "string", "briefing_doc_tone": "string" },
    "label_risk": { "boxed_warning": false, "rems": false, "narrow_label": false, "confirmatory_trial": false },
    "precedent": "string",
    "poa": { "point": 0.0, "scenarios": { "clean_approve": 0.0, "approve_restricted": 0.0, "crl": 0.0 } }
  },
  "financial": {
    "bottom_line": "string",
    "liquidity": { "cash_m": 0, "securities_m": 0, "total_liquidity_m": 0, "debt_m": 0, "covenants": "string" },
    "runway": { "quarterly_burn_m": 0, "runway_months": 0, "clears_catalyst": true, "cushion_months": 0 },
    "capital_structure": { "shares_basic_m": 0, "fully_diluted_m": 0, "warrant_overhang": "string", "annual_dilution_pct": 0 },
    "financing_history": [ { "date": "YYYY-MM-DD", "vehicle": "ATM|follow_on|PIPE|convert|debt", "gross_m": 0, "discount_pct": 0, "warrant_coverage": "string", "investors": "string" } ],
    "insiders": { "net_direction": "buy|sell|mixed", "discretionary_buys": [], "10b5-1_sales": [], "specialist_13f_change": "string" },
    "rnpv": { "peak_sales_m": 0, "pos": 0.0, "net_price": 0, "addressable_pop": 0, "penetration_pct": 0, "loe_date": "YYYY-MM-DD", "discount_rate": 0.11, "rnpv_m": 0 },
    "signal_synthesis": "string"
  },
  "market": {
    "bottom_line": "string",
    "run_up": { "move_4w_pct": 0, "move_8w_pct": 0, "vs_xbi_pct": 0, "short_covering_component": "string" },
    "expected_move": { "atm_straddle": 0, "expected_move_pct": 0, "iv_current": 0, "iv_post_event_est": 0 },
    "implied_prob": { "x": 0, "z": 0, "y": 0, "implied_p_approval": 0.0 },
    "short_interest": { "si_pct_float": 0, "days_to_cover": 0, "cost_to_borrow_pct": 0, "squeeze_setup": true },
    "ownership": { "float_pct": 0, "institutional_pct": 0, "top10_concentration_pct": 0 },
    "sentiment": { "buy": 0, "hold": 0, "sell": 0, "target_dispersion": "string", "revision_trend": "up|down|flat" },
    "analogs": [ { "name": "string", "implied_move_pct": 0, "realized_move_pct": 0, "outcome": "string" } ],
    "asymmetry": { "ev_pct": 0, "position_size_pct": 0, "driver": "positioning | fundamentals", "expression": "string" }
  },
  "rollup": {
    "fundamental_p_approval": 0.0,
    "market_implied_p_approval": 0.0,
    "edge": 0.0,
    "bottom_line": "string",
    "conviction": "very_high|high|moderate|speculative",
    "size_pct": 0,
    "what_would_change_view": "string"
  }
}
```

**Every leaf that is a number carries a paired `_context` or `_source` string in the emitted report prose** (the schema stores the value; the one-pager renders value + context + source per the Plain-Language Standard). Numeric fields default to `null` when genuinely unavailable — never fabricate; an empty slot is a finding.

---

## 8. SOURCES

**Clinical / Scientific**
- FuzeBio — How to Read a Phase 3 Readout: https://getfuzebio.com/blog/how-to-read-a-phase-3-clinical-trial-readout
- STAT — How to spot when drug companies spin trial results: https://www.statnews.com/2023/11/28/clinical-trials-data-readouts-spin/
- Pharmagellan — Resources for analyzing biotech trial results: https://www.pharmagellan.com/blog/clinical-trial-resources
- FDA — Clinical Trial Endpoints for Cancer Drugs (guidance): https://www.fda.gov/media/71195/download
- FDA — Surrogate Endpoint Resources: https://www.fda.gov/drugs/development-resources/surrogate-endpoint-resources-drug-and-biologic-development
- FDA — Table of Surrogate Endpoints Basis of Approval: https://www.fda.gov/drugs/development-resources/table-surrogate-endpoints-were-basis-drug-approval-or-licensure
- Blood Cancer Journal — Clinically meaningful benefit (ASCO ≥20%/2.5–6mo): https://www.nature.com/articles/s41408-017-0009-8
- ESMO-MCBS v2.0 (Annals of Oncology): https://www.annalsofoncology.org/article/S0923-7534(25)00166-8/fulltext
- Clinical vs. statistical significance (PMC): https://pmc.ncbi.nlm.nih.gov/articles/PMC11673624/
- Risk Ratios / Odds Ratios / Hazard Ratios (PMC): https://pmc.ncbi.nlm.nih.gov/articles/PMC7515812/
- Multiplicity & Subgroup Analyses — Clinical Trials 101: https://www.clinicaltrials101.com/clinical-biostatistics-data-analysis/multiplicity-subgroup-analyses/
- The Lancet — Multiplicity in RCTs II (subgroups): https://www.thelancet.com/journals/lancet/article/PIIS0140-6736(05)66516-6/abstract
- NNT / ARR / RRR — Smart Health Choices (NCBI Bookshelf): https://www.ncbi.nlm.nih.gov/books/NBK63647/

**Regulatory**
- FDA-AdCom concordance 2010–2021 (88%, JAMA Network Open): https://pmc.ncbi.nlm.nih.gov/articles/PMC10329213/
- FDA went against AdComs 43% in 2025 vs 16% (2020–24) — BioSpace: https://www.biospace.com/fda/fda-went-against-adcomms-votes-more-held-fewer-adcomms-in-2025 ; center4research: https://www.center4research.org/biospace-fda-rejects_adcom-advice/
- FDA overrides split votes (FierceBiotech): https://www.fiercebiotech.com/biotech/fda-goes-against-adcomm-votes-22-time-study-finds
- Priority (6mo) vs Standard (10mo) review — FDA: https://www.fda.gov/patients/fast-track-breakthrough-therapy-accelerated-approval-priority-review/priority-review
- 2023 first-cycle 84% / 89% PDUFA on-time — FDA Novel Drug Approvals 2023: https://www.fda.gov/drugs/novel-drug-approvals-fda/novel-drug-approvals-2023 ; BioPharm Int'l: https://www.biopharminternational.com/view/cder-approved-55-novel-drugs-in-2023
- CRL resubmission rates + Class 1/2 timelines — Assyro: https://www.assyro.com/blog/complete-response-letter-guide ; 21 CFR 314.110: https://www.ecfr.gov/current/title-21/chapter-I/subchapter-D/part-314/subpart-D/section-314.110
- BLA vs NDA — Allucent: https://www.allucent.com/resources/blog/what-are-regulatory-differences-between-nda-and-bla
- FDA Advisory Committee calendar: https://www.fda.gov/advisory-committees
- Reading briefing documents — 3D Communications: https://3dcommunications.us/latest-thinking/posts/the-debrief-on-briefing-documents-how-to-maximize-your-briefing-book-for-fda-advisory-committee-meetings/
- FDA REMS public dashboard: https://www.fda.gov/drugs/risk-evaluation-and-mitigation-strategies-rems/risk-evaluation-and-mitigation-strategy-rems-public-dashboard
- Drugs@FDA: https://www.accessdata.fda.gov/scripts/cder/daf/
- PoA scorecard heuristics + catalyst trading — BiopharmaWatch: https://www.biopharmawatch.com/blog/biotech-catalyst-trading-hedge-funds-insiders-fda-decisions

**Financial**
- rNPV methodology / discount rates — Alacrita: https://www.alacrita.com/whitepapers/valuing-pharmaceutical-assets-when-to-use-npv-vs-rnpv
- rNPV formula + worked table + peak-sales build — Healthcare IB Guide: https://ibinterviewquestions.com/guides/healthcare-investment-banking/risk-adjusted-npv-biotech-valuation
- Peak sales / SOTP estimation — Healthcare IB Guide: https://ibinterviewquestions.com/guides/healthcare-investment-banking/pipeline-sotp-peak-sales-estimation
- rNPV / PoS-by-phase / LoE erosion — DrugPatentWatch: https://www.drugpatentwatch.com/blog/value-a-biotech-like-a-pro-the-metrics-that-actually-move-price-targets/
- BIO/Informa/QLS "Clinical Development Success Rates 2011–2020": https://www.bio.org/clinical-development-success-rates-and-contributing-factors-2011-2020 ; exact numbers via CPHI: https://www.cphi-online.com/news/clinical-development-success-rates-and-contributing-factors-2011-2020-new-report/
- Oncology-vs-non-oncology PoS by phase — Statista: https://www.statista.com/statistics/597819/drug-development-phases-probability-of-success-oncology-nononcology-drugs/
- Cash runway / burn / 18–24 month rule — K38 Consulting: https://k38consulting.com/biotech-15/ ; G-Squared CFO: https://www.gsquaredcfo.com/blog/burn-rate-and-runway-modeling-biotech
- ATM vs follow-on vs PIPE (87% of 2025 volume; 5–15% discount) — P05 PIPEs deep dive: https://www.p05.org/pipes-in-biopharma-a-2025-deep-dive/ ; New Street on ATMs: https://newstreetir.com/2025/04/23/should-every-public-biotech-have-an-atm-facility-when-should-one-be-put-in-place-and-which-banks-are-the-top-atm-managers/
- Rule 10b5-1 mechanics / Form 4 codes — SEC EDGAR: https://www.sec.gov/edgar

**Market / Positioning**
- Straddle expected-move math — FatTail: https://fattail.ai/straddle-option-guide/ ; Brilliant: https://brilliant.org/wiki/straddle-approximation-formula/
- IV crush — SpotGamma: https://support.spotgamma.com/hc/en-us/articles/15249330755859-IV-Crush-Explained-What-It-Is-When-It-Happens-and-How-to-Trade-It ; FatTail: https://fattail.ai/iv-crush-options/
- Options strategies for high-vol biotech — QuantStrategy: https://quantstrategy.io/blog/options-trading-strategies-for-high-volatility-biotech/
- Days-to-cover — QuantVPS: https://www.quantvps.com/blog/days-to-cover-explained
- Short-interest / squeeze data — TradeAlgo: https://www.tradealgo.com/trading-guides/stocks/short-interest-trading-how-to-use-short-squeeze-data-to-find-trading-opportunities
- ORTEX short-interest methodology: https://public.ortex.com/help-short-interest-overview/ ; ORTEX vs S3: https://www.alphanume.com/blog/ortex-vs-s3-partners
- FINRA short-interest reporting (bi-monthly, ~7-day lag): https://www.finra.org/filing-reporting/regulatory-filing-systems/short-interest
- Options-implied probabilities — Morgan Stanley Research: https://www.morganstanley.com/content/dam/msdotcom/en/assets/pdfs/Options_Probabilities_Exhibit_Link.pdf
- Biotech catalyst playbook — BioCatalysts.AI: https://biocatalysts.ai/learn/biotech-catalyst-trading-strategies ; MarketChameleon biotech catalyst report: https://marketchameleon.com/Reports/biotech-stock-catalysts
- Why some FDA approvals trigger stock drops — BiotechAnalyzer: https://biotechanalyzer.com/insights/why-some-fda-approvals-trigger-stock-drops-instead-of-gains

**Caveats on the numbers:** heuristic priors (PoA anchors 85/90/93%, prior-CRL −28%; positioning thresholds SI 20/30%, DTC 5/7, CTB 30/80%; run-up 20–40%) are *convention/rules-of-thumb*, not hard data — calibrate per name. Lean on the FDA / JAMA / BIO figures for defensible base rates. Flag the 2025 AdCom-concordance regime shift: the 88% "FDA follows the panel" prior is materially weaker under the current FDA. rNPV worked outputs are illustrative textbook cases — swap in the target's real inputs.
