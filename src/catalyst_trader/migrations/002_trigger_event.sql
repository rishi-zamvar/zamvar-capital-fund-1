-- trigger_event: the T-2 seam's recorded fire marker (DATA-05).
-- One row per (catalyst_id, event_date) is the dedup key so a second refresh the
-- same day — or the next day when T-2 becomes T-1 — does not re-fire. Phases 4+
-- read these rows when they register the real Workflow-1 launcher.
CREATE TABLE trigger_event (
  id INTEGER PRIMARY KEY,
  catalyst_id INTEGER NOT NULL REFERENCES catalyst(id),
  event_date TEXT NOT NULL,
  fired_at TEXT NOT NULL,
  UNIQUE (catalyst_id, event_date)
);
