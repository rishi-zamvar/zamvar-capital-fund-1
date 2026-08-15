# Free Data Sources — Zamvar Capital Fund 1

Research date: 2026-08-15. Constraint: FREE, EOD/15-min-delayed acceptable, quality over latency.
All live tests run this date from this machine unless marked UNVERIFIED. WebSearch budget was exhausted by prior agents; findings below are from direct endpoint tests (high confidence) and single WebFetch reads (single-source confidence, marked where relevant).

---

## Section 1 — Options-implied move / IV / options chains (THE priority)

### TL;DR ranking for thinly-traded biotech ATM IV / expected move

1. **CBOE delayed-quotes JSON (cdn.cboe.com)** — best free source, full stop. Per-contract IV + greeks + OI + bid/ask sizes + symbol-level `iv30`, no auth, one JSON GET per ticker.
2. **yfinance / Yahoo option chains** — best as cross-check + fallback; IV included but Yahoo-computed and flaky on stale contracts.
3. **Alpha Vantage `HISTORICAL_OPTIONS`** — best free source for *historical* EOD chains with IV/greeks (backtesting the move-estimator), useless intraday (25 req/day).
4. **Tradier sandbox** — legit documented free API, 15-min delayed chains, but **no greeks/IV in sandbox** → we'd compute IV ourselves.
5. **Nasdaq.com API / optionsprofitcalculator** — price-only chains (no IV), scrape-tier redundancy.
6. Polygon/Finnhub/Twelve Data free tiers — not competitive for this need (details below).

---

### 1.1 CBOE free delayed quotes — RECOMMENDED PRIMARY ✅ VERIFIED LIVE

- **URL pattern:** `https://cdn.cboe.com/api/global/delayed_quotes/options/{TICKER}.json` (human page: https://www.cboe.com/delayed_quotes/)
- **Live test (KURA, 2026-08-15):** HTTP 200, 140 contracts, one request, no auth, no key. Fields per contract: `option` (OCC symbol → strike/expiry/type), `bid/ask` + sizes, `iv`, `delta/gamma/vega/theta/rho`, `theo`, `open_interest`, `volume`, `last_trade_price/time`, `prev_day_close`. Symbol-level: `current_price`, **`iv30`**, `iv30_change`, bid/ask, OHLC.
- **Delay:** CBOE delayed quotes are 15-min delayed (industry standard). Timestamp field included in response.
- **Rate limits:** none documented on the CDN endpoint. Be polite anyway (it's a CDN; cache per-ticker ≥5 min).
- **IV caveat observed:** deep-ITM/no-quote contracts return `iv: 0.0` — filter to near-the-money contracts with live bid>0 before trusting IV. ATM contracts on our test names had sane IVs.
- **ToS posture:** YELLOW. It's the JSON backing CBOE's own public delayed-quotes page — publicly served, no auth, but not a documented public API. Personal/internal research use at low volume is the standard posture here. Don't redistribute.
- **Why it wins:** the *only* free source with exchange-side per-contract IV + greeks + `iv30` in one call. CBOE is the options exchange — this is the most authoritative free IV available anywhere.

### 1.2 Yahoo Finance via yfinance — RECOMMENDED CROSS-CHECK ✅ VERIFIED LIVE

- **Access:** `pip install yfinance` (tested v0.2.66); `Ticker(t).options` → expirations; `Ticker(t).option_chain(exp)` → calls/puts DataFrames.
- **Live test (KURA/IOVA/SRPT, 2026-08-15):** all returned chains. Fields: strike, lastPrice, bid, ask, volume, openInterest, **impliedVolatility**, lastTradeDate. Spot via `fast_info`.
  - KURA ATM 11C: bid 0.20 / ask 0.50, IV 0.689, OI 1828 — usable.
  - IOVA ATM 7C: bid 0.25 / ask 0.35, IV 0.805, OI 1086 — good.
  - SRPT ATM 18C: bid 0.20 / ask **1.20**, IV 0.650, vol 25 — spread so wide the mid is nearly meaningless. This is the thin-biotech reality on every source.
- **Delay:** delayed (typically 15 min). No auth, no documented rate limit; yfinance scrapes Yahoo's internal API.
- **ToS posture:** YELLOW-RED. Yahoo ToS prohibits automated access; yfinance is tolerated-in-practice but breaks periodically (crumb/auth changes). We already treat yfinance as non-authoritative — correct.
- **Where it's good enough as ENRICHING signal:** ATM IV and straddle mid on names with OI > ~200 and bid > 0 on both legs. Cross-check against CBOE; if the two disagree by >10 vol points, distrust both and fall back.
- **Where it's NOT:** anything relying on Yahoo's `impliedVolatility` on zero-bid/stale contracts (it happily prints garbage IV off stale lasts); greeks (not provided); historical IV (not provided).

### 1.3 Alpha Vantage `HISTORICAL_OPTIONS` — RECOMMENDED FOR BACKTESTS ✅ VERIFIED LIVE

- **URL:** `https://www.alphavantage.co/query?function=HISTORICAL_OPTIONS&symbol={T}&date={YYYY-MM-DD}&apikey={key}` (docs: https://www.alphavantage.co/documentation/)
- **Live test (demo key, IBM):** returns full EOD chain per date with `implied_volatility`, `delta/gamma/theta/vega/rho`, bid/ask + sizes, mark, OI, volume. 15+ years history claimed.
- **Free tier:** 25 requests/day (hard). Realtime options endpoint (`REALTIME_OPTIONS`) is premium-only.
- **ToS posture:** GREEN — documented free API, free key signup.
- **Role:** 25/day is useless for daily scanning but perfect for *building the historical IV-into-catalyst dataset* one ticker-date at a time (e.g., pull the chain for each past PDUFA date to calibrate the move estimator). Queue-and-drip.

### 1.4 Tradier developer sandbox — LEGIT FREE API, NO IV ✅ VERIFIED (docs, single-source)

- **Docs:** https://docs.tradier.com/docs/market-data (old documentation.tradier.com redirects here)
- **Free:** sandbox developer account = free; option chains 15-min delayed. Endpoint `GET /v1/markets/options/chains?symbol=&expiration=&greeks=true`.
- **Confirmed from docs:** sandbox options data is 15-min delayed; **greeks/IV (ORATS-sourced) are NOT available in sandbox** — production (requires funded brokerage account) gets hourly ORATS greeks. Rate limits per docs historically 60 req/min sandbox (UNVERIFIED — confirm on signup).
- **ToS posture:** GREEN — documented, keyed, intended for developers.
- **Role:** clean fallback chain-price source if CBOE/Yahoo both break; we compute IV ourselves (see 1.8).

### 1.5 Nasdaq.com option-chain API ✅ VERIFIED LIVE

- **URL:** `https://api.nasdaq.com/api/quote/{T}/option-chain?assetclass=stocks` (needs browser User-Agent header; returned 200 with chain rows for KURA).
- **Fields:** bid/ask/last/volume/OI per strike for calls+puts. **No IV, no greeks.** Data lagged (showed "as of Aug 13" on Aug 15 pre-market).
- **ToS posture:** YELLOW — undocumented internal API, known to be UA-sensitive and occasionally bot-blocked.
- **Role:** tertiary price-only redundancy. Skip unless CBOE + Yahoo + Tradier all fail.

### 1.6 optionsprofitcalculator.com ✅ VERIFIED LIVE

- **URL:** `https://www.optionsprofitcalculator.com/ajax/getOptions?stock={T}&reqId=1` — returned full chain for KURA: per strike `{oi, l(ast), b(id), a(sk), v(olume)}` by expiry.
- **No IV.** Compact, no auth. ToS posture: YELLOW (site's internal ajax; small operator — be gentle or skip).
- **Role:** same as Nasdaq — price-only redundancy. Not needed given the above.

### 1.7 The rest — tested or assessed, not competitive

| Source | Finding | Status |
|---|---|---|
| **Polygon.io** (note: now redirects to massive.com — rebrand in progress) | Free "Options Basic": 5 calls/min, **EOD only**, 2y history, all US options tickers, aggregates + reference. **Greeks/IV NOT in free tier** (start at $29/mo Starter). https://massive.com/pricing?product=options | Verified via pricing page (single-source). EOD chains w/o IV at 5 calls/min loses to CBOE on every axis. Skip. |
| **Finnhub** | `/stock/option-chain` exists; demo key rejected; free-tier access to it could not be confirmed without signup. Free tier is 60 calls/min generally. https://finnhub.io/docs/api/option-chain | UNVERIFIED for free-tier options — worth a 5-min keyed test, but CBOE already covers the need. |
| **Twelve Data** | `/options/chain` endpoint exists (403 on demo key with "get your own free key" message). Historically options = paid Pro+. https://twelvedata.com/pricing | UNVERIFIED free access; likely paid. Skip. |
| **Barchart free pages** | Options pages show IV/greeks in-browser but are aggressively bot-protected; free API (getHistory etc.) doesn't include option chains. | UNVERIFIED (not tested). Not worth scraper effort given CBOE. |
| **MarketWatch** | No option-chain data product distinct from other feeds; heavy paywall/bot-wall. | Skip (not tested — no plausible edge). |
| **Market Chameleon** | The one thing it has that others don't: precomputed **earnings/event expected-move** and IV-term-structure analytics. Free tier requires login and shows limited teaser data; bulk scraping their analytics is against ToS and they actively defend. | RED for scraping. If we ever want their exact analytics, that's a paid product. We can compute the same expected-move ourselves from CBOE data (1.8). |

### 1.8 Computing IV / expected move ourselves (needed for Tradier-fallback path; also our cross-check)

- **Straddle-implied expected move** (no IV solve needed): `expected_move_% = (ATM call mid + ATM put mid) / spot` for the expiry straddling the catalyst date. Slightly better: 0.85 × straddle for the standard approximation-to-±1σ adjustment — but for ranking catalysts the raw straddle/spot is fine and assumption-free.
- **IV solve when needed:** Black-Scholes implied vol via **`vollib`** (PyPI `vollib` 1.0.11, http://vollib.org, uses Jäckel's "Let's Be Rational" — fast, robust at extreme moneyness). Note: PyPI `py_vollib` 1.0.12 is now a deprecated transition shim pointing at `vollib`; `py_vollib_vectorized` (0.1.1) exists for DataFrame-wide solves. Verified on PyPI 2026-08-15.
- **Term-structure event signal:** front-expiry ATM IV minus next-expiry ATM IV (event premium in the front). Both legs straight off the CBOE JSON.

### 1.9 Thin-name degradation policy (the honest part)

Small-cap biotech options are frequently unusable: $0.05–$1.00 wide quotes, single-digit OI, zero volume, IV printed off stale trades. Gate the options-implied input:

1. **Liquidity gate** (all must pass): ATM bid > 0 on both call and put; ATM spread/mid < ~60%; combined ATM OI ≥ ~100; an expiry exists at/after the catalyst date.
2. Pass → use CBOE straddle-implied move + ATM IV as the enriching input, store CBOE `iv30` alongside.
3. Fail → **fall back to the in-house historical-gap estimator** (existing) and tag the row `options_data: none/illiquid` so the model never silently ingests junk IV.
4. Marginal names: use straddle *mid* only if both legs have live bids; never use last-trade prices for the straddle on thin names.

No free (or paid) source fixes illiquidity — Market Chameleon and ORATS are computing from the same wide quotes. The gate is the quality control, not a better vendor. **Free data is genuinely sufficient here.**

---
## Section 2 — PDUFA / AdCom / regulatory dates (free)

### TL;DR
No single free source is complete. Best free stack: **RTTNews FDA Calendar (scrape — verified structured rows)** for PDUFA dates + panel outcomes, **Federal Register API (documented free JSON)** for AdCom meeting notices, with **company PR confirmation** remaining the authoritative step for dates we trade. This cuts hand-curation to a review task rather than a discovery task.

### 2.1 RTTNews FDA Calendar — BEST FREE PDUFA LIST ✅ VERIFIED LIVE
- **URL:** https://www.rttnews.com/corpinfo/fdacalendar.aspx — HTTP 200 to plain curl with browser UA, 143KB, no login.
- **Verified structure:** ASP.NET repeater rows, each = `Company (TICKER) | Drug (application type: NDA/BLA/sNDA/ANDA) | date (MM/DD/YYYY) | event description | outcome`. Live example captured: `Capricor Therapeutics (CAPR) | Deramiocel (BLA) | 07/29/2026 | FDA panel to review… | FDA panel voted 9-3 against approval`.
- **Coverage:** PDUFA dates, AdCom (panel) review dates, CRLs, approvals — with outcomes backfilled. Freshness: entries current to within days at test time.
- **Access:** plain HTML scrape (no JS wall as of 2026-08-15). ToS posture: YELLOW — media site, no API, scrape politely (1 page, once/day is plenty).
- **Caveat:** editorial curation by RTTNews — treat as a discovery feed; confirm any tradeable date against the company's own PR/8-K before it enters the model (cite-or-drop).

### 2.2 Federal Register API — BEST ADCOM SOURCE (GREEN) ✅ VERIFIED LIVE
- **URL:** `https://www.federalregister.gov/api/v1/documents.json?conditions[term]="advisory committee" meeting&conditions[agencies][]=food-and-drug-administration&conditions[type][]=NOTICE&order=newest` — documented, free, no key. Docs: https://www.federalregister.gov/developers/documentation/api/v1
- **Verified live:** 2,691 matching FDA notices; recent results include drug-specific AdCom meeting notices (e.g., Cellular, Tissue & Gene Therapies AdCom re: a specific BLA, 2026-07-24). Every AdCom meeting is legally required to be noticed here — coverage is complete by construction.
- **Fields:** title, publication_date, abstract, full-text URL, JSON. Meeting date + drug/BLA parsed from title/abstract text (LLM-parse friendly).
- **Lag caveat:** notices publish ~15+ days before the meeting — fine for our horizon, but the market usually knows from the company PR slightly earlier.

### 2.3 FDA.gov Advisory Committee Calendar — exists, JS-walled ✅ PARTIALLY VERIFIED
- **URL:** https://www.fda.gov/advisory-committees/advisory-committee-calendar — 200 to curl, but the table (`Start Date | End Date | Meeting | Office | Center`) is an empty shell whose rows load via a Drupal/DataTables AJAX call I could not locate (guessed endpoint returned FDA error page). Needs the headless-browser agent, or just use the Federal Register API (same data, better format). WebFetch tool itself got a 404 (bot rules).

### 2.4 BioPharmaCatalyst — bot-gated, headless required ⚠️
- **URL:** https://www.biopharmacatalyst.com/calendars/fda-calendar — curl receives a JS fingerprint/redirect gate (`fingerprint/iife.min.js` + tracking-UUID redirect), not the site. Content unverifiable without a real browser. Historically the best-curated free FDA calendar (ticker, drug, phase, catalyst date) with paid tiers on top. Posture: YELLOW-RED — they actively gate bots; if we want it, it's a job for the human-like browser agent at low frequency, or skip. UNVERIFIED content as of today.

### 2.5 Drugs.com FDA calendar — bot-walled ⚠️
- **URL:** https://www.drugs.com/new-drug-applications.html — 403 to both curl and WebFetch. Known to list NDA/BLA entries with PDUFA month granularity (often not exact dates). UNVERIFIED today; headless-only. Lower value than RTTNews anyway (date granularity).

### 2.6 FDATracker — thin free layer ⚠️
- **URL:** https://www.fdatracker.com/fda-calendar/ — 200, WordPress page loads but calendar content is a JS embed; depth of free access UNVERIFIED. Their real product is paid. Skip unless the browser agent finds a full free table.

### 2.7 Curated GitHub datasets — nothing usable ✅ CHECKED
- GitHub API search for `pdufa` / `fda calendar` (2026-08-15): only 0-star personal experiments, several auto-generated; the one "auto-updating pipeline" repo's README 404'd. No maintained community PDUFA dataset exists. r/biotech wikis: not checked (Reddit API auth friction; low expected value given RTTNews covers it) — UNVERIFIED.

### 2.8 What stays manual
PDUFA dates originate in company PRs and are only *aggregated* by the above. The residual manual work: (a) confirming each RTTNews-discovered date against the company PR/8-K, (b) catching date *changes* (CRL, extensions, resubmissions — RTTNews does backfill these but with lag). openFDA (api.fda.gov) is retrospective-approvals only — no PDUFA dates — not useful here.

---
## Section 3 — Short interest, float, ownership, insider (free)

Cross-check note: KURA short interest for settlement 2026-07-31 = **13,160,945** identically from FINRA API, Nasdaq API, and yfinance — three independent free sources agree. High confidence in this pipeline.

### 3.1 FINRA short interest — PRIMARY ✅ VERIFIED LIVE (upgraded: use the free Query API, not just bulk files)
- **Query API (better than the bulk files):** `POST https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest` with JSON body `{"limit":N, "compareFilters":[{"compareType":"EQUAL","fieldName":"settlementDate","fieldValue":"2026-07-31"}], "domainFilters":[{"fieldName":"symbolCode","values":["KURA","IOVA",...]}]}` — **no auth, no key**, tested live: returned exact per-ticker rows (`currentShortPositionQuantity`, `previousShortPositionQuantity`, `averageDailyVolumeQuantity`, `daysToCoverQuantity`, `changePercent`, `marketClassCode`). Docs: https://developer.finra.org/docs
  - Gotcha (hit live): sorting requires an EQUAL filter on the partition key `settlementDate` — so query by explicit settlement date (dates are the 15th & EOM, published ~T+9 business days).
- **Bulk files (backup/bootstrap):** https://www.finra.org/finra-data/browse-catalog/equity-short-interest/files — bi-monthly pipe-delimited files, same fields. UNVERIFIED today (page not re-fetched) but this is the long-standing documented location.
- **Cadence:** bi-monthly (mid-month + month-end settlement), ~9 business days publication lag. ToS: GREEN — FINRA publishes this for public use.

### 3.2 Nasdaq per-ticker short interest ✅ VERIFIED LIVE
- **URL:** `https://api.nasdaq.com/api/quote/{T}/short-interest?assetClass=stocks` (browser UA required). Returns bi-monthly history rows: settlementDate, interest, avgDailyShareVolume, daysToCover. Human page: https://www.nasdaq.com/market-activity/stocks/{t}/short-interest
- **Role:** convenience cross-check of FINRA; same underlying data. ToS: YELLOW (undocumented internal API).

### 3.3 SEC EDGAR — ownership + insider — GREEN, all verified live
- **Full-text search API:** `https://efts.sec.gov/LATEST/search-index?q=%22Kura+Oncology%22&forms=4` → JSON hits (tested: 249 results). UI equivalent: https://efts.sec.gov/LATEST/search-index?q= / https://www.sec.gov/cgi-srv/efts (docs: https://www.sec.gov/edgar/search/)
- **Company submissions JSON:** `https://data.sec.gov/submissions/CIK{10-digit}.json` — every filing incl. Form 4 (insider), 13D/G, 13F, 8-K, with accession numbers → document URLs. (KURA CIK = 0001422143, confirmed via atom lookup.)
- **Company browse/Atom:** `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=kura+oncology&type=4&output=atom` — tested live, returns filing feed.
- **Requirements:** declared User-Agent with contact email (we used one; SEC enforces), ≤10 req/sec. Cadence: near-real-time as filed (Form 4 = within 2 business days of trade; 13F quarterly +45d lag; 13D within 5 days of >5% events).
- **ToS posture:** GREEN — public-domain government data, documented APIs.
- **Role:** Form 4 = insider signal into catalysts; 13F/13D/G = institutional/activist ownership. Parse XML from the filing documents (Form 4 XML is well-structured).

### 3.4 Float — the weak spot (no authoritative free source)
- **yfinance `Ticker.info`** ✅ tested live (KURA): `floatShares` 70,563,563, `sharesOutstanding` 88,960,619, plus `sharesShort`, `shortRatio`, `heldPercentInstitutions`, `heldPercentInsiders` in one call. Yahoo's float is vendor-estimated (ultimately Refinitiv-derived) — fine as an enriching denominator (SI % of float), not authoritative.
- **Authoritative-ish free alternative:** shares outstanding from the company's own latest 10-Q/10-K cover page via EDGAR `data.sec.gov/api/xbrl/companyconcept/CIK{...}/dei/EntityCommonStockSharesOutstanding.json` (GREEN, exact, but that's outstanding, not float). UNVERIFIED endpoint today but standard XBRL frames API.
- **Verdict:** use SEC shares-outstanding as the exact base + yfinance float as the estimate; flag float-derived metrics as estimate-grade. FMP free tier (250 req/day) also carries float if we already hold a key — same estimate-grade.

---
## Section 4 — Conference calendars + trials/earnings (free, confirmed)

### 4.1 ClinicalTrials.gov API v2 ✅ CONFIRMED LIVE
- `https://clinicaltrials.gov/api/v2/studies?query.spons=Kura+Oncology&fields=NCTId,BriefTitle,OverallStatus,PrimaryCompletionDate,Phase&pageSize=N` — tested live, returned sponsor-filtered studies with `primaryCompletionDateStruct`, phase, status. Free, no auth, no key, JSON, OpenAPI-documented (https://clinicaltrials.gov/data-api/api). GREEN. Still our authoritative trial-timing source — no change needed.

### 4.2 Earnings calendar ✅ CONFIRMED LIVE (Nasdaq)
- `https://api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD` (browser UA required) — tested live: full-day list with symbol, company, market cap, time (pre/after hours), consensus EPS, # estimates. YELLOW (undocumented internal API) but one request/day covers the whole market.
- Backups: FMP earnings-calendar endpoint on free 250-req/day key (GREEN, we already planned FMP); Finnhub `/calendar/earnings` free tier (UNVERIFIED today — needs keyed test). Nasdaq suffices.

### 4.3 Medical conference calendars — annual seed entries, partially bot-walled
Tested 2026-08-15 (plain curl, browser UA):
| Conference | URL | Status |
|---|---|---|
| ESMO | https://www.esmo.org/meeting-calendar | 200 — scrapeable calendar page ✅ |
| ASH | https://www.hematology.org/meetings/annual-meeting | 200 — scrapeable ✅ |
| ASCO | https://conferences.asco.org/am/dates-locations | 403 to curl — needs headless browser ⚠️ |
| AHA | https://professional.heart.org/en/meetings | 403 to curl — needs headless browser ⚠️ |
- These are a handful of fixed annual dates for a ~20-name universe. Verdict unchanged from STACK: **manual/annual seed entries** (10 minutes/year of human time) beat building scrapers for bot-walled association sites. The browser agent can refresh them opportunistically. What no free source gives: *which company presents which abstract when* — that comes from company PRs (8-Ks) and conference abstract portals near the event; keep that in the catalyst-curation workflow.

---
## Section 5 — Verdict: the free data stack + scraper design

### 5.1 The free stack (ranked verdict table)

| Data need | Recommended FREE source | Access | Cadence | Reliability | ToS posture |
|---|---|---|---|---|---|
| ATM IV / straddle-implied move / term structure | **CBOE delayed-quotes JSON** (`cdn.cboe.com/api/global/delayed_quotes/options/{T}.json`) | JSON GET, no auth | 15-min delayed; pull 1-2×/day per name | A (exchange-side IV/greeks; gate for liquidity) | 🟡 undocumented-but-public JSON |
| Options cross-check | yfinance option chains | pip lib | delayed | B (breaks periodically; garbage IV on stale contracts) | 🟡/🔴 ToS-gray, tolerated |
| Historical chains+IV (backtest calibration) | Alpha Vantage `HISTORICAL_OPTIONS` | keyed API | EOD, 25 req/day | A- (drip-feed only) | 🟢 documented free |
| Options fallback (compute own IV via `vollib`) | Tradier sandbox | keyed API | 15-min delayed | B+ | 🟢 documented free |
| PDUFA dates + panel outcomes (discovery) | **RTTNews FDA Calendar** | HTML scrape, 1 page | daily pull | B+ (editorial; confirm vs company PR) | 🟡 scrape, gentle |
| AdCom meetings (authoritative) | **Federal Register API** | JSON API, no key | as-published (~15d pre-meeting) | A (legally complete) | 🟢 documented free |
| PDUFA confirmation (authoritative) | Company PR / 8-K via EDGAR full-text search | JSON API | as-filed | A | 🟢 government |
| Short interest | **FINRA Query API** (`api.finra.org` consolidatedShortInterest) | JSON POST, no auth | bi-monthly (+~9bd lag) | A (triple-verified vs Nasdaq+Yahoo) | 🟢 |
| Insider (Form 4), 13F/13D/G | SEC EDGAR (data.sec.gov + efts full-text) | JSON APIs, UA header | as-filed | A | 🟢 |
| Float / SI-%-float denominator | yfinance `info.floatShares` + SEC XBRL shares outstanding | lib + API | daily / quarterly | B (float is estimate-grade everywhere free) | 🟡 + 🟢 |
| Trial readout timing | ClinicalTrials.gov API v2 | JSON API | daily | A | 🟢 |
| Earnings calendar | Nasdaq `api/calendar/earnings` | JSON GET, UA header | daily, 1 req/day | A- | 🟡 |
| Conference dates | Manual annual seed (ESMO/ASH scrapeable; ASCO/AHA bot-walled) | manual + browser agent | yearly | A (they're fixed dates) | 🟢/🟡 |

### 5.2 Where free is NOT good enough (honest flags)
1. **Precomputed event expected-move analytics** (Market Chameleon / ORATS-style): free sources give us the raw chain; we compute the expected move ourselves. That's fine — same math — but if we ever want *historical intraday* IV surfaces or vendor-cleaned event studies, that's paid (ORATS ~$99/mo, or Polygon Starter $29/mo for greeks). Not needed for the current enriching-input design.
2. **Float**: no authoritative free float anywhere (it's a vendor calculation). Estimate-grade is acceptable; label it.
3. **PDUFA discovery breadth**: RTTNews + Federal Register + PR confirmation covers a ~20-name curated universe well. For a *broad-universe* screener someday, BPIQ/BiopharmaWatch paid tiers are the real products. Not needed now.
4. **Options on the thinnest names**: no vendor fixes zero-OI chains. The liquidity gate + historical-gap fallback (Section 1.9) is the answer, not spend.

### 5.3 Reference repo evaluated: jcaperella29/Financial-Data-Scraper — DO NOT FORK
- **URL:** https://github.com/jcaperella29/Financial-Data-Scraper (assessed 2026-08-15 via GitHub API + README)
- **What it is:** ~15KB of Python, three versioned single-file Selenium/Firefox scripts scraping **fundamentals only** (income statement / balance sheet / cash flow / ratios) from stockanalysis.com into CSVs, tickers from `ticker.csv`. XPath-based, JS-click fallbacks, screenshot debugging.
- **Fit check:** zero overlap with our needs — no options, no IV, no prices, no FDA/SI/EDGAR. Fundamentals we'd get from EDGAR XBRL or FMP anyway. Fills no gap in Sections 1-4.
- **Maintenance/license:** last push 2025-02-04 (18 months stale), 11 stars, 7 commits, **NO LICENSE file** → default all-rights-reserved: we legally cannot fork or reuse the code even if we wanted to.
- **Verdict: build our own; don't fork, don't borrow code.** The only transferable ideas (ticker-list CSV input, screenshot-on-failure debugging) are one-liners we'd write anyway. Its architecture (single-site XPath Selenium) is also the fragile pattern our design below avoids — we scrape JSON endpoints wherever they exist and reserve the browser for the few genuinely bot-walled pages. Tradeoff of building our own: ~a day of work vs. inheriting an unlicensed, stale, wrong-scope script. Easy call.

### 5.4 Scraper-agent spec (the yellow-source handler)
**Scope — which sources it owns** (everything green above is plain httpx, no browser needed):
- Tier A (plain HTTP w/ browser UA, no JS): CBOE JSON, Nasdaq option-chain/SI/earnings JSONs, RTTNews FDA calendar, optionsprofitcalculator (optional), ESMO/ASH pages.
- Tier B (headless browser / human-like, low frequency): BioPharmaCatalyst (fingerprint gate), Drugs.com (403 wall), ASCO/AHA (403), FDA.gov AdCom datatable (JS rows) — all *optional redundancy*; nothing on this tier is a primary source.
- yfinance stays a library call, not a scraper target.

**Discipline:**
- Cache-first: per-(source,ticker) cache with ≥5-min TTL intraday, 24h for calendars; never refetch inside TTL. Bi-monthly sources (FINRA) fetch on publication schedule only.
- Rate: ≤1 req/sec per host, jittered; sequential per host; browser-tier ≤1 visit/day/site. Respect robots.txt for tier-B page discovery; identify honestly in UA for green/government APIs (SEC requires contact email — already in use).
- Failure: on 403/structure-change, mark source degraded, fall through the ranked fallbacks (each need above has ≥2 sources), never block the pipeline on a yellow source.
- **Provenance (cite-or-drop invariant): every datum persisted as `{value, source_url, fetch_ts_utc, source_grade(green/yellow), raw_snapshot_path}`.** Yellow-sourced data must additionally carry the cross-check field (e.g., CBOE-vs-Yahoo IV delta) or be marked single-source. Anything that can't cite a fetched URL + timestamp gets dropped, not imputed.

*(End of research. All live tests 2026-08-15; single-source WebFetch findings marked inline.)*
