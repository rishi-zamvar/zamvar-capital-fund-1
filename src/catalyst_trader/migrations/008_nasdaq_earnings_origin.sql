-- 008: add 'nasdaq_earnings' to the catalyst.source_origin CHECK whitelist.
--
-- The SourceOrigin enum gained `nasdaq_earnings` in 6.10-05 (honest provenance for the FMP-402 ->
-- Nasdaq earnings fallback), but the DB CHECK constraint (001_init) was never widened. The live
-- 06.10-07 daemon shakedown hit exactly this: FMP 402'd, the fallback emitted nasdaq_earnings
-- Catalysts, and insert_catalyst raised `CHECK constraint failed: source_origin IN (...)` — crashing
-- the whole run_cycle (no data_health.json written). SQLite can't ALTER a CHECK, so rebuild the table.
-- ids are preserved by the INSERT..SELECT, so the catalyst_source FK rows stay valid.

PRAGMA foreign_keys=OFF;

CREATE TABLE catalyst_new (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL,
  company_name TEXT,
  catalyst_type TEXT NOT NULL CHECK (catalyst_type IN
     ('pdufa','adcom','trial_readout','earnings','conference')),
  event_date TEXT NOT NULL,
  event_date_end TEXT,
  date_precision TEXT NOT NULL CHECK (date_precision IN ('day','month','quarter','year')),
  uncertainty_type TEXT NOT NULL CHECK (uncertainty_type IN ('firm','window','soft')),
  status TEXT NOT NULL CHECK (status IN
     ('unverified','verified','excluded','resolved')) DEFAULT 'unverified',
  source_origin TEXT NOT NULL CHECK (source_origin IN
     ('clinicaltrials_gov','fmp_earnings','nasdaq_earnings','curated_pdufa','ad_hoc_user')),
  last_verified_at TEXT,
  external_ref TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

INSERT INTO catalyst_new SELECT
  id, ticker, company_name, catalyst_type, event_date, event_date_end, date_precision,
  uncertainty_type, status, source_origin, last_verified_at, external_ref, created_at, updated_at
FROM catalyst;

DROP TABLE catalyst;
ALTER TABLE catalyst_new RENAME TO catalyst;

PRAGMA foreign_keys=ON;
