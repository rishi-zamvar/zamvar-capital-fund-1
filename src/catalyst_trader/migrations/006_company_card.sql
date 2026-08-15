-- Phase 6.8 (SCAN-01/02): point-in-time per-company vetting cards + the scan-flag ledger.
-- The data substrate the weekly Haiku scanner reads/writes. Mirrors 005_price_bars.sql:
-- write-once per (ticker, week_end), read point-in-time via store.card_asof / scan_flags_asof
-- (week_end <= as_of — the same no-look-ahead rule as bars_asof). The card + payload are
-- single JSON TEXT columns (no per-metric columns until a query needs them).

CREATE TABLE company_card (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL,
  week_end TEXT NOT NULL,               -- ISO date; the anchor close date (mirrors price_bar)
  card TEXT NOT NULL,                    -- json.dumps(card dict) — the full per-company vetting card
  source TEXT,                           -- 'fmp' | 'fixture'
  retrieved_at TEXT,
  UNIQUE(ticker, week_end)
);
CREATE INDEX idx_company_card_ticker_week ON company_card(ticker, week_end);

CREATE TABLE scan_flag (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL,
  week_end TEXT NOT NULL,
  payload TEXT NOT NULL,                 -- json.dumps(OpportunityFlag / no-opportunity payload)
  routed INTEGER NOT NULL DEFAULT 0,     -- 1 once the MD acts on it (audit ledger)
  UNIQUE(ticker, week_end)
);
CREATE INDEX idx_scan_flag_ticker_week ON scan_flag(ticker, week_end);
