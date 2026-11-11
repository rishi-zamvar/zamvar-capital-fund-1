-- Phase 10 LEARN-01: the post-resolution LLM judge + its calibration record.
-- learn_calibration: one row per calibration run of a judge model against hand-graded labels. A judge
-- is "calibrated" only via a passed row here (real labels only — synthetic seeds never count).
-- learn_judgement: one grade per resolved paper_position (UNIQUE -> idempotent pass). calibrated=1 is
-- STRUCTURALLY tied to a passed calibration of the SAME judge model (trigger below), so an uncalibrated
-- judge can never be dressed up as a calibrated one.

CREATE TABLE learn_calibration (
  id INTEGER PRIMARY KEY,
  judge_model TEXT NOT NULL,
  rubric_sha TEXT NOT NULL,                 -- sha256 of the judge RUBRIC graded under (a new rubric = recalibrate)
  labels_sha TEXT NOT NULL,                 -- sha256 of the exact label set graded against
  n_labels INTEGER NOT NULL,
  n_real INTEGER NOT NULL,                  -- non-synthetic labels (the only ones that count)
  metrics TEXT NOT NULL,                    -- JSON: the full calibrate() report
  passed INTEGER NOT NULL CHECK(passed IN (0,1)),
  created_at TEXT NOT NULL,
  CHECK (passed = 0 OR n_real >= 20)        -- mirrors CALIBRATION_THRESHOLDS min_real_labels (retune = migration)
);

CREATE TRIGGER learn_calibration_no_update BEFORE UPDATE ON learn_calibration
BEGIN SELECT RAISE(ABORT, 'LEARN judge: calibration records are immutable'); END;
CREATE TRIGGER learn_calibration_no_delete BEFORE DELETE ON learn_calibration
BEGIN SELECT RAISE(ABORT, 'LEARN judge: calibration records are immutable'); END;

CREATE TABLE learn_judgement (
  id INTEGER PRIMARY KEY,
  position_id INTEGER NOT NULL UNIQUE REFERENCES paper_position(id),
  grade INTEGER NOT NULL CHECK(grade BETWEEN 1 AND 5),
  direction_correct INTEGER NOT NULL CHECK(direction_correct IN (0,1)),
  rationale TEXT NOT NULL,
  judge_model TEXT NOT NULL,
  rubric_sha TEXT NOT NULL,
  calibration_id INTEGER REFERENCES learn_calibration(id),
  calibrated INTEGER NOT NULL CHECK(calibrated IN (0,1)),
  case_json TEXT NOT NULL,                  -- the exact prediction-vs-realized case the judge saw
  created_at TEXT NOT NULL
);

CREATE TRIGGER learn_judgement_calibrated_guard BEFORE INSERT ON learn_judgement
WHEN NEW.calibrated = 1 AND NOT EXISTS (
  SELECT 1 FROM learn_calibration c
  WHERE c.id = NEW.calibration_id AND c.passed = 1 AND c.judge_model = NEW.judge_model
    AND c.rubric_sha = NEW.rubric_sha)
BEGIN
  SELECT RAISE(ABORT, 'LEARN judge: calibrated=1 requires a passed calibration of the same judge model + rubric');
END;
