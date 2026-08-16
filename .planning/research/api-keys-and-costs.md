# API Keys & Costs — Zamvar Capital Fund 1

**Researched:** 2026-08-16
**Domain:** Real, current pricing + signup links for every data key / paid source the trading system could use.
**Confidence:** HIGH on prices marked ✅ VERIFIED LIVE (WebFetch of the vendor's own pricing page, this date). MEDIUM/UNVERIFIED on prices marked ⚠️ — those vendors bot-wall WebFetch and the session's WebSearch budget was already exhausted (200/200) by prior agents, so they carry only what the project's own prior live-verified research (`free-data-sources.md`, `free-data-pipeline.md`, `STACK.md`) established, or are flagged for the operator to confirm at the signup link.

> **Cite-or-drop discipline.** Every dollar figure below is tagged ✅ VERIFIED LIVE (with the pricing-page URL I fetched today) or ⚠️ UNVERIFIED (bot-walled — confirm at the link). No price is stated as fact unless I pulled it from the vendor's page today. This feeds a real-money decision.

---

## Bottom line up front

- **Minimum required spend to run the system as designed: $0/month.** Every capability the desk needs has a working FREE source (mostly keyless or free-instant-key), and the project already runs live on that stack (cross-check hit 99.6% on real data at the 6.10 shakedown). Confirmed — the operator's expectation is correct.
- **The only thing money buys is PDUFA/FDA-catalyst breadth + convenience** (removing the manual "confirm each RTTNews date vs. company PR" curation step). Even that is *optional* for a curated ~20-name universe — RTTNews (discovery) + Federal Register API (AdCom, legally complete) + company 8-K/PR (authoritative) already cover it for free.
- **Recommended spend if you want to buy down the manual PDUFA burden: ~$0–100/month**, and it's a genuine judgment call, not a requirement — see the PDUFA deep-dive. My recommendation: **stay $0, keep PDUFA a reviewed manual table**, and revisit only if the universe expands beyond ~20 names.
- **Separate, non-optional operating cost: the Anthropic API (Claude)** — usage-based, not a subscription. Rough order-of-magnitude below. This is the desk's engine, not a data key.

---

## The key stack (grouped by capability)

Legend — **Key:** 🔓 keyless (no signup) · 🔑 free key (instant signup) · 💳 paid key. **Rank:** primary / secondary / tertiary within its category (fallback order if one rate-limits or breaks).

### Prices / OHLC (weekly bars — the desk's price spine)

| Source | Req/Opt | Key | Signup / key link | Free-tier limit | Monthly cost | What it gives | Rank |
|---|---|---|---|---|---|---|---|
| **yfinance** | Required | 🔓 keyless | `pip install yfinance` (no signup) | none (unofficial Yahoo scrape) | $0 | EOD/delayed OHLC + `info.floatShares` | **primary** |
| **Stooq** | Optional | 🔓 keyless | https://stooq.com/db/h/ | none | $0 | EOD OHLC | secondary — **currently IP/geo-blocked from this machine; left disabled** (redundant; don't proxy around it) |
| **Alpha Vantage** | Optional | 🔑 free key | https://www.alphavantage.co/support/#api-key | 25 req/day, 5 req/min | $0 free · $49.99/mo (75 rpm) ✅ | EOD/intraday OHLC, adjusted | secondary |
| **Tiingo** | Optional | 🔑 free key | https://www.tiingo.com/account/token | 500 symbols/mo, 50 req/hr, 1000 req/day, 1 GB/mo ✅ | $0 free · **$30/mo** Power (10k req/hr) ✅ | EOD composite OHLC, 30+ yr history | secondary |
| **Twelve Data** | Optional | 🔑 free key | https://twelvedata.com/register | 800 req/day, 8 credits/min ✅ | $0 free · $29/mo Grow ✅ | Real-time US equities/ETF, EOD | tertiary |
| **Finnhub** | Optional | 🔑 free key | https://finnhub.io/register | 60 calls/min free (per project research §1.7) | $0 free · paid ⚠️ UNVERIFIED | US stock quotes, candles | tertiary |
| **Polygon.io / Massive** | Optional | 🔑 free key | https://polygon.io/dashboard/signup | Basic: 5 calls/min, EOD only, 2 yr ✅ | $0 free · $29 Starter (15-min delayed, 5 yr) · $79 Developer (10 yr) · $199 Advanced (real-time, 20 yr+) ✅ | US stocks EOD→real-time | tertiary |
| **EODHD** | Optional | 🔑 free key | https://eodhd.com/register | 20 req/day ✅ | $0 free · $19.99/mo EOD All-World · $29.99 +intraday ✅ | Global EOD + fundamentals | tertiary |
| **Marketstack** | Optional | 🔑 free key | https://marketstack.com/signup | 100 req/mo ✅ | $0 free · $9.99 Basic (10k) · $49.99 Pro (100k) ✅ | EOD OHLC | tertiary |
| **financialdatasets.ai** | Optional | 🔑 free key | https://www.financialdatasets.ai/ | free tier exists ⚠️ UNVERIFIED | ⚠️ UNVERIFIED | prices + fundamentals (LLM-oriented) | skip unless a gap opens |

**Impact if absent:** none — the desk needs weekly EOD bars and multiple free sources agree to 0.000% (yfinance + Nasdaq + AV + Tiingo cross-checked live). Redundancy here is a *quality* lever (N-source median), not a spend lever.

### Options / IV (backtest calibration + enriching implied-move signal)

| Source | Req/Opt | Key | Signup / key link | Free-tier limit | Monthly cost | What it gives | Rank |
|---|---|---|---|---|---|---|---|
| **CBOE delayed-quotes JSON** | Required | 🔓 keyless | `cdn.cboe.com/api/global/delayed_quotes/options/{T}.json` (page: https://www.cboe.com/delayed_quotes/) | none documented (be polite) | $0 | **Exchange-side per-contract IV + greeks + OI + `iv30`**, 15-min delayed | **primary** — the best free IV anywhere |
| **yfinance option chains** | Optional | 🔓 keyless | `pip install yfinance` | none | $0 | chains + Yahoo-computed IV (flaky on stale) | secondary (cross-check) |
| **Alpha Vantage `HISTORICAL_OPTIONS`** | Optional | 🔑 free key | https://www.alphavantage.co/support/#api-key | 25 req/day ✅ | $0 (drip) · premium tiers ✅ (see prices) | **EOD historical chains w/ IV + greeks**, 15+ yr — backtest calibration | secondary (historical only) |
| **Tradier sandbox** | Optional | 🔑 free key | https://developer.tradier.com/user/sign_up | 15-min delayed, ~60 req/min ⚠️ | $0 | chain prices — **no greeks/IV in sandbox** (compute own via `vollib`) | tertiary (price fallback) |
| **Polygon / Massive Options** | Optional | 🔑/💳 | https://polygon.io/dashboard/signup | Basic: 5 calls/min, EOD, **no greeks/IV**, 2 yr ✅ | $0 free · **$29 Starter (real-time greeks + IV, unlimited calls, 2 yr)** · $79 Developer (4 yr) · $199 Advanced (5 yr+) ✅ | vendor-computed greeks/IV | secondary if CBOE ever insufficient |
| **ORATS** | Optional | 💳 paid | https://orats.com/data-api | trial ⚠️ | ⚠️ UNVERIFIED (~$99/mo cited in prior research §5.2, single-source — **confirm at link**) | cleaned historical IV surfaces, event expected-move | skip — CBOE + our own math covers it |

**Impact if absent:** CBOE (free, keyless) fully covers the enriching implied-move + IV input; Alpha Vantage historical (free, 25/day drip) covers backtest calibration. **No vendor fixes illiquid biotech option chains** — the liquidity gate + in-house historical-gap fallback is the answer, not spend. Polygon Options Starter ($29) is the cheapest paid upgrade *if* real-time vendor greeks ever become a hard DD input; not needed today.

### Clinical-trial readouts (readout-timing)

| Source | Req/Opt | Key | Signup / key link | Free-tier limit | Monthly cost | What it gives | Rank |
|---|---|---|---|---|---|---|---|
| **ClinicalTrials.gov API v2** | Required | 🔓 keyless | https://clinicaltrials.gov/data-api/api | none | $0 | Trial registry, primary-completion dates, phase, sponsor, status — authoritative | **primary** |
| **WHO ICTRP** | Optional | 🔓 keyless | https://trialsearch.who.int/ | none ⚠️ | $0 | cross-registry meta-search (incl. ex-US) | secondary |
| **ISRCTN registry** | Optional | 🔓 keyless | https://www.isrctn.com/ | none ⚠️ | $0 | UK/EU trial registry | tertiary |
| **EU CTIS (EU Clinical Trials)** | Optional | 🔓 keyless | https://euclinicaltrials.eu/ | none ⚠️ | $0 | EU trial registry | tertiary |

**Impact if absent:** ClinicalTrials.gov v2 is authoritative and free; the others are ex-US redundancy, rarely needed for a US-listed biotech universe.

### PDUFA / FDA catalysts (**the one real paid decision** — see deep-dive)

| Source | Req/Opt | Key | Signup / key link | Free-tier | Monthly cost | What it gives | Rank |
|---|---|---|---|---|---|---|---|
| **RTTNews FDA Calendar** | Required | 🔓 scrape | https://www.rttnews.com/corpinfo/fdacalendar.aspx | free HTML (scrape gently) | $0 | **Best free PDUFA + AdCom list w/ outcomes** (editorial — confirm vs PR) | **primary (discovery)** |
| **Federal Register API** | Required | 🔓 keyless | https://www.federalregister.gov/developers/documentation/api/v1 | none | $0 | **AdCom meeting notices — legally complete** | **primary (AdCom)** |
| **Company 8-K / PR via SEC EDGAR** | Required | 🔓 keyless | https://efts.sec.gov/LATEST/search-index (UA email) | ≤10 req/s | $0 | **Authoritative PDUFA date confirmation** | **primary (confirm)** |
| **openFDA** | Optional | 🔑 free key (optional) | https://open.fda.gov/apis/authentication/ | 240 req/min w/ key; 40/min keyless ⚠️ | $0 | retrospective approvals only — **no forward PDUFA dates** | low value for this need |
| **Drugs.com FDA calendar** | Optional | 🔓 scrape | https://www.drugs.com/new-drug-applications.html | bot-walled (403) | $0 | NDA/BLA list, month-granularity | skip (bot-walled, coarse) |
| **FDA.gov AdCom calendar** | Optional | 🔓 scrape | https://www.fda.gov/advisory-committees/advisory-committee-calendar | JS-walled | $0 | same data as Federal Register, worse format | skip (use Fed Register) |
| **BioPharmaCatalyst / BPIQ** | Optional | 💳 paid | https://www.biopharmacatalyst.com/pro | teaser free (bot-gated) | ⚠️ **UNVERIFIED** — bot-walls WebFetch; confirm at link | curated PDUFA/AdCom/catalyst calendar, phase, breadth | the paid breadth option |
| **FDATracker** | Optional | 💳 paid | https://www.fdatracker.com/fda-calendar/ | thin free JS embed | ⚠️ UNVERIFIED | paid FDA calendar | alt paid option |
| **MarketBeat FDA calendar** | Optional | 💳 paid (MarketBeat All Access) | https://www.marketbeat.com/fda-calendar/ | teaser free | ⚠️ UNVERIFIED | FDA calendar within a general-markets sub | alt paid option |
| **Benzinga Pro** | Optional | 💳 paid | https://pro.benzinga.com/ | trial | ⚠️ UNVERIFIED | catalyst/newsfeed incl. FDA | alt paid option (news-heavy) |

### Earnings calendar

| Source | Req/Opt | Key | Signup / key link | Free-tier | Monthly cost | What it gives | Rank |
|---|---|---|---|---|---|---|---|
| **Nasdaq public JSON** | Required | 🔓 keyless (UA header) | `api.nasdaq.com/api/calendar/earnings?date=` (page https://www.nasdaq.com/market-activity/earnings) | none (1 req/day covers market) | $0 | full-day earnings list + consensus EPS | **primary** |
| **FMP earnings calendar** | Optional | 🔑/💳 | https://site.financialmodelingprep.com/register | 250 req/day free (per STACK.md) — **but our free key 402'd on this endpoint** | ⚠️ paid tier UNVERIFIED (bot-walled) | earnings dates | secondary — needs a paid tier to unlock (see fundamentals note) |
| **Finnhub `/calendar/earnings`** | Optional | 🔑 free key | https://finnhub.io/register | 60/min free | $0 | earnings dates | secondary |
| **Alpha Vantage `EARNINGS_CALENDAR`** | Optional | 🔑 free key | https://www.alphavantage.co/support/#api-key | 25 req/day | $0 | earnings dates | tertiary |
| **Twelve Data earnings** | Optional | 🔑 free key | https://twelvedata.com/register | 800 req/day | $0 | earnings dates | tertiary |

**Impact if absent:** Nasdaq keyless covers the whole market in one request/day — the FMP 402 is a non-issue; just use Nasdaq (already the primary).

### Short interest

| Source | Req/Opt | Key | Signup / key link | Free-tier | Monthly cost | What it gives | Rank |
|---|---|---|---|---|---|---|---|
| **FINRA Query API** | Required | 🔓 keyless | https://developer.finra.org/docs (`api.finra.org` consolidatedShortInterest) | none (tested no-auth) | $0 | bi-monthly consolidated short interest, days-to-cover | **primary** (triple-verified vs Nasdaq + Yahoo) |
| **Nasdaq short-interest JSON** | Optional | 🔓 keyless (UA) | `api.nasdaq.com/api/quote/{T}/short-interest` | none | $0 | same underlying data | secondary (cross-check) |
| **yfinance `sharesShort`/`shortRatio`** | Optional | 🔓 keyless | `pip install yfinance` | none | $0 | short shares + ratio estimate | tertiary |

### Filings / fundamentals / float / insider

| Source | Req/Opt | Key | Signup / key link | Free-tier | Monthly cost | What it gives | Rank |
|---|---|---|---|---|---|---|---|
| **SEC EDGAR via `edgartools`** | Required | 🔓 keyless (set email) | `pip install edgartools` → `set_identity("email")`; docs https://www.sec.gov/edgar/search/ | ≤10 req/s | $0 | XBRL financials, **shares outstanding**, cash-runway, Form 4/13F/13D, 8-K | **primary** |
| **SEC XBRL raw JSON** | Optional | 🔓 keyless (UA email) | `data.sec.gov/api/xbrl/...` (docs https://www.sec.gov/edgar/sec-api-documentation) | ≤10 req/s | $0 | same facts, keyless GET (fallback if edgartools undesired) | secondary |
| **yfinance `info.floatShares`** | Optional | 🔓 keyless | `pip install yfinance` | none | $0 | float estimate (vendor-derived) | secondary (float denominator) |
| **FMP** | Optional | 🔑/💳 | https://site.financialmodelingprep.com/register | 250 req/day free (STACK.md) | ⚠️ paid UNVERIFIED (bot-walled) | quotes + statements + float in one API | tertiary — convenience only; EDGAR is authoritative |
| **finvizfinance** | Optional | 🔓 scrape | `pip install finvizfinance` | Finviz bot-sensitive | $0 | float / short-float% / insider-own% cross-check | skip unless a 3rd float estimate wanted |

**Impact if absent:** `edgartools` (keyless) is authoritative and free for fundamentals, shares-outstanding, cash-runway, and insider/institutional filings. FMP adds nothing the free stack lacks — its only draw was one-call convenience, and the free key 402s on the endpoints that mattered.

### Macro / rates / VIX (risk-regime context)

| Source | Req/Opt | Key | Signup / key link | Free-tier | Monthly cost | What it gives | Rank |
|---|---|---|---|---|---|---|---|
| **FRED API** | Required | 🔑 free key (instant) | https://fredaccount.stlouisfed.org/apikeys (docs https://fred.stlouisfed.org/docs/api/api_key.html) | ~120 req/min | $0 | treasuries, curve (`T10Y2Y`), fed funds, **free VIX history (`VIXCLS`)**, CPI, unemployment | **primary** (fills the macro gap — we had zero) |

**Impact if absent:** no risk-regime input (biotech binaries behave differently in a risk-off/high-VIX tape). FRED is a free instant key — get it.

### News / headlines (intra-week monitor)

| Source | Req/Opt | Key | Signup / key link | Free-tier | Monthly cost | What it gives | Rank |
|---|---|---|---|---|---|---|---|
| **Finnhub company news** | Optional | 🔑 free key | https://finnhub.io/register | 60/min free | $0 | per-ticker news headlines | primary (free) |
| **GDELT** | Optional | 🔓 keyless | https://www.gdeltproject.org/ | none | $0 | global news event stream | secondary |
| **Company 8-K via EDGAR** | Required | 🔓 keyless | https://efts.sec.gov/LATEST/search-index | ≤10 req/s | $0 | material-event filings (authoritative) | **primary (material events)** |
| **RSS (company IR / FDA / PR wires)** | Optional | 🔓 keyless | per-source feeds | none | $0 | headline monitoring | secondary |
| **Benzinga Pro** | Optional | 💳 paid | https://pro.benzinga.com/ | trial | ⚠️ UNVERIFIED | low-latency catalyst newsfeed | skip unless latency edge wanted |

### Execution (broker)

| Source | Req/Opt | Key | Signup / key link | Free-tier | Monthly cost | What it gives | Rank |
|---|---|---|---|---|---|---|---|
| **Robinhood Agentic Trading MCP** (official) | Required | 🔑 OAuth (funded RH acct) | https://robinhood.com/us/en/agentic-trading/ | n/a | **$0 for the MCP itself** — you pay only standard RH trading costs; equities commission-free | live equities buy/sell + read portfolio/quotes; segregated agent account | **primary (only ToS-safe path)** |

**Cost note (Robinhood):** the Agentic Trading MCP is **free to connect** — it's a feature of a Robinhood brokerage account, not a paid API. No monthly fee for the MCP was found (⚠️ the *MCP fee* is UNVERIFIED-as-$0 but consistent with RH's commission-free model and the official newsroom framing). You need a funded Robinhood account; equities trades are commission-free (regulatory/exchange pass-through fees still apply per RH's fee schedule). ToS: sanctioned, segregated agent account, per-trade push notifications, disconnect anytime.

---

## PDUFA-tracker deep-dive (the one decision money is actually about)

**The gap:** there is no clean, free, authoritative *forward* PDUFA-date API. Company PRs originate the dates; commercial trackers aggregate them. That aggregation is the only thing a subscription buys.

**What free already covers (and it's a lot):**
- **RTTNews FDA Calendar** (free HTML) — best free PDUFA + AdCom list *with outcomes backfilled*; live-verified structured rows (ticker, drug, application type, date, event, outcome). Editorial → treat as discovery, confirm before trading.
- **Federal Register API** (free, keyless) — every AdCom meeting is *legally required* to be noticed here; coverage is complete by construction.
- **Company 8-K / PR via EDGAR** (free, keyless) — the authoritative confirmation and change-detection (CRL, extension, resubmission).

For a **curated ~20-name universe**, this three-source free stack reduces PDUFA work to a *review* task (confirm/adjust a small table), not a *discovery* task. That's the honest state of the art.

**What a paid tracker buys:** breadth (whole-market catalyst discovery), a pre-curated calendar with phase/drug metadata, and removal of the manual confirm step. It does **not** buy authoritativeness — the trackers are aggregating the same PRs.

**Paid options and prices:**

| Tracker | Signup | Price | Verified? | Notes |
|---|---|---|---|---|
| **BioPharmaCatalyst / BPIQ** | https://www.biopharmacatalyst.com/pro | ⚠️ **UNVERIFIED** | No — site fingerprint-gates bots; WebFetch got a parked/placeholder page and the session's WebSearch budget (200/200) was spent by prior agents | Historically the best-curated FDA calendar. **Operator must open the link in a real browser to read the current tier price.** |
| **FDATracker** | https://www.fdatracker.com/fda-calendar/ | ⚠️ UNVERIFIED | No — JS embed | paid product; confirm at link |
| **MarketBeat FDA calendar** | https://www.marketbeat.com/fda-calendar/ | ⚠️ UNVERIFIED | No | FDA calendar bundled inside MarketBeat All Access (general-markets sub) |
| **Benzinga Pro** | https://pro.benzinga.com/ | ⚠️ UNVERIFIED | No | catalyst + newsfeed; priced for active traders, likely the most expensive |

> **Honesty flag:** I could not verify a single paid-PDUFA price today — all four bot-wall automated fetching, and WebSearch was exhausted. Per cite-or-drop, I am **not** printing a number I can't source. The operator should open the BPIQ link in a browser to get the live figure; expect a consumer-SaaS monthly (roughly the $30–100/mo band these tools have historically occupied — **stated as a band to size the decision, explicitly NOT a verified quote**).

**Verdict:** For 20 names, **free covers it.** Buy a tracker only to (a) expand the universe well beyond 20 names, or (b) eliminate the ~10-min/week confirm step and you value that more than the subscription. It's a convenience purchase, not a capability purchase.

---

## LLM runtime cost (flagged separately — usage-based, NOT a data key)

The desk runs on the **Anthropic API (Claude)** — a per-use operating cost, not a fixed monthly subscription. Verified per-token prices (✅ platform.claude.com pricing docs, 2026-08-16):

| Model | Input ($/MTok) | Output ($/MTok) | Batch input | Batch output |
|---|---|---|---|---|
| **Claude Opus 4.8** | $5 | $25 | $2.50 | $12.50 |
| **Claude Sonnet 5** | $2 | $10 | $1 | $5 |
| **Claude Haiku 4.5** | $1 | $5 | $0.50 | $2.50 |

Cache reads = 0.1× input; Batch API = 50% off both directions.

**Rough per-weekly-cycle order of magnitude (DERIVED, not measured — label accordingly):** The `TOKEN-NOTES.md` ledger tracks *build* spend (~16.6M tokens cumulative across all phases), which is **not** the same as one runtime desk cycle. A weekly cycle ≈ catalyst scan + a multi-agent analyst desk (bull/bear/judge) + DD pass + recommendation, per active candidate. If a cycle consumes on the order of **~1–3M tokens** (build agents run ~80–160k each; a desk is several such invocations across a handful of candidates), then:
- **Sonnet-heavy mix, with prompt caching:** **~$3–15/week** (~$12–65/month).
- **Opus-heavy mix:** **~2–4× that** (~$10–50/week).

This is an **order-of-magnitude estimate from build-phase token sizes, not a metered runtime number** — the real figure lands after the first live cycles. It is usage-based and scales with how many desks run per week and the model mix. Not a subscription; not part of the "minimum data-key spend."

---

## Confirm the genuinely-free / no-cost keys (for the "$0, just register" list)

| Source | Key type | Action |
|---|---|---|
| **FRED** | 🔑 free instant key | Register + request key: https://fredaccount.stlouisfed.org/apikeys |
| **Alpha Vantage** | 🔑 free key | Instant: https://www.alphavantage.co/support/#api-key (free tier = 25 req/day ✅) |
| **Tiingo** | 🔑 free key | https://www.tiingo.com/account/token (free = 500 symbols/mo ✅) |
| **Finnhub** | 🔑 free key | https://finnhub.io/register (free = 60/min) |
| **openFDA** | 🔑 free key (optional) | https://open.fda.gov/apis/authentication/ (raises keyless 40/min → 240/min) |
| **ClinicalTrials.gov v2** | 🔓 no key at all | Just call https://clinicaltrials.gov/data-api/api |
| **Federal Register** | 🔓 no key at all | https://www.federalregister.gov/developers/documentation/api/v1 |
| **SEC EDGAR** | 🔓 no key — set a UA/`set_identity` email | https://www.sec.gov/edgar/search/ |
| **FINRA (short interest Query API)** | 🔓 no key (tested no-auth) | https://developer.finra.org/docs |
| **CBOE delayed quotes** | 🔓 no key | `cdn.cboe.com/api/global/delayed_quotes/options/{T}.json` |
| **Nasdaq public JSON** | 🔓 no key (browser UA header) | `api.nasdaq.com/...` |
| **GDELT** | 🔓 no key | https://www.gdeltproject.org/ |

---

## Minimum required spend — the verdict

**$0/month.** Confirmed. The system as designed runs entirely on free sources:
- Prices: yfinance + free-key redundancy (AV/Tiingo/Twelve Data/Polygon/EODHD) — all $0.
- Options/IV: CBOE (keyless) + AV historical (free drip) — $0.
- Trials: ClinicalTrials.gov v2 (keyless) — $0.
- PDUFA/AdCom: RTTNews + Federal Register + EDGAR PR confirmation — $0.
- Earnings: Nasdaq (keyless) — $0.
- Short interest: FINRA (keyless) — $0.
- Fundamentals/float/insider: edgartools (keyless) — $0.
- Macro/VIX: FRED (free instant key) — $0.
- News: Finnhub free + EDGAR 8-K + GDELT — $0.
- Execution: Robinhood Agentic MCP — $0 for the MCP (funded RH account, commission-free equities).

**Only cost that always exists:** the Anthropic API (usage-based, ~$12–65/mo order-of-magnitude, not a data key).

## Recommended tier

**Recommended data-key spend: $0/month** — get the free keys (FRED, Alpha Vantage, Tiingo, Finnhub; optionally openFDA), which cost nothing and add redundancy, and keep PDUFA as a reviewed manual table (RTTNews + Federal Register + PR).

**If, and only if, the operator wants to remove the PDUFA manual-curation burden:** open the BPIQ link in a browser, read the live price, and subscribe to the cheapest tier that gives an exportable/curated FDA calendar — **budget ~$30–100/month for it** (band, not a verified quote). This is a convenience purchase; it does not change what the system *can* do, only how much human time the PDUFA table costs each week. Revisit necessarily if the universe expands past ~20 names, where free discovery breadth starts to strain.

**Cheapest paid *capability* upgrade if ever needed (not now):** Polygon/Massive Options **Starter $29/mo** ✅ — real-time vendor greeks/IV — only if CBOE-free IV ever proves insufficient for a hard DD input.

---

## Sources

**✅ VERIFIED LIVE (WebFetch of vendor pricing page, 2026-08-16):**
- Alpha Vantage premium — https://www.alphavantage.co/premium/ (free 25/day; $49.99/$99.99/$149.99/$199.99/$249.99 per rpm tier)
- Tiingo — https://www.tiingo.com/pricing (free $0 / Power $30)
- Twelve Data — https://twelvedata.com/pricing (Basic free / Grow $29 / Pro $99 / Ultra $329)
- EODHD — https://eodhd.com/pricing (free / $19.99 / $29.99 / $59.99 / $99.99)
- Polygon / Massive Options — https://massive.com/pricing?product=options (free / $29 / $79 / $199)
- Polygon / Massive Stocks — https://massive.com/pricing?product=stocks (free / $29 / $79 / $199)
- Marketstack — https://marketstack.com/product (free 100/mo / $9.99 / $49.99 / $149.99)
- Claude API pricing — https://platform.claude.com/docs/en/about-claude/pricing (Opus 4.8 $5/$25; Sonnet 5 $2/$10; Haiku 4.5 $1/$5; Batch 50% off; cache read 0.1×)

**⚠️ UNVERIFIED (bot-walled to WebFetch; WebSearch budget exhausted 200/200 — confirm at link):**
- FMP pricing — https://site.financialmodelingprep.com/pricing-plans (403; free tier 250 req/day per project STACK.md)
- ORATS — https://orats.com (404/403; ~$99/mo cited single-source in free-data-sources.md §5.2)
- Finnhub paid tiers — https://finnhub.io/pricing (not fetchable; free 60/min per free-data-sources.md §1.7)
- BioPharmaCatalyst / BPIQ, FDATracker, MarketBeat, Benzinga Pro — parked/JS/bot-walled

**Carried from project's prior live-verified research (2026-08-15/16):**
- `.planning/research/free-data-sources.md`, `.planning/research/free-data-pipeline.md`, `CLAUDE.md` STACK table, `.planning/TOKEN-NOTES.md`

**Metadata:** Prices ✅-tagged are HIGH confidence (fetched today). Prices ⚠️-tagged are UNVERIFIED — not to be treated as quotes. Research date 2026-08-16; valid ~30 days for stable SaaS pricing.
