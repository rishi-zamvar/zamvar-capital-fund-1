# GREEN-key setup — live cross-check redundancy

The daemon's price cross-check triangulates a weekly bar across multiple sources and keeps a bar only
when it agrees within tolerance (see `providers/prices.get_weekly_bars`). Two sources are **always-on**
and need no key; the rest are free keyed sources that add redundancy so the N-source median never
leans on a single feed. Every source **degrades to skip** when its key is absent — nothing here is
required for the daemon to run, and no key is ever hardcoded (all read from `.env` via
`catalyst_trader.config.Settings`).

## Always-on (no key)

| Source | Grade | Role |
|--------|-------|------|
| **yfinance** | YELLOW | Default price leg. `auto_adjust=False` raw Close (adjusted = look-ahead). |
| **Nasdaq** | YELLOW | Default cross-check partner. Raw daily → resampled to Friday weeks. |

With just these two, the cross-check already confirms `>=2` sources on virtually every bar
(this run: **1091/1092**). The GREEN keys below add a 3rd/4th leg so a single bad/absent source
can never silently become the reference.

## Free keyed sources

Set each in the project `.env` (never commit real keys — `.env` is gitignored):

### 1. `FRED_API_KEY` — macro / rates / VIX (PIPE-04)
- **Get it:** https://fredaccount.stlouisfed.org/apikeys (free, instant)
- **Adds:** the FRED macro-regime bundle (rates/VIX context). Absent → the `macro` slot degrades to
  `None` (context only, never a price gate) — the cycle still completes.
- `.env`: `FRED_API_KEY=...`

### 2. `ALPHA_VANTAGE_API_KEY` — GREEN 3rd price leg (PIPE-10)
- **Get it:** https://www.alphavantage.co/support/#api-key (free, 25 req/day)
- **Adds:** a GREEN-grade 3rd price source so the median has `>=3` legs and out-of-tolerance outliers
  fall out of the agreeing set. Uses `TIME_SERIES_WEEKLY` (never `_ADJUSTED`) → raw Close.
- Absent → `_av_weekly` returns `[]` and the cascade simply skips it.
- `.env`: `ALPHA_VANTAGE_API_KEY=...`

### 3. `TIINGO_API_KEY` — optional GREEN 4th price leg
- **Get it:** https://www.tiingo.com/account/api/token (free tier)
- **Adds:** an optional 4th median leg. Reads `close` (never `adjClose`).
- Absent → `_tiingo_eod` returns `[]`, skipped.
- `.env`: `TIINGO_API_KEY=...`

### 4. `SEC_USER_AGENT` — edgartools identity (PIPE-03)
- **Set it:** any `"Your Name your-email@example.com"` string. SEC **requires** a declared contact UA;
  edgartools calls `set_identity` with it. An unset UA is the one legitimate config error (raises,
  never sends an empty UA).
- **Adds:** SEC EDGAR filings (`live_shelf`, offering accessions) + XBRL fundamentals
  (`cash_runway_months`, `shares_outstanding`). CIK is resolved internally by edgartools — no
  ticker→CIK map needed.
- `.env`: `SEC_USER_AGENT=Your Name your-email@example.com`

## Verify keys load

```bash
.venv/bin/python -c "from catalyst_trader.config import Settings; s=Settings(); \
print('fred', bool(s.fred_api_key), 'av', bool(s.alpha_vantage_api_key), \
'tiingo', bool(s.tiingo_api_key), 'sec', bool(s.sec_user_agent))"
```

## Cost

All four are **free** (AV/Tiingo/FRED free tiers; SEC UA is just a string). The only added Python
dependency across the whole pipeline is `edgartools`. No paid API is ever called: FMP runs on the free
tier and, when it 402s, the daemon falls back to Nasdaq earnings (still $0).
