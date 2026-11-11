"""Phase 10 LEARN-02 / SC3 — ADVERSARIAL: a proposed diff (and the loop code holding it) tries every way
we could think of to reach the money path (kb.load_params) without passing the gate. Each attempt must be
refused AND leave load_params exactly as it was.

Threat model (CONTEXT A11): the adversary is the diff + loop code — forged fields, skipping/failing the
gate, post-gate mutation, holdout tampering, direct KB writes. A human with raw SQL is out of scope.
"""

import re
import sqlite3
from pathlib import Path

import pytest
from pydantic import ValidationError

from catalyst_trader import kb
from catalyst_trader.learn import gate as lg
from catalyst_trader.store import upsert_bars

from tests.test_learn_gate import (H_START, WEEKS, _diff, _evaluate, _frozen, passed_proposal,
                                   stub_replay)

EV = [kb.EvidenceSource(url="https://evil", retrieved_at="2026-11-11", snippet_hash="evil")]
EVIL = {**kb.BOOTSTRAP_DEFAULT, "weekly": {**kb.BOOTSTRAP_DEFAULT["weekly"], "edge_min_pts": 0.0,
                                           "hard_veto_drop": -0.9}}


@pytest.fixture
def frozen():
    conn, _ = _frozen()
    before = kb.load_params(conn, "weekly")
    yield conn
    assert kb.load_params(conn, "weekly") == before, "the money path moved without a gate pass"


# ------------------------------------------------------------------ forged / smuggled fields


@pytest.mark.parametrize("forged", [{"gate_passed": True}, {"status": "passed"},
                                    {"confidence": 0.99}, {"strategy": EVIL}])
def test_given_diff_with_forged_fields_when_submitted_then_rejected(frozen, forged):
    with pytest.raises(ValidationError):
        lg.submit_proposal(frozen, {**_diff(), **forged})


@pytest.mark.parametrize("patch", [
    {"weekly.hard_veto_drop": -0.9},                 # disable the falling-knife veto
    {"weekly.edge_min_pts": 0.0},                    # loosen the tradeability bar
    {"weekly.shortlist_k": 1000},
    {"weekly": {"edge_min_pts": 0.0}},               # nested smuggle of a whole group
    {"min_dsr": 0.0},                                # aim at the gate's own thresholds
    {"learn.holdout": "none"},
])
def test_given_patch_aimed_at_safety_or_the_gate_when_submitted_then_rejected(frozen, patch):
    with pytest.raises((ValueError, ValidationError)):
        lg.submit_proposal(frozen, _diff(patch))


# ------------------------------------------------------------------ skipping / failing the gate


def test_given_unevaluated_proposal_when_promoted_then_refused(frozen):
    pid = lg.submit_proposal(frozen, _diff())
    with pytest.raises(lg.GateRefused):
        lg.promote(frozen, pid)


def test_given_failed_proposal_when_promoted_then_refused(frozen):
    pid = lg.submit_proposal(frozen, _diff({"weekly.shortlist_k": 1}))
    assert not _evaluate(frozen, pid)["passed"]
    with pytest.raises(lg.GateRefused):
        lg.promote(frozen, pid)


def test_given_proposal_status_flipped_to_passed_by_sql_when_promoted_then_refused(frozen):
    pid = lg.submit_proposal(frozen, _diff())
    frozen.execute("UPDATE learn_proposal SET status='passed' WHERE id=?", (pid,))
    with pytest.raises(lg.GateRefused):  # no passed gate run backs the status
        lg.promote(frozen, pid)


def test_given_promoted_proposal_when_promoted_again_then_refused():
    conn, pid = passed_proposal()
    lg.promote(conn, pid)
    with pytest.raises(lg.GateRefused):
        lg.promote(conn, pid)


# ------------------------------------------------------------------ post-gate mutation


def test_given_passed_proposal_when_patch_mutated_then_trigger_refuses():
    conn, pid = passed_proposal()
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute("UPDATE learn_proposal SET patch_json=? WHERE id=?",
                     ('{"weekly.edge_min_pts": 0.0}', pid))


def test_given_passed_proposal_when_patch_mutated_past_the_trigger_then_sha_check_refuses():
    conn, pid = passed_proposal()
    conn.execute("DROP TRIGGER learn_proposal_immutable")  # defence in depth: the sha binding still holds
    conn.execute("UPDATE learn_proposal SET patch_json=? WHERE id=?", ('{"weekly.shortlist_k": 5}', pid))
    with pytest.raises(lg.GateRefused, match="content"):
        lg.promote(conn, pid)


def test_given_passed_gate_run_when_mutated_or_deleted_then_refused():
    conn, pid = passed_proposal()
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute("UPDATE learn_gate_run SET passed=1")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        conn.execute("DELETE FROM learn_gate_run")


# ------------------------------------------------------------------ holdout tampering / leakage


def test_given_frozen_holdout_when_updated_or_deleted_then_refused(frozen):
    with pytest.raises(sqlite3.IntegrityError, match="frozen"):
        frozen.execute("UPDATE learn_holdout SET start='2020-01-01'")
    with pytest.raises(sqlite3.IntegrityError, match="frozen"):
        frozen.execute("DELETE FROM learn_holdout")


def test_given_holdout_data_revised_after_pass_when_promoted_then_refused():
    conn, pid = passed_proposal()
    upsert_bars(conn, "AAAA", [{"week_end": WEEKS[45], "open": 9, "high": 9, "low": 9, "close": 9,
                               "volume": 9}])
    with pytest.raises(lg.GateRefused, match="holdout"):
        lg.promote(conn, pid)


def test_given_holdout_refrozen_after_pass_when_promoted_then_refused():
    conn, pid = passed_proposal()
    lg.freeze_holdout(conn, start=WEEKS[45], end=WEEKS[59])  # a friendlier holdout appears
    with pytest.raises(lg.GateRefused, match="holdout"):
        lg.promote(conn, pid)


def test_given_holdout_drift_before_eval_when_evaluated_then_fails(frozen):
    pid = lg.submit_proposal(frozen, _diff())
    upsert_bars(frozen, "AAAA", [{"week_end": WEEKS[50], "open": 9, "high": 9, "low": 9, "close": 9,
                                 "volume": 9}])
    rep = _evaluate(frozen, pid)
    assert not rep["passed"] and any("drift" in r for r in rep["reasons"])


def test_given_diff_trained_on_holdout_when_submitted_then_leak(frozen):
    with pytest.raises(lg.HoldoutLeak):
        lg.submit_proposal(frozen, _diff(trained_through=H_START))


def test_given_proposer_peeking_into_holdout_when_replaying_then_leak(frozen):
    tr = lg.TrainingReplay(stub_replay(), lg.training_cutoff(lg.active_holdout(frozen)))
    with pytest.raises(lg.HoldoutLeak):
        tr(kb.BOOTSTRAP_DEFAULT, H_START, WEEKS[59])


# ------------------------------------------------------------------ going around the gate into the KB


def test_given_direct_high_confidence_fitted_params_insert_when_written_then_trigger_refuses(frozen):
    with pytest.raises(sqlite3.IntegrityError, match="LEARN gate"):
        kb.insert_playbook(frozen, "fitted_params:weekly", "sneaky", EVIL, 0.9, EV)


def test_given_direct_seed_tier_weekly_insert_when_written_then_trigger_refuses(frozen):
    # plan-check B1: weekly has no seed tier, so even a low-confidence row is gated
    with pytest.raises(sqlite3.IntegrityError, match="LEARN gate"):
        kb.insert_playbook(frozen, "fitted_params:weekly", "sneaky", EVIL, 0.1, EV)


def test_given_direct_above_seed_insert_for_any_catalyst_type_when_written_then_refused(frozen):
    with pytest.raises(sqlite3.IntegrityError, match="LEARN gate"):
        kb.insert_playbook(frozen, "fitted_params:pdufa", "sneaky", EVIL, 0.31, EV)


def test_given_seed_tie_when_loaded_then_first_seed_still_wins(frozen):
    kb.seed_fitted_params(frozen)
    seeded = kb.load_params(frozen, "pdufa")
    kb.insert_playbook(frozen, "fitted_params:pdufa", "tie", EVIL, 0.3, EV)
    assert kb.load_params(frozen, "pdufa") == seeded


def test_given_forged_promotion_id_on_a_claim_when_written_then_refused():
    conn, pid = passed_proposal()
    node = kb.KBNode(kind="playbook", confidence=0.5, attrs={
        "scenario_type": "fitted_params:weekly", "scenario": "x", "strategy": EVIL,
        "learn_promotion_id": 1})
    with pytest.raises(sqlite3.IntegrityError, match="LEARN gate"):
        kb.insert_claim(conn, node, EV)


def test_given_armed_promotion_when_a_different_strategy_rides_it_then_refused():
    conn, pid = passed_proposal()
    run = conn.execute("SELECT id FROM learn_gate_run WHERE proposal_id=?", (pid,)).fetchone()[0]
    good = lg.apply_patch(kb.load_params(conn, "weekly"), {"weekly.shortlist_k": 6})
    import json
    promo = conn.execute(
        "INSERT INTO learn_promotion (proposal_id, gate_run_id, scenario_type, strategy_json, confidence,"
        " status, created_at) VALUES (?,?,?,?,?,'armed','2026-11-11')",
        (pid, run, "fitted_params:weekly", json.dumps(good), 0.37)).lastrowid
    node = kb.KBNode(kind="playbook", confidence=0.37, attrs={
        "scenario_type": "fitted_params:weekly", "scenario": "x", "strategy": EVIL,
        "learn_promotion_id": promo})
    with pytest.raises(sqlite3.IntegrityError, match="LEARN gate"):
        kb.insert_claim(conn, node, EV)


def test_given_promotion_for_a_failed_gate_run_when_armed_then_refused(frozen):
    pid = lg.submit_proposal(frozen, _diff({"weekly.shortlist_k": 1}))
    _evaluate(frozen, pid)
    run = frozen.execute("SELECT id FROM learn_gate_run WHERE proposal_id=?", (pid,)).fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError, match="LEARN gate"):
        frozen.execute(
            "INSERT INTO learn_promotion (proposal_id, gate_run_id, scenario_type, strategy_json,"
            " confidence, status, created_at) VALUES (?,?,?,?,?,'armed','x')",
            (pid, run, "fitted_params:weekly", "{}", 0.5))


def test_given_consumed_promotion_when_replayed_then_refused():
    conn, pid = passed_proposal()
    nid = lg.promote(conn, pid)
    node = kb.get_node(conn, nid)
    replay = kb.KBNode(kind="playbook", confidence=node["confidence"], attrs=node["attrs"])
    with pytest.raises(sqlite3.IntegrityError, match="LEARN gate"):
        kb.insert_claim(conn, replay, EV)   # one-shot: the promotion is already 'applied'


def test_given_promoted_version_when_edited_or_deleted_in_place_then_refused():
    conn, pid = passed_proposal()
    nid = lg.promote(conn, pid)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE kb_node SET confidence=0.99 WHERE id=?", (nid,))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE kb_node SET attrs_json=json_set(attrs_json,'$.strategy.weekly.edge_min_pts',0)"
                     " WHERE id=?", (nid,))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM kb_node WHERE id=?", (nid,))


# ------------------------------------------------------------------ code invariants (grep)


_SRC = Path(lg.__file__).resolve().parent
_WRITERS = re.compile(r"insert_claim|insert_playbook|seed_fitted_params|INSERT INTO kb_node|"
                      r"UPDATE kb_node|learn_promotion \(")


def test_no_learn_module_writes_the_kb_except_gate_promote():
    for f in sorted(_SRC.glob("*.py")):
        src = f.read_text()
        if f.name == "gate.py":
            body = src.split("def promote(", 1)[0]  # everything BEFORE promote must be write-free
            after = src.split("def promote(", 1)[1].split("\ndef ", 1)[1] if "\ndef " in \
                src.split("def promote(", 1)[1] else ""
            assert not _WRITERS.search(body + after), "only gate.promote may write the KB"
        else:
            assert not _WRITERS.search(src), f"{f.name} writes the KB — only gate.promote may"
