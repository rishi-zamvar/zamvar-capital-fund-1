-- 012: options_snapshot — cached straddle/IV inputs for the football-field implied-move method.
-- RH option MCP tools are available ONLY in an interactive/agent session, so the headless
-- backtest/engine reads implied-move inputs from this table instead of calling RH live. Purely
-- additive (CREATE TABLE only, no DROP/rewrite) — written by the interactive backfill (plan Task 4),
-- read by the builder/engine via desk.options_adapter.options_snapshot_provider. No existing store
-- read/write contract is touched. Mirrors 011's additive style; provisioned by db.migrate().
CREATE TABLE options_snapshot (
  ticker           TEXT    NOT NULL,
  event_date       TEXT    NOT NULL,
  underlying_price REAL    NOT NULL,
  call_mid         REAL,
  put_mid          REAL,
  iv               REAL,
  days_to_event    INTEGER,
  source           TEXT,
  fetched_at       TEXT,
  PRIMARY KEY (ticker, event_date)
);
