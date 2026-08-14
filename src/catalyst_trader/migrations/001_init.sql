-- Phase 1 schema. The migration runner (db.migrate) records the version, not this file.

-- catalyst: the rolling calendar (DATA-01)
CREATE TABLE catalyst (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL,
  company_name TEXT,
  catalyst_type TEXT NOT NULL CHECK (catalyst_type IN
     ('pdufa','adcom','trial_readout','earnings','conference')),
  event_date TEXT NOT NULL,            -- ISO; may be YYYY, YYYY-MM, or YYYY-MM-DD
  event_date_end TEXT,                 -- set when the source gives a range
  date_precision TEXT NOT NULL CHECK (date_precision IN ('day','month','quarter','year')),
  uncertainty_type TEXT NOT NULL CHECK (uncertainty_type IN ('firm','window','soft')),  -- DATA-04
  status TEXT NOT NULL CHECK (status IN
     ('unverified','verified','excluded','resolved')) DEFAULT 'unverified',              -- DATA-03
  source_origin TEXT NOT NULL CHECK (source_origin IN
     ('clinicaltrials_gov','fmp_earnings','curated_pdufa','ad_hoc_user')),               -- DATA-02
  last_verified_at TEXT,               -- DATA-03 freshness stamp
  external_ref TEXT,                   -- e.g. NCTId, for re-fetch/dedup
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- catalyst_source: provenance rows — the two-source rule lives here (DATA-03)
CREATE TABLE catalyst_source (
  id INTEGER PRIMARY KEY,
  catalyst_id INTEGER NOT NULL REFERENCES catalyst(id),
  source_name TEXT NOT NULL,           -- 'ClinicalTrials.gov' | 'Company IR' | 'FDA' | 'FMP' | user
  source_url TEXT,                     -- required for external; user note for ad-hoc
  source_type TEXT NOT NULL CHECK (source_type IN ('primary','secondary')),
  reported_date TEXT NOT NULL,         -- date THIS source claims
  date_type TEXT NOT NULL CHECK (date_type IN ('estimated','actual')) DEFAULT 'estimated', -- DATA-04
  agrees INTEGER NOT NULL DEFAULT 1,   -- does it match the catalyst event_date within tolerance
  retrieved_at TEXT NOT NULL
);

-- universe_snapshot: point-in-time membership, append-only (DATA-06)
CREATE TABLE universe_snapshot (
  id INTEGER PRIMARY KEY,
  as_of_date TEXT NOT NULL,
  ticker TEXT NOT NULL,
  included INTEGER NOT NULL,
  delisted INTEGER NOT NULL DEFAULT 0, -- retain delisted names for backtest (survivorship)
  criteria_json TEXT,                  -- {catalyst_density, market_cap, adv_usd, therapeutic_area}
  reason TEXT
);
