# Inverse Exposure Instruments for a Long-Only Equities Account

**Purpose:** every realistic way to get short-like exposure to a biotech catalyst long, buyable as a common share or US-exchange-listed ETF only (Robinhood agentic MCP constraint: no options, no futures, no OTC, no sub-$1, no crypto).

**Date of research:** 2026-08-15
**Data sources:** yfinance (Yahoo Finance) daily OHLCV + fund profile data, fetched live on 2026-08-15; FMP API where noted. Every number below was fetched, not recalled, unless explicitly marked `UNVERIFIED`.

**Standing lessons honored here:**
- Same-disease siblings are read-through TRAPS (PHVS/BCRX both rose on one's win). A class win lifts the class.
- Displacement flows from a challenger's failure go to the entrenched mega-cap incumbent, not a same-size peer.
- Prior 77-ticker pair study found no statistically airtight single-name inverse pair on daily returns. Single-name inverses must be validated per-event, not per-correlation.

---
## Section 1 — Inverse / bear ETFs (the workhorse)

All figures fetched live via yfinance on 2026-08-15. "$ vol/day" = 3-month average daily dollar volume (6-month for SPDN/QQQD). Correlations are 2-year daily returns vs XBI, n=500 trading days, 2024-08-16 → 2026-08-14.

**Headline structural fact: there is NO live -1x biotech ETF.** Direxion's LABS (Daily S&P Biotech Bear 1X) is delisted — Yahoo still returns a name stub but zero price history. Direxion's PILS (pharma bear 2x) is likewise dead. The only live biotech bears are LABD (-3x) and BIS (-2x), and BIS is untradeable (see below). If you want -1x biotech-index exposure, you build it by sizing LABD at ~1/3 notional.

### 1a. Biotech / healthcare sector bears

| Ticker | Name / Issuer | Inverses | Lev | ER | AUM | $ vol/day | Verdict |
|---|---|---|---|---|---|---|---|
| **LABD** | Direxion Daily S&P Biotech Bear 3X (NYSE Arca) | S&P Biotechnology Select Industry Index (same index as XBI — modified equal weight, small/mid-cap heavy) | **-3x** | 1.07% | $65.9M | **$107M** | **The workhorse.** r = -0.999 vs XBI, fitted beta -2.98 (n=500). Liquid. |
| **BIS** | ProShares UltraShort Nasdaq Biotechnology (Nasdaq) | Nasdaq Biotechnology Index (cap-weighted — AMGN/GILD/VRTX dominate) | -2x | 0.95% | **$2.3M** | **$102K** | **Zero-liquidity death-trap.** ~$100K/day means you ARE the volume. Also wrong index: NBI is mega-cap weighted, poor proxy for small-cap catalyst names. Avoid. |
| **RXD** | ProShares UltraShort Health Care (NYSE Arca) | S&P Health Care Select Sector Index (UNH/LLY/JNJ-heavy) | -2x | 0.95% | **$3.2M** | **$98K** | **Death-trap.** Same story. r only -0.565 vs XBI anyway — big-pharma index, not biotech. Avoid. |
| **SARK** | Tradr 1X Short Innovation Daily (Nasdaq) | ARK Innovation ETF (ARKK) — speculative growth incl. some genomics | -1x | 0.99% | $46.8M | $5.7M | Tradeable but thin. r = -0.583 vs XBI. It's an anti-speculative-growth instrument, not an anti-biotech one. Niche. |
| LABS | Direxion S&P Biotech Bear 1X | — | -1x | — | — | — | **DELISTED.** No price history on Yahoo. Do not plan around it. |
| PILS | Direxion Pharma & Medical Bear 2X | — | -2x | — | — | — | **DELISTED.** |

### 1b. Broad-market bears (the tape hedge; small-cap inverse matters most for catalyst names)

| Ticker | Name / Issuer | Inverses | Lev | ER | AUM | $ vol/day | r vs XBI (2y daily) |
|---|---|---|---|---|---|---|---|
| **RWM** | ProShares Short Russell2000 (NYSE Arca) | Russell 2000 | **-1x** | 0.95% | $134M | $248M | **-0.677** — the best-fitting broad -1x for small-cap biotech |
| TWM | ProShares UltraShort Russell2000 | Russell 2000 | -2x | 0.95% | $44M | $12.7M | (scales RWM) — thinner, OK |
| **TZA** | Direxion Small Cap Bear 3X (NYSE Arca) | Russell 2000 | -3x | 0.99% | $225M | **$839M** | (scales RWM) — far more liquid than SRTY |
| SRTY | ProShares UltraPro Short Russell2000 | Russell 2000 | -3x | 0.95% | $80M | $59M | (scales RWM) |
| **SPDN** | Direxion Daily S&P 500 Bear 1X (NYSE Arca) | S&P 500 | -1x | **0.48%** | $229M | $549M | ~ -0.59 (via SPX) — cheapest -1x SPX |
| SH | ProShares Short S&P500 (NYSE Arca) | S&P 500 | -1x | 0.89% | $928M | $292M | -0.592 |
| SDS | ProShares UltraShort S&P500 | S&P 500 | -2x | 0.91% | $418M | $178M | (scales SH) |
| SPXU | ProShares UltraPro Short S&P500 | S&P 500 | -3x | 0.90% | $432M | $336M | (scales SH) |
| PSQ | ProShares Short QQQ (NYSE Arca) | Nasdaq-100 | -1x | 0.95% | $759M | $220M | -0.547 |
| QID | ProShares UltraShort QQQ | Nasdaq-100 | -2x | 0.95% | $274M | $288M | (scales PSQ) |
| SQQQ | ProShares UltraPro Short QQQ (Nasdaq) | Nasdaq-100 | -3x | 0.95% | $2.0B | **$2.55B** | (scales PSQ) |
| QQQD | Direxion Mag7 Bear 1X (NYSE Arca) | Magnificent 7 | -1x | 0.50% | $34M | $2.1M | thin; anti-megacap-tech, not anti-biotech |

### 1c. Single-stock bear ETF (special case)

| Ticker | Name | Lev | ER | AUM | Status |
|---|---|---|---|---|---|
| ELIS | Direxion Daily LLY Bear 1X (Nasdaq) | -1x LLY | 1.01% | $2.9M | **Effectively dead** — Yahoo shows no trade prints since 2026-04-10. Treat as unavailable; likely closing. `UNVERIFIED` whether formally delisted. |

No single-stock bear ETFs exist for any small/mid-cap biotech (probed LLYD, LLYS, MRKD, NVOD, AMGD — all 404). Inverse single-stock products only ever launched on mega-caps, and the pharma ones are dying of low AUM.

### 1d. The two warnings that apply to everything above

**Daily-rebalance decay (leveraged/inverse funds).** LABD, TZA, SQQQ, SDS, etc. deliver -2x/-3x of the index's return FOR ONE DAY, then rebalance. Over multi-week holds in a choppy tape they bleed value even if the index goes nowhere (volatility drag). These are event-window instruments: put the hedge on days before the catalyst, take it off days after. -1x funds (RWM, SPDN, SH, PSQ) decay far less but still compound path-dependently. None of these are buy-and-hold hedges.

**Sector-beta damper ≠ binary hedge — per instrument, bluntly:**
- **LABD**: hedges "XBI sells off 5% into a risk-off tape." Does NOTHING for your single name gapping -70% on a failed readout — one small-cap is well under 1% of the S&P Biotech Select Industry Index, so your ticker's -70% moves XBI (and thus LABD) by rounding-error amounts.
- **BIS / RXD**: same limitation, plus you can't get out of the position. Double-avoid.
- **RWM / TWM / TZA / SRTY**: hedges "small caps broadly de-rate" (rates, risk appetite). Zero idiosyncratic protection.
- **SPDN / SH / SDS / SPXU / PSQ / QID / SQQQ**: hedges the macro tape only. Weakest link to a biotech catalyst name of anything on this page.
- **SARK**: hedges "speculative growth unwinds." Zero idiosyncratic protection.

Nothing in Section 1 pays off on YOUR readout failing. It pays off on the market/sector falling, which sometimes coincides and usually doesn't.

---
## Section 2 — Single-name genuine inverse relationships (event-tested)

Method: for each proposed pair, (1) name the economic mechanism, (2) pull the actual same-day closing moves on real catalyst dates (yfinance daily closes, adjusted), (3) report the 2-year daily-return correlation with sample size so nobody mistakes an event inverse for a continuous hedge. Window for correlations: 2024-08-15 → 2026-08-14, n=501 trading days.

### 2a. VALIDATED: UTHR ↔ LQDA — binary approval/litigation rivals (the best zero-sum pair found)

**Mechanism (one sentence):** Liquidia's Yutrepia is a direct substitute attacking United Therapeutics' Tyvaso franchise (the majority of UTHR's revenue), so FDA/court outcomes between them are close to winner-take-share zero-sum.

Event prints (same-day closes, yfinance):

| Date | LQDA | UTHR | XBI | Read |
|---|---|---|---|---|
| 2024-08-19 | **-30.6%** | **+8.6%** | +3.2% | Clean inverse: LQDA setback → UTHR up ~5% in excess of the tape. (News driver consistent with a Yutrepia regulatory/litigation setback; specific headline `UNVERIFIED` — confirm before citing externally.) |
| 2026-02-25 | **-10.6%** | **+13.0%** | -0.7% | Clean inverse, opposite tape day. (Headline `UNVERIFIED`.) |
| 2025-05-14 | +16.6% | -2.7% | -1.5% | Weak inverse in the other direction. |
| 2025-06-10 | **-16.9%** | **-14.3%** | +1.2% | **The counter-print: BOTH crushed** by a third party (Insmed's TPIP win). A zero-sum pair inverts only on head-to-head events; a third-party threat sinks both at once. |

Daily correlation: r = **+0.066**, n=501, |t|=1.5 — statistically nothing. This pair has NO continuous relationship; it is purely event-driven. Both legs are liquid (UTHR $21.4B cap, ~$275M/day; LQDA $6.7B cap, ~$142M/day; 3-mo avgs, 2026-08-15).

**Use:** if the desk is ever long one side of a UTHR/LQDA head-to-head event, buying the other side is a genuine partial hedge — the only pair found where both directions have real prints. It does NOT hedge non-head-to-head risk (see 2025-06-10).

### 2b. VALIDATED one direction only: challenger-win → incumbent-fall (INSM → UTHR/LQDA)

**Mechanism:** a challenger's positive readout in the incumbent's core franchise re-prices the incumbent's future market share down.

- **2025-06-10** — Insmed TPIP Ph2b PAH data: **INSM +28.7%, UTHR -14.3%, LQDA -16.9%** on a +1.2% XBI, +0.6% SPY day. Cleanest incumbent-displacement print in the dataset. Works because Tyvaso-franchise exposure is a huge share of UTHR/LQDA value and UTHR ($21B) is small enough to re-price.

**But the hedge direction (challenger stumbles → incumbent rises) is much weaker.** INSM's 8 worst days since 2023: UTHR rose on essentially none of them. Best case 2026-06-05 (INSM -10.2%, UTHR +0.4% on a -3.6% XBI day — ~+4% excess, driver `UNVERIFIED`); typical case UTHR flat-to-down with the tape (e.g. 2026-05-07: INSM -23.4%, UTHR **-4.6%**). Daily r = +0.146 (n=501, |t|=3.3) — they mildly CO-move day to day.

**Verdict:** owning the incumbent hedges a long-challenger catalyst only when the catalyst is a direct, dated attack on the incumbent's franchise, and even then expect a fraction of the challenger's move. Treat as a partial damper, size accordingly, validate the specific event linkage per trade.

### 2c. QUANTIFIED FAILURE: mega-cap incumbent as hedge (obesity, LLY/NVO)

**Mechanism sounds right, sizing kills it.** The incumbent is too big relative to the stake:

- **2024-12-20** — NVO CagriSema miss: **NVO -17.8%, LLY +1.3%** on a +1.2% SPY / +1.6% XBI day → LLY excess ≈ **zero**. A rival's disaster bought the incumbent nothing beyond the tape. (Note NVO/LLY is the closest thing to a mega-cap duopoly pair and it still didn't pay.)
- **2024-02-27** — VKTX VK2735 Ph2 win: **VKTX +121.0%, LLY -0.9%, NVO -1.0%** (SPY +0.2%). The challenger doubled; the incumbents dipped ~1%. Read in hedge direction: if VKTX had failed, LLY would have gained ~1% while VKTX lost most of its value — a ~100:1 payoff mismatch.

LLY is a $1.05T company (2026-08-15); no small-cap binary meaningfully re-prices it. **Rule of thumb from these prints: the incumbent-long hedge only pays when the incumbent's market cap is within roughly 10–20x of the value genuinely at stake (UTHR at $21B vs a franchise-threatening readout: -14%; LLY at $1T vs a Ph2 challenger: -1%).**

### 2d. DIRECTION-BY-MECHANISM: same disease, opposite signs (ATTR, 2024-06-24)

**ALNY HELIOS-B win (vutrisiran, ATTR-CM): ALNY +34.5%, BBIO -15.9%, IONS +6.8%** (XBI +1.6%, SPY -0.3%).

Same event, same disease, opposite signs on the two "peers": BBIO (acoramidis, fighting for the same commercial patients) took a genuine inverse hit; IONS (silencer class sibling) got a POSITIVE class read-through. You cannot classify a name as hedge-vs-trap by disease label — you must map who actually loses patients if the target wins. This also upgrades the prior study's IONS↔BBIO intuition: their daily r is +0.207 (n=501) but they landed on opposite sides of this ATTR event.

### 2e. HYPOTHESIS-ONLY / data-unavailable

- **EXAS (Cologuard incumbent) vs GH (Shield challenger), CRC screening.** GH fell **-27.1%** on 2022-12-16 (ECLIPSE data day) with XBI +0.3% — verified. The claim that EXAS rallied on the same day is the textbook incumbent-relief print, but **EXAS price history is no longer retrievable** (Yahoo returns no data — ticker appears delisted via acquisition; FMP tier blocks historical quotes). `UNVERIFIED` → HYPOTHESIS-ONLY. Moot going forward if EXAS is truly delisted.
- **AKRO vs MDGL (MASH read-through trap check).** MDGL +268.1% on 2022-12-19 (XBI -2.1%) — verified. AKRO same-day unavailable (no Yahoo history; apparently delisted via acquisition). Contemporaneous reporting said AKRO ROSE on MDGL's win (read-through trap, consistent with PHVS/BCRX) but that is `UNVERIFIED` here.
- **Supplier / royalty inversions: none found.** Exchange-listed royalty vehicles (e.g. RPRX) are diversified and LONG drug success — no listed pure-play whose economics improve when a specific drug fails. CDMOs/suppliers lose revenue on a client failure (positive correlation, not inverse). No candidate cleared the bar; recording the null result so we don't re-hunt it.

---
## Section 3 — The honest verdict (the usable menu)

### (a) Reliable sector/tape dampers — the ones we'd actually use

| Rank | Instrument | Role | Sizing note |
|---|---|---|---|
| 1 | **LABD** (-3x S&P Biotech Select) | The biotech-tape hedge. Same index as XBI, r=-0.999, $107M/day. | Size at 1/3 of desired hedge notional to synthesize -1x (no live -1x biotech ETF exists — LABS is delisted). Event-window only: on days before catalyst, off days after. |
| 2 | **RWM** (-1x Russell 2000) | Small-cap tape hedge; best-fitting broad -1x for small-cap biotech (r=-0.677 vs XBI). Minimal decay at -1x. | The default when the worry is "small caps de-rate this week," not "biotech specifically." |
| 3 | **TZA** (-3x Russell 2000) | Capital-efficient version of RWM ($839M/day, far more liquid than SRTY). | 1/3 sizing; event-window only. |
| 4 | **SPDN** (-1x S&P 500) | Macro-tape hedge at the cheapest ER (0.48% vs SH's 0.89%). | Weakest linkage to biotech (r≈-0.59); use only for macro-event weeks. |
| 5 | PSQ / SQQQ (-1x/-3x NDX) | Only if the risk being hedged is a growth/rates tape event. | SQQQ is the most liquid inverse ETF in existence ($2.55B/day) but the worst biotech fit. |

### (b) Plausible single-name inverses — worth per-trade validation, never assumed

1. **UTHR ↔ LQDA** (either direction) around a **head-to-head** FDA/court event — the only pair with verified inverse prints in both directions (2024-08-19, 2026-02-25, 2025-05-14). Re-validate before each use: confirm the event is head-to-head (2025-06-10 proved a third party can sink both), and confirm the litigation posture hasn't been settled/mooted since these prints.
2. **Incumbent-long vs challenger catalyst** — ONLY when all three hold: (i) the catalyst directly attacks the incumbent's core franchise (≥~30-50% of its value), (ii) the incumbent's market cap is within ~10-20x of the value at stake (UTHR-sized, never LLY-sized), (iii) a prior same-franchise print exists. Expect a fraction of the challenger's move; treat as partial damper, not a hedge.
3. Anything else single-name: assume NO until an event print proves otherwise. The 2y daily correlations of every mechanism-plausible pair tested here are POSITIVE (+0.07 to +0.29) — biotech co-moves day-to-day even when event-inverse.

### (c) Traps to avoid

- **Same-disease / same-mechanism "hedges"** — PHVS/BCRX (burned already), MDGL→MASH peers, IONS class read-through on ALNY's win. A class win lifts the class. Disease label ≠ hedge; map the patient flows.
- **BIS, RXD** — ~$100K/day liquidity death-traps; you cannot exit on the day you need to.
- **ELIS** (LLY Bear 1x) — no trade prints since 2026-04-10; effectively dead.
- **Mega-cap incumbent as hedge** — LLY +1.3% on NVO's -17.8% disaster; ~100:1 payoff mismatch. Feels safe, pays nothing.
- **Holding any -2x/-3x fund through a multi-week catalyst wait** — volatility drag bleeds the position even if the index goes nowhere.
- **Reading daily correlation as hedge quality** — LQDA/UTHR (r=+0.07) is the best event-inverse pair found; VKTX/LLY (r=+0.22) is useless. Correlation on dailies tells you about the tape, not the event.

### The restated hard truth

**Sector inverse ETFs hedge the TAPE, not the binary.** Your catalyst name is <1% of any index; when it gaps -70% on a failed readout, LABD moves by rounding error. Nothing buyable as a share or ETF replicates a put's idiosyncratic payoff, and we don't have options. Within long-only equities, single-name binary risk is controlled by exactly two things: **position sizing** and, where a real displacement mechanism exists (UTHR/LQDA-class, verified per-event), a **partial incumbent/rival long**. Everything in Section 1 is tape insurance layered on top of that — useful, decaying, and blind to your specific readout.

---
*All prices/volumes/correlations fetched via yfinance 2026-08-15 (yfinance 1.6.0; note project policy: yfinance is research-grade only, not for trade decisions). FMP API attempted for delisted-ticker history; current tier returned 402/403 on historical endpoints. Web-search verification of ETF landscape was unavailable this session (search budget exhausted) — existence/delisting claims verified instead by live price-history probes, which is stronger evidence than a listing page anyway.*
