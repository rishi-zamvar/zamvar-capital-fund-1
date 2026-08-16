-- Phase 6.9 (INGEST-01/04): columnar cross-check provenance on the most load-bearing datum.
-- The multi-source price cascade grades each kept bar and records which sources agreed within
-- tolerance (cite-or-drop, columnar). Both columns are OPTIONAL/additive — existing upsert_bars
-- callers (seed_history, _seed_std, fixtures) are unaffected; natural key + idempotency unchanged.

ALTER TABLE price_bar ADD COLUMN source_grade TEXT;      -- 'green' | 'yellow' — grade of the kept source
ALTER TABLE price_bar ADD COLUMN agreeing_sources TEXT;  -- comma-joined set that agreed (single name if unconfirmed)
