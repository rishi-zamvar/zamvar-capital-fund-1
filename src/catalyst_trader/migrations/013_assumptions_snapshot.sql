-- 013: assumptions_snapshot — cached valuation-assumption dicts (rnpv/sop/analyst_pt) for the
-- football-field valuation methods. Live agent estimation is available ONLY in an interactive/agent
-- session, so the headless backtest/engine reads valuation assumptions from THIS table instead of
-- estimating live (same constraint as options_snapshot). Purely additive (CREATE TABLE only, no
-- DROP/rewrite) — written by the interactive agent estimation pass (plan Task 4), read by the
-- builder/engine via desk.assumptions_adapter.assumptions_snapshot_provider. No existing store
-- read/write contract is touched.
--   assumptions_json  the rnpv/sop/analyst_pt dict (json)
--   as_of             the date the estimate was knowable AS-OF — the no-look-ahead stamp
-- PK (ticker, event_date) matches the options_snapshot pattern. Mirrors 012's additive style;
-- provisioned by db.migrate().
CREATE TABLE assumptions_snapshot (
  ticker           TEXT    NOT NULL,
  event_date       TEXT    NOT NULL,
  assumptions_json TEXT    NOT NULL,
  as_of            TEXT,
  source           TEXT,
  fetched_at       TEXT,
  PRIMARY KEY (ticker, event_date)
);
