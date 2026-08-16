# Robinhood Agentic MCP — Live Probe Results (RH-DATA-02 DONE)

**Probed:** 2026-08-16 · MCP `robinhood-trading` connected (HTTP, OAuth) · server: `https://agent.robinhood.com/mcp/trading`
**Verdict:** CONNECTED + rich read surface live-verified. The connection dependency is RESOLVED — RH-DATA-02 (probe) is complete; RH-DATA-01/03 (wire the reads) are now buildable.

## Account safety (airtight)
`get_accounts` → 4 accounts. Only the **"Agentic" account `560662892`** has `agentic_allowed=true` (the only one this agent can act on). `get_portfolio(560662892)` → **total_value 0, cash 0, buying_power 0** — completely empty. Even the (never-called) order tools are inert with $0 buying power. Read-only discipline stands; I call ONLY read tools.

## Live-verified read tools (the high-value surface)
| Tool | Live result | Use in the stack |
|---|---|---|
| `get_equity_quotes` | Real-time last + bid/ask + prev-close + official close (IONS 57.21 / SRPT 18.10 / BBIO 79.84) | **PRIMARY real-time quote** — monitor + execution pricing (beats CBOE 15-min-delayed) |
| `get_equity_fundamentals` | IONS: **float 162,910,507**, **shares_outstanding 166,184,322**, market_cap 9.5B, pe -16.48, pb 21.04, 52wk hi/lo, avg_volume, sector/industry, 24_5 overnight_volume | **FILLS THE FLOAT GAP** (our #1 weak spot) — clean, current, no scraping. Feeds SI-%-float + card balance-sheet fields |
| `get_earnings_calendar` | Full-market calendar, date + am/pm timing + EPS est/actual + verified flag (up to 31-day window; `high_market_cap` filter excludes our small biotechs — omit the filter for our names) | Redundant earnings source (cross-check Nasdaq) |
| `get_portfolio` | market-value breakdown + real-time buying_power | Paper/live LEDGER reconciliation |

## Available, not-yet-called (buildable reads)
- `get_equity_historicals` — OHLCV bars, `adjustment_type='none'` = **RAW** (point-in-time correct), `interval` down to 15second; a clean authenticated raw-price source → can JOIN the N-source price cross-check.
- `get_option_chains` / `get_option_quotes` / `get_option_historicals` — options + IV (cross-check CBOE).
- `get_equity_technical_indicators` — TA (monitor triggers).
- `get_equity_price_book` — **order-book depth** (a signal we have from nowhere else; liquidity/monitor).
- `get_equity_tradability`, `get_pnl_trade_history`, `get_realized_pnl`, `get_indexes`/`get_index_quotes` (index/VIX cross-check), scans/watchlists.

## Integration design (operator directive: "maximize Robinhood as a data source")
One authenticated MCP-tool adapter (`providers/robinhood.py`, Claude Agent SDK MCP surface — NOT `_http`), registered as pluggable slots that degrade-to-None when the MCP is disconnected (mirrors macro/FRED-key). Slot map:
- `quotes_rt` → `get_equity_quotes` (PRIMARY real-time; monitor + exec pricing)
- `fundamentals`/`float` → `get_equity_fundamentals` (PRIMARY float/shares-out; augments edgartools XBRL)
- `portfolio` → `get_portfolio` (ledger reconciliation)
- cross-check (secondary, don't overuse the broker): `get_equity_historicals(adjustment_type='none')` into the price cascade; `get_option_*` vs CBOE; `get_earnings_calendar` vs Nasdaq; `get_index_quotes` (VIX) vs FRED.
- NEW monitor signals: `get_equity_technical_indicators`, `get_equity_price_book`.

**Discipline:** RH is broker-grade + authenticated but IS the live broker — use it for real-time + fundamentals/float + cross-check + ledger; keep the FREE sources as the bulk/historical spine (don't hammer the broker for years of history). Never sole-source. Read tools ONLY (never place/cancel/exercise). Provenance: source_name="Robinhood", grade tagged.

## Status vs plan
- RH-DATA-01 (degrade-to-None adapter): build now.
- RH-DATA-02 (probe): **DONE** (this doc).
- RH-DATA-03 (wire quotes/portfolio/float into monitor + ledger + cross-check): now UNBLOCKED (connection live) — expand from the original quotes+portfolio scope to include float/fundamentals (the gap-filler) + the historicals/options/TA/price-book cross-checks.
