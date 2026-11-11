-- Phase 10 LEARN-02: the promotion gate. A config/playbook DIFF reaches the money path
-- (kb.load_params = top-confidence fitted_params:<type> playbook) ONLY through learn.gate.promote,
-- and these tables + triggers make that STRUCTURAL rather than a convention:
--   learn_holdout    frozen evaluation window (no UPDATE/DELETE; the gate re-hashes its data too)
--   learn_proposal   a proposed diff; its content is immutable once written (only status moves)
--   learn_gate_run   one immutable evaluation record binding content/holdout/golden shas + verdict
--   learn_promotion  a one-shot ticket: armed only for a PASSED gate run, consumed by the KB insert
-- kb_node triggers: a gated playbook insert must match an armed ticket exactly (scenario_type,
-- strategy JSON, confidence); fitted_params versions are append-only. 0.3 == kb._SEED_CONFIDENCE.

CREATE TABLE learn_holdout (
  id INTEGER PRIMARY KEY,
  name TEXT,
  start TEXT NOT NULL,
  "end" TEXT NOT NULL,
  embargo_days INTEGER NOT NULL CHECK(embargo_days >= 0),
  manifest TEXT NOT NULL,            -- JSON: weeks, catalyst ids, price-bar digest
  manifest_sha TEXT NOT NULL,
  frozen_at TEXT NOT NULL,
  CHECK(start <= "end")
);
CREATE TRIGGER learn_holdout_no_update BEFORE UPDATE ON learn_holdout
BEGIN SELECT RAISE(ABORT, 'LEARN gate: the holdout is frozen'); END;
CREATE TRIGGER learn_holdout_no_delete BEFORE DELETE ON learn_holdout
BEGIN SELECT RAISE(ABORT, 'LEARN gate: the holdout is frozen'); END;

CREATE TABLE learn_proposal (
  id INTEGER PRIMARY KEY,
  target TEXT NOT NULL,              -- e.g. 'fitted_params:weekly'
  patch_json TEXT NOT NULL,          -- {"weekly.shortlist_k": 5, ...}
  rationale TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  trained_through TEXT NOT NULL,     -- the last training as_of (must be <= the holdout training cutoff)
  holdout_id INTEGER NOT NULL REFERENCES learn_holdout(id),
  base_sha TEXT NOT NULL,            -- sha of load_params(target) when proposed (stale if it moves)
  content_sha TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('proposed','passed','failed','promoted')),
  created_at TEXT NOT NULL
);
CREATE TRIGGER learn_proposal_immutable BEFORE UPDATE ON learn_proposal
WHEN NEW.target IS NOT OLD.target OR NEW.patch_json IS NOT OLD.patch_json
  OR NEW.trained_through IS NOT OLD.trained_through OR NEW.holdout_id IS NOT OLD.holdout_id
  OR NEW.base_sha IS NOT OLD.base_sha OR NEW.content_sha IS NOT OLD.content_sha
  OR NEW.rationale IS NOT OLD.rationale OR NEW.evidence_json IS NOT OLD.evidence_json
BEGIN SELECT RAISE(ABORT, 'LEARN gate: proposal content is immutable'); END;

CREATE TABLE learn_gate_run (
  id INTEGER PRIMARY KEY,
  proposal_id INTEGER NOT NULL REFERENCES learn_proposal(id),
  holdout_id INTEGER NOT NULL REFERENCES learn_holdout(id),
  content_sha TEXT NOT NULL,
  holdout_sha TEXT NOT NULL,
  golden_sha TEXT NOT NULL,
  n_trials INTEGER NOT NULL,
  report TEXT NOT NULL,
  passed INTEGER NOT NULL CHECK(passed IN (0,1)),
  created_at TEXT NOT NULL
);
CREATE TRIGGER learn_gate_run_no_update BEFORE UPDATE ON learn_gate_run
BEGIN SELECT RAISE(ABORT, 'LEARN gate: gate runs are immutable'); END;
CREATE TRIGGER learn_gate_run_no_delete BEFORE DELETE ON learn_gate_run
BEGIN SELECT RAISE(ABORT, 'LEARN gate: gate runs are immutable'); END;

CREATE TABLE learn_promotion (
  id INTEGER PRIMARY KEY,
  proposal_id INTEGER NOT NULL UNIQUE REFERENCES learn_proposal(id),
  gate_run_id INTEGER NOT NULL REFERENCES learn_gate_run(id),
  scenario_type TEXT NOT NULL,
  strategy_json TEXT NOT NULL,
  confidence REAL NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('armed','applied')),
  playbook_node_id INTEGER,
  created_at TEXT NOT NULL
);
CREATE TRIGGER learn_promotion_needs_passed_run BEFORE INSERT ON learn_promotion
WHEN NEW.status <> 'armed' OR NOT EXISTS (
  SELECT 1 FROM learn_gate_run g WHERE g.id = NEW.gate_run_id AND g.passed = 1
    AND g.proposal_id = NEW.proposal_id)
BEGIN SELECT RAISE(ABORT, 'LEARN gate: a promotion needs a passed gate run for the same proposal'); END;
CREATE TRIGGER learn_promotion_one_shot BEFORE UPDATE ON learn_promotion
WHEN NOT (OLD.status = 'armed' AND NEW.status = 'applied'
  AND NEW.proposal_id IS OLD.proposal_id AND NEW.gate_run_id IS OLD.gate_run_id
  AND NEW.scenario_type IS OLD.scenario_type AND NEW.strategy_json IS OLD.strategy_json
  AND NEW.confidence IS OLD.confidence)
BEGIN SELECT RAISE(ABORT, 'LEARN gate: a promotion is one-shot'); END;
CREATE TRIGGER learn_promotion_no_delete BEFORE DELETE ON learn_promotion
BEGIN SELECT RAISE(ABORT, 'LEARN gate: a promotion is one-shot'); END;

CREATE TRIGGER kb_playbook_learn_gate BEFORE INSERT ON kb_node
WHEN NEW.kind = 'playbook' AND (
    json_extract(NEW.attrs_json, '$.learn_promotion_id') IS NOT NULL
    OR json_extract(NEW.attrs_json, '$.scenario_type') = 'fitted_params:weekly'
    OR (json_extract(NEW.attrs_json, '$.scenario_type') LIKE 'fitted_params:%' AND NEW.confidence > 0.3))
  AND NOT EXISTS (
    SELECT 1 FROM learn_promotion p JOIN learn_gate_run g ON g.id = p.gate_run_id
    WHERE p.id = json_extract(NEW.attrs_json, '$.learn_promotion_id')
      AND p.status = 'armed' AND g.passed = 1 AND g.proposal_id = p.proposal_id
      AND p.scenario_type = json_extract(NEW.attrs_json, '$.scenario_type')
      AND json(p.strategy_json) = json_extract(NEW.attrs_json, '$.strategy')
      AND p.confidence = NEW.confidence)
BEGIN
  SELECT RAISE(ABORT, 'LEARN gate: this playbook version needs an armed promotion of a passed gate run');
END;

CREATE TRIGGER kb_playbook_learn_consume AFTER INSERT ON kb_node
WHEN json_extract(NEW.attrs_json, '$.learn_promotion_id') IS NOT NULL
BEGIN
  UPDATE learn_promotion SET status = 'applied', playbook_node_id = NEW.id
  WHERE id = json_extract(NEW.attrs_json, '$.learn_promotion_id');
END;

CREATE TRIGGER kb_fitted_params_append_only BEFORE UPDATE ON kb_node
WHEN OLD.kind = 'playbook' AND json_extract(OLD.attrs_json, '$.scenario_type') LIKE 'fitted_params:%'
BEGIN SELECT RAISE(ABORT, 'LEARN gate: fitted_params versions are append-only'); END;
CREATE TRIGGER kb_fitted_params_no_delete BEFORE DELETE ON kb_node
WHEN OLD.kind = 'playbook' AND json_extract(OLD.attrs_json, '$.scenario_type') LIKE 'fitted_params:%'
BEGIN SELECT RAISE(ABORT, 'LEARN gate: fitted_params versions are append-only'); END;
