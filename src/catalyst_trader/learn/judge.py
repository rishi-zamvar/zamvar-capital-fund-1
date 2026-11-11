"""learn/judge.py (Phase 10, LEARN-01) — score each resolved paper trade's prediction vs what happened.

The judge is an injected callable ``judge_fn(prompt) -> dict | JudgeVerdict`` (tests stub it; the live
binding goes through the ONE SDK seam, desk.runtime.run_structured, with NO tools). Its output is
validated at the boundary (JudgeVerdict, extra=forbid).

A judge is only as good as its agreement with a human grader, so ``calibrate`` scores the judge over
hand-graded labels and reports quadratic-weighted kappa / within-one agreement / MAE. It PASSES only on
>= CALIBRATION_THRESHOLDS["min_real_labels"] REAL labels; synthetic placeholder labels (the shipped seed
set — every one needs CEO grading) are reported but never count. A judgement is stored calibrated=1 only
against a passed calibration of the same model AND rubric (migration 019's trigger enforces that).

Grading is post-hoc by design: the judge sees the prediction AND the realized outcome. It is not a
forecast and is not a gate input this phase (an uncalibrated judge must never steer money).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sqlite3
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from catalyst_trader.dates import now_iso

logger = logging.getLogger(__name__)

LABELS_PATH = Path(__file__).resolve().parents[3] / "data" / "learn" / "judge_labels.json"

# Documented default floors (CEO retunes — CONTEXT D3). kappa >= 0.6 = "substantial" agreement.
CALIBRATION_THRESHOLDS = {"min_real_labels": 20, "min_qwk": 0.6, "min_within_one": 0.8}

RUBRIC = """\
Grade the desk's PREDICTION against the REALIZED outcome on this 1-5 scale:
  5 = right direction for the right reason (the catalyst effect drove the move, as the thesis said)
  4 = right direction, and the reasoning was mostly right
  3 = right direction for the wrong reason (sector tape / beta did it), OR right reason but badly sized
  2 = wrong direction, but the kill criteria / pre-mortem named what actually happened
  1 = wrong direction and the thesis missed what happened entirely
direction_correct = whether the predicted direction matched the realized gross move's sign.
Judge only from the case below; give a one-paragraph rationale citing its fields."""


RUBRIC_SHA = hashlib.sha256(RUBRIC.encode()).hexdigest()


class JudgeVerdict(BaseModel):
    """The judge's output contract — the trust boundary on an LLM grade."""

    model_config = ConfigDict(extra="forbid")
    grade: int = Field(ge=1, le=5)
    direction_correct: bool
    rationale: str = Field(min_length=1)


class Label(BaseModel):
    """One hand-graded case. ``synthetic`` labels are placeholders that MUST be flagged for CEO grading."""

    model_config = ConfigDict(extra="forbid")
    id: str
    case: dict
    human_grade: int = Field(ge=1, le=5)
    human_direction_correct: bool
    grader: str
    synthetic: bool
    needs_ceo_grading: bool
    note: str = ""

    @model_validator(mode="after")
    def _synthetic_is_never_done(self):
        if self.synthetic and not self.needs_ceo_grading:
            raise ValueError("a synthetic label must be flagged needs_ceo_grading")
        return self


# --------------------------------------------------------------------------- the judge call


def judge_prompt(case: dict) -> str:
    return f"{RUBRIC}\n\nCASE (JSON):\n{json.dumps(case, sort_keys=True)}"


def score_case(case: dict, judge_fn) -> JudgeVerdict:
    raw = judge_fn(judge_prompt(case))
    return raw if isinstance(raw, JudgeVerdict) else JudgeVerdict.model_validate(raw)


def make_live_judge(model: str = "sonnet"):
    """The live judge_fn: one structured call through desk.runtime.run_structured with NO tools.
    Only for a Claude Code session (the LLM needs Max); never called by the test suite."""
    from catalyst_trader.desk import runtime

    def fn(prompt: str) -> JudgeVerdict:
        return asyncio.run(runtime.run_structured(prompt, JudgeVerdict, allowed_tools=[], model=model))
    return fn


# --------------------------------------------------------------------------- calibration


def quadratic_weighted_kappa(a: list[int], b: list[int], k: int = 5) -> float | None:
    """Cohen's quadratic-weighted kappa over grades 1..k. None when undefined (no expected disagreement,
    e.g. both raters constant) — never a fabricated number."""
    n = len(a)
    if n == 0 or n != len(b):
        return None
    ha = [sum(1 for x in a if x == i) for i in range(1, k + 1)]
    hb = [sum(1 for x in b if x == i) for i in range(1, k + 1)]
    obs = sum((x - y) ** 2 for x, y in zip(a, b)) / n
    exp = sum(ha[i] * hb[j] * (i - j) ** 2 for i in range(k) for j in range(k)) / (n * n)
    return None if exp == 0 else 1.0 - obs / exp


def _agreement(pairs: list[tuple[int, int]]) -> dict:
    if not pairs:
        return {"n": 0, "qwk": None, "within_one": None, "exact": None, "mae": None}
    h, j = [p[0] for p in pairs], [p[1] for p in pairs]
    n = len(pairs)
    return {
        "n": n, "qwk": quadratic_weighted_kappa(h, j),
        "within_one": sum(abs(x - y) <= 1 for x, y in pairs) / n,
        "exact": sum(x == y for x, y in pairs) / n,
        "mae": sum(abs(x - y) for x, y in pairs) / n,
    }


def load_labels(path: str | Path | None = None) -> list[Label]:
    data = json.loads(Path(path or LABELS_PATH).read_text())
    return [Label.model_validate(x) for x in data["labels"]]


def labels_sha(labels: list[Label]) -> str:
    blob = json.dumps([l.model_dump() for l in labels], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()


def calibrate(labels: list[Label], judge_fn, *, judge_model: str,
              thresholds: dict = CALIBRATION_THRESHOLDS) -> dict:
    """Score the judge over every label; PASS iff enough REAL labels clear the kappa + within-one floors.
    A judge error on a label is a counted failure (it never silently drops out of the sample)."""
    real, synth, errors = [], [], 0
    for lab in labels:
        try:
            g = score_case(lab.case, judge_fn).grade
        except Exception as exc:  # a judge that cannot grade a case is a calibration failure, not a skip
            errors += 1
            logger.warning("judge failed on label %s (%s)", lab.id, exc)
            continue
        (synth if lab.synthetic else real).append((lab.human_grade, g))

    n_real = sum(not l.synthetic for l in labels)
    rm = _agreement(real)
    reasons = []
    if n_real < thresholds["min_real_labels"]:
        reasons.append(f"insufficient real labels (N={n_real} < min {thresholds['min_real_labels']})")
    if errors:
        reasons.append(f"judge failed on {errors} label(s)")
    if rm["qwk"] is None or rm["qwk"] < thresholds["min_qwk"]:
        reasons.append(f"qwk={rm['qwk']} below floor {thresholds['min_qwk']}")
    if rm["within_one"] is None or rm["within_one"] < thresholds["min_within_one"]:
        reasons.append(f"within_one={rm['within_one']} below floor {thresholds['min_within_one']}")
    return {
        "judge_model": judge_model, "passed": not reasons, "reasons": reasons,
        "n_labels": len(labels), "n_real": n_real, "n_synthetic": len(labels) - n_real,
        "judge_errors": errors, "real": rm, "synthetic_only": _agreement(synth),
        "thresholds": dict(thresholds),
    }


def record_calibration(conn: sqlite3.Connection, report: dict, labels: list[Label]) -> int:
    cid = conn.execute(
        "INSERT INTO learn_calibration (judge_model, rubric_sha, labels_sha, n_labels, n_real, metrics,"
        " passed, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (report["judge_model"], RUBRIC_SHA, labels_sha(labels), report["n_labels"], report["n_real"],
         json.dumps(report), int(report["passed"]), now_iso()),
    ).lastrowid
    conn.commit()
    return cid


# --------------------------------------------------------------------------- post-resolution pass


def build_case(conn: sqlite3.Connection, position_id: int) -> dict:
    """The prediction (what the desk said, from the position + its Phase-9 review snapshot) vs the
    realized outcome (the Phase-8 attribution). Raises if the position is not yet attributed."""
    pos = conn.execute("SELECT * FROM paper_position WHERE id=?", (position_id,)).fetchone()
    if pos is None or pos["attribution"] is None:
        raise ValueError(f"paper_position {position_id} is not resolved + attributed")
    att = json.loads(pos["attribution"])
    rev = conn.execute("SELECT review FROM paper_pending WHERE position_id=?", (position_id,)).fetchone()
    dossier = (json.loads(rev["review"]).get("dossier") or {}) if rev and rev["review"] else {}
    return {
        "prediction": {
            "ticker": pos["ticker"], "direction": pos["direction"], "size_pct": pos["size_pct"],
            "catalyst_type": pos["catalyst_type"], "event_date": pos["event_date"],
            "opened_at": pos["opened_at"], "exit_by": pos["exit_by"],
            "thesis": dossier.get("verdict_summary"), "kill_criteria": dossier.get("kill_criteria"),
            "pre_mortem": dossier.get("pre_mortem"),
        },
        "realized": {
            "verdict": att["verdict"], "r_gross": att["r_gross"], "realized_ret": att["realized_ret"],
            "components": att["components"], "beta_available": att["beta_available"],
        },
    }


def _latest_passed_calibration(conn, judge_model: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM learn_calibration WHERE judge_model=? AND rubric_sha=? AND passed=1 "
        "ORDER BY id DESC LIMIT 1", (judge_model, RUBRIC_SHA)).fetchone()
    return row["id"] if row else None


def judge_resolved(conn: sqlite3.Connection, *, judge_fn, judge_model: str) -> dict:
    """Judge every closed + attributed paper trade not yet judged; returns {judged, failed, calibrated}.
    One failure is logged + counted and stays pending for the next pass (mirrors postmortem_closed)."""
    rows = conn.execute(
        "SELECT p.id FROM paper_position p LEFT JOIN learn_judgement j ON j.position_id=p.id "
        "WHERE p.status='closed' AND p.attribution IS NOT NULL AND j.id IS NULL ORDER BY p.id"
    ).fetchall()
    cal_id = _latest_passed_calibration(conn, judge_model)
    out = {"judged": 0, "failed": 0, "calibrated": 0}
    for r in rows:
        try:
            case = build_case(conn, r["id"])
            v = score_case(case, judge_fn)
            conn.execute(
                "INSERT INTO learn_judgement (position_id, grade, direction_correct, rationale,"
                " judge_model, rubric_sha, calibration_id, calibrated, case_json, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (r["id"], v.grade, int(v.direction_correct), v.rationale, judge_model, RUBRIC_SHA, cal_id,
                 int(cal_id is not None), json.dumps(case), now_iso()))
            conn.commit()
            out["judged"] += 1
            out["calibrated"] += cal_id is not None
        except Exception as exc:  # one bad case never sinks the pass — retried next week
            conn.rollback()
            out["failed"] += 1
            logger.warning("judge for paper_position %s failed (%s) — left pending", r["id"], exc)
    return out
