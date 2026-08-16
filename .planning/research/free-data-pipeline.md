# Free Data Pipeline — Ecosystem, Anti-Block, Always-On Architecture

**Researched:** 2026-08-16
**Domain:** Extending free-source coverage + designing the constantly-running, accuracy-first ingestion daemon on top of the Phase 6.9 foundation.
**Confidence:** HIGH on the ecosystem/library survey (repo + PyPI metadata pulled live this date); HIGH on architecture (reuses signatures already read in `06.9-RESEARCH.md`); MEDIUM on a few endpoint shapes (SEC/FRED bot-walled to WebFetch — endpoints carried from prior verified research + training, re-validated at shakedown).

> **Reading note.** This doc EXTENDS `free-data-sources.md` and `06.9-RESEARCH.md` — it does not restate the CBOE/FINRA/FedRegister/RTTNews/CT.gov/price-cascade findings, which are settled there. Scope here: (1) new gap-filling sources + a survey of how indie quants actually pull free data, (2) anti-block + N-source triangulation, (3) the always-on daemon, (4) a proposed roadmap phase.

**Search-budget honesty:** the session's 200-call WebSearch budget was already spent by prior agents; every finding below is from a direct `gh api` / PyPI / WebFetch probe this date, prior live-verified research, or clearly-flagged training knowledge. No unverified web-search claims.

---

## Summary

Two genuine gaps remain after 6.9: **fundamentals/float** (our known weak spot) and **macro/rates regime** (we have none). Both are filled by GREEN, keyless-or-instant-key, authoritative free sources — **SEC XBRL via the `edgartools` library** (fundamentals, shares outstanding, cash-for-runway, Form 4/13F/13D — MIT, maintained *yesterday*, "runs in production at hedge funds") and the **FRED API** (rates, VIX, regime — free instant key, ~120 req/min, GREEN). Neither needs scraping.

**OpenBB is MIRROR, not adopt.** It is AGPL-3.0-only with 50+ dependencies, and its provider menu (`alpha_vantage, cboe, finra, fmp, fred, nasdaq, sec, tiingo, tradier, yfinance` + macro) is a near-superset of what we already wire directly and a *menu of what to add next*. We already have its core idea — a ranked provider registry + cascade. Adopting it would import copyleft + a heavy tree into a system the operator must read end-to-end. Steal the menu; keep our ~20-line httpx providers.

**The always-on pipeline is thin.** Because the store is idempotent-by-construction (UPSERT on natural keys) and every consumer reads the store, a constantly-running daemon is just: a `launchd` job that invokes one `run_cycle()` on a cadence, a gap-detector that enqueues backfill, a raw-snapshot write in the existing `_http` base, and a `.monitor/data_health.json` writer for the existing monitor. launchd IS the supervisor and crash-recovery; idempotency IS the resumability. No long-lived loop, no queue, no new infra, $0.

**Primary recommendation:** Add **edgartools** (fundamentals/float — the one new dependency worth it) and a plain-httpx **FRED** provider; extend the price cross-check to **N-source median**; write **raw snapshots to a local lake**; and ship the daemon as a **launchd + `scripts/daemon.py` + gap-detector + health-json** phase after 6.9. Everything else reuses 6.9 unchanged.

---

## 1. Ecosystem survey — how indie quants pull free data (2026), gap-first

All repo/license/freshness fields pulled live via `gh api` / PyPI on 2026-08-16.

### 1.1 GAP-FILLERS (add these — they cover what we lack)

| Source / tool | Coverage | Free-tier / access | ToS | Adopt vs mirror | Gap or overlap | Verdict |
|---|---|---|---|---|---|---|
| **SEC XBRL via `edgartools`** (dgunning/edgartools, MIT, pushed 2026-08-15, 2.6k★) | Income/balance/cash-flow (XBRL-standardized), **shares outstanding**, public-float fields, Form 4 insiders, 13F, 13D/G, 8-K — back to 1994, typed Python objects | `pip install edgartools`; **no key, no bills**; `set_identity("email")` sets the SEC UA for you; handles XBRL parsing | 🟢 GREEN (public-domain gov data, keyless) | **ADOPT** (1 MIT dep) | **FILLS #1 gap (fundamentals/float/cash-runway)** + overlaps & *upgrades* the hand-rolled `edgar.py` (accessions/live_shelf) | **ADOPT.** Replaces fragile hand-XBRL parsing with a maintained lib "run in production at hedge funds." Passes ponytail rung 5: a few lines can't do XBRL-standardization correctly. Operator pre-greenlit edgartools as a candidate. |
| **SEC XBRL raw JSON** (`data.sec.gov/api/xbrl/...`) | Same facts, keyless JSON: `companyfacts/CIK{10d}.json` (all facts), `companyconcept/CIK/us-gaap/{tag}.json` (one series), `frames/us-gaap/{tag}/USD/CY{Y}Q{Q}I.json` (one concept, all filers) | keyless GET, **UA with contact email required**, ≤10 req/s | 🟢 GREEN | **MIRROR** (fallback if we don't want the dep) | Fills fundamentals | **FALLBACK path.** If `edgartools` is ever undesirable, `companyconcept .../dei/EntityCommonStockSharesOutstanding.json` gives exact shares-out in one keyless GET (already cited in `free-data-sources.md §3.4`). Prefer edgartools; keep the raw endpoints documented. |
| **FRED API** (St. Louis Fed) | Macro/rates regime: `DGS10`/`DGS2` (treasuries), `T10Y2Y` (curve), `FEDFUNDS`/`DFF`, `VIXCLS` (**free VIX history**), `CPIAUCSL`, unemployment | `api.stlouisfed.org/fred/series/observations?series_id=&api_key=&file_type=json`; **free instant key**, ~120 req/min | 🟢 GREEN documented | **MIRROR** (~20-line httpx provider) | **FILLS macro gap — we have ZERO macro/regime data today** | **ADD as `providers/fred.py`.** Rates + VIX give the desk a risk-regime input (biotech binaries behave differently in a risk-off/high-VIX tape). One keyed httpx provider. |
| **archive.org Wayback CDX** | Point-in-time reconstruction of HTML pages we didn't capture live: `web.archive.org/cdx/search/cdx?url=&output=json&from=&to=` lists snapshots; `web.archive.org/web/{ts}id_/{url}` returns the *raw* original (no banner rewrite) | keyless, polite rate | 🟢/🟡 (public archive, be gentle) | **MIRROR** (only if backfill needs it) | Fills **deep-history** for HTML sources (RTTNews calendar, company IR pages) | **BACK-POCKET.** Genuinely useful for slowly rebuilding a clean historical archive (accuracy-over-speed). Honest caveat: Wayback rarely archived JSON API endpoints (`api.nasdaq.com` etc.), so it's for HTML pages, not our JSON feeds. MEDIUM value; wire only when a specific historical gap needs it (YAGNI until then). |
| **SEC EDGAR full-text search** (`efts.sec.gov/LATEST/search-index?q=&forms=`) | Full-text filings back to 2001 (8-K/PR discovery, PDUFA confirmation) | keyless JSON, UA rule | 🟢 GREEN | already planned (`edgar.py`) | Deep-history PR/8-K confirmation | Already in `free-data-sources.md §3.3`; `edgartools` also exposes it. Keep. |

### 1.2 AGGREGATORS & COMMUNITY LIBS (mostly mirror-not-adopt)

| Tool | Status (live 2026-08-16) | What it gives | Verdict |
|---|---|---|---|
| **OpenBB Platform** (`openbb` 4.7.2) | **AGPL-3.0-only**, 71.9k★, 50+ deps, providers: `alpha_vantage cboe finra fmp fred nasdaq sec tiingo tradier yfinance` + macro (`ecb econdb eia imf oecd bls federal_reserve multpl famafrench`) + `congress_gov government_us` | One standardized interface over dozens of free sources; ranked-provider pattern | **MIRROR — do NOT adopt.** (a) AGPL-3.0 copyleft is a landmine for a system with a network/iOS bridge + possible distribution; (b) 50+ deps vs. "minimal deps, read end-to-end"; (c) it wraps the SAME sources we already wire directly; (d) **we already have its core pattern** (`PRICE_PROVIDERS` ranked registry + cascade). Its real value = **a menu**: it confirms `sec`, `fred`, and macro (`ecb/oecd/imf`) are the standard next adds. Steal the menu, keep our httpx providers. |
| **yfinance** (Apache-2.0, pushed 2026-08-13, 25k★) | prices, chains, `info.floatShares` | 🟡 tolerated | **KEEP** — already primary-history-in-cascade + float estimate. Very actively maintained. |
| **yahooquery** (MIT, pushed 2025-05-15, 916★) | bulk Yahoo modules (multi-ticker `info` in one call) | 🟡 | **SKIP for now.** 15-months-stale; only edge over yfinance is bulk multi-ticker fetch — irrelevant at 20 names. Note as a fallback if yfinance breaks. |
| **finvizfinance** (PyPI, MIT) | Finviz screener snapshot: float, short-float%, insider-own%, quick fundamentals in one row | 🟡 (Finviz bot-sensitive) | **MAYBE** — a convenient *cross-check* for float/short-float vs SEC+yfinance. Not authoritative. Only add if we want a 3rd float estimate; SEC shares-out + yfinance float already give the denominator. |
| **FinanceDatabase** (MIT, pushed 2026-08-09, 8.3k★) | static reference DB of ~300k symbols w/ sector/industry/country metadata | 🟢 (bundled data) | **SKIP** — corporate metadata for a hand-curated 20-name universe is 10 min of a CSV. YAGNI. |
| **sec-edgar-downloader** (MIT, pushed 2026-06-22, 714★) | bulk-downloads raw filing files | 🟢 | **SKIP** — `edgartools` does this + parses. Redundant. |
| **pandas-datareader** (BSD, pushed 2026-07-21, 3.2k★) | legacy multi-source reader (FRED, Stooq, etc.) | mixed | **SKIP** — thin wrapper; we call FRED/sources directly. Its Stooq path hits the same geo-block. |
| **stockanalysis.com / macrotrends** | free fundamentals web/undocumented-JSON | 🟡 scrape | **SKIP** — SEC XBRL is the authoritative free fundamentals source; these are YELLOW redundancy. (stockanalysis `api/symbol/...` probe 404'd this date — endpoint moved; not worth chasing.) |

### 1.3 Undocumented-but-public JSON APIs (the retail backbone) — status

Already in our stack or covered: Yahoo `query1/2` (via yfinance), `api.nasdaq.com` (prices/SI/earnings/option-chain — 🟡, live-verified), CBOE cdn (🟡, primary IV), SEC `data.sec.gov`/`efts` (🟢). **New/confirmed-standard to add:** SEC XBRL (§1.1), FRED (§1.1). Wikipedia/Wikidata for corporate metadata — SKIP (20-name CSV). This is exactly the set OpenBB's provider list validates.

---

## 2. Anti-block + accuracy / triangulation

### 2.1 Polite scraping (all already in the 6.9 `_http` base — confirm, don't rebuild)

Realistic rotating/browser UA per YELLOW host (SEC gets a *contact-email* UA, not a browser one); **session reuse** (`httpx.Client`, keep-alive); backoff + jitter; ≤1 req/s per host; **cache-first ≥5-min TTL** (never refetch in-window); honor rate limits + robots for page-discovery. Nothing new — `06.9-RESEARCH.md Pattern 2` already specifies this base. The daemon just *runs it on a schedule*.

### 2.2 IP / geo-block (Stooq) — HONEST VERDICT: don't proxy, route around

- **Free proxies:** unreliable (most dead/slow), and dangerous — many public proxies are honeypots that intercept traffic; you'd be routing financial fetches through unknown hosts. Also evades a geo-block (ToS-gray). **Reject.**
- **Tor:** exit nodes are widely blacklisted by financial sites (you'll trade a geo-block for a Tor-block), slow. **Reject.**
- **Paid residential proxies:** violate the FREE-only constraint. **Reject.**
- **Self-hosted egress** (free-tier cloud VM / GitHub-Actions runner in an allowed region as a SOCKS tunnel): $0 and your own IP, not a shared proxy — the *only* non-sketchy free option. But it adds ops + still evades the block. **Not worth it for Stooq**, which is a REDUNDANT price source: yfinance + Nasdaq + AV + Tiingo already return RAW OHLC and **agree to 0.000%** (`free-data-sources.md` cross-check). **Verdict: leave Stooq disabled in the registry; the correct answer to a geo-block on a redundant source is to drop it, not evade it.** Keep the self-hosted-egress option in the back pocket *only* if a genuinely UNIQUE source ever gets blocked — none is today.

### 2.3 Accuracy / data-quality (the operator's priority — lean in hard)

- **N-source median triangulation (extend the 6.9 pairwise cross-check).** For prices, instead of yfinance-vs-Nasdaq pairwise, take the **median close across all available sources** per `week_end`; accept if max pairwise delta ≤ `tol_pct` (0.5%); store `agreeing_sources` = the in-tolerance set. Median is robust to one bad source in ≥3; pairwise stays the ≤2-source case. Same store columns (`source_grade`, `agreeing_sources` from migration 007) — no new schema.
- **Split/dividend artifact detection.** A ~2× or ~0.5× jump in *raw* close between consecutive weeks with no matching volume/news pattern → candidate corporate action; cross-check against an 8-K (`edgartools`) or a divergence between sources at that boundary (RAW sources legitimately diverge across a split date — the divergence flag *catches* it). Log, don't auto-adjust (RAW is locked).
- **Bad-tick / stale detection.** Single-bar spike > N·σ that reverts next bar → drop the tick, refetch. Stale = `fetch_ts` age > 2× the source's cadence → mark degraded.
- **Reconciling disagreements:** keep the highest-grade source's bar, narrow `agreeing_sources` to it, **log the divergence** (ticker, week, per-source values, max delta), surface the count in the health JSON + shakedown report. Never average across a disagreement into a fabricated value.
- **Raw-snapshot archive (`raw_snapshot_path`) — the audit lever.** Write every fetched response to a local lake keyed by `(source, ticker, fetch_ts)` (§3.4). Lets us **re-parse** when a parser bug is found *without* re-fetching, and prove provenance. Cheap on local disk. This is the concrete form of "accuracy over speed": keep the evidence.

---

## 3. Always-on / constantly-running pipeline architecture

**Design principle:** the store is idempotent-by-construction (UPSERT on natural keys) and every consumer reads the store → a daemon is *just scheduled ingestion + gap-repair + health reporting*. No queue, no long-lived state machine, no new infra.

### 3.1 Scheduler — launchd + a stateless `run_cycle()` (ponytail: launchd IS the daemon)

```
scripts/daemon.py:  run_cycle()  # one full pass, then exit
  → for each source due (per cadence table): fetch → snapshot → UPSERT via existing store paths
  → detect_gaps() → enqueue backfill for missing/stale
  → write .monitor/data_health.json
```

- **launchd** `StartInterval` (or `StartCalendarInterval`) invokes `run_cycle()` on a cadence and **relaunches on crash** (`KeepAlive` on failure). launchd is the supervisor + crash-recovery; idempotency is the resumability. This beats a hand-rolled `while True: … sleep()` + supervisor (skip that — more state, no benefit). Matches the fleet's launchd standard.
- **Cadence table** (accuracy-first, polite — NOT low-latency), driving what's "due":

| Source | Cadence | Why |
|---|---|---|
| prices (cascade) | daily after US close | weekly bars settle EOD; N-source median |
| options/IV (CBOE) | 1–2×/day per name | 15-min delayed anyway |
| short interest (FINRA) | on publication (bi-monthly, ~T+9) | no point polling more |
| catalysts (CT.gov / FedRegister / RTTNews / earnings) | daily | discovery + verify |
| fundamentals / XBRL (edgartools) | weekly | 10-Q/K change quarterly |
| macro / VIX (FRED) | daily | regime context |

### 3.2 Self-healing (gap detection + backfill + dead-source failover)

- **Gap detection** each cycle: expected name-weeks (universe × weeks in window) vs. present rows in `price_bar` → missing set; `fetch_ts` older than 2× cadence → stale set; universe names with a known upcoming catalyst but no card → missing card.
- **Backfill:** feed the gap set back through the *same* `ingest` path with a wider window. Idempotent → safe to re-run; drip keyed GREEN budgets (AV 25/day) across days (accuracy-over-speed).
- **Dead-source detection + failover:** per-source consecutive-failure counter; mark degraded after N; the price **cascade already fails over** to the next-ranked source, and each other need has ≥2 sources. Degradation is logged, never fatal — `_http` returns empty, never raises into the pipeline.
- **Resumability:** none needed beyond idempotency — a crash mid-cycle just re-runs; UPSERT means no dupes, no partial-write corruption (writes are atomic per `store.py`).

### 3.3 Data-quality monitoring → the existing monitor

`monitor/server.py` already reads `.monitor/*.json`. The daemon writes **`.monitor/data_health.json`** each cycle:

```json
{ "updated": "...", "sources": { "yfinance": {"last_success":"...","consec_fail":0,"degraded":false}, ... },
  "coverage_pct": 0.98, "stale_sources": [], "gaps": {"price_weeks_missing": 3},
  "divergences_7d": 1, "degraded": [] }
```

Metrics that matter: **per-source last_success + consec_fail + degraded flag; coverage %** (name-weeks present / expected); **stale-source list; gap counts; cross-source divergence count.** Alert (surface in monitor, optionally a ZeeChat ping) on: a source degraded > threshold, coverage drop, divergence spike, staleness beyond cadence. This makes "is the desk reading fresh, triangulated data?" answerable at a glance.

### 3.4 Raw-snapshot lake (provenance archive, cheap local disk)

- Layout: `data/raw/{source}/{yyyy}/{mm}/{ticker}_{fetch_ts}.json` (`.html` for scrapes). Written by the `_http` base on every fetch + a small hook for the yfinance/edgartools calls.
- Persisted datum stores `raw_snapshot_path` alongside `source_url/fetch_ts/grade` → full audit trail; enables re-parse without re-fetch.
- Cheap: JSON/HTML on local disk; a size cap + monthly prune keeps it bounded (biotech universe = tiny). $0.

### 3.5 Cost = $0 (verified)

launchd (built-in), local disk, all free sources (keyless or free-instant-key), no cloud, no paid tier. **Redundancy (N-source median) + slow polite polling is the accuracy lever — not spend.**

### 3.6 Reuse vs. build (pipeline)

**REUSE unchanged:** `_http` (cache/rate-limit/degrade), every provider + the price cascade/cross-check, all `store` UPSERT paths (idempotency = crash-safety + backfill-safety), `ingest.assemble_raw` + the historical loop, `monitor/server.py`. **NEW (thin):** the cadence table + `run_cycle()`/`scripts/daemon.py`, `detect_gaps()`, the `.monitor/data_health.json` writer, the raw-snapshot write hook, and the launchd plist. Plus the two new source providers (edgartools-backed fundamentals, FRED) and the N-source-median upgrade.

---

## 4. Proposed ROADMAP phase (addition after 6.9)

### Phase 6.10 — Always-On Data Daemon, Coverage Expansion & Quality Monitor

**Goal:** turn the 6.9 one-shot ingestion into a constantly-running, self-healing, quality-monitored pipeline that keeps the store warm, triangulated, and point-in-time-correct — and fill the two remaining source gaps (fundamentals/float, macro). $0, accuracy-first.

**Depends on:** 6.9 (providers, `_http`, price cascade, store UPSERTs, `ingest`) merged.

| Req ID | Requirement | Success criterion |
|---|---|---|
| PIPE-01 | **Fundamentals/float provider** via `edgartools` (income/balance/cash-flow, shares-outstanding, cash-runway, Form 4/13F/13D) behind the provider interface, provenance-tagged | offline test: fixture filing → typed fundamentals dict w/ `source_url/fetch_ts/grade=green`; feeds `raw["cash_runway_months"]`/shares-out; **replaces or wraps** hand-rolled `edgar.py` accessions/live_shelf with zero downstream contract change |
| PIPE-02 | **FRED macro provider** (`providers/fred.py`, keyed httpx) — rates + VIX + curve series into the store/regime context | offline test (pytest-httpx): fixture → macro series dict w/ provenance; `settings.fred_api_key` optional env-first; degrades to skip when absent |
| PIPE-03 | **N-source median triangulation** for prices (extend 6.9 pairwise) + split/bad-tick/stale detectors | offline test: 3 stubbed sources, 1 outlier → median kept, outlier flagged, divergence logged; single-bar spike dropped; no imputation on all-miss |
| PIPE-04 | **`run_cycle()` daemon + cadence table** (`scripts/daemon.py`) driven by per-source cadence; idempotent, crash-safe | offline test: `run_cycle()` against fixtures populates store + is idempotent on double-run; a launchd plist + documented `launchctl load` |
| PIPE-05 | **Self-heal: gap detection + backfill + dead-source failover** | offline test: seeded store with holes → `detect_gaps()` finds missing name-weeks/stale/missing-cards → backfill fills them; degraded source → cascade fails over, pipeline never raises |
| PIPE-06 | **Quality monitor: `.monitor/data_health.json`** (coverage %, per-source health, staleness, gaps, divergences) surfaced by `monitor/server.py` | offline test: cycle writes valid health JSON w/ all metrics; monitor renders it; alert fires on a simulated dead source / coverage drop |
| PIPE-07 | **Raw-snapshot lake** (`data/raw/{source}/{ticker}_{fetch_ts}`) + `raw_snapshot_path` on persisted datums | offline test: a fetch writes a snapshot file and the datum records its path; re-parse-from-snapshot path works without network |
| PIPE-08 | **Live shakedown of the running daemon** (operator-directed verification): run ≥1 real cycle, confirm coverage/freshness/divergence on the real universe, log edge cases | separate explicit network run (`scripts/daemon.py --once`), NOT pytest; edge-case + divergence report artifact |

**Reuses (unchanged):** `_http`, all 6.9 providers + price cascade, `store` UPSERTs (idempotency = crash-safety), `ingest`, `monitor/server.py`, pytest-httpx test infra, migration-007 provenance columns.
**Builds new:** `providers/fred.py`; `edgartools`-backed fundamentals provider (adopt `edgartools` — the one new dep); N-source median in `providers/prices.py`; `scripts/daemon.py` (`run_cycle` + cadence + `detect_gaps`); `.monitor/data_health.json` writer; raw-snapshot hook in `_http`; the launchd plist; 7 offline test files + fixtures.
**New deps:** `edgartools` (MIT) — the only add, justified by PIPE-01 (operator-greenlit). FRED = plain httpx, no dep.
**Explicitly NOT in scope (YAGNI):** Wayback backfill (wire only when a specific historical gap demands it); finvizfinance/yahooquery/FinanceDatabase (redundant); OpenBB (mirror, never adopt); self-hosted proxy egress (Stooq stays disabled).

---

## Report-back (the four asks)

1. **Top gap-filling sources to add:** (a) **SEC XBRL via `edgartools`** (MIT, maintained yesterday, keyless) — fills fundamentals/float/cash-runway, the #1 weak spot, and upgrades hand-rolled `edgar.py`; **adopt it.** (b) **FRED API** (free instant key) — fills the macro/rates/**VIX** regime gap we have zero coverage of; ~20-line httpx provider. (c) *Back-pocket:* Wayback CDX for slow HTML deep-history backfill — wire only on demand.
2. **Proxy / IP-block verdict:** **Don't proxy.** Free proxies (honeypot/interception risk), Tor (blacklisted by finance sites), paid residential (violates FREE) are all rejected. Stooq is a REDUNDANT source already covered by yfinance+Nasdaq+AV+Tiingo agreeing to 0.000% — **leave it disabled; route around, don't evade.** Self-hosted free-VM egress is the only non-sketchy free option and it's not worth the ops for a redundant source; keep it back-pocket only if a UNIQUE source ever gets geo-blocked.
3. **OpenBB — adopt or mirror:** **MIRROR.** AGPL-3.0-only + 50+ deps into a system that must stay minimal/readable and has a network bridge = don't adopt. It wraps the same free sources we already wire directly, and we already have its core pattern (ranked provider registry + cascade). Its value is its **provider menu** — which validated `sec`, `fred`, and macro as the standard next adds. Steal the menu, keep our httpx providers.
4. **Proposed phase shape:** **Phase 6.10 — Always-On Data Daemon, Coverage Expansion & Quality Monitor** (PIPE-01…08 above). Thin because the store is idempotent and consumers read the store: launchd + a stateless `run_cycle()` + gap-detector + `data_health.json` + raw-snapshot lake, plus the two gap-filler providers and N-source median. One new dep (`edgartools`). $0.

---

## Sources & confidence

**HIGH (probed live 2026-08-16):**
- `gh api` repo metadata: edgartools (MIT, pushed 2026-08-15, 2.6k★), yfinance (Apache-2.0, 2026-08-13), yahooquery (MIT, 2025-05-15), FinanceDatabase (MIT, 2026-08-09), sec-edgar-downloader (MIT, 2026-06-22), pandas-datareader (BSD, 2026-07-21), OpenBB (2026-07-30, 71.9k★).
- OpenBB provider-extension list (`gh api .../providers` contents): `alpha_vantage benzinga bls cboe cftc congress_gov deribit ecb econdb eia famafrench federal_reserve finra finviz fmp fred government_us imf intrinio multpl nasdaq oecd sec seeking_alpha stockgrid tiingo tmx tradier tradingeconomics wsj yfinance`.
- PyPI `openbb` 4.7.2 — **AGPL-3.0-only**, Python 3.10–3.14, ~50+ deps (heavy). WebFetch of GitHub README confirmed AGPLv3.
- edgartools README + readthedocs (WebFetch): XBRL financials, shares-outstanding/float, Form 4/13F/13D, back to 1994, `pip install edgartools` + `set_identity`, MIT, "runs in production at hedge funds," no keys.

**MEDIUM (carried from prior verified research + training; re-validate at shakedown):**
- SEC `data.sec.gov/api/xbrl/{companyfacts,companyconcept,frames}` endpoints + 10 req/s + UA-with-email rule (WebFetch 403'd — bot-wall, as `free-data-sources.md` also noted; endpoints from prior research §3.4 + training).
- FRED base endpoint / free key / ~120 req/min (WebFetch 403'd; from training — GREEN, well-established).
- Wayback CDX + `id_` raw-snapshot URL form (training).
- `free-data-sources.md` + `06.9-RESEARCH.md` (all live-verified 2026-08-15): CBOE/FINRA/FedRegister/RTTNews/CT.gov, price cascade, store signatures, `_http` base, monitor.

**LOW / not chased:** stockanalysis.com `api/symbol/...` (404 this date — endpoint moved); finvizfinance repo (gh search returned empty — it's on PyPI, MIT; unverified freshness).

**Metadata:** ecosystem/library survey HIGH (live repo+PyPI metadata); architecture HIGH (reuses read signatures); endpoint shapes MEDIUM (bot-walled to WebFetch, re-validated at shakedown). Research date 2026-08-16; valid ~30 days for GREEN sources, ~7 for YELLOW.
