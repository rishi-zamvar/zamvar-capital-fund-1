# Fund 1 — Data-Driven Inverse Pair Discovery (Biotech)

**Status:** COMPLETE
**Date:** 2026-08-14
**Analyst:** quant-research (solo, sequential run)
**Data:** yfinance daily adjusted closes, ~2 years (through 2026-08-14). Sector = XBI. FMP `stable/profile` for size-parity checks. Event dates reused from `.planning/research/universe-candidates.md` where already two-source verified.

---

## 1. Method

1. **Universe (~80 US-listed):** the Fund 1 candidate universe + their named competitors + major clinical/commercial biotechs + reference ETFs (XBI, IBB, LABD, SPY).
2. **Returns:** daily close-to-close returns. **Abnormal return = residual from a per-name two-factor OLS on SPY + XBI daily returns** (full-sample betas). A first pass using the naive "return − XBI" netting produced a wall of spurious "inverses" (every high-beta small-cap looked inverse to every low-XBI-beta mega-pharma, |t| up to 6) — that is a beta-mismatch artifact, not a trading signal, and it was discarded. All reported statistics use the two-factor residuals.
3. **Full-sample correlation:** Pearson corr of residual returns per pair (n ≈ 500 days).
4. **Big-move-day co-movement (the core test):** for ordered pair A→B, take days where |resid_A| ≥ 5% (also 7%); response = sign(resid_A) × resid_B. **Negative mean response = B reliably moves OPPOSITE to A's big idiosyncratic moves.** Report mean, n, t-stat. Both directions tested.
5. **Multiple-testing honesty:** ~2,800 pairs × 2 directions ≈ 5,600 tests → ≈ 140 pairs show |t| ≥ 2 by pure chance. Anything below |t| ≈ 3 (or without a mechanistic story + both-direction consistency) is treated as suggestive, not significant.
6. **Catalyst-conditional overlay:** for top inverse candidates, overlay known verified binary-event dates (both directions: A's events → B, B's events → A). With n of 1–5 events these are ANECDOTAL by construction and labeled as such.
7. **Ranking:** inverse strength + consistency × sample size × size-parity (RH-tradeable, comparable ADV) × mechanistic rationale.

## 2. Universe

**77 usable tickers, 2024-08-15 → 2026-08-14 (501 trading days), yfinance adjusted closes.**

- **Fund 1 candidates (28):** PHVS BCRX NTLA BBIO ALNY IONS MDGL IVA DYN RGNX SRPT SION CLDX SMMT RVMD IDYA OLMA CMPS DFTX PRAX RARE MIRM TVTX INSM SVRA ACAD PCVX AMLX
- **Named competitors (14):** IMCR ATAI STOK BNTX GILD MRK PFE NVS SNY REGN BMY AZN LLY NVO
- **Broad biotech (31):** VRTX AMGN BIIB MRNA INCY EXEL NBIX ALKS UTHR JAZZ RYTM ARWR ARDX AXSM CORT CRSP BEAM EDIT RCKT TGTX IMVT VKTX CYTK ROIV PTCT HALO KURA RIGL SUPN HRMY XENE
- **Reference (4):** XBI IBB LABD SPY

**Dropped:** APLS, FOLD, SWTX, DVAX (no yfinance data — presumed delisted/acquired; UNVERIFIED which), CPRX (only 5 stale observations). SION has 381 obs (listed Feb 2025) — included with reduced n. **DFTX carries the full pre-rebrand MNMD history under the new ticker** (501 obs) — usable, but pre-Jan-2026 rows are economically "MindMed". Acquired names from the candidate doc (AKRO, KALV, CDTX, ETNB, RNA/Avidity) were deliberately not requested (dead/spliced series).

## 3. Full-sample residual correlations — most-negative pairs

Distribution across 2,850 pairs: **mean +0.012, 5th percentile −0.089**. Residual correlations in biotech are essentially centered at zero — even the most negative full-sample values are small.

| A | B | resid corr | Read |
|---|---|---:|---|
| PCVX | CORT | −0.378 | **Drift artifact, not co-movement**: on each other's big days the sign agreement is coin-flip (40%/52% opposite). The negative corr comes from opposite multi-month residual drifts (PCVX de-rating while CORT re-rated). Not tradeable as an event hedge. |
| BIIB | RYTM | −0.222 | Defensive-vs-high-vol factor tinge (see §4); RYTM big days → BIIB tiny drips (mean −1.3%, 91% opposite sign but responses of −0.1…−3%). No mechanism. |
| EDIT | SUPN | −0.202 | No mechanism; both sides thin. |
| MDGL | REGN | −0.192 | No mechanism. |
| SMMT | MRK | −0.172 | The one negative corr WITH a mechanism (ivonescimab attacks Keytruda). See §4/§5. |
| INSM | MRNA | −0.171 | No mechanism. |
| IVA | UTHR | −0.166 | No mechanism; IVA is illiquid. |
| CMPS | EXEL | −0.165 | No mechanism (psychedelics vs oncology). |
| BBIO | PTCT | −0.151 | Suggestive big-day behavior too (§4); no product-level mechanism identified. |
| BCRX | BNTX | −0.137 | Suggestive big-day behavior (§4); no mechanism; 9× size gap. |

Takeaway: **no biotech pair in this universe carries a strong standing inverse daily correlation.** Anything real must show up conditionally, on big-move days — which is the next test.

## 4. Big-move-day co-movement — ranked inverse candidates

**Multiple-testing reality first:** 4,743 ordered tests at the 5% threshold produced **175 results with t ≤ −2 where one-sided chance alone predicts ~109**. The genuine inverse signal in this universe is a thin layer on top of noise. Additionally, the t ≤ −2 responders concentrate in **defensive/commercial names (INSM, MRK, HALO, UTHR, RYTM, BIIB, PFE, LLY, REGN — 4–7 hits each across unrelated movers)**: that pattern is the signature of a residual style factor (high-vol clinical smallcaps vs cash-flowing defensives moving intraday on risk appetite that SPY+XBI betas don't fully capture), NOT of pair-specific competitive displacement. Any pair whose "inverse" responder is a defensive commercial name and whose mover is a volatile clinical name gets discounted for this.

### 4a. Data-discovered pairs that survive inspection (both directions negative at 5%)

| A | B | resid corr | A→B (n, mean, t) | B→A (n, mean, t) | Opp-sign share | Mechanism? |
|---|---|---:|---|---|---|---|
| **AMLX** | **MIRM** | −0.124 | 77, −0.93%, **t=−2.61** (7%: 38, −1.73%, t=−3.29) | 19, −3.43%, **t=−3.41** (7%: 9, −5.21%, t=−3.73) | 68% / 89% | **None identified.** Avexitide (PBH) vs Livmarli/volixibat (cholestatic liver) don't compete. Strongest size-parity statistical inverse in the whole scan — and it has no story. |
| **BBIO** | **PTCT** | −0.151 | 28, −1.38%, t=−3.13 (7%: 12, t=−1.58) | 22, −1.27%, t=−2.66 (7%: 10, t=−2.07) | 75% / 80% | **None identified.** Both diversified rare-disease platforms; no head-to-head product found. |
| **BCRX** | **BNTX** | −0.137 | 36, −1.32%, t=−2.86 (7%: 14, t=−3.49 as responder dir) | 29, −1.40%, t=−2.81 | 57% / 79% | **None.** HAE vs mRNA-oncology. Size gap 9× ($2.5B vs $23.4B). Treat as noise. |
| SMMT | MRK | −0.172 | 92, −0.38%, t=−2.44 (7%: 42, −0.53%, t=−2.24) | MRK rarely moves 5% — insufficient n | — | **YES: ivonescimab vs Keytruda is real displacement.** But MRK is ~$280B: a −0.4% mean response to SMMT ±5% days is directionally right and economically useless as a proportionate hedge (confirms universe-candidates §3.2). |
| RVMD | IONS | −0.082* | 19, −0.75%, t=−2.67 (7%: 11, −1.25%, t=−4.50) | 10, −0.62%, t=−1.31 | — | Weak (no product overlap; possibly specialist-fund flow rotation). RVMD $43B = out of band; one-way significance only. |

*pair-level resid corr small.

### 4b. The prior (mechanistic) hedge pairs — measured, both directions, 5% threshold

This is the empirical test of the hedge map in `universe-candidates.md` §4:

| Pair | resid corr | A→B: n, mean, t (%opp) | B→A: n, mean, t (%opp) | Verdict on dailies |
|---|---:|---|---|---|
| **IONS→BBIO** | −0.082 | 10, −1.63%, t=−0.99 (60%) | 28, −2.10%, t=−1.46 (61%) | **Directionally inverse BOTH ways, not significant.** Consistent with the +14.1% catalyst-day print but the daily sample can't confirm it alone. |
| **PHVS→BCRX** | +0.169 | 58, **+1.22%, t=+3.15** (40%) | 36, **+1.71%, t=+2.30** (42%) | **POSITIVE — the opposite of a hedge on ordinary days.** HAE names trade as a class (see §5: on PHVS's own positive readout BCRX rose +7.5%). |
| IVA→MDGL | +0.014 | 93, +0.06%, t=+0.24 | 31, −0.39%, t=−0.72 | **Zero.** No daily inverse either way. |
| DYN→SRPT | +0.024 | 49, +0.07%, t=+0.06 | 55, +0.36%, t=+0.56 | Zero. |
| RGNX→SRPT | +0.062 | 72, +1.08%, t=+1.75 | 55, +0.73%, t=+1.12 | Mildly POSITIVE (gene-tx class sympathy). |
| SMMT→BNTX | +0.340 | 92, +1.52%, t=+3.67 | 29, +7.17%, t=+2.85 | **Strongly positive** — class read-through, as the ASCO event study said. |
| CMPS→ATAI | +0.469 | 92, +4.67%, **t=+6.98** | 109, +3.89%, t=+5.70 | Massively positive. Psychedelics are one trade. |
| CMPS→DFTX | +0.258 | 92, +2.44%, t=+6.57 | 72, +3.40%, t=+4.24 | Same. |
| ATAI→DFTX | +0.314 | 109, +2.70%, t=+6.77 | 72, +4.29%, t=+6.17 | Same. |
| IDYA→IMCR | +0.107 | 23, −0.14%, t=−0.37 | 13, +1.28%, t=+3.21 | Zero-to-positive. Confirms the structural weakness (complementary populations). |
| ALNY→IONS | +0.222 | 20, +1.96%, t=+3.78 | 10, +2.29%, t=+2.69 | Positive — silencer siblings co-move, never hedge each other. |
| ALNY→BBIO | +0.117 | 20, +0.77%, t=+0.62 | 28, −0.14%, t=−0.22 | Zero on dailies. |

**The two most important findings of this study are in this table:** (1) the only mechanistic pair whose dailies lean inverse in both directions is **IONS↔BBIO** — the same pair the catalyst event proved; (2) **PHVS↔BCRX, the book's second-ranked hedge, is empirically a POSITIVE-co-movement pair** on every measure available, including PHVS's own event day.

## 4. Big-move-day co-movement — ranked inverse candidates

_(pending)_

## 5. Catalyst-conditional overlay (both directions)

Two-factor residuals on verified binary-event days (dates from `universe-candidates.md` §2–3 unless noted). **All of these are n=1 observations — anecdotes by construction.**

| Event day | Name (resid) | Event | Peer residuals |
|---|---|---|---|
| 2026-07-09 | IONS **−24.4%** | CARDIO-TTRansform FAIL | **BBIO +14.1%** (inverse ✅) · ALNY −3.9% (sibling ✗) · BCRX −4.2% |
| 2026-07-30 | ALNY **−30.0%** | Q2 miss/guidance cut | BBIO −4.3% (✗ no inverse) · IONS −3.4% (sibling down) — *reverse-direction test for the ATTR cluster: commercial stumbles hit everyone, only clinical failure displaced share to BBIO* |
| 2026-05-01 | SMMT **−23.8%** | HARMONi-3 interim miss | **MRK +3.0%** (inverse ✅, but 26× size) · BNTX −5.2% (sympathy ✗) |
| 2026-06-01 | SMMT −6.6% | ASCO HARMONi-6 reaction | BNTX −2.8% (✗) · MRK −2.1% (✗) |
| 2025-12-03 | PHVS **+19.1%** | RAPIDe-3 POSITIVE | **BCRX +7.5% (moved WITH — hedge failed its only live test)** · NTLA +7.3% (class rally) |
| 2026-04-27 | NTLA −3.9% | HAELO Ph3 positive (sell-the-news) | PHVS +0.4% · BCRX −0.3% — no displacement either way |
| 2025-06-23 | CMPS **−49.4%** | COMP005 topline | ATAI −19.3% (✗) · DFTX −6.2% (✗) |
| 2026-06-22 | DFTX **+44.4%** | Ph3 GAD WIN | CMPS −3.8% · ATAI −3.8% (mild displacement ✅ — the only inverse print psychedelics ever produced) |
| 2026-08-12 | DFTX +3.1% | 2nd Ph3 WIN | CMPS +5.1% (✗ back to sympathy) · ATAI −1.0% |
| 2026-08-10 | SION **−91.8%** | PreciSION-CF FAIL | **VRTX +5.4%** (inverse ✅ — CFTR incumbent; but VRTX $128B vs SION $0.3B) |
| 2026-04-13 | RVMD **+38.9%** | RASolute-302 POSITIVE | IONS −2.1% · MRK −1.8% · AMGN −1.3% (all mildly inverse, all ~noise-scale) |
| 2026-04-13 | IDYA +5.3% | OptimUM-02 positive | IMCR −0.1% (nothing) |
| 2026-05-04 | MIRM +7.5% | VISTAS positive | AMLX −1.0% · GILD −0.1% (nothing conclusive) |
| 2026-07-21 | CLDX −2.3% | PN Ph2 miss | RGNX −4.2% (✗) |
| 2026-04-15 | TVTX −3.9% | FILSPARI approval (sell-news) | HALO +0.7% |
| 2026-04-13 | PRAX −2.6% | Essential3 positive (sell-news) | ACAD −3.0% · SUPN −2.3% · XENE −1.7% (all with) |
| 2026-06-01 | PRAX −1.5% | POWER miss/pause | ACAD +0.9% · SUPN −2.3% · XENE −0.2% |

**Both-directions scorecard for the headline pairs:**
- **IONS↔BBIO:** A-fails→B-rallies ✅ (n=1, +14.1%). B-direction untestable — BBIO had no dated binary in-sample; nearest proxy (ALNY's crash) shows commercial/guidance shocks do NOT produce the inverse (BBIO fell too). Inverse holds for *clinical displacement* events only, n=1.
- **PHVS↔BCRX:** A-wins→B-fell? **NO — BCRX ROSE +7.5%** on PHVS's win (n=1). B-direction untestable (no dated BCRX binary in-sample). Combined with t=+3.15 dailies: currently a sympathy pair. (Caveat: RAPIDe-3 was on-demand treatment, not the prophylaxis market Orladeyo owns; CHAPTER-3 could still displace — but there is zero supporting price evidence.)
- **AMLX↔MIRM:** on MIRM's one verified event (VISTAS, +7.5%), AMLX −1.0% — consistent in sign, trivial in size. The pair's statistical inverse comes from many un-cataloged big days (e.g., 2026-08-06: AMLX +8.9%/MIRM −12.0%, then both reversed next day), not from known catalysts.
- **SMMT↔MRK:** SMMT-fails→MRK-up ✅ (+3.0%, n=1) and dailies agree (t=−2.44) — the only pair where dailies AND a catalyst day both show the inverse. Useless in practice: proportionality ~26:1.

## 6. Ranked verdict table

Size data: FMP `stable/profile` 2026-08-14 ($ADV = averageVolume × price). All names NASDAQ, RH-tradeable.

| Rank | Pair | Daily-stat evidence | Catalyst evidence | Size parity | Mechanism | **Verdict** |
|---|---|---|---|---|---|---|
| 1 | **IONS ↔ BBIO** ($9.5B/$142M vs $15.6B/$250M) | Inverse both directions, NOT significant (t=−0.99/−1.46, n=10/28) | ✅ +14.1% BBIO on IONS fail (n=1); reverse-type event (ALNY commercial miss) did NOT produce inverse | Good | **Strong** (silencer vs stabilizer, same patients) | **Merely-plausible→credible.** The only pair where mechanism, catalyst print, and daily direction all agree. Still resting on n=1 catalysts + insignificant dailies — treat as a *conditional* hedge (clinical-displacement events only), not a standing correlation. |
| 2 | **AMLX ↔ MIRM** ($2.4B/$32M vs $6.1B/$93M) | **Strongest size-parity inverse in scan**: t=−2.61/−3.41 at 5% (n=77/19), t=−3.29/−3.73 at 7%, opp-sign 68%/89% | MIRM's VISTAS win → AMLX −1.0% (sign-consistent, trivial) | Good | **NONE — no competing products found** | **Statistically suggestive, mechanism-free.** With ~4,700 tests, the top mechanism-free result is exactly what noise (or a latent style factor) produces. Do NOT trade as a hedge; flag for out-of-sample monitoring — if it persists 6 months forward, investigate holders/flows. |
| 3 | **BBIO ↔ PTCT** ($15.6B/$250M vs $6.0B/$115M) | t=−3.13/−2.66 at 5% (n=28/22), opp-sign 75%/80%; weakens at 7% | None available | OK (2.6×) | None identified | **Suggestive, anecdotal-mechanism.** Same treatment as #2. |
| 4 | **SMMT → MRK** ($10.7B vs ~$280B) | t=−2.44 (n=92), one direction only | ✅ MRK +3.0% on SMMT's HARMONi-3 miss | **Fails (26×)** | Strong (ivonescimab vs Keytruda) | **Statistically credible direction, economically unusable.** Confirms displacement is real but flows to a mega-cap where it can't hedge proportionately. |
| 5 | BCRX ↔ BNTX ($2.5B vs $23.4B) | t=−2.86/−2.81 both dirs | None | Fails (9×) | None | **Noise.** |
| 6 | SION → VRTX | n/a (SION dead) | ✅ VRTX +5.4% on SION's −91% CF failure | Fails (400×) | Strong (CFTR incumbent) | **Anecdote (n=1), lesson only:** displacement prints DO happen when a challenger to a franchise dies — the beneficiary is just usually too big. |
| 7 | RVMD → IONS ($43B vs $9.5B) | t=−2.67/−4.50 one direction | RVMD +38.9% day → IONS −2.1% | Fails | Weak (fund-flow rotation at best) | Suggestive one-way; out of band. |

**Definitively negative results (worth as much as the positives):**
- **PHVS ↔ BCRX is NOT an inverse pair today** — positive co-movement t=+3.15/+2.30 and BCRX +7.5% on PHVS's own win. If used as the CHAPTER-3 hedge it must be justified purely on forward mechanism (prophylaxis-market displacement), against the price evidence.
- **IVA↔MDGL, DYN↔SRPT, IDYA↔IMCR: zero measurable inverse** on ~2 years of dailies. These hedges are faith-based until a live displacement event proves otherwise.
- **Class siblings are anti-hedges everywhere measured:** CMPS/ATAI/DFTX (t up to +7.0), SMMT/BNTX (+3.67), ALNY/IONS (+3.78), RGNX/SRPT (+1.75), and the HAE trio.
- **LABD** is a mechanical −3× XBI instrument (a levered sector short, decays over holds >~1 week) — it is the fallback beta damper, not a discovered pair, and was excluded from pair stats.

**Bottom line for the desk:** ~2 years of daily data across 77 names and ~2,850 pairs contains **no statistically-credible, size-parity, mechanistically-sound standing inverse pair**. The inverse that matters (IONS↔BBIO) is *event-conditional*: it appears only when a clinical binary displaces share between rivals, and is invisible-to-weak in daily correlations. Hedge design should therefore be event-typed (hedge only the displacement scenario, sized to the n=1 evidence) rather than correlation-based — consistent with universe-candidates §5's conclusion that ~75% of the book has no valid equity hedge.

## 7. Data caveats

- **yfinance, not a validated feed:** adjusted closes; unaudited splits/dividends; the project's own stack doc bans yfinance for trade decisions — this study is research-grade only.
- **Missing/dead tickers:** APLS, FOLD, SWTX, DVAX returned no data (presumed delisted/acquired — UNVERIFIED); CPRX had 5 stale rows and was dropped. Acquired candidates (AKRO, KALV, CDTX, ETNB, RNA/Avidity) were excluded up-front; **the recycled RNA ticker (now Atrium) would have silently spliced two companies** — keyed out by design.
- **DFTX = MNMD rebrand:** yfinance serves the full pre-Jan-2026 MindMed history under DFTX; rows before the rebrand are the same legal entity but pre-pivot economics.
- **SION** listed Feb 2025 → 381 obs; its −91.8% day dominates any statistic it touches.
- **Residualization limits:** two-factor (SPY+XBI) OLS with full-sample betas removes market+sector but NOT a latent "defensive commercial vs volatile clinical" style factor — the responder-concentration analysis (§4) shows that factor is real and inflates mega-/commercial-name "inverses." Full-sample betas also peek slightly (not tradeable-real-time), a minor look-ahead bias.
- **Multiple testing:** 175 of 4,743 ordered tests hit t ≤ −2 vs ~109 expected by one-sided chance — the excess (~66 results) is the entire real signal budget across the whole universe; individual |t|<3 results without mechanism should be presumed false.
- **Close-to-close event attribution:** pre-market PR events (e.g., IONS 7/9) are captured on the right day, but after-hours events would shift one day; each overlay date was taken from the two-source-verified table in `universe-candidates.md`.
- **Catalyst n:** every catalyst-conditional claim here is n=1–2 per pair-direction. None are statistically significant and none are labeled as such.

---
*Run complete 2026-08-14. Artifacts (prices, residuals, full pair CSVs) in session scratchpad; report is self-contained.*
