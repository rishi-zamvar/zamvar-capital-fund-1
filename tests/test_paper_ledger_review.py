"""Phase 9 (09-01 Task 1): the review snapshot persisted at submit + the race-free approve.

The iOS dossier screen needs the WHY (thesis, kill criteria, SL/TP, DD, MD rationale) that
paper_pending.params alone does not carry. The gate itself is unchanged: approve_pending stays the
sole opener; these tests also pin that two concurrent approves open exactly ONE position.
"""

import json
import threading
from types import SimpleNamespace

from catalyst_trader import db as _db
from catalyst_trader import paper_ledger as pl

import scripts.paper_run as pr

PARAMS = {"ticker": "ABCD", "entry": 10.0, "size_pct": 0.02, "opened_at": "2026-08-14",
          "exit_by": "2026-08-21", "evidence_refs": ["kb:1"]}


def _conn(path=":memory:"):
    conn = _db.connect(path)
    _db.migrate(conn)
    return conn


def _review(conn, pid):
    raw = conn.execute("SELECT review FROM paper_pending WHERE id=?", (pid,)).fetchone()["review"]
    return None if raw is None else json.loads(raw)


def test_submit_stores_review_json():
    conn = _conn()
    pid = pl.submit_for_approval(conn, PARAMS, review={"dossier": {"kill_criteria": ["CRL"]}})
    assert _review(conn, pid) == {"dossier": {"kill_criteria": ["CRL"]}}


def test_submit_without_review_is_null_and_backward_compatible():
    conn = _conn()
    pid = pl.submit_for_approval(conn, PARAMS)
    assert _review(conn, pid) is None
    assert pl.approve_pending(conn, pid) is not None  # the gate works exactly as before


def test_review_snapshot_from_fake_result_is_plain_json():
    result = pr._fake_enter_result("ABCD", entry=10.0, exit_by="2026-08-21")
    snap = pl.review_snapshot(result)
    json.dumps(snap)  # must be JSON-serializable
    assert snap["dossier"]["trade"]["target_long"] == "ABCD"
    assert snap["dd"] is None
    assert snap["decision"]["decision"] == "enter"


def test_review_snapshot_from_real_contracts_drops_round_log_keeps_count():
    from catalyst_trader.contracts import MDDecision, ReconciliationRound

    rnd = ReconciliationRound(round=1, response_delta="unmoved", convergence={}, cross_check={},
                              disposition="converged")
    dec = MDDecision(decision="enter", rationale="edge priced", accepted_residuals=["gap risk -> size"],
                     dissent_preserved=["bear: CMC"], round_log=[rnd, rnd])
    snap = pl.review_snapshot({"decision": dec, "dossier": None, "dd": None,
                               "catalyst": {"ticker": "ABCD", "event_date": "2026-08-20"}})
    assert snap["decision"]["rationale"] == "edge priced"
    assert snap["decision"]["rounds"] == 2
    assert "round_log" not in snap["decision"]
    assert snap["catalyst"]["event_date"] == "2026-08-20"
    json.dumps(snap)


def test_paper_run_submit_decision_persists_snapshot():
    conn = _conn()
    result = pr._fake_enter_result("ABCD", entry=10.0, exit_by="2026-08-21")
    pid = pr.submit_decision(conn, result, as_of="2026-08-14")
    assert _review(conn, pid)["dossier"]["trade"]["entry"] == 10.0
    assert pl.get_open_positions(conn) == []  # still nothing opens on submit


def test_concurrent_approves_open_exactly_one_position(tmp_path):
    path = str(tmp_path / "race.db")
    setup = _conn(path)
    pid = pl.submit_for_approval(setup, PARAMS)
    setup.close()

    barrier = threading.Barrier(4)
    results = []

    def worker():
        conn = _db.connect(path)
        barrier.wait()
        results.append(pl.approve_pending(conn, pid))
        conn.close()

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    check = _db.connect(path)
    n = check.execute("SELECT COUNT(*) c FROM paper_position").fetchone()["c"]
    assert n == 1
    assert len(set(results)) == 1 and results[0] is not None  # every caller sees the SAME position


def test_reject_never_opens_and_blocks_later_approve():
    conn = _conn()
    pid = pl.submit_for_approval(conn, PARAMS)
    pl.reject_pending(conn, pid)
    assert pl.approve_pending(conn, pid) is None
    assert conn.execute("SELECT COUNT(*) c FROM paper_position").fetchone()["c"] == 0


def test_snapshot_handles_namespace_without_model_dump():
    snap = pl.review_snapshot({"decision": SimpleNamespace(decision="enter", rationale="r"),
                               "dossier": SimpleNamespace(trade=SimpleNamespace(stop_loss=8.0))})
    assert snap["dossier"]["trade"]["stop_loss"] == 8.0
    assert snap["catalyst"] is None
