"""paper_ledger.py (7.8-S4) — the forward PAPER trading ledger + the inviolable operator gate.

Three concerns, in order:
  1. STORE (this half): plain sqlite helpers mirroring store.py — open/mark/close a paper_position,
     upsert a paper_mark, and the pending gate (submit/approve/reject). The gate is STRUCTURAL: the
     ONLY code path that inserts a paper_position is ``approve_pending`` over a pending record, so no
     position can open without an explicit operator approval (the human gate, enforced by construction
     — there is no public ``open_*`` function).
  2. LIFECYCLE (Task 2): map an APPROVED MDDecision 'enter' -> position params; mark every open at the
     point-in-time quote and CLOSE any past exit_by at the SAME pessimistic fill the backtest uses
     (fill.fill_price + engine._net_return, half-spread both sides) — realized P&L is byte-identical to
     the backtest, no live-vs-backtest drift.
  3. FEEDBACK (Task 2): a closed position writes a CITED KB outcome referencing the decision's OWN
     evidence refs (cite-or-drop) — never a fabricated citation.

PAPER ONLY: no live-broker order path is ever imported or called here (Phase 11 is strictly last).
# ponytail: plain sqlite helpers mirroring store.py; no repository class, no ORM.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

from catalyst_trader.dates import now_iso

# --- store: paper_position (write path is PRIVATE — only approve_pending opens) ---------------

_POS_COLS = (
    "ticker", "side", "entry_price", "size_pct", "opened_at", "exit_by",
    "held_through", "direction", "decision_ref", "catalyst_id", "evidence_refs",
)


def _open_paper_position(conn: sqlite3.Connection, params: dict) -> int:
    """Insert one OPEN paper_position from an approved decision's params; return its id.

    PRIVATE by design — the SOLE caller is ``approve_pending`` (the structural human gate). Never
    call this directly; a position with no approved pending record is a gate violation.
    """
    row = (
        params["ticker"], params.get("side", "long"), float(params["entry"]),
        float(params["size_pct"]), params["opened_at"], params["exit_by"],
        1 if params.get("held_through", True) else 0, params.get("direction"),
        params.get("decision_ref"), params.get("catalyst_id"),
        json.dumps(params.get("evidence_refs", [])),
    )
    return conn.execute(
        f"INSERT INTO paper_position ({', '.join(_POS_COLS)}, status) "
        f"VALUES ({', '.join('?' * len(_POS_COLS))}, 'open')",
        row,
    ).lastrowid


def get_open_positions(conn: sqlite3.Connection) -> list[dict]:
    """Every position with status='open', as plain dicts (evidence_refs parsed back to a list)."""
    rows = conn.execute("SELECT * FROM paper_position WHERE status='open' ORDER BY id").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["held_through"] = bool(d["held_through"])
        d["evidence_refs"] = json.loads(d["evidence_refs"]) if d["evidence_refs"] else []
        out.append(d)
    return out


def mark_paper_position(
    conn: sqlite3.Connection, position_id: int, mark_date: str, mark_price: float,
    unrealized_ret: float | None, *, source: str = "bars",
) -> int:
    """UPSERT one weekly mark for an open position; idempotent on (position_id, mark_date) — a
    re-mark at the same date UPDATES in place (mirrors upsert_bars). Returns the row id."""
    try:
        existing = conn.execute(
            "SELECT id FROM paper_mark WHERE position_id=? AND mark_date=?",
            (position_id, mark_date),
        ).fetchone()
        if existing is not None:
            conn.execute(
                "UPDATE paper_mark SET mark_price=?, unrealized_ret=?, source=? WHERE id=?",
                (mark_price, unrealized_ret, source, existing["id"]),
            )
            row_id = existing["id"]
        else:
            row_id = conn.execute(
                "INSERT INTO paper_mark (position_id, mark_date, mark_price, unrealized_ret, source) "
                "VALUES (?,?,?,?,?)",
                (position_id, mark_date, mark_price, unrealized_ret, source),
            ).lastrowid
        conn.commit()
        return row_id
    except Exception:
        conn.rollback()
        raise


def close_paper_position(
    conn: sqlite3.Connection, position_id: int, *, close_price: float, realized_ret: float,
) -> None:
    """Book the realized close: status->'closed', close_price, realized_ret, closed_at. Guards a
    re-close (an already-closed position RAISES — realized P&L is never double-booked)."""
    row = conn.execute("SELECT status FROM paper_position WHERE id=?", (position_id,)).fetchone()
    if row is None:
        raise ValueError(f"no paper_position id={position_id}")
    if row["status"] != "open":
        raise ValueError(f"paper_position id={position_id} is already {row['status']} — refuse to re-close")
    try:
        conn.execute(
            "UPDATE paper_position SET status='closed', close_price=?, realized_ret=?, closed_at=? "
            "WHERE id=?",
            (close_price, realized_ret, now_iso(), position_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# --- the INVIOLABLE operator-approval gate ---------------------------------------------------
# submit -> a pending record only. approve -> the SOLE path that opens a position. reject -> nothing.


def submit_for_approval(conn: sqlite3.Connection, params: dict) -> int:
    """Record a decision as PENDING operator approval; return the pending id. Opens NOTHING."""
    try:
        pid = conn.execute(
            "INSERT INTO paper_pending (status, params, submitted_at) VALUES ('pending', ?, ?)",
            (json.dumps(params), now_iso()),
        ).lastrowid
        conn.commit()
        return pid
    except Exception:
        conn.rollback()
        raise


def approve_pending(conn: sqlite3.Connection, pending_id: int) -> int | None:
    """The SOLE opener: over a still-'pending' record, open the position from its params and flip the
    record to 'approved' (returns the new position id). Idempotent — an already-approved record
    returns its existing position id (no duplicate); a rejected/absent record returns None."""
    row = conn.execute("SELECT status, params, position_id FROM paper_pending WHERE id=?",
                       (pending_id,)).fetchone()
    if row is None:
        return None
    if row["status"] == "approved":
        return row["position_id"]  # idempotent: no second position
    if row["status"] != "pending":
        return None  # rejected -> never opens
    try:
        pos_id = _open_paper_position(conn, json.loads(row["params"]))
        conn.execute(
            "UPDATE paper_pending SET status='approved', resolved_at=?, position_id=? WHERE id=?",
            (now_iso(), pos_id, pending_id),
        )
        conn.commit()
        return pos_id
    except Exception:
        conn.rollback()
        raise


def reject_pending(conn: sqlite3.Connection, pending_id: int) -> None:
    """Flip a pending record to 'rejected'; opens NO position (the gate's negative path)."""
    try:
        conn.execute(
            "UPDATE paper_pending SET status='rejected', resolved_at=? WHERE id=? AND status='pending'",
            (now_iso(), pending_id),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
