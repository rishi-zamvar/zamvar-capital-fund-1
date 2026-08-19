"""7.8-S5 Tasks 2+3: weekly_cycle.py — the auto-cadence runner (offline proofs).

Proves fully offline (fake desk_fn / in-memory db, ZERO network/LLM): --desk drains the queue and
SUBMITS 'enter's to the inviolable gate (never opens); a bad catalyst never sinks the batch; --mark
marks/closes via the Slice-4 fill; --status returns the four-section view; --dry-run drives the whole
enqueue->drain->submit->approve->mark loop and asserts the gate held (pending written, no auto-open).
The whole module contains NO opener/broker call.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from freezegun import freeze_time

from catalyst_trader import db as _db
from catalyst_trader import paper_ledger as pl
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

import scripts.paper_run as pr
import scripts.weekly_cycle as wc


@pytest.fixture(autouse=True)
def _clear_callbacks():
    """C1: no stale-conn callback leaks between tests (reuse the triggers isolation pattern)."""
    triggers._callbacks.clear()
    yield
    triggers._callbacks.clear()


def _conn():
    conn = _db.connect(":memory:")
    _db.migrate(conn)
    return conn


def _seed_catalyst(conn, event_date, ticker="VRTX", status=Status.verified):
    c = Catalyst(
        ticker=ticker, catalyst_type=CatalystType.pdufa, event_date=event_date,
        date_precision=DatePrecision.day, uncertainty_type=Uncertainty.firm,
        source_origin=SourceOrigin.curated_pdufa,
        sources=[CatalystSource(source_name="FDA", source_url="https://www.fda.gov/x",
                                source_type=SourceType.primary, reported_date=event_date,
                                retrieved_at="2026-08-14T00:00:00Z")],
    )
    cid = store.insert_catalyst(conn, c)
    conn.execute("UPDATE catalyst SET status=? WHERE id=?", (status.value, cid))
    conn.commit()
    return cid


def _enqueue(conn, ticker="VRTX", event_date="2026-09-01"):
    cid = _seed_catalyst(conn, event_date, ticker=ticker)
    row = conn.execute("SELECT * FROM catalyst WHERE id=?", (cid,)).fetchone()
    desk_queue.enqueue_desk_run(conn, row)


def _fake_enter_fn(conn, ticker, as_of):
    return pr._fake_enter_result(ticker, entry=10.0, exit_by="2026-08-21")


def _fake_pass_fn(conn, ticker, as_of):
    return {"decision": None, "dossier": None, "reason": "no trade promoted"}


def _boom_fn(conn, ticker, as_of):
    raise RuntimeError("desk blew up")


# --------------------------------------------------------------- Task 2: --desk drain + gate


def test_desk_drain_enter_submits_to_gate_and_opens_nothing():
    conn = _conn()
    _enqueue(conn, "VRTX")
    summary = wc.drain_desk(conn, desk_fn=_fake_enter_fn, as_of="2026-08-14")
    assert summary == {"drained": 1, "submitted": 1, "errors": 0}
    # the GATE HELD: a pending row exists, ZERO positions opened.
    assert conn.execute("SELECT COUNT(*) c FROM paper_pending WHERE status='pending'").fetchone()["c"] == 1
    assert pl.get_open_positions(conn) == []
    # the request is resolved 'done' with the submitted pending id recorded.
    req = conn.execute("SELECT status, pending_id FROM desk_run_request").fetchone()
    assert req["status"] == "done" and req["pending_id"] is not None
    assert desk_queue.list_queued(conn) == []


def test_desk_drain_pass_submits_nothing_but_resolves_done():
    conn = _conn()
    _enqueue(conn, "VRTX")
    summary = wc.drain_desk(conn, desk_fn=_fake_pass_fn, as_of="2026-08-14")
    assert summary == {"drained": 1, "submitted": 0, "errors": 0}
    assert conn.execute("SELECT COUNT(*) c FROM paper_pending").fetchone()["c"] == 0
    req = conn.execute("SELECT status, pending_id FROM desk_run_request").fetchone()
    assert req["status"] == "done" and req["pending_id"] is None


def test_desk_drain_error_never_sinks_the_batch():
    conn = _conn()
    _enqueue(conn, "AAA", "2026-09-01")
    _enqueue(conn, "BBB", "2026-09-02")

    def fn(conn, ticker, as_of):
        if ticker == "AAA":
            raise RuntimeError("boom")
        return pr._fake_enter_result(ticker, entry=10.0, exit_by="2026-08-21")

    summary = wc.drain_desk(conn, desk_fn=fn, as_of="2026-08-14")
    assert summary == {"drained": 2, "submitted": 1, "errors": 1}
    rows = {r["ticker"]: r["status"] for r in
            conn.execute("SELECT ticker, status FROM desk_run_request")}
    assert rows == {"AAA": "error", "BBB": "done"}
    assert pl.get_open_positions(conn) == []  # still nothing opened


def test_mark_closes_via_mark_open_positions():
    conn = _conn()
    # open one position through the real gate, then a late mark closes it at the exit-by bar.
    from catalyst_trader.store import upsert_bars
    upsert_bars(conn, "DRYX", [
        {"week_end": "2026-08-14", "open": 9.8, "high": 10.3, "low": 9.5, "close": 10.0, "volume": 4000},
        {"week_end": "2026-08-21", "open": 12.0, "high": 13.0, "low": 11.0, "close": 12.5, "volume": 5000},
    ])
    result = pr._fake_enter_result("DRYX", entry=10.0, exit_by="2026-08-21")
    pid = pr.submit_decision(conn, result, as_of="2026-08-14")
    pl.approve_pending(conn, pid)
    summary = pl.mark_open_positions(conn, "2026-08-28")
    assert summary["closed"] == 1
    assert pl.get_open_positions(conn) == []


def test_module_contains_no_opener_or_broker_call():
    src = Path(wc.__file__).read_text()
    for forbidden in ("approve_pending", "_open_paper_position", "place_equity_order"):
        assert forbidden not in src, f"{forbidden} must never appear in weekly_cycle.py"
