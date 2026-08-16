# Free Intraday (5-/15-min) Prices — Monitor-Scoped Feed for the Intra-Week Watchdog

**Researched:** 2026-08-16 (all endpoint tests run LIVE this date from this machine, `.venv/bin/python`, seed names IONS/SRPT; market closed Sun, so "last bar" = Fri 2026-08-14 close).
**Domain:** intraday OHLC / last-price feed for the deterministic trigger layer of the intra-week position monitor (Phase 8.5).
**Confidence:** HIGH on the four sources tested live (yfinance, CBOE, Nasdaq — pass/fail directly observed); MEDIUM on the keyed sources that walled the demo key (Finnhub/TwelveData/AlphaVantage — free access + limits from documented behavior + the demo-wall responses observed).

> **Scope + isolation up front.** This feed is **MONITOR-scoped, defend-only**. It exists so the 8 deterministic triggers (`intra-week-monitoring.md`) can compute a delayed `last`/volume during the one-week hold. It is **NOT** a decision/backtest input — decisions stay EOD/weekly by design. This provider **never** writes the point-in-time weekly `price_bar` store and **never** touches the backtest. Accuracy-over-speed holds: delayed + laggy is fine; FREE only.
>
> **Reading note.** Extends `free-data-sources.md` (§1 CBOE, price cascade), `free-data-pipeline.md` (daemon/cadence), and `intra-week-monitoring.md` (the 8 triggers this feeds). Does not restate them.

---

## Summary

The gap is small and already mostly filled. **The single cheapest win: the CBOE `/options/{T}.json` call we ALREADY make per name for IV/greeks also carries, at the symbol level, a free 15-min-delayed underlying `current_price` + full day OHLC + `prev_day_close` + cumulative `volume` + `last_trade_time` + bid/ask.** That delayed *snapshot* satisfies the monitor's price-level triggers (ATR-move, stop-proximity, volume-spike, gap) with **no new call** for any optionable name. The only thing CBOE does not give is a *bar sequence* — for 2-bar anti-whipsaw confirmation, intraday high/low progression, and non-optionable names, **yfinance `interval="15m"`** supplies a ~60-day rolling OHLCV series, verified live, and **batches all 20 names into one HTTP round-trip**.

Everything else ranks below these two. Nasdaq's chart endpoint is a price-only, single-session, lagged line (no OHLCV, no rolling history). Finnhub free is last-price-only (candles are now premium). Twelve Data needs its own free key and rate-limits at 20 names/15-min. Alpha Vantage's 25-req/day free cap makes it **useless for polling** — backtest-only, do not register it for the monitor.

**Primary recommendation:** intraday cascade = **CBOE-underlying snapshot (primary, free, already polled) → yfinance 15m batched (bar series + non-optionable fallback)**, on a **15-minute RTH cadence** (Nyquist-matched to the 15-min delay — 5-min polling a 15-min-delayed feed buys nothing but rate-limit risk), in a **separate `providers/intraday.py`** that feeds the monitor and never the weekly store. **Own it in Phase 8.5**, not 6.10.

---

## Live-verified source table (ranked cascade)

Ranked for a rolling live monitor (recent bars only, not deep history). "Snapshot" = one delayed last/OHLC/cum-vol value per fetch; "Bar series" = a sequence of interval OHLCV bars.

| # | Source | Shape | Interval | Rolling history (free) | Delay | Rate limit | Key | Grade | Live result |
|---|--------|-------|----------|------------------------|-------|-----------|-----|-------|-------------|
| **1** | **CBOE `cdn.cboe.com/api/global/delayed_quotes/options/{T}.json`** | **delayed snapshot**: `current_price`, day `open/high/low/close`, `prev_day_close`, cum `volume`, `bid/ask`, `last_trade_time`, `iv30` | n/a (snapshot) | none (point-in-time) | ~15 min | none documented (CDN) | no | 🟡 | ✅ **VERIFIED** — IONS/SRPT returned all fields; **already fetched by `options_cboe.fetch`** |
| **2** | **yfinance `interval="15m"`** (also `"5m"`) | **bar series** OHLCV, TZ-aware | 1m/5m/15m/… | **~60 trading days** (hard cap) | ~15 min (Yahoo delayed) | undocumented; 429-prone per-ticker → **batch** | no | 🟡 | ✅ **VERIFIED** — 15m: 1560 bars/60d; **batch 3 names = 1 round-trip**; 90d rejected ("within the last 60 days") |
| 3 | Nasdaq `api.nasdaq.com/api/quote/{T}/chart` | price-only line (`x`,`y`), single session incl pre/post | irregular ~1min | **1 session only**, lagged | lagged (`timeAsOf` 2 days stale on test) | UA-gated, YELLOW | no (browser UA) | 🟡 | ✅ VERIFIED — 364 points, **no OHLCV**, no rolling history → last-price cross-check only |
| 4 | Twelve Data `/time_series` | bar series OHLCV | 1min/5min/15min | limited (free) | delayed | **8 req/min, 800/day** | own free key | 🟢 | ❌ demo walled (401 "get your own free key"); free access documented, **rate-limits at 20 names/sweep** |
| 5 | Finnhub `/quote` | last-price snapshot only | n/a | none | delayed | 60/min free | own free key | 🟢 | ❌ demo/no-key = 401; `/stock/candle` 401 (**candles now premium**) → last-price cross-check only |
| — | **Alpha Vantage `TIME_SERIES_INTRADAY`** | bar series 5/15min | 5/15min | ~1–2mo | delayed | **25 req/day (free)** | own free key | 🟢 | ❌ demo walled; **25/day = useless for polling** → **EXCLUDE from monitor**, backtest-only |

**Verified live:** CBOE (#1), yfinance (#2), Nasdaq (#3). **Failed to verify (demo-walled, documented behavior):** Twelve Data (#4), Finnhub (#5), Alpha Vantage.

### The CBOE cheapest-win, in detail (this is the headline)
`options_cboe.fetch` already GETs `/options/{T}.json` and already returns `underlying_price` (=`current_price`) and `underlying_quote={bid,volume,oi}`. The same payload's symbol-level scalars **also** include `open/high/low/close/prev_day_close/last_trade_time/price_change/tick` — currently discarded. Surfacing those (a ~5-line add to that provider's `underlying_quote` block) gives the monitor a free 15-min-delayed **last + day OHLC + prev-close + cum-volume + exchange timestamp** for every **optionable** name, with **no new HTTP call**. Live IONS: `current_price=56.18, open=55.16, high=57.24, low=55.16, prev_day_close=55.87, volume=1,343,684, last_trade_time='2026-08-14T15:59:59'`.

**CBOE limit:** exists only for **optionable** names. Most of the ~20-name universe is optionable (that is why CBOE is our IV source), but any non-optionable holding has no CBOE row → yfinance 15m is its price feed. That is exactly why the cascade needs #2 as well.

### yfinance 15m, in detail
`yf.download("IONS SRPT ARWR", period="1d", interval="15m", auto_adjust=False, group_by="ticker")` = **one round-trip for N names**. 15m gave 1560 bars over 60d for one name; 5m gave 4678. **Hard 60-trading-day cap** for 5m/15m confirmed (90d rejected). TZ-aware (`-04:00`). **RAW vs adjusted is a non-issue intraday**: within the 60-day window `Adj Close == Close` unless a split/dividend fell inside it; keep `auto_adjust=False` for consistency with the weekly cascade's no-look-ahead rule (moot intraday, but free).

---

## Poll-budget verdict — 20 names

Cadence assumption: **15-min sweeps during RTH** (6.5h → ~26 sweeps/day). `_http` already caches 300 s and rate-limits ≤1 req/s.

| Source | Calls/sweep | Calls/day (26 sweeps) | Survives? |
|--------|-------------|-----------------------|-----------|
| **CBOE (primary)** | 20 GET (already polled for IV) | ~520 | ✅ no key, no documented limit (CDN), 300 s cache; polite ≤1/s = 20 s/sweep |
| **yfinance 15m (batched)** | **1** batched download | ~26 | ✅ trivially — **batching is the trick**; per-ticker (520/day) would risk 429s |
| Twelve Data | 20 (or batched credits) | ~520 (< 800/day) | ⚠️ marginal — 20 in one sweep breaches **8 req/min**; only as a throttled fallback |
| Finnhub | 20 | ~520 (< 60/min·day) | ✅ within limit but **last-price only** → cross-check use |
| Alpha Vantage | 20 | ~520 ≫ **25/day** | ❌ dead on arrival — exclude |

**Verdict:** the sustainable free feed at 20 names is **CBOE (20 GET/sweep, already made) + yfinance 15m batched (1 call/sweep)**. Both survive 15-min RTH cadence with margin. Twelve Data/Finnhub are optional keyed cross-checks; Alpha Vantage rate-limits out.

---

## Cadence + staleness design

- **Cadence = 15 minutes during RTH, held names only.** This is **Nyquist-matched to the ~15-min data delay**: both CBOE and yfinance are ~15 min delayed, so polling every 5 min re-reads the *same* delayed value at 3× the cost and 3× the 429/ban risk. 5-min buys ≤10 min earlier detection of nothing fresher. **Reject 5-min; use 15-min.** (Halt detection stays on its own 60 s Nasdaq-RSS clock — that is not a price feed and is unaffected.)
- **Stale flag = `age(fetch_ts) > 2 × cadence = 30 min`** — mirrors the EOD store rule (`stale = fetch_ts age > 2× cadence`).
- **Two timestamps, always.** Persist BOTH:
  - `fetch_ts` — when *we* fetched (our wall clock; drives staleness).
  - `data_ts` — the exchange's delayed timestamp (`last_trade_time` from CBOE; the last bar's index from yfinance). **This is the datum's true as-of.**
  - Surface `delayed_minutes = now − data_ts`.
- **Honest-delay invariant:** every trigger evaluates against `data_ts`, never `now`. A trigger **must never treat `current_price` as real-time** — it is a ~15-min-old print. The monitor payload carries `delayed_minutes` so the agent (and any human page) reads the price as delayed. This is the same cite-or-drop discipline as the rest of the stack: `{value, source_url, fetch_ts, data_ts, grade}` or drop.

---

## Trigger → minimum granularity map

The load-bearing finding: **most triggers need only a delayed *snapshot* (CBOE), not a bar series.** 15-min is sufficient for every defend-only trigger.

| Trigger (from `intra-week-monitoring.md`) | Needs | Min granularity | Source | Snapshot enough? |
|---|---|---|---|---|
| **P2 ATR-normalized move** | `last`, daily ATR14 (cached EOD) | 15-min last | CBOE `current_price` | ✅ snapshot |
| **P4 stop-proximity** | `last` vs stop/entry | 15-min last | CBOE `current_price` | ✅ snapshot |
| **P5 volume spike** | cum-volume-today, ADV20, elapsed-fraction | 15-min cum vol | CBOE `volume` (+ wall-clock elapsed) | ✅ snapshot |
| **Gap** (into event) | `prev_close`, today `open` | first print of day | CBOE `prev_day_close`+`open` | ✅ snapshot |
| **2-bar confirmation** (anti-whipsaw on P2/P5) | two consecutive bars beyond threshold | **bar sequence** | yfinance 15m bars, OR two successive 15-min CBOE snapshots (the two snapshots *are* the two bars) | ➖ needs sequence; 15-min cadence supplies it |
| Non-optionable held name (any of the above) | `last`/OHLCV where no CBOE row exists | 15-min bar | yfinance 15m | ➖ yfinance only |

**Verdict: 15-min suffices for all defend-only triggers. Do NOT build a 5-min loop.** CBOE snapshots cover the price-level fires; yfinance 15m covers the two-bar confirmation and non-optionable names. Cheaper granularity that satisfies the need wins.

---

## Reuse + isolation design

New module **`providers/intraday.py`**, mirroring `providers/prices.py` (ranked registry + cross-check + provenance), but feeding the **monitor**, not the store.

```
providers/intraday.py
  _cboe_snapshot(ticker)  -> {last, open, high, low, prev_close, volume, data_ts, _source:"cboe", _grade:"yellow"}
        # reuses options_cboe payload / _http (already cached, rate-limited, degrade-safe)
  _yf_15m(ticker|batch)   -> last N 15-min OHLCV bars (lib call, like prices._yf_weekly; auto_adjust=False)
  _nasdaq_last(ticker)    -> last-price cross-check only (optional)
  INTRADAY_PROVIDERS = [_cboe_snapshot, _yf_15m]   # ranked; cross-check on `last` within tol_pct
  get_intraday_snapshot(ticker) / get_intraday_bars(ticker)  -> provenance-tagged, None/[] on degrade
```

**Reuses unchanged:**
- `_http` (cache TTL, ≤1 req/s, browser UA, degrade→None never raise) for CBOE/Nasdaq/TwelveData.
- yfinance-as-lib pattern from `prices._yf_weekly` (injectable `downloader` for offline tests), `auto_adjust=False`.
- The `prices.py` cascade shape: ranked providers, cross-check `last` within `tol_pct`, keep highest-grade, `agreeing_sources`, never fabricate a miss.
- `config.settings` env-first keys (add optional `twelvedata_api_key`, `finnhub_api_key`; `[]`/skip when absent).
- Provenance contract `{value, source_url, fetch_ts, data_ts, grade}`.

**Isolation invariants (the point-in-time store + backtest stay clean):**
- `intraday.py` has its **own registry + cadence**, separate from `PRICE_PROVIDERS`.
- It **never** calls `store.upsert_bars` / writes `price_bar`, and **never** feeds the backtest. Its output goes to the monitor only (returned to the trigger layer, or cached to `.monitor/intraday.json`).
- It **never** re-anchors to `week_end` — intraday is intra-day, not weekly; no path into the weekly point-in-time substrate.
- RAW/adjusted look-ahead concern does not apply (intra-day, no corporate action inside a session), but `auto_adjust=False` is kept for consistency.

**Optional 5-line pull-forward:** extend `options_cboe.fetch`'s `underlying_quote` block to also return `open/high/low/prev_day_close/last_trade_time` (already in the payload it fetches). Zero new calls; makes `_cboe_snapshot` a thin re-read.

---

## Honest gaps — what free intraday CANNOT give (and why it's fine)

- **No true real-time.** Every free source is ~15-min delayed. Fine: the monitor is **defend-only** on a **one-week** hold; a 15-min-old print catches an ATR-scaled collapse hours before an EOD-only monitor would, and stops don't protect through gaps/halts anyway (halt detection is the 60 s RSS feed, separate).
- **No tick data / no sub-15-min freshness.** Not needed; triggers are ATR/stop/volume-scaled, not microstructure.
- **Shallow rolling history (~60 trading days for 5/15m).** Fine — the monitor needs *recent* bars for the current hold, not deep history. Deep history lives in the EOD/weekly store.
- **Illiquid biotech intraday is sparse/gappy** (thin names print few bars). Same illiquidity reality as the options chains (`free-data-sources.md §1.9`); no vendor fixes it. The trigger layer degrades honestly (stale flag, `agreeing_sources`), never imputes a bar.

---

## Roadmap slot — recommend **Phase 8.5 (the monitor)**, not 6.10

**Own the intraday provider + RTH cadence + triggers in Phase 8.5.** Reasons:
1. **It only matters for HELD names**, which do not exist until the paper ledger (Phase 8). Polling intraday in 6.10 (before there are positions) is wasted work.
2. **The 15-min RTH loop is the monitor's clock**, not the daemon's. Phase 6.10's cadence table is deliberately **accuracy-first EOD/weekly** for the point-in-time store (`free-data-pipeline.md §3.1`); bolting a market-hours 15-min loop onto it pollutes that clean separation and would poll un-held names.
3. **8.5's research already assumes yfinance 5m/daily** (`intra-week-monitoring.md §2`); the provider slots directly under its trigger layer.
4. **Isolation** — keeping intraday in 8.5, wired to the monitor, structurally guarantees it never leaks into the weekly store/backtest.

**The one thing worth pulling into 6.10 (optional, cheap):** surface CBOE's day-OHLC/`last_trade_time` scalars from the existing `options_cboe.fetch` (already fetched at 1–2×/day for IV). It readies the cheapest-win snapshot at zero new cost. Do **not** add a market-hours loop to 6.10.

---

## Sources

**HIGH (probed live 2026-08-16, IONS/SRPT):**
- yfinance 1.6.0 — `interval` 5m/15m, `period=60d` (4678/1560 bars), 90d rejected (60-day cap), batch `group_by="ticker"` = 1 round-trip, TZ-aware, `Adj Close==Close` intraday.
- CBOE `cdn.cboe.com/api/global/delayed_quotes/options/{T}.json` — symbol-level `current_price/open/high/low/close/prev_day_close/volume/bid/ask/last_trade_time/iv30`; `/quote/` path 403s (use `/options/`). Already fetched by `options_cboe.fetch`.
- Nasdaq `api.nasdaq.com/api/quote/{T}/chart` — 364 price-only points, single session, `timeAsOf` lagged, no OHLCV.

**MEDIUM (demo-walled; free access + limits from the walled responses + documented behavior):**
- Twelve Data `/time_series` — 401 "get your own free key"; free 800/day, 8/min.
- Finnhub `/quote` (401 no key), `/stock/candle` (401 demo — candles premium); free 60/min, last-price only.
- Alpha Vantage `TIME_SERIES_INTRADAY` — demo wall; free 25 req/day (poll-disqualifying).

**Carried (settled elsewhere):** `free-data-sources.md` (CBOE IV, price cascade, `_http`), `free-data-pipeline.md` (daemon/cadence/staleness), `intra-week-monitoring.md` (the 8 triggers), `prices.py`/`_http.py`/`options_cboe.py`/`config.py` (read this date).

**Metadata:** live sources HIGH; keyed sources MEDIUM. Research date 2026-08-16; valid ~30 days (YELLOW endpoints ~7 — CBOE/Nasdaq/yfinance shapes drift).
