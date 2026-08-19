"""7.8-S4 Task 1: the paper ledger store + the INVIOLABLE operator-approval gate.

Money-path invariants under test (all offline / :memory:):
  - migration 015 applies on top of 014 (the three paper_ tables exist).
  - the ONLY way a paper_position opens is approve_pending over a pending record — a rejected or
    un-approved decision produces ZERO positions (the inviolable human gate, tested structurally).
  - approve is idempotent (approve twice -> one position, never a double-book).
  - mark is upsert on (position_id, mark_date); close guards against a re-close double-book.
"""

import pytest

from catalyst_trader import db as _db
from catalyst_trader import paper_ledger as pl


def _conn():
    conn = _db.connect(":memory:")
    _db.migrate(conn)
    return conn


def _params(**over):
    base = dict(
        ticker="ABCD", side="long", entry=10.0, size_pct=0.02, opened_at="2026-08-14",
        exit_by="2026-08-21", held_through=True, direction="positive",
        catalyst_id="cat-1", decision_ref="kb:42", evidence_refs=["kb:42"],
    )
    base.update(over)
    return base


# --------------------------------------------------------------------------- migration


def test_given_fresh_db_when_migrated_then_paper_tables_exist():
    conn = _conn()
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'paper_%'"
    ).fetchall()}
    assert tables == {"paper_position", "paper_mark", "paper_pending"}


# --------------------------------------------------------------------------- the gate


def test_given_submitted_when_rejected_then_no_position_opens():
    conn = _conn()
    pid = pl.submit_for_approval(conn, _params())
    pl.reject_pending(conn, pid)
    assert pl.get_open_positions(conn) == []
    row = conn.execute("SELECT status, position_id FROM paper_pending WHERE id=?", (pid,)).fetchone()
    assert row["status"] == "rejected" and row["position_id"] is None


def test_given_only_submitted_when_never_approved_then_no_position_opens():
    conn = _conn()
    pl.submit_for_approval(conn, _params())
    # a pending-but-unapproved decision is INERT — nothing in the ledger.
    assert pl.get_open_positions(conn) == []


def test_given_submitted_when_approved_then_exactly_one_open_with_submitted_params():
    conn = _conn()
    pid = pl.submit_for_approval(conn, _params(ticker="WXYZ", entry=42.5, size_pct=0.03))
    pos_id = pl.approve_pending(conn, pid)
    opens = pl.get_open_positions(conn)
    assert len(opens) == 1
    pos = opens[0]
    assert pos["id"] == pos_id
    assert pos["ticker"] == "WXYZ" and pos["entry_price"] == 42.5 and pos["size_pct"] == 0.03
    assert pos["status"] == "open"
    row = conn.execute("SELECT status, position_id FROM paper_pending WHERE id=?", (pid,)).fetchone()
    assert row["status"] == "approved" and row["position_id"] == pos_id


def test_given_approved_when_approved_again_then_no_duplicate_position():
    conn = _conn()
    pid = pl.submit_for_approval(conn, _params())
    first = pl.approve_pending(conn, pid)
    second = pl.approve_pending(conn, pid)  # idempotent no-op
    assert second == first
    assert len(pl.get_open_positions(conn)) == 1


def test_given_rejected_when_approved_then_still_no_position():
    conn = _conn()
    pid = pl.submit_for_approval(conn, _params())
    pl.reject_pending(conn, pid)
    assert pl.approve_pending(conn, pid) is None
    assert pl.get_open_positions(conn) == []


def test_no_public_open_bypasses_the_gate():
    # the gate is STRUCTURAL: paper_ledger exposes no public opener other than approve_pending.
    assert not hasattr(pl, "open_paper_position")


# --------------------------------------------------------------------------- mark / close


def test_given_open_when_marked_twice_same_date_then_upsert_in_place():
    conn = _conn()
    pos_id = pl.approve_pending(conn, pl.submit_for_approval(conn, _params()))
    pl.mark_paper_position(conn, pos_id, "2026-08-16", 10.5, 0.05)
    pl.mark_paper_position(conn, pos_id, "2026-08-16", 11.0, 0.10)  # same date -> update
    rows = conn.execute("SELECT mark_price, unrealized_ret FROM paper_mark WHERE position_id=?",
                        (pos_id,)).fetchall()
    assert len(rows) == 1
    assert rows[0]["mark_price"] == 11.0 and rows[0]["unrealized_ret"] == 0.10


def test_given_open_when_closed_then_status_and_realized_booked():
    conn = _conn()
    pos_id = pl.approve_pending(conn, pl.submit_for_approval(conn, _params()))
    pl.close_paper_position(conn, pos_id, close_price=11.0, realized_ret=0.098)
    assert pl.get_open_positions(conn) == []
    pos = conn.execute("SELECT * FROM paper_position WHERE id=?", (pos_id,)).fetchone()
    assert pos["status"] == "closed" and pos["close_price"] == 11.0
    assert pos["realized_ret"] == 0.098 and pos["closed_at"] is not None


def test_given_closed_when_reclosed_then_raises_never_double_books():
    conn = _conn()
    pos_id = pl.approve_pending(conn, pl.submit_for_approval(conn, _params()))
    pl.close_paper_position(conn, pos_id, close_price=11.0, realized_ret=0.098)
    with pytest.raises(ValueError):
        pl.close_paper_position(conn, pos_id, close_price=9.0, realized_ret=-0.1)
    # the original booking is untouched
    pos = conn.execute("SELECT realized_ret FROM paper_position WHERE id=?", (pos_id,)).fetchone()
    assert pos["realized_ret"] == 0.098
