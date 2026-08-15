# Fund 1 — Universe Candidates: Verification & Hedge Research

**Status:** COMPLETE
**Date:** 2026-08-14
**Method:** FMP `stable` API for metrics (market cap, ADV, float, runway); WebSearch/WebFetch for two-source catalyst dates; FMP historical prices for event studies. Confidence tagged HIGH/MED/LOW per claim. Numbers never fabricated — anything unverifiable is marked UNVERIFIED.
**Criteria reference:** `docs/universe-criteria.html` (Screen A core-name criteria 1–11, Screen B hedge-peer criteria 1–8, hard disqualifiers).

---

## 1. FMP metrics table (all candidates)

Source: FMP `stable/profile` pulled 2026-08-14 (HIGH confidence for mkt cap / price / avg volume / exchange). **$ADV = profile averageVolume × price** (approximates 30-day dollar-ADV; MED confidence). **Float and short interest: FMP `shares-float` / short-interest endpoints returned HTTP 402 (premium tier) on this key → UNVERIFIED from FMP**; filled from secondary sources only where noted in cluster sections. **Runway: FMP balance-sheet/cash-flow endpoints also 402 → runway sourced from company press releases / 10-Q guidance found during catalyst research (cited per name), else UNVERIFIED.**

| Ticker | Company | Mkt Cap | $ADV (M/day) | Exchange | Active | Flags |
|---|---|---:|---:|---|---|---|
| PHVS | Pharvaris N.V. | $2.46B | $13.8 | NASDAQ | Yes | — |
| BCRX | BioCryst Pharmaceuticals | $2.48B | $45.6 | NASDAQ | Yes | — |
| NTLA | Intellia Therapeutics | $1.66B | $69.2 | NASDAQ | Yes | — |
| BBIO | BridgeBio Pharma | $15.6B | $249.9 | NASDAQ | Yes | ⚠ >$10B cap band |
| ALNY | Alnylam Pharmaceuticals | $30.6B | $334.8 | NASDAQ | Yes | ⚠ >>$10B — hedge-peer only |
| IONS | Ionis Pharmaceuticals | $9.5B | $142.9 | NASDAQ | Yes | near cap ceiling |
| MDGL | Madrigal Pharmaceuticals | $11.7B | $174.0 | NASDAQ | Yes | ⚠ >$10B cap band |
| AKRO | Akero Therapeutics | $4.5B | $140.0 | NASDAQ | **No** | ⚠ isActivelyTrading=false — M&A check §2.3 |
| IVA | Inventiva S.A. (ADR) | $239M | $3.8 | NASDAQ | Yes | ⚠ $ADV <$5M; near $200M cap floor |
| DYN | Dyne Therapeutics | $4.8B | $51.9 | NASDAQ | Yes | — |
| RGNX | REGENXBIO | $557M | $19.0 | NASDAQ | Yes | — |
| SRPT | Sarepta Therapeutics | $1.9B | $57.4 | NASDAQ | Yes | ⚠ flagged (Elevidys fallout — muddled attribution) |
| SION | Sionna Therapeutics | $292M | $3.1 | NASDAQ | Yes | ⚠ $ADV <$5M; 52wk range 4.01–54.97 (blowup) |
| CLDX | Celldex Therapeutics | $2.8B | $43.2 | NASDAQ | Yes | — |
| SMMT | Summit Therapeutics | $10.7B | $64.2 | NASDAQ | Yes | ⚠ >$10B cap band (was much higher) |
| RVMD | Revolution Medicines | $43.3B | $614.8 | NASDAQ | Yes | ⚠ >>$10B — outgrew the band |
| IDYA | IDEAYA Biosciences | $3.5B | $44.6 | NASDAQ | Yes | — |
| OLMA | Olema Pharmaceuticals | $929M | $13.4 | NASDAQ | Yes | — |
| CMPS | COMPASS Pathways | $1.8B | $57.7 | NASDAQ | Yes | — |
| MNMD | Mind Medicine (MindMed) | $1.6B | $52.3 | NASDAQ | **No** | ⚠ isActivelyTrading=false — M&A check §2.8 |
| PRAX | Praxis Precision Medicines | $10.2B | $171.5 | NASDAQ | Yes | ⚠ at $10B ceiling (post-ESSA win, $366/sh) |
| RARE | Ultragenyx Pharmaceutical | $2.6B | $55.5 | NASDAQ | Yes | — |
| MIRM | Mirum Pharmaceuticals | $6.1B | $92.6 | NASDAQ | Yes | — |
| TVTX | Travere Therapeutics | $5.8B | $140.6 | NASDAQ | Yes | — |
| INSM | Insmed | $26.8B | $434.0 | NASDAQ | Yes | ⚠ >>$10B — hedge-peer only |
| SVRA | Savara | $1.1B | $8.6 | NASDAQ | Yes | — |
| ACAD | ACADIA Pharmaceuticals | $4.8B | $47.9 | NASDAQ | Yes | — |
| PCVX | Vaxcyte | $8.4B | $84.3 | NASDAQ | Yes | — |
| AMLX | Amylyx Pharmaceuticals | $2.4B | $32.4 | NASDAQ | Yes | — |
| KALV | KalVista Pharmaceuticals | $1.4B | $95.5 | NASDAQ | **No** | ⚠ isActivelyTrading=false — M&A check §2.12 |
| CDTX | Cidara Therapeutics | $5.6B | $303.4 | NASDAQ | **No** | ⚠ inactive at $221.38 ≈ deal price — acquired |
| RNA | ~~Avidity~~ → **Atrium Therapeutics** | $220M | $2.6 | NASDAQ | Yes | ⚠ ticker RECYCLED — Avidity gone, RNA is now a different company |
| ETNB | 89bio | $2.2B | $80.0 | NASDAQ | **No** | ⚠ inactive at $14.84 ≈ GSK deal price — acquired |

All 33 tickers are NASDAQ-listed common/ADR → RH-tradeable in principle (HIGH); the five inactive ones are being/have been delisted via M&A (verified per-name in §2).

## 2. Catalyst verification by cluster (two sources per date)

### 2.1 HAE — PHVS, BCRX, NTLA

**PHVS (Pharvaris) — KEEP, core.** RAPIDe-3 on-demand Ph3 already hit (positive, Dec 3 2025: [GlobeNewswire](https://www.globenewswire.com/news-release/2025/12/03/3198720/0/en/Pharvaris-Announces-Positive-Topline-Data-from-RAPIDe-3-Pivotal-Study-Confirming-Potential-of-Deucrictibant-for-On-Demand-Treatment-of-HAE-Attacks.html)). **Next catalyst: CHAPTER-3 pivotal Ph3 topline (oral deucrictibant XR, HAE prophylaxis) — Q3 2026 window, i.e. imminent.** Two sources: [2026 Strategic Priorities, Jan 12 2026](https://www.globenewswire.com/news-release/2026/01/12/3216675/0/en/Pharvaris-Outlines-2026-Strategic-Priorities.html) and [Q1 2026 results, May 13 2026](https://ir.pharvaris.com/news-releases/news-release-details/pharvaris-reports-first-quarter-2026-financial-results-and). Type: WINDOW (Q3 2026), firm-up 48h out when company announces date. NDA for on-demand filed 1H 2026 → future PDUFA adds catalyst density. Cash €318M per 6-K ([StockTitan](https://www.stocktitan.net/sec-filings/PHVS/6-k-pharvaris-n-v-current-report-foreign-issuer-5f8ecf2bac62.html)) — runway comfortably clears the catalyst (MED; quarters not computed, FMP statements endpoint is premium). Single-asset company → clean attribution. Confidence: HIGH.

**BCRX (BioCryst) — RECLASSIFY: hedge peer first, core second.** Commercial (Orladeyo, oral HAE prophylaxis incumbent). Own near-term catalysts are soft: BCX17725 Netherton Ph1 PoC "by end of 2026" ([Q1 2026 earnings transcript](https://www.aol.com/articles/biocryst-bcrx-q1-2026-earnings-191137000.html), [Q1 2026 PR](https://www.biospace.com/press-releases/biocryst-reports-first-quarter-2026-financial-results-and-provides-business-update)); avoralstat DME discontinued. Fails Screen A criterion 1 (≥2 dateable binaries/yr) as a core name — but it is the cleanest RH-tradeable **inverse** to PHVS CHAPTER-3 (deucrictibant XR is aimed directly at Orladeyo's oral-prophylaxis market; PHVS failure → BCRX relief rally). Revenue-generating → no runway concern (HIGH). Confidence: HIGH on reclassification.

**NTLA (Intellia) — DOWNGRADE to tier-2/watch.** Its big binary already fired: HAELO Ph3 positive Apr 27 2026 (87% attack reduction; [GlobeNewswire](https://www.globenewswire.com/news-release/2026/04/27/3281473/0/en/intellia-therapeutics-reports-positive-phase-3-results-in-hereditary-angioedema-marking-a-global-first-for-in-vivo-gene-editing.html), [IR](https://ir.intelliatx.com/news-releases/news-release-details/intellia-therapeutics-reports-positive-phase-3-results)). Rolling BLA initiated → next binary is BLA acceptance/PDUFA (undated as of now) and MAGNITUDE Ph3 (ATTR-CM, ~2027). **No firm dateable catalyst in the next ~2 quarters → does not currently earn a core slot** (criterion 2). Re-add when PDUFA is set. Confidence: MED (PDUFA date could appear any week).

**KALV — EXCLUSION CONFIRMED.** Acquired by Chiesi Group at $27.00/share tender; deal announced Apr 29 2026, completed and delisted Jun 11 2026 ([Chiesi PR](https://www.chiesi.com/en/media-hub/press-releases/chiesi-group-to-acquire-kalVista-pharmaceuticals-expanding-its-global-rare-disease-portfolio), [TipRanks](https://www.tipranks.com/news/company-announcements/chiesi-group-completes-acquisition-of-kalvista-pharmaceuticals)). FMP still returns a stale quote (isActivelyTrading=false). HIGH.

### 2.2 ATTR-CM — BBIO, ALNY, IONS

**The defining event already happened: CARDIO-TTRansform failed Jul 9 2026.** Eplontersen (Ionis/AstraZeneca silencer) missed the primary composite endpoint in ATTR-CM on top of standard-of-care (majority on stabilizer) — [Ionis IR PR](https://ir.ionis.com/news-releases/news-release-details/update-cardio-ttransform-phase-3-trial-eplontersen-adults), [StockTitan, Jul 9 2026 2:00 AM](https://www.stocktitan.net/news/IONS/update-on-cardio-tt-ransform-phase-3-trial-of-eplontersen-in-adults-b8cvgp6ldlgr.html), [touchCARDIO](https://touchcardio.com/insight/eplontersen-misses-primary-endpoint-in-phase-3-cardio-ttransform-trial-for-attr-cardiomyopathy/). Full data at ESC Congress late Aug 2026 (residual catalyst). See §3.1 for the price study. HIGH.

**IONS (Ionis) — KEEP, core (MED).** $9.5B, just under cap ceiling. Diversified commercial base (Tryngolza, Wainua, Dawnzera) means attribution is less clean than a single-asset name, but it retains genuine binary catalysts (ESC full-data presentation Aug 2026; pipeline readouts flagged in [Q2 2026 results](https://ir.ionis.com/news-releases/news-release-details/ionis-reports-second-quarter-2026-financial-results-and) and the [2026 outlook PR](https://ir.ionis.com/news-releases/news-release-details/ionis-well-positioned-continued-momentum-and-substantial-value) citing "several pivotal data readouts" in 2026). Cash-flow: revenue-generating, no runway concern (HIGH).

**BBIO (BridgeBio) — KEEP despite $15.6B (band exception recommended).** Acoramidis (Attruby, ATTR-CM stabilizer) is the direct zero-sum beneficiary of silencer failures — empirically proven +15.1% on Jul 9 (§3.1). Own catalysts 2026: BBP-418 (LGMD2I) and encaleret (ADH1) regulatory/readout events — dates UNVERIFIED here (search budget), firm up in the per-name workflow pass. Role: **both core name AND the designated ATTR hedge peer for IONS**. Revenue-generating + partnered; runway not a concern (MED). Note: no longer "small/mid single-asset" — flag per criterion 3.

**ALNY (Alnylam) — EXCLUDE from core; WEAK as hedge.** $30.6B (>> band). Two disqualifying observations: (1) on the IONS failure it traded DOWN −3.3%/−4.5%/−3.6% over three sessions — same-class (silencer) read-through, i.e. it moves WITH a silencer failure, violating Screen B-4 for hedging IONS; (2) on Jul 30 2026 it dropped **−28.3% on its own Q2 miss + Amvuttra guidance cut** ([Yahoo/Zacks, Jul 31 2026](https://finance.yahoo.com/), [Endpoints News, Jul 30 2026](https://endpts.com/), via Google News index) — massive own-noise, violating B-3 catalyst-cleanliness. Keep only as a landscape reference. HIGH.

### 2.3 MASH — MDGL, AKRO, IVA

**AKRO — EXCLUDED (stale hypothesis).** Acquired by Novo Nordisk: announced Oct 9 2025 (up to $5.2B), shareholders approved Dec 3 2025, **closed and delisted Dec 9 2025** ([CNBC/Reuters Oct 9 2025](https://www.cnbc.com/), [GlobeNewswire Dec 9 2025](https://www.globenewswire.com/), via Google News index). FMP quote is a stale artifact. HIGH.

**IVA (Inventiva) — BEST CATALYST IN THE CLUSTER, but liquidity-marginal.** NATiV3 Ph3 topline (lanifibranor, MASH F2/F3) guided **H2 2026** — window catalyst, still pending as of Aug 14 2026. Two sources: CEO interview "Top-Line Data Due in H2" ([Yahoo Finance, Feb 13 2026](https://finance.yahoo.com/)) + "Ahead of Expected Phase 3 Data Readout" ([GlobeNewswire, Apr 22 2026](https://www.globenewswire.com/)). Funding: €130M financing secured Jun 16 2026 ([scanx.trade](https://scanx.trade/)) → runway clears the catalyst (MED). **Problem: $239M cap (at band floor) and $3.8M/day ADV (< $5M bar)** → Screen A criterion 4 fail at normal size. Verdict: include as **size-tiny tier** or exit-before-event; the binary is huge (sole remaining pan-PPAR Ph3 in MASH) but you cannot build a week-long position of real size. MED-HIGH.

**MDGL (Madrigal) — hedge peer first, core second.** $11.7B (above band). Commercial Rezdiffra story; no firm own-binary found in the next ~2 quarters (F4c outcomes data ~2027; recent newsflow is earnings + patents + Ph1 GLP-1 start — [StockTitan Jul 30 2026](https://www.stocktitan.net/news/MDGL/), Google News index Aug 2026). **Role: the natural RH-tradeable inverse for IVA's NATiV3** — lanifibranor failure entrenches Rezdiffra (zero-sum, same indication/population, different mechanism → passes B-1/B-4 on paper; no historical analog event study available for this pair → B-8 thin, size the hedge modestly). MED.

**Cluster note:** MASH is now a 2-name cluster (AKRO and ETNB both acquired). GLP-1 overhang (Novo/Lilly MASH programs) is a common-mode risk to BOTH IVA and MDGL — a semaglutide MASH data drop hits the pair together (B-7 caution).

### 2.4 Neuromuscular — DYN, RGNX, SRPT

**DYN (Dyne) — KEEP, one of the strongest core names.** $4.8B, $52M ADV. **Firm catalyst: PDUFA Jan 21 2027 for z-rostudirsen (DYNE-251, DMD exon-51)** — BLA accepted Jul 20 2026 with target action date set; two sources: [GlobeNewswire Jul 20 2026](https://www.globenewswire.com/) + [StockTitan Jul 20 2026](https://www.stocktitan.net/news/DYN/). Second program: z-basivarsen (DYNE-101, DM1) registrational cohort fully enrolled Jun 3 2026 → data late 2026/2027 (window, soften until dated). Raised $431M Jul 29 2026 → runway clears catalysts (HIGH). Catalyst density ≥2/yr: PASS. HIGH.

**RGNX (REGENXBIO) — KEEP, tier-2 (timing soft).** $557M, $19M ADV — inside band. AFFINITY DUCHENNE Ph3 positive topline already fired May 14 2026 ([PR Newswire](https://www.prnewswire.com/)); next binary = RGX-202 BLA filing/acceptance (near per [Quiver, Aug 6 2026](https://www.quiverquant.com/) "RGX-202 BLA nears") → PDUFA likely mid-2027 once accepted. Q2 2026 revenue $108M, net income positive — runway fine (HIGH). No firm date in next 2 quarters yet → tier-2 until BLA acceptance sets the clock. MED.

**SRPT (Sarepta) — FLAG CONFIRMED: exclude from core.** Elevidys sales −34% Y/Y after safety events, guidance cuts, CEO transition Aug 10 2026 (sources: Q2 results Aug 5-6 2026, [IBD/Yahoo via Google News](https://news.google.com/)). Price is a muddle of safety fallout + restructuring + financing — fails criterion 5 (single-catalyst attributability) and the "going-concern/muddle" spirit of the disqualifiers even though it's not literally going-concern. **Usable only cautiously on the hedge side** (it's the incumbent that benefits if DYN's exon-51 challenger is rejected), but its own-noise dominates → prefer sector ETF for DYN hedging. HIGH.

**Cluster hedge map:** DYN PDUFA ↔ SRPT (exon-51 incumbent, zero-sum on franchise, but B-3 own-noise fail) → fallback XBI/IBB beta hedge. RGNX ↔ SRPT (DMD gene-therapy rivals — RGNX historically rallied on Elevidys safety halts) — but both share gene-therapy-sentiment common-mode risk (B-7 partial fail).

### 2.5 CF — SION

**SION (Sionna) — EXCLUDE.** The binary already fired, catastrophically: **Aug 10 2026, SION-719 Phase 2a PreciSION-CF add-on trial missed; stock −91% to record low** ([Barron's Aug 10 2026](https://www.barrons.com/), [STAT Aug 10 2026](https://www.statnews.com/), [StockTitan Aug 10 2026](https://www.stocktitan.net/news/SION/)). Now $292M cap ≈ its $268M cash (Q2 10-Q), trading as a cash shell pivoting to SION-451 with no dateable near-term catalyst; ADV $3.1M also fails the bar. This name is a cautionary exhibit for the strategy (a −91% single-day binary), not a candidate. HIGH.

### 2.6 Urticaria — CLDX

**CLDX (Celldex) — KEEP, core.** $2.8B, $43M ADV, in-band. **Catalyst: EMBARQ-CSU Phase 3 topline (barzolvolimab, chronic spontaneous urticaria, 1,939 patients) — Q4 2026 window.** Two sources: [StockTitan Feb 25 2026](https://www.stocktitan.net/news/CLDX/) ("results due Q4 2026", enrollment finished 6 months early) + company Q2 2026 report cadence ([TradingView Aug 6 2026](https://www.tradingview.com/)). Runway: cash+securities $717.6M at Jun 30 2026 vs $73.5M Q2 net loss → **~9–10 quarters, clears catalyst easily** (HIGH). Caution: Ph2 prurigo nodularis miss Jul 21 2026 (mast-cell depletion without itch relief) already dented the de-risking narrative — expect elevated implied move into Q4. Hedge problem: CSU competitors are mega-caps (Novartis — Xolair/remibrutinib; Sanofi/Regeneron — Dupixent CSU) where barzolvolimab news is a rounding error → **no proportionate inverse exists; hedge = sector ETF beta or size discipline** (brutal-honesty note in §4). HIGH on catalyst, LOW on hedgeability.

### 2.7 Oncology — SMMT, RVMD, IDYA, OLMA

**SMMT (Summit) — KEEP, core. FIRM catalyst: PDUFA Nov 14 2026** (ivonescimab + chemo, EGFRm NSCLC post-TKI). Two sources: [Business Wire Jan 29 2026 BLA-acceptance PR](https://www.businesswire.com/) + [Yahoo Finance Feb 5 2026](https://finance.yahoo.com/) ("November 14 PDUFA date"), reconfirmed [Fierce Pharma Jul 22 2026](https://www.fiercepharma.com/). History 2026: HARMONi-3 interim miss May 1 (shares tumbled), HARMONi-6 China OS win presented at ASCO May 30-31. $10.65B — sits right at the cap ceiling (accept, it re-enters band on any drawdown). Attribution is clean (single asset). Hedgeability: poor (see §3.2/§4). HIGH.

**RVMD (Revolution Medicines) — EXCLUDE: outgrew the band.** RASolute-302 fired positive Apr 13 2026 (once-daily daraxonrasib beat chemo in 2L mPDAC; ASCO plenary; NEJM May 6 — [StockTitan Apr 13 2026](https://www.stocktitan.net/news/RVMD/), [PharmaLetter](https://www.thepharmaletter.com/)). Now $43.3B — 4× above the cap band; the defining binary already resolved. Watch only for RAS-class read-through effects on smaller RAS names. HIGH.

**IDYA (IDEAYA) — KEEP, core (window catalyst).** $3.5B, $44.6M ADV, in-band. OptimUM-02 registrational topline already positive Apr 13 2026 ([PR Newswire](https://www.prnewswire.com/)); NDA accepted under FDA **real-time review Apr 30 2026** ([StockTitan](https://www.stocktitan.net/news/IDYA/)) → **approval decision window H2 2026** (RTOR = no public firm PDUFA; treat as WINDOW and re-verify 48h out per criterion 2). Deep pipeline (IDE397, IDE161) adds catalyst density. Hedge caution: Immunocore (IMCR) is the incumbent in HLA-A2-POSITIVE mUM while darovasertib's trial is A2-NEGATIVE — populations are largely complementary, so the "competitor" inverse is structurally weak (B-1 partial fail). MED-HIGH.

**OLMA (Olema) — DROP to watch.** OPERA-01 Ph3 topline **pushed into 2027** (announced with Q2 results; stock −12.9% Aug 10-11 2026 — [TradingView Aug 11 2026](https://www.tradingview.com/), [scanx Aug 10 2026](https://scanx.trade/)). No dateable catalyst inside the horizon → fails criterion 2 today. Re-add when the 2027 window firms. HIGH.

### 2.8 CNS/psychedelics — CMPS, MNMD(→DFTX), PRAX

**MNMD NO LONGER EXISTS AS A TICKER — MindMed rebranded to Definium Therapeutics (NASDAQ: DFTX) Jan 2026** ([Fierce Pharma, Jan 12 2026: "Definium points the way forward as MindMed drops old identity"](https://www.fiercepharma.com/); confirmed by FMP profile DFTX = "Definium Therapeutics, Inc."). MM120→DT120 (LSD-based). 2026 record: Phase 3 GAD win Jun 22 2026 (+~40%, [Investing.com](https://www.investing.com/)) + $700M raise ([simplywall.st Jun 24 2026](https://simplywall.st/)) + second Phase 3 win Aug 12 2026 (+20%, [Investing.com](https://www.investing.com/)). **DFTX metrics (FMP, 2026-08-14): $5.66B cap, $42.63, ~$108.8M/day ADV, NASDAQ, active.** Remaining catalysts: remaining Ph3 (Panorama/Emerge — whichever hasn't read out) + NDA path — timing UNVERIFIED, firm up in per-name pass. Runway into 2028 pre-raise, now stronger (HIGH). **KEEP as core under DFTX, not MNMD.**

**CMPS (COMPASS Pathways) — KEEP, tier-2.** COMP006 Ph3 hit primary ~mid-Feb 2026; 6-month durability positive Jul 7 2026 ([Business Wire](https://www.businesswire.com/), [TipRanks](https://www.tipranks.com/)) though shares fell 8.6% in the aftermath ([Yahoo, Jul 17 2026](https://finance.yahoo.com/)) — this name habitually sells off on positive prints (see §3.3). Next binaries: NDA submission → acceptance → likely AdCom + PDUFA 2027 (all UNDATED today → criterion 2 keeps it tier-2 until the FDA clock starts). Q2 2026 net loss $253.8M (incl. non-cash?) — runway needs verification before any position (LOW on runway). MED.

**PRAX (Praxis) — KEEP, core. FIRM catalyst: relutrigine PDUFA Dec 27 2026** (rare pediatric epilepsy/DEE; NDA accepted Mar 30 2026, review extended Jun 29 2026 to Dec 27 — two sources: [GlobeNewswire Mar 30 2026](https://www.globenewswire.com/) + [StockTitan Jun 29 2026](https://www.stocktitan.net/news/PRAX/)). Second clock: ulixacaltamide (essential tremor) NDA accepted Apr 14 2026, **PDUFA early 2027** ([Seeking Alpha Jun 23 2026](https://seekingalpha.com/)). Essential3 Ph3 positive Apr 13 2026 already fired (source of the ~10× run to $366). Vormatrigine POWER missed/paused Jun 1 2026 (absorbed). $10.2B — at ceiling; ADV $171M. Catalyst density: PASS easily. Runway: ~$85M/q burn, post-run financing status UNVERIFIED — check before sizing. MED-HIGH.

### 2.9 Commercial rare-disease / PDUFA — RARE, MIRM, TVTX, INSM, SVRA, ACAD

**RARE (Ultragenyx) — KEEP, core. FIRM catalyst: UX111 (ABO-102, Sanfilippo MPS IIIA gene therapy) PDUFA Aug 23 2026 — nine days out.** Two sources: [StockTitan Feb 23 2026](https://www.stocktitan.net/news/RARE/) ("decision Aug. 23") + [GlobeNewswire Apr 2 2026 BLA-acceptance PR](https://www.globenewswire.com/). Context: CRL Jul 2025 (manufacturing), resubmission accepted Apr 2026. Q2 2026 revenue $214M, net loss $92M, guidance reaffirmed ([TradingView Aug 4 2026](https://www.tradingview.com/)) — revenue base + funded (MED-HIGH on runway). Additional 2026-27 catalysts: setrusumab OI Ph3 (UNVERIFIED timing). $2.6B, $55M ADV — in-band. HIGH.

**MIRM (Mirum) — KEEP, tier-2.** VISTAS (volixibat, PSC itch) hit primary May 4 2026 ([Business Wire](https://www.businesswire.com/)) — fired. Remaining: VANTAGE Ph3 (PBC) topline — expected 2026 but exact window UNVERIFIED in this pass; NDA path for PSC to follow. $6.1B, $92.6M ADV, commercial (Livmarli/Ctexli) → runway fine (MED). Firm up VANTAGE window before slotting trades. MED.

**TVTX (Travere) — DOWNGRADE to watch.** Its 2026 binary fired positive: FILSPARI approved for FSGS ~Apr 14-15 2026 (FDA extension Jan 13 2026 [Business Wire](https://www.businesswire.com/) → approval [IBT Apr 15 2026](https://www.ibtimes.com.au/)). Pegtibatinase HARMONY remains paused since Sep 2024 (manufacturing — [Fierce Pharma Sep 27 2024](https://www.fiercepharma.com/)) → no dateable near-term binary. Commercial execution story now. HIGH.

**INSM (Insmed) — EXCLUDE from core: $26.8B, ~2.7× above band.** Brensocatib launch + TPIP story is consensus large-cap now; a single readout no longer moves it ±30-70%. No search spent; exclusion on FMP metrics alone. Possible use: none needed as hedge (no core name competes with it). HIGH.

**SVRA (Savara) — KEEP, core. Catalyst: Molbreevi (molgramostim, aPAP) PDUFA ≈ Nov 22 2026** — original priority-review PDUFA Aug 22 2026 ([Yahoo Finance Mar 1 2026](https://finance.yahoo.com/)), FDA extended review 3 months Apr 16 2026 ([BioSpace](https://www.biospace.com/)) → derived new date ~Nov 22 2026 (MED — derived, not yet seen printed; re-verify 48h out per criterion 2; SA Aug 5 2026 confirms "cruising to PDUFA"). $1.1B in-band; ADV $8.6M — above bar but thin, cap position size. Runway UNVERIFIED (net loss widening) — check 10-Q before sizing. MED.

**ACAD (ACADIA) — KEEP, tier-2/core. Catalyst: ACP-204 (Alzheimer's disease psychosis) Ph3 topline Sept–Oct 2026 window** ([StockTitan Jul 20 2026](https://www.stocktitan.net/news/ACAD/); second source = company Q2 guidance backing the same window — verify in Q2 PR before trading; currently single-source → provisional). Commercial base (Nuplazid $, Daybue +20% Y/Y — [Market Index May 7 2026](https://www.marketindex.com.au/)) → no runway risk (HIGH), but diversification muddies single-event attribution (criterion 5 partial). MED.

### 2.10 Vaccines — PCVX

**PCVX (Vaxcyte) — KEEP, core. Catalyst: OPUS-1 (VAX-31 adult, PCV) Ph3 topline Q4 2026 window.** Two sources: [StockTitan Mar 23 2026](https://www.stocktitan.net/news/PCVX/) ("sets up 2026 Phase 3 data") + Q2 2026 PR "fully enrolled; OPUS-1 topline expected Q4 2026" ([TradingView Aug 5 2026](https://www.tradingview.com/)). $8.4B in-band, $84M ADV. Burn is violent (Q2 net loss $284.3M) but Vaxcyte historically holds multi-billion cash (balance UNVERIFIED on this key — confirm 10-Q cash before sizing; LOW-MED on runway detail, though no going-concern narrative exists). Hedge reality: competitors are PFE/MRK — no proportionate inverse (see §4). MED-HIGH.

### 2.11 Metabolic — AMLX

**AMLX (Amylyx) — KEEP, core. Catalyst: LUCIDITY Ph3 topline (avexitide, post-bariatric hypoglycemia) — Q3 2026, trial already completed → imminent.** Two sources: [Seeking Alpha Mar 4 2026](https://seekingalpha.com/) ("Q3 inflection point") + Q2 2026 PR/recap "LUCIDITY trial completion… topline data anticipated" ([TradingView Aug 6/10 2026](https://www.tradingview.com/)). Runway company-stated **into 2028** (cash $250.8M at Q2 vs $43.4M/q net loss — HIGH, two consecutive PRs state it). $2.4B, $32.4M ADV, in-band. First-in-class GLP-1 antagonist in PBH with no public direct competitor → clean attribution, zero hedgeability (see §4). HIGH.

### 2.12 Verify-excluded — KALV, CDTX, RNA (Avidity), ETNB, SRPT

| Ticker | Verdict | Evidence | Conf |
|---|---|---|---|
| KALV | **EXCLUDED — acquired.** Chiesi, $27.00/sh; announced Apr 29 2026, closed/delisted Jun 11 2026 | [Chiesi PR](https://www.chiesi.com/en/media-hub/press-releases/chiesi-group-to-acquire-kalVista-pharmaceuticals-expanding-its-global-rare-disease-portfolio), [TipRanks](https://www.tipranks.com/news/company-announcements/chiesi-group-completes-acquisition-of-kalvista-pharmaceuticals) | HIGH |
| CDTX | **EXCLUDED — acquired.** Merck, $221.50/sh (announced Nov 2025); FMP shows isActivelyTrading=false pinned at $221.38 ≈ deal price | FMP profile + deal-price pin (closing-date URL not re-pulled this pass) | MED-HIGH |
| RNA | **EXCLUDED — acquired AND ticker recycled.** Novartis closed Avidity $12B on Feb 27 2026; **"RNA" now = Atrium Therapeutics** (Avidity cardiac spin-out, $270M) | [Manila Times Feb 27 2026](https://www.manilatimes.net/), [BioPharma Dive Feb 27 2026](https://www.biopharmadive.com/) | HIGH |
| ETNB | **EXCLUDED — acquired.** GSK, $14.50/sh + CVR (announced Sep-Oct 2025); FMP inactive at $14.84 | FMP profile + deal-price pin | MED-HIGH |
| SRPT | **EXCLUDED from core — not acquired, but attribution-muddled** (Elevidys safety fallout, −34% rev, CEO change). See §2.4 | Q2 2026 results + Aug 10 2026 coverage | HIGH |

**Data-integrity warning for the pipeline:** the "RNA" ticker recycling means any historical price/fundamental series keyed by ticker will silently splice Avidity and Atrium together. The universe store must key names by CIK/legal entity, not ticker alone.

**Additional exclusions discovered this pass (not in the original exclude list):** AKRO (Novo Nordisk, closed Dec 9 2025 — §2.3), MNMD (ticker retired — rebrand to DFTX, §2.8), SION (blew up Aug 10 2026, −91% — §2.5), OLMA (catalyst slipped to 2027 — §2.7), RVMD ($43B, outgrew band — §2.7), INSM ($26.8B — §2.9), ALNY ($30.6B + own-noise — §2.2), TVTX (binary fired, nothing dateable next — §2.9), NTLA (nothing dateable near-term — §2.1).

## 3. Event studies (real price moves)

### 3.1 IONS CARDIO-TTRansform failure (Jul 9 2026) → BBIO / ALNY reaction

Prices: Yahoo Finance daily closes (FMP historical endpoint is premium-gated on this key). Event = pre-market PR Jul 9 2026. **All numbers below are real closes, HIGH confidence.**

| Date | IONS (target, failed) | BBIO (stabilizer competitor) | ALNY (silencer competitor) |
|---|---:|---:|---:|
| Jul 8 (d−1) | $84.46 | $78.33 | $323.50 |
| **Jul 9 (event)** | **−23.90% → $64.27** | **+15.12% → $90.17** | **−3.31% → $312.79** |
| Jul 10 (d+1) | −9.37% → $58.25 | −4.75% → $85.89 | −4.49% → $298.76 |
| Jul 13 (d+2) | −2.58% → $56.75 | −3.27% → $83.08 | −3.58% → $288.06 |
| 3-day cumulative | **−32.8%** | **+6.1%** | **−11.0%** |

**Did the inverse relationship hold?**
- **BBIO: YES, emphatically** — +15.1% on the day a rival mechanism failed in its indication. This is the competitive-displacement payoff Screen B is built around (silencer add-on failure → stabilizer franchise entrenched). Note the giveback (−4.8%, −3.3%) on d+1/d+2 — the hedge pays on the event day; exit discipline matters.
- **ALNY: NO — it moved WITH the loser.** Despite Amvuttra being an approved ATTR-CM competitor that "should" benefit, the market traded silencer-class read-through (doubt about silencers on top of stabilizers, the same population Amvuttra expansion needs). Same-mechanism "competitors" are read-through siblings, not hedges (Screen B-4 confirmed empirically).
- Bonus lesson: ALNY's own −28.3% on Jul 30 2026 (Q2/guidance) shows a "hedge peer" carrying its own event risk inside a hold window can dwarf the protection (Screen B-3).

### 3.2 SMMT ASCO print (May 30–Jun 1 2026) → PD-1/VEGF peers

Event: HARMONi-6 China OS data (ivonescimab +chemo cut death risk 34% vs tislelizumab +chemo, 1L squamous NSCLC) presented at ASCO May 30–31 2026 ([Fierce Pharma](https://www.fiercepharma.com/), [STAT](https://www.statnews.com/), [BioPharma Dive](https://www.biopharmadive.com/), May 30-31 2026). **Positive print — yet SMMT sold off** ("China data doesn't prove global benefit" — [BioSpace Jun 1 2026](https://www.biospace.com/)). Real closes (Yahoo):

| Date | SMMT | BNTX (same class, PD-L1xVEGF) | MRK (incumbent PD-1) | XBI (sector) | SPY |
|---|---:|---:|---:|---:|---:|
| **Jun 1 (first session post-print)** | **−10.43%** | −4.43% | −2.99% | −2.25% | +0.27% |
| Jun 2 | −5.41% | −2.79% | +0.42% | −4.39% | +0.14% |
| 2-day cum | **−15.3%** | −7.1% | −2.6% | −6.5% | +0.4% |

**Did the inverse relationship hold? Mostly NO — and the sector confound was large.**
- A biotech-wide selloff (XBI −6.5% over the two days vs SPY flat) accounts for roughly half of every name's move; SMMT's idiosyncratic move was ≈ −9% ON POSITIVE DATA (sell-the-news / translatability discount). Second CMPS-style lesson: sign-of-topline ≠ sign-of-move.
- **BNTX moved WITH SMMT** (≈ −0.6% to −2.7%/day beyond sector): same-class PD-(L)1xVEGF names trade in sympathy, not inversely (Screen B-4: class read-through, disqualified as hedge).
- **MRK (the displacement candidate) barely responded** (−3.0% day 1 ≈ sector + noise; +0.4% day 2): at $280B+, ivonescimab news is diluted ~30× relative to SMMT — directionally consistent with displacement but useless as proportionate protection.
- Practical implication: **SMMT's Nov 14 PDUFA has no proportionate long-side equity hedge.** The only instruments that move enough are same-class names — in the SAME direction. Hedge = reduce size / XBI-IBB short-proxy via inverse ETF (LABD is XBI-3x-inverse — RH-tradeable but decays; only for ~1-week holds) / accept unhedged with tiny size.

### 3.3 CMPS COMP005 topline (Jun 23 2025) → psychedelic peer reaction

Event: COMP005 Phase 3 (psilocybin/COMP360, TRD) topline Jun 23 2025 — **statistically significant on the primary endpoint, yet the stock was cut in half** (effect size / durability doubts). Real closes (Yahoo):

| Date | CMPS | ATAI (class peer) | XBI |
|---|---:|---:|---:|
| Jun 20 2025 (d−1) | $4.63 | $2.48 | $82.38 |
| **Jun 23 2025 (event)** | **−49.24% → $2.35** | **−18.55% → $2.02** | −0.13% |
| Jun 24 (d+1) | +7.66% | +4.46% | +1.88% |

(The −49.2% close-to-close is consistent with the widely reported "−42%…−46%" intraday/at-print figures.)

**Did the inverse hold? NO — decisively.**
- **ATAI fell −18.6% on CMPS's bad print** with XBI flat: pure class read-through DOWN. A psychedelic "competitor" is not a hedge; the whole modality reprices together (Screen B-4's disqualifier, empirically).
- **MNMD same-day move: UNVERIFIED** — MindMed's price history is no longer retrievable from free sources (ticker rebranded to DFTX Jan 2026; Yahoo purged the MNMD series, FMP history is premium-gated). Given ATAI's −18.6% and sector coverage describing a group-wide selloff, the direction was almost certainly down as well, but no number is claimed. (LOW)
- **Second, independent lesson: positive topline ≠ positive move.** CMPS −49% on a statistically significant WIN. The desk's payoff matrix must model "win-but-sell-off" as a real outcome class (also seen in SMMT §3.2 and CMPS again Jul 2026).
- Hedge implication for CNS/psychedelics: CMPS/DFTX/ATAI mutually amplify, never offset → hedge = size discipline or inverse-ETF beta only.

## 4. Hedge search per core name (any RH-tradeable asset)

Instruments considered: competitor equities, sector ETFs (XBI, IBB, ARKG), inverse ETFs held long (LABD = 3× inverse XBI — RH-tradeable, daily-reset decay makes it usable only for ~1-week event windows), larger peers. Equities-only v1 (no options), long-only per strategy design.

| Core name | Best available hedge | What it actually hedges — brutally honest |
|---|---|---|
| **PHVS** | **BCRX long** | **Genuine idiosyncratic inverse.** Deucrictibant XR attacks Orladeyo's oral-prophylaxis HAE market; CHAPTER-3 failure → BCRX relief rally is a real zero-sum mechanism (B-1/B-4 pass). No same-window BCRX binary found (B-3 pass — Netherton data is "by YE"). Untested empirically (B-8 thin): no prior head-to-head analog. Secondary: NTLA rises on PHVS prophylaxis failure (lonvo-z gains the market) but NTLA carries gene-editing beta noise. |
| **IONS** | **BBIO long** | **The only empirically PROVEN inverse in the book: +15.1% on IONS's Jul 9 failure (§3.1).** Hedges the ATTR-silencer component of IONS only; IONS is diversified (Tryngolza/olezarsen events are NOT hedged by BBIO). Watch B-3: BBIO has its own 2026 regulatory calendar — check event windows before pairing. |
| **BBIO** (when core) | IONS/ALNY partial | Weak. If Attruby stumbles commercially, share flows to silencers — but ALNY is 2× BBIO's size (diluted) and IONS is diversified. Mostly sector beta → LABD/size discipline. |
| **IVA** | **MDGL long** | Real zero-sum on paper (NATiV3 fail → Rezdiffra entrenched; NATiV3 win → MDGL multiple compresses). No historical analog trade to verify (B-8 thin) and GLP-1 headlines are a shared common-mode risk (B-7 partial fail). Position must be small anyway (IVA liquidity). |
| **MDGL** (when core) | IVA long (symmetric pair) | Same pair traded from the other side; IVA leg is liquidity-capped at tiny size — imperfect. |
| **DYN** | SRPT long (degraded) / LABD | SRPT is the exon-51 incumbent — direction is right on a DYN CRL — but SRPT's own Elevidys/financing noise (±10-15% weeks) can swamp the signal (B-3 fail). Honest: treat DYN as ETF-hedged or size-run. |
| **RGNX** | SRPT long (degraded) | Same SRPT caveat + DMD gene-therapy names share FDA-safety-sentiment common-mode (B-7 fail): an FDA gene-tx safety action sinks both. Partial hedge at best. |
| **CLDX** | none proportionate → LABD/size | CSU competitors are NVS ($200B+) and SNY/REGN — barzolvolimab outcome is noise to them. **No valid equity hedge; fallback rule applies.** |
| **SMMT** | none → LABD/size | Empirically shown §3.2: MRK too diluted (~30×), same-class BNTX moves in SYMPATHY. **Unhedgeable long-only; PDUFA Nov 14 must be sized as naked binary.** |
| **IDYA** | IMCR long (structurally weak) | KIMMTRAK serves HLA-A2-POSITIVE mUM; darovasertib's label pursuit is A2-NEGATIVE — populations complementary, displacement minimal (B-1 fail). ETF/size fallback. |
| **DFTX** | none → LABD/size | CMPS/ATAI are class-sympathy names (move WITH, §3.3). No inverse exists in psychedelics. |
| **CMPS** | none → LABD/size | Same; proven by ATAI −18.6% on CMPS's own crash. |
| **PRAX** | none clean → LABD/size | DEE "competitors" (STOK zorevunersen = Dravet-specific) target different genotypes; no zero-sum public pure-play against relutrigine. |
| **RARE** | none → LABD/size | No surviving public Sanfilippo competitor. Mitigant: RARE is multi-product commercial — UX111 CRL is a partial, not existential, hit (smaller expected move than pure binaries). |
| **MIRM** | GILD long (very diluted) | Livdelzi (PBC incumbent) gains if volixibat disappoints — at $100B+ GILD the move is negligible. ETF/size fallback. |
| **SVRA** | none → LABD/size | Molgramostim is alone in aPAP. Naked binary; size accordingly. |
| **ACAD** | none proportionate | ADP rival Cobenfy sits inside $100B+ BMY. Mitigant: ACAD's Nuplazid/Daybue revenue floors the downside vs pure clinical names. |
| **PCVX** | none proportionate → LABD/size | PCV incumbents PFE/MRK are ~30-60× larger. VAX-31 miss barely registers there. Naked binary. |
| **AMLX** | none → LABD/size | No public PBH competitor exists at all. Cleanest attribution in the universe, zero hedgeability. |

## 5. Hedgeability verdict

**Genuinely hedgeable (real competitive-displacement equity inverse): ~4 of ~18 core names (~22%)** — IONS↔BBIO (proven), PHVS↔BCRX (mechanistically sound, untested), IVA↔MDGL (sound, untested, common-mode caveat), and the degraded DYN/RGNX↔SRPT pair (~half-credit). **Roughly 75% of the tradeable universe has NO valid long-equity hedge** — the competitor is either a mega-cap (CLDX, PCVX, MIRM, ACAD, SMMT), a class-sympathy sibling (SMMT/BNTX, CMPS/DFTX/ATAI), population-complementary (IDYA/IMCR), or nonexistent (AMLX, SVRA, RARE, PRAX).

The three event studies make the structural reason explicit: **same-class peers move WITH the event name (validation read-through), and different-mechanism displacement winners are usually too big to move.** The only reliable inverse found (BBIO) is exactly the configuration Screen B predicts: similar-size, single-franchise, different-mechanism, same-patient-population rival.

**Recommended scope decision (accept fallback + lean on beta hedges + concentrate where real hedges exist):**
1. **Run the hedged clusters at full intended size** — ATTR (IONS/BBIO), HAE (PHVS/BCRX), MASH (IVA/MDGL at IVA's liquidity-capped size).
2. **For everything else, accept the criteria doc's own fallback rule as the norm, not the exception**: naked binaries sized so a −50% single-name event costs ≤ the weekly risk budget; LABD (or short-dated XBI exposure reduction) only as an event-week sector-beta damper — it does NOT hedge idiosyncratic outcomes and decays.
3. **Do not manufacture fake hedges** — pairing SMMT with MRK or CLDX with NVS creates the illusion of protection while adding a second uncorrelated position.
4. **Prioritize the options capability (Polygon + RH options) on the roadmap**: for ~75% of this universe, defined-risk structures (puts/put-spreads on the core name) are the only true idiosyncratic hedge. The equities-only constraint is the binding limitation of v1, and the universe research says so loudly.

## 6. Final recommended ~20-name ranked universe

## 6. Final recommended ~20-name ranked universe

Ranked by: catalyst firmness × in-band metrics × liquidity × hedgeability. "Hedge" column = best RH-tradeable instrument per §4. Catalyst sources are in §2 (each has ≥2 sources unless marked).

| # | Ticker | Cluster | Mkt cap | $ADV | Next catalyst (type) | Hedge | Conf |
|---|---|---|---:|---:|---|---|---|
| 1 | RARE | Rare/gene tx | $2.6B | $55M | **PDUFA Aug 23 2026** (FIRM) — UX111 Sanfilippo | none → size/LABD | HIGH |
| 2 | SMMT | Onc (NSCLC) | $10.7B⚠ | $64M | **PDUFA Nov 14 2026** (FIRM) — ivonescimab EGFRm | none → size/LABD | HIGH |
| 3 | PRAX | CNS (epilepsy) | $10.2B⚠ | $172M | **PDUFA Dec 27 2026** (FIRM) — relutrigine DEE; + ulixacaltamide PDUFA early 2027 | none clean → size/LABD | HIGH |
| 4 | DYN | Neuromuscular | $4.8B | $52M | **PDUFA Jan 21 2027** (FIRM) — z-rostudirsen DMD; + DM1 data late '26 | SRPT (degraded) → LABD | HIGH |
| 5 | PHVS | HAE | $2.5B | $14M | **CHAPTER-3 topline Q3 2026** (WINDOW, imminent) | **BCRX (real inverse)** | HIGH |
| 6 | AMLX | Metabolic | $2.4B | $32M | **LUCIDITY topline Q3 2026** (WINDOW, trial complete) | none → size/LABD | HIGH |
| 7 | SVRA | Rare pulm | $1.1B | $8.6M | **PDUFA ~Nov 22 2026** (DERIVED from Aug 22 + 3mo ext — re-verify) | none → size/LABD | MED |
| 8 | CLDX | Immunology/derm | $2.8B | $43M | **EMBARQ-CSU Ph3 topline Q4 2026** (WINDOW) | none → size/LABD | HIGH |
| 9 | PCVX | Vaccines | $8.4B | $84M | **OPUS-1 VAX-31 adult topline Q4 2026** (WINDOW) | none → size/LABD | MED-HIGH |
| 10 | IONS | ATTR/cardio-met | $9.5B | $143M | ESC full CARDIO-TTRansform data late Aug 2026 (SOFT); pipeline readouts H2'26 | **BBIO (proven +15.1%)** | MED |
| 11 | IDYA | Onc (mUM) | $3.5B | $45M | FDA RTOR decision H2 2026 (WINDOW, no public PDUFA) | IMCR (weak) → LABD | MED-HIGH |
| 12 | DFTX (ex-MNMD) | CNS (psychedelic) | $5.7B | $109M | Remaining Ph3 (Panorama/Emerge) + NDA path (TIMING UNVERIFIED — firm up) | none → size/LABD | MED |
| 13 | IVA | MASH | $239M⚠ | $3.8M⚠ | **NATiV3 topline H2 2026** (WINDOW) — biggest binary, smallest float | **MDGL (sound, untested)** | MED-HIGH |
| 14 | ACAD | CNS (ADP) | $4.8B | $48M | ACP-204 Ph3 topline Sept–Oct 2026 (WINDOW — single-source, verify) | none → size | MED |
| 15 | MIRM | Rare hepatology | $6.1B | $93M | VANTAGE PBC Ph3 topline 2026 (WINDOW UNVERIFIED — firm up) | GILD (very diluted) | MED |
| 16 | BBIO | ATTR | $15.6B⚠ | $250M | Own reg. events (dates UNVERIFIED) — **primary role: IONS hedge peer** | IONS/ALNY partial | MED |
| 17 | BCRX | HAE | $2.5B | $46M | BCX17725 PoC by YE 2026 (SOFT) — **primary role: PHVS hedge peer** | n/a (is the hedge) | HIGH |
| 18 | MDGL | MASH | $11.7B⚠ | $174M | F4c outcomes ~2027 (SOFT) — **primary role: IVA hedge peer** | IVA (symmetric) | MED |
| 19 | RGNX | Neuromuscular | $557M | $19M | RGX-202 BLA acceptance → PDUFA ~2027 (SOFT until accepted) | SRPT (degraded) | MED |
| 20 | CMPS | CNS (psychedelic) | $1.8B | $58M | NDA submission → AdCom/PDUFA 2027 (UNDATED — tier-2) | none → size | MED |

**Watch list (re-add on trigger):** NTLA (when lonvo-z PDUFA is set), OLMA (when OPERA-01 2027 window firms), TVTX (if pegtibatinase restarts), SRPT (if Elevidys noise settles → hedge-peer only).
**Hard-excluded:** KALV, CDTX, RNA/Avidity, ETNB, AKRO (all acquired), MNMD (ticker retired → DFTX), SION (post-blowup shell), RVMD/INSM/ALNY (out of band).

**Therapeutic-area spread check (criterion 7): PASS** — HAE, ATTR/cardio-metabolic, MASH, neuromuscular, immunology/derm, oncology, CNS, rare pulm/hepatology/gene-tx, vaccines, metabolic (≥4 areas, no cluster >4 names).

**Near-term event calendar implied by this universe (next ~90 days):** RARE Aug 23 · IONS ESC late-Aug · PHVS Q3 window · AMLX Q3 window · ACAD Sept-Oct window · SMMT Nov 14 · SVRA ~Nov 22 · CLDX Q4 · PCVX Q4 · IVA H2.

---

*Report complete 2026-08-14. All prices/caps/ADV = FMP stable/profile pull 2026-08-14; event-study prices = Yahoo Finance daily closes; catalyst dates per inline citations. FMP free tier blocked float/short-interest/statements endpoints (HTTP 402) — float and short interest remain UNVERIFIED for all names and runway is press-release-sourced where stated; fill via the per-name workflow before seed_universe.csv is cut.*
