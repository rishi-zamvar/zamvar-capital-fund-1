"""7.8-S5 Task 1: the T-2 -> desk-run queue seam (DATA-05 real launcher, headless-safe).

Proves, fully offline (no LLM/network): migration 016 gives a desk_run_request table;
enqueue is idempotent and OPENS NOTHING; register(conn)+detect_and_fire enqueues exactly
one request for a seeded verified T-2 catalyst; list_queued/mark_request round-trip.
"""

from datetime import datetime, timezone

import pytest
from freezegun import freeze_time

from catalyst_trader import db as _db
from catalyst_trader import store
from catalyst_trader.calendar import triggers
from catalyst_trader.desk import desk_queue
from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    CatalystType,
    DatePrecision,
    SourceOrigin,
    SourceType,
    Status,
    Uncertainty,
)


@pytest.fixture(autouse=True)
def _clear_callbacks():
    """Reuse the triggers test isolation pattern (C1): no callback bound to a stale conn
    may leak into the next detect_and_fire (double-enqueue / wrong-conn writes)."""
    triggers._callbacks.clear()
    yield
    triggers._callbacks.clear()


def _conn():
    conn = _db.connect(":memory:")
    _db.migrate(conn)
    return conn


def _seed_catalyst(conn, event_date, status=Status.verified, ticker="VRTX"):
    c = Catalyst(
        ticker=ticker,
        catalyst_type=CatalystType.pdufa,
        event_date=event_date,
        date_precision=DatePrecision.day,
        uncertainty_type=Uncertainty.firm,
        source_origin=SourceOrigin.curated_pdufa,
        sources=[
            CatalystSource(
                source_name="FDA",
                source_url="https://www.fda.gov/x",
                source_type=SourceType.primary,
                reported_date=event_date,
                retrieved_at="2026-08-14T00:00:00Z",
            )
        ],
    )
    cid = store.insert_catalyst(conn, c)
    conn.execute("UPDATE catalyst SET status=? WHERE id=?", (status.value, cid))
    conn.commit()
    return cid


def test_migration_016_creates_desk_run_request():
    conn = _conn()
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(desk_run_request)")}
    assert {"catalyst_id", "ticker", "event_date", "status", "enqueued_at",
            "resolved_at", "pending_id"} <= cols


def test_enqueue_is_idempotent_and_opens_nothing():
    conn = _conn()
    cid = _seed_catalyst(conn, "2026-09-01")
    row = conn.execute("SELECT * FROM catalyst WHERE id=?", (cid,)).fetchone()
    desk_queue.enqueue_desk_run(conn, row)
    desk_queue.enqueue_desk_run(conn, row)  # second fire for same (catalyst,event_date) => no-op
    n = conn.execute("SELECT COUNT(*) c FROM desk_run_request").fetchone()["c"]
    assert n == 1
    # the callback OPENS NOTHING — the gate is untouched.
    assert conn.execute("SELECT COUNT(*) c FROM paper_position").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM paper_pending").fetchone()["c"] == 0


def test_register_then_detect_and_fire_enqueues_exactly_one():
    conn = _conn()
    # a verified, day-precision catalyst 2 days out.
    with freeze_time("2026-08-19T12:00:00Z"):
        _seed_catalyst(conn, "2026-08-21")
        desk_queue.register(conn)
        fired = triggers.detect_and_fire(conn, datetime(2026, 8, 19, 12, tzinfo=timezone.utc))
        # re-run same day: trigger_event dedups => no second enqueue.
        triggers.detect_and_fire(conn, datetime(2026, 8, 19, 12, tzinfo=timezone.utc))
    assert len(fired) == 1
    rows = desk_queue.list_queued(conn)
    assert len(rows) == 1
    assert rows[0]["ticker"] == "VRTX" and rows[0]["status"] == "queued"
    # still opened nothing.
    assert conn.execute("SELECT COUNT(*) c FROM paper_position").fetchone()["c"] == 0


def test_list_queued_oldest_first_and_mark_request():
    conn = _conn()
    c1 = conn.execute("SELECT * FROM catalyst WHERE id=?", (_seed_catalyst(conn, "2026-09-01", ticker="AAA"),)).fetchone()
    c2 = conn.execute("SELECT * FROM catalyst WHERE id=?", (_seed_catalyst(conn, "2026-09-02", ticker="BBB"),)).fetchone()
    desk_queue.enqueue_desk_run(conn, c1)
    desk_queue.enqueue_desk_run(conn, c2)
    rows = desk_queue.list_queued(conn)
    assert [r["ticker"] for r in rows] == ["AAA", "BBB"]  # oldest-first
    desk_queue.mark_request(conn, rows[0]["id"], "done", pending_id=42)
    remaining = desk_queue.list_queued(conn)
    assert [r["ticker"] for r in remaining] == ["BBB"]  # done rows drop out of the queue
    done = conn.execute("SELECT status, pending_id, resolved_at FROM desk_run_request WHERE id=?",
                        (rows[0]["id"],)).fetchone()
    assert done["status"] == "done" and done["pending_id"] == 42 and done["resolved_at"] is not None
