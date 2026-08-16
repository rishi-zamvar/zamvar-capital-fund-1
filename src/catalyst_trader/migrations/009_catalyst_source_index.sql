-- 009: index catalyst_source(catalyst_id).
--
-- _hydrate() fires one `SELECT * FROM catalyst_source WHERE catalyst_id=?` per catalyst, and
-- tradeable_catalysts() runs it for every verified row — called ~2U+1 times per backtest week.
-- catalyst_id had no index (only the implicit PK on id), so each of those was a full scan of
-- catalyst_source. Additive index only: no schema/data change, purely a read-path speedup.

CREATE INDEX IF NOT EXISTS idx_catalyst_source_cat ON catalyst_source(catalyst_id);
