-- Slice 7.8-S4: the PAPER trading ledger — open/mark/close lifecycle behind an inviolable gate.
-- SEPARATE from price_bar/catalyst on purpose: these are the money-path RESULT rows (a tracked
-- forward paper position + its weekly marks + its realized close), not market data or events. A
-- paper_position is only ever written through approve_pending over a paper_pending record (the
-- structural human gate — no other code path inserts one), so no position can open without an
-- explicit operator approval. PAPER ONLY: nothing here touches a live broker (Phase 11 is last).

CREATE TABLE paper_position (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL,
  side TEXT NOT NULL,                          -- 'long' (desk is long-only; direction carried below)
  entry_price REAL NOT NULL,                   -- the decision-week entry (dossier.trade.entry)
  size_pct REAL NOT NULL,
  opened_at TEXT NOT NULL,                      -- the DECISION as_of DATE (the entry week) — the C1
                                               -- close-guard compares exit_bars[-1].week_end > opened_at,
                                               -- mirroring engine._fill_leg so realized P&L cannot drift.
  exit_by TEXT NOT NULL,                        -- dossier.trade.exit_by_date (the one-week horizon)
  held_through INTEGER NOT NULL DEFAULT 1,      -- into fill_price: held-through -> gap-open fill (money path)
  direction TEXT,                              -- 'positive'|'negative' provenance (side is always long)
  status TEXT NOT NULL CHECK(status IN ('open','closed')),
  close_price REAL,
  realized_ret REAL,
  closed_at TEXT,
  decision_ref TEXT,                           -- back-ref to the catalyst/decision that authored it
  catalyst_id TEXT,
  evidence_refs TEXT                           -- JSON list of the decision's evidence refs (cited on close)
);

CREATE TABLE paper_mark (
  id INTEGER PRIMARY KEY,
  position_id INTEGER NOT NULL REFERENCES paper_position(id),
  mark_date TEXT NOT NULL,
  mark_price REAL NOT NULL,
  unrealized_ret REAL,                         -- _net_return(entry, mark, apply_costs=False) — no exit spread yet
  source TEXT,                                 -- 'bars' | 'quotes_rt'
  UNIQUE(position_id, mark_date)               -- idempotent re-mark (update in place, mirrors upsert_bars)
);

CREATE TABLE paper_pending (
  id INTEGER PRIMARY KEY,
  status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected')),
  params TEXT NOT NULL,                         -- JSON position params from position_params_from_decision
  submitted_at TEXT NOT NULL,
  resolved_at TEXT,
  position_id INTEGER REFERENCES paper_position(id)  -- set on approve (NULL on pending/rejected)
);

CREATE INDEX idx_paper_position_status ON paper_position(status);
CREATE INDEX idx_paper_mark_position ON paper_mark(position_id);
