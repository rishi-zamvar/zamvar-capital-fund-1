-- 010: catalyst_move — the point-in-time realized move around each historical catalyst (UNIV-06).
--
-- The catalyst table (001/008) has NO move column, so the warm-start backfill (Plan 06) records the
-- realized price move as a separate additive table. knowable_asof = the ISO date of the T+2 close =
-- when the move became knowable (point-in-time, NO look-ahead for anything downstream). No ALTER/DROP
-- of catalyst — purely additive, so no consumer of the existing schema breaks.
--
-- UNIQUE(catalyst_id, move_window) makes recompute idempotent: re-running the backfill upserts the
-- same (catalyst, window) row rather than duplicating it.
CREATE TABLE catalyst_move (
  id            INTEGER PRIMARY KEY,
  catalyst_id   INTEGER NOT NULL REFERENCES catalyst(id),
  realized_move REAL    NOT NULL,   -- abs(close(T+2)/close(T-1) - 1)
  move_window   TEXT    NOT NULL,   -- e.g. "(-1,2)" trading-day offsets around event_date
  knowable_asof TEXT    NOT NULL,   -- ISO date of the T+2 close (point-in-time; NO look-ahead)
  source_grade  TEXT,               -- price-data grade at T+2 (green/yellow)
  computed_at   TEXT    NOT NULL,
  UNIQUE(catalyst_id, move_window)
);
