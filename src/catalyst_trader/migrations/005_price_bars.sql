-- Phase 6.5 (WEEK-02): point-in-time weekly OHLCV price bars.
-- The GATING data substrate for the weekly thesis engine. Survivorship-free (delisted names
-- and non-universe reference series like XBI are retained) and read point-in-time via
-- store.bars_asof (week_end <= as_of, mirroring universe_snapshot's no-future-cohort rule).

CREATE TABLE price_bar (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL,
  week_end TEXT NOT NULL,              -- ISO date; the anchor close date (see params['weekly']['anchor'])
  open REAL, high REAL, low REAL,
  close REAL NOT NULL,
  volume REAL,
  delisted INTEGER NOT NULL DEFAULT 0, -- retain delisted names for survivorship-free base rates
  source TEXT,                         -- 'fmp' | 'fixture'
  retrieved_at TEXT,
  UNIQUE(ticker, week_end)
);
CREATE INDEX idx_price_bar_ticker_week ON price_bar(ticker, week_end);
