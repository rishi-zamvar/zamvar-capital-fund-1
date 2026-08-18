-- 011: bitemporal cutoff-served databook — the transaction-time (knowable-time) stamps the
-- 07.6 audit found MISSING, plus the append-only catalyst revision history (DBOOK-01/02).
--
-- The classic look-ahead bug is stamping a fact by when it HAPPENED (event_date, week_end,
-- as_of_date) instead of when it was KNOWABLE (when WE recorded/learned it). Two of the served
-- tables had NO transaction column at all, and amended catalyst dates were OVERWRITTEN in place
-- (store.insert_catalyst UPDATE), which destroys the pre-amendment version and makes a point-in-
-- time replay impossible. This migration is the schema half of the fix:
--
--   * scan_flag.recorded_at        — MISSING; scan_flag had only week_end + routed.
--   * universe_snapshot.recorded_at — MISSING; as_of_date conflated valid + transaction time.
--   * catalyst_version              — append-never-overwrite history so a revised event_date is a
--                                     NEW row (old retained); an as-of query returns the LATEST
--                                     version with recorded_at <= cutoff.
--
-- NO column is added where a correct stamp already exists (catalyst.created_at,
-- catalyst_move.knowable_asof, trigger_event.fired_at, kb.created_at, price_bar/company_card
-- week_end). Purely additive — ADD COLUMN / CREATE TABLE only, no DROP/rewrite — so no existing
-- store read/write contract breaks. The main catalyst row stays the materialized LATEST version
-- (live-view cache); catalyst_version is the replay source of truth.

ALTER TABLE scan_flag ADD COLUMN recorded_at TEXT;
ALTER TABLE universe_snapshot ADD COLUMN recorded_at TEXT;

-- Append-only catalyst revision history. Captures ONLY the amendable fact (event_date /
-- event_date_end) + its knowable-time stamp — not the whole catalyst. recorded_at is the
-- transaction time the gateway gates on (store.catalyst_version_asof: latest recorded_at<=cutoff).
CREATE TABLE catalyst_version (
  id             INTEGER PRIMARY KEY,
  catalyst_id    INTEGER NOT NULL REFERENCES catalyst(id),
  event_date     TEXT    NOT NULL,
  event_date_end TEXT,
  recorded_at    TEXT    NOT NULL
);
CREATE INDEX idx_catalyst_version_cat ON catalyst_version(catalyst_id, recorded_at);

-- Non-destructive, idempotent backfill (guarded so a re-run never double-seeds):
--   * every pre-existing catalyst gets a version-1 row (recorded_at = created_at = first-recorded).
--   * scan_flag / universe_snapshot recorded_at = their contemporaneous valid time (documented
--     ceiling: the scanner/cohorts were built at the time they claim; a backdated backfill after
--     this point is stamped honestly on write).
INSERT INTO catalyst_version (catalyst_id, event_date, event_date_end, recorded_at)
SELECT c.id, c.event_date, c.event_date_end, c.created_at
FROM catalyst c
WHERE NOT EXISTS (SELECT 1 FROM catalyst_version v WHERE v.catalyst_id = c.id);

UPDATE scan_flag SET recorded_at = week_end WHERE recorded_at IS NULL;
UPDATE universe_snapshot SET recorded_at = as_of_date WHERE recorded_at IS NULL;
