"""The real T-2 launcher (DATA-05): a persistent desk-run queue between the HEADLESS daily
refresh and the Claude-Code desk pass.

The T-2 trigger seam (``triggers.register_callback``) has been a log-only stub since Phase 1
("Phases 4+ register the real Workflow-1 launcher here"). Slice 5 registers it — but the callback
fires inside the headless daily refresh, which has NO API key and CANNOT call the LLM desk. So the
launcher does the only headless-safe thing: it ENQUEUES a desk-run request. An operator drains the
queue inside a Claude Code session (``weekly_cycle.py --desk``) to produce approval-gated decisions.

enqueue is deterministic, offline, and OPENS NOTHING — it only writes a work-log row. The UNIQUE
(catalyst_id, event_date) key mirrors trigger_event, so enqueue is idempotent (no double-enqueue).
"""

import sqlite3

from catalyst_trader.calendar import triggers
from catalyst_trader.dates import now_iso


def enqueue_desk_run(conn: sqlite3.Connection, row: sqlite3.Row) -> None:
    """The T-2 callback body: INSERT OR IGNORE a queued desk-run request from the fired catalyst row.

    Headless-safe (no LLM/network) and idempotent (UNIQUE catalyst_id,event_date). NEVER touches
    paper_position/paper_pending — the human gate is the only opener.
    """
    conn.execute(
        "INSERT OR IGNORE INTO desk_run_request (catalyst_id, ticker, event_date, status, enqueued_at) "
        "VALUES (?, ?, ?, 'queued', ?)",
        (row["id"], row["ticker"], row["event_date"], now_iso()),
    )
    conn.commit()


def register(conn: sqlite3.Connection) -> None:
    """Wire the seam: register the enqueue callback bound to this conn (the callback contract is
    ``Callable[[Row], None]`` with NO conn, so the closure supplies it). Call this ONCE per process —
    refresh.main() does so after migrate and before detect_and_fire."""
    triggers.register_callback(lambda r: enqueue_desk_run(conn, r))


def list_queued(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Queued (not-yet-drained) desk-run requests, oldest-first — the drain order."""
    return conn.execute(
        "SELECT * FROM desk_run_request WHERE status='queued' ORDER BY id"
    ).fetchall()


def mark_request(conn: sqlite3.Connection, request_id: int, status: str,
                 pending_id: int | None = None) -> None:
    """Flip a request queued -> done/error, stamping resolved_at and the submitted pending_id (or None)."""
    conn.execute(
        "UPDATE desk_run_request SET status=?, resolved_at=?, pending_id=? WHERE id=?",
        (status, now_iso(), pending_id, request_id),
    )
    conn.commit()
