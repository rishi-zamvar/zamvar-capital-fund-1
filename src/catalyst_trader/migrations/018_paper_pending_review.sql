-- Phase 9: the REVIEW snapshot behind a pending decision (thesis, kill criteria, SL/TP, DD verdict,
-- MD rationale) so the iOS dossier screen can show the operator WHY before they approve. Display-only:
-- the gate still opens from `params` alone, and a NULL review (pre-Phase-9 rows) is an empty state.
ALTER TABLE paper_pending ADD COLUMN review TEXT;
