-- Phase 8: per-resolved-trade P&L attribution + post-mortem bookkeeping on the paper ledger.
-- Additive columns only (no new table): the facts the post-mortem needs that the close path did not
-- persist, plus the attribution result itself. attribution IS NULL on a closed row == post-mortem
-- not yet run, so the pass is idempotent and self-healing (a failed pass is simply retried next week).

ALTER TABLE paper_position ADD COLUMN catalyst_type TEXT;      -- the catalyst type (analog prior key)
ALTER TABLE paper_position ADD COLUMN event_date TEXT;         -- the catalyst event date (provenance)
ALTER TABLE paper_position ADD COLUMN hedge_ticker TEXT;       -- dossier.trade.hedge.ticker (NULL = single-leg)
ALTER TABLE paper_position ADD COLUMN hedge_ret REAL;          -- the hedge leg's backtest-identical realized return
ALTER TABLE paper_position ADD COLUMN attribution TEXT;        -- JSON: components + verdict (NULL = pending)
ALTER TABLE paper_position ADD COLUMN postmortem_node_id INTEGER;  -- the KB outcome node (NULL = no evidence to cite)
