-- Slice 7.8-S5: the T-2 -> Claude-Code-desk handoff queue (DATA-05 real launcher).
-- The daily HEADLESS refresh has no API key, so its T-2 callback cannot run the LLM desk. It
-- instead ENQUEUES a desk-run request here; an operator drains the queue inside a Claude Code
-- session (weekly_cycle.py --desk) and SUBMITS any 'enter' to the inviolable approval gate.
-- UNIQUE(catalyst_id, event_date) makes enqueue idempotent EXACTLY like trigger_event — a second
-- fire (same day, or T-2 -> T-1) is a no-op. This table NEVER opens a position; it is a work log.

CREATE TABLE desk_run_request (
  id INTEGER PRIMARY KEY,
  catalyst_id INTEGER NOT NULL,
  ticker TEXT NOT NULL,
  event_date TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','done','error')),
  enqueued_at TEXT NOT NULL,
  resolved_at TEXT,
  pending_id INTEGER,                          -- the paper_pending id a drained 'enter' submitted (else NULL)
  UNIQUE(catalyst_id, event_date)
);

CREATE INDEX idx_desk_run_request_status ON desk_run_request(status);
