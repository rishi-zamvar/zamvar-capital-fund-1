-- Quick 260819-p1x (BACK-02/04): the DAILY-bars cache for the intraweek reflex backtest.
-- A SEPARATE table from price_bar on purpose: price_bar is UNIQUE(ticker, week_end) with a FRIDAY
-- week_end (the weekly money-path substrate). Daily bars key on the raw TRADE date, so a daily
-- Friday row would OVERWRITE the weekly Friday bar and corrupt BOTH the weekly entry price and the
-- weekly baseline. Isolating daily bars here keeps the weekly substrate byte-for-byte untouched.
-- Read point-in-time via store.daily_bars_asof (trade_date windowed), mirroring bars_asof's guard.

CREATE TABLE daily_bar (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL,
  trade_date TEXT NOT NULL,            -- ISO raw trade date (get_daily_bars' week_end convention)
  open REAL, high REAL, low REAL,
  close REAL NOT NULL,
  volume REAL,
  source TEXT,                         -- 'yfinance' | 'nasdaq' | 'fixture'
  source_grade TEXT,                   -- 'green' | 'yellow' (columnar provenance, mirrors price_bar)
  agreeing_sources TEXT,               -- comma-joined cross-check set
  retrieved_at TEXT,
  UNIQUE(ticker, trade_date)
);
CREATE INDEX idx_daily_bar_ticker_date ON daily_bar(ticker, trade_date);
