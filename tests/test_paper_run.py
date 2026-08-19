"""7.8-S4 Task 3: the paper_run.py operator harness — offline --dry-run wiring proof.

Proves the WHOLE loop with ZERO network/LLM: fake 'enter' decision -> submit -> approve -> open ->
mark (future) -> close (past exit_by). Also: a non-'enter' decision submits nothing.
"""

from types import SimpleNamespace

from catalyst_trader import db as _db
from catalyst_trader import paper_ledger as pl

import scripts.paper_run as pr


def _conn():
    conn = _db.connect(":memory:")
    _db.migrate(conn)
    return conn


def test_dry_run_drives_full_loop_offline():
    conn = _conn()
    out = pr.dry_run(conn)
    assert out["pending_id"] is not None
    assert out["position_id"] is not None
    # exactly one position opened after approve, then closed on the past-exit_by mark pass.
    assert out["close_summary"]["closed"] == 1
    assert pl.get_open_positions(conn) == []
    pos = conn.execute("SELECT status, realized_ret FROM paper_position").fetchone()
    assert pos["status"] == "closed" and pos["realized_ret"] is not None


def test_submit_decision_enter_submits_one_pending():
    conn = _conn()
    result = pr._fake_enter_result("ABCD", entry=10.0, exit_by="2026-08-21")
    pid = pr.submit_decision(conn, result, as_of="2026-08-14")
    assert pid is not None
    assert conn.execute("SELECT COUNT(*) c FROM paper_pending WHERE status='pending'").fetchone()["c"] == 1
    assert pl.get_open_positions(conn) == []  # nothing opens before approval (the gate)


def test_submit_decision_non_enter_submits_nothing():
    conn = _conn()
    result = {"decision": SimpleNamespace(decision="pass"), "dossier": None,
              "reason": "no trade promoted", "catalyst": {"ticker": "ABCD"}}
    pid = pr.submit_decision(conn, result, as_of="2026-08-14")
    assert pid is None
    assert conn.execute("SELECT COUNT(*) c FROM paper_pending").fetchone()["c"] == 0


def test_no_live_broker_order_in_harness():
    import scripts.paper_run as mod
    assert not hasattr(mod, "place_equity_order")
