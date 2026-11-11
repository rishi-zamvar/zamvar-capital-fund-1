"""Phase 10 LEARN-01: the post-resolution LLM judge + its calibration harness. Fully offline.

  - JudgeVerdict is the trust boundary on the judge's output (grade 1..5, non-empty rationale, no extras).
  - calibrate() measures judge-vs-human agreement (quadratic-weighted kappa, within-one, MAE) and can
    PASS only on enough REAL hand-graded labels — synthetic placeholders are reported, never counted.
  - judge_resolved() scores each closed + Phase-8-attributed paper trade exactly once; the calibrated flag
    follows the latest PASSED calibration of the same judge model (and a DB trigger backs that up).
  - every judge_fn here is a stub — no live LLM call (the live test is tests/test_learn_judge_live.py).
"""

import inspect
import json
import sqlite3

import pytest
from pydantic import ValidationError

from catalyst_trader import kb
from catalyst_trader import paper_ledger as pl
from catalyst_trader.learn import judge as jd

from tests.test_paper_attribution import _close_one, _conn

MODEL = "stub-judge"


def _verdict(grade=4, direction_correct=True, rationale="right call, catalyst-driven"):
    return {"grade": grade, "direction_correct": direction_correct, "rationale": rationale}


def _label(i, grade, *, synthetic=False):
    return jd.Label(
        id=f"L{i}", case={"prediction": {"i": i}, "realized": {}}, human_grade=grade,
        human_direction_correct=grade >= 3, grader="SYNTHETIC-PLACEHOLDER" if synthetic else "CEO",
        synthetic=synthetic, needs_ceo_grading=synthetic,
    )


def _echo_judge(labels, *, invert=False):
    """A stub judge that returns each label's own human grade (or its mirror) — perfect/anti agreement."""
    by_id = {json.dumps(l.case, sort_keys=True): l.human_grade for l in labels}

    def fn(prompt):
        for key, g in by_id.items():
            if key in prompt:
                g = 6 - g if invert else g
                return _verdict(grade=g, direction_correct=g >= 3)
        raise AssertionError("case not in prompt")
    return fn


# ====================================================================== the verdict contract


@pytest.mark.parametrize("bad", [
    {"grade": 0, "direction_correct": True, "rationale": "x"},
    {"grade": 6, "direction_correct": True, "rationale": "x"},
    {"grade": 3, "direction_correct": True, "rationale": ""},
    {"grade": 3, "direction_correct": True, "rationale": "x", "promote": True},
])
def test_given_malformed_judge_output_when_validated_then_rejected(bad):
    with pytest.raises(ValidationError):
        jd.JudgeVerdict.model_validate(bad)


def test_given_dict_or_model_from_judge_when_score_case_then_verdict_returned():
    case = {"prediction": {"direction": "positive"}, "realized": {"verdict": "skill"}}
    assert jd.score_case(case, lambda p: _verdict(grade=5)).grade == 5
    assert jd.score_case(case, lambda p: jd.JudgeVerdict(**_verdict(grade=2))).grade == 2
    with pytest.raises(ValidationError):
        jd.score_case(case, lambda p: {"grade": "great"})


def test_given_a_case_when_prompted_then_rubric_and_case_are_in_the_prompt():
    case = {"prediction": {"direction": "positive", "ticker": "ABCD"}, "realized": {"r_gross": 0.2}}
    p = jd.judge_prompt(case)
    assert "ABCD" in p and "r_gross" in p
    for g in ("5", "4", "3", "2", "1"):
        assert f"{g} =" in p  # the full 1..5 rubric is spelled out


# ====================================================================== agreement metric


def test_given_identical_raters_when_qwk_then_one():
    assert jd.quadratic_weighted_kappa([1, 2, 3, 4, 5], [1, 2, 3, 4, 5]) == pytest.approx(1.0)


def test_given_known_vectors_when_qwk_then_matches_hand_computation():
    # hand-computed: O=[[1,0],[1,1]] over grades {1,2} (k=5 bins, weights (i-j)^2/16)
    # observed disagreement = 1 * 1/16 / 3 ; expected = (2/3*1/3 + 1/3*2/3)... -> kappa = 0.4
    assert jd.quadratic_weighted_kappa([1, 2, 2], [1, 1, 2]) == pytest.approx(0.4)


def test_given_constant_raters_when_qwk_then_undefined_not_fabricated():
    assert jd.quadratic_weighted_kappa([3, 3, 3], [3, 3, 3]) is None


def test_given_opposite_raters_when_qwk_then_negative():
    assert jd.quadratic_weighted_kappa([1, 2, 4, 5], [5, 4, 2, 1]) < 0


# ====================================================================== labels


def test_given_shipped_seed_labels_when_loaded_then_all_synthetic_and_flagged_for_ceo():
    labels = jd.load_labels()
    assert len(labels) >= 10
    assert all(l.synthetic and l.needs_ceo_grading for l in labels)
    assert {l.human_grade for l in labels} == {1, 2, 3, 4, 5}
    assert all("SYNTHETIC" in l.grader for l in labels)


def test_given_synthetic_label_claiming_no_ceo_grading_needed_when_loaded_then_rejected():
    with pytest.raises(ValidationError):
        jd.Label(id="x", case={}, human_grade=3, human_direction_correct=True, grader="me",
                 synthetic=True, needs_ceo_grading=False)


def test_given_labels_file_with_extra_fields_when_loaded_then_rejected(tmp_path):
    p = tmp_path / "labels.json"
    p.write_text(json.dumps({"labels": [{"id": "x", "case": {}, "human_grade": 3,
                                         "human_direction_correct": True, "grader": "CEO",
                                         "synthetic": False, "needs_ceo_grading": False,
                                         "trust_me": True}]}))
    with pytest.raises(ValidationError):
        jd.load_labels(p)


# ====================================================================== calibration


def test_given_only_synthetic_labels_when_calibrated_then_never_passes_even_if_perfect():
    labels = jd.load_labels()
    rep = jd.calibrate(labels, _echo_judge(labels), judge_model=MODEL)
    assert rep["passed"] is False
    assert rep["n_real"] == 0 and rep["n_synthetic"] == len(labels)
    assert any("real labels" in r for r in rep["reasons"])
    assert rep["synthetic_only"]["qwk"] == pytest.approx(1.0)  # reported, informational only


def test_given_enough_real_labels_and_agreeing_judge_when_calibrated_then_passes():
    labels = [_label(i, 1 + i % 5) for i in range(20)]
    rep = jd.calibrate(labels, _echo_judge(labels), judge_model=MODEL)
    assert rep["passed"] is True and rep["reasons"] == []
    assert rep["real"]["qwk"] == pytest.approx(1.0)
    assert rep["real"]["within_one"] == 1.0 and rep["real"]["mae"] == 0.0


def test_given_enough_real_labels_and_contrarian_judge_when_calibrated_then_fails_naming_metrics():
    labels = [_label(i, 1 + i % 5) for i in range(20)]
    rep = jd.calibrate(labels, _echo_judge(labels, invert=True), judge_model=MODEL)
    assert rep["passed"] is False
    assert any("qwk" in r for r in rep["reasons"]) and any("within_one" in r for r in rep["reasons"])


def test_given_too_few_real_labels_when_calibrated_then_fails_on_sample():
    labels = [_label(i, 1 + i % 5) for i in range(19)]
    rep = jd.calibrate(labels, _echo_judge(labels), judge_model=MODEL)
    assert rep["passed"] is False and any("real labels" in r for r in rep["reasons"])


def test_given_a_judge_that_errors_on_a_label_when_calibrated_then_counted_as_failure():
    labels = [_label(i, 1 + i % 5) for i in range(20)]

    def flaky(prompt):
        raise RuntimeError("model down")
    rep = jd.calibrate(labels, flaky, judge_model=MODEL)
    assert rep["passed"] is False and rep["judge_errors"] == 20


def test_given_a_calibration_report_when_recorded_then_persisted_with_labels_sha(db):
    labels = [_label(i, 1 + i % 5) for i in range(20)]
    rep = jd.calibrate(labels, _echo_judge(labels), judge_model=MODEL)
    cid = jd.record_calibration(db, rep, labels)
    row = db.execute("SELECT * FROM learn_calibration WHERE id=?", (cid,)).fetchone()
    assert row["passed"] == 1 and row["judge_model"] == MODEL and row["n_real"] == 20
    assert row["labels_sha"] == jd.labels_sha(labels)


# ====================================================================== post-resolution scoring


def _resolved(conn, **kw):
    pos_id, _ = _close_one(conn, **kw)
    pl.postmortem_closed(conn, embed=kb.hash_embed)
    review = {"dossier": {"verdict_summary": "approval likely", "kill_criteria": ["CRL"],
                          "pre_mortem": "label delay"}}
    conn.execute("UPDATE paper_pending SET review=? WHERE position_id=?", (json.dumps(review), pos_id))
    conn.commit()
    return pos_id


def test_given_resolved_trade_when_case_built_then_prediction_and_realized_present():
    conn = _conn()
    pos_id = _resolved(conn)
    case = jd.build_case(conn, pos_id)
    pred, real = case["prediction"], case["realized"]
    assert pred["ticker"] == "ABCD" and pred["direction"] == "positive"
    assert pred["size_pct"] == 0.02 and pred["kill_criteria"] == ["CRL"]
    assert pred["thesis"] == "approval likely" and pred["pre_mortem"] == "label delay"
    assert real["verdict"] in pl.VERDICTS and "r_gross" in real
    assert {"catalyst_effect", "beta_drift"} <= set(real["components"])


def test_given_resolved_trades_when_judged_then_scored_once_and_idempotent():
    conn = _conn()
    pos_id = _resolved(conn)
    calls = []

    def judge(prompt):
        calls.append(prompt)
        return _verdict(grade=4)
    out = jd.judge_resolved(conn, judge_fn=judge, judge_model=MODEL)
    assert out == {"judged": 1, "failed": 0, "calibrated": 0}
    row = conn.execute("SELECT * FROM learn_judgement WHERE position_id=?", (pos_id,)).fetchone()
    assert row["grade"] == 4 and row["calibrated"] == 0 and row["calibration_id"] is None
    assert jd.judge_resolved(conn, judge_fn=judge, judge_model=MODEL)["judged"] == 0
    assert len(calls) == 1


def test_given_open_or_unattributed_trade_when_judged_then_skipped():
    conn = _conn()
    _close_one(conn)  # closed but NOT attributed yet (no post-mortem)
    out = jd.judge_resolved(conn, judge_fn=lambda p: _verdict(), judge_model=MODEL)
    assert out["judged"] == 0


def test_given_judge_failure_when_judged_then_counted_and_left_pending():
    conn = _conn()
    _resolved(conn)

    def boom(prompt):
        raise RuntimeError("down")
    assert jd.judge_resolved(conn, judge_fn=boom, judge_model=MODEL) == {
        "judged": 0, "failed": 1, "calibrated": 0}
    assert jd.judge_resolved(conn, judge_fn=lambda p: _verdict(), judge_model=MODEL)["judged"] == 1


def test_given_passed_calibration_of_same_model_when_judged_then_flagged_calibrated():
    conn = _conn()
    _resolved(conn)
    labels = [_label(i, 1 + i % 5) for i in range(20)]
    cid = jd.record_calibration(conn, jd.calibrate(labels, _echo_judge(labels), judge_model=MODEL),
                                labels)
    out = jd.judge_resolved(conn, judge_fn=lambda p: _verdict(), judge_model=MODEL)
    assert out["calibrated"] == 1
    row = conn.execute("SELECT calibrated, calibration_id FROM learn_judgement").fetchone()
    assert row["calibrated"] == 1 and row["calibration_id"] == cid


def test_given_passed_calibration_of_other_model_when_judged_then_uncalibrated():
    conn = _conn()
    _resolved(conn)
    labels = [_label(i, 1 + i % 5) for i in range(20)]
    jd.record_calibration(conn, jd.calibrate(labels, _echo_judge(labels), judge_model="other"),
                          labels)
    assert jd.judge_resolved(conn, judge_fn=lambda p: _verdict(), judge_model=MODEL)["calibrated"] == 0


def test_given_no_passed_calibration_when_raw_insert_claims_calibrated_then_trigger_refuses():
    conn = _conn()
    pos_id = _resolved(conn)
    with pytest.raises(sqlite3.IntegrityError, match="calibrat"):
        conn.execute(
            "INSERT INTO learn_judgement (position_id, grade, direction_correct, rationale, judge_model,"
            " rubric_sha, calibration_id, calibrated, case_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (pos_id, 5, 1, "x", MODEL, jd.RUBRIC_SHA, None, 1, "{}", "2026-11-11"))


def test_given_calibration_under_an_old_rubric_when_judged_then_uncalibrated(monkeypatch):
    conn = _conn()
    _resolved(conn)
    labels = [_label(i, 1 + i % 5) for i in range(20)]
    jd.record_calibration(conn, jd.calibrate(labels, _echo_judge(labels), judge_model=MODEL), labels)
    monkeypatch.setattr(jd, "RUBRIC_SHA", "changed-rubric")
    assert jd.judge_resolved(conn, judge_fn=lambda p: _verdict(), judge_model=MODEL)["calibrated"] == 0


def test_given_forged_passed_calibration_on_too_few_real_labels_when_inserted_then_refused(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("INSERT INTO learn_calibration (judge_model, rubric_sha, labels_sha, n_labels, n_real,"
                   " metrics, passed, created_at) VALUES ('m','r','l',5,5,'{}',1,'2026-11-11')")


def test_given_a_recorded_calibration_when_mutated_then_refused(db):
    labels = [_label(i, 1 + i % 5) for i in range(20)]
    cid = jd.record_calibration(db, jd.calibrate(labels, _echo_judge(labels, invert=True),
                                                 judge_model=MODEL), labels)
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        db.execute("UPDATE learn_calibration SET passed=1 WHERE id=?", (cid,))
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        db.execute("DELETE FROM learn_calibration WHERE id=?", (cid,))


def test_given_live_judge_factory_when_called_then_routes_through_the_one_sdk_seam(monkeypatch):
    from catalyst_trader.desk import runtime
    seen = {}

    async def fake(prompt, schema, **kw):
        seen.update(kw, schema=schema)
        return schema(**_verdict(grade=3))
    monkeypatch.setattr(runtime, "run_structured", fake)
    v = jd.make_live_judge(model="sonnet")("prompt")
    assert v.grade == 3 and seen["schema"] is jd.JudgeVerdict
    assert seen["allowed_tools"] == [] and seen["model"] == "sonnet"  # the judge can touch nothing


# ====================================================================== deferred wiring (xfail)


@pytest.mark.xfail(strict=True, reason="DEFERRED: headless resolution -> judge auto-fire. The judge "
                   "needs an LLM (CC session); weekly_mark_pass is the launchd-headless path. The judge "
                   "runs in weekly_cycle.py --learn for now (deferred wiring ships as an xfail test)")
def test_given_headless_mark_pass_when_trade_resolves_then_judge_fires():
    assert "judge_fn" in inspect.signature(pl.weekly_mark_pass).parameters
