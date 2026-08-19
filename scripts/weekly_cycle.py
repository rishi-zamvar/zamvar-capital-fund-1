"""scripts/weekly_cycle.py (7.8-S5) — the auto-cadence runner for forward PAPER trading.

Slice 5 automates the weekly cadence the operator ran by hand (paper_run.py per catalyst):

    weekly_cycle.py --desk       DRAIN the T-2 desk-run queue: run the live desk per queued catalyst
                                 -> SUBMIT any 'enter' to the approval gate. NOTHING opens — the human
                                 gate is the only opener. Runs ONLY inside a Claude Code session (the
                                 LLM desk needs Max; a headless cron has no API key).
    weekly_cycle.py --mark       the weekly mark/close pass (HEADLESS, launchd-schedulable, no LLM):
                                 mark every open + close any past exit_by at the Slice-4 byte-identical fill.
    weekly_cycle.py --status     offline snapshot: open positions, pending approvals, upcoming catalysts,
                                 queued desk runs. No LLM/network.
    weekly_cycle.py --dry-run    offline proof of the whole enqueue->drain->submit loop with the gate HELD.

`drain_desk`/`status`/`dry_run` are the TESTABLE cores (no network/LLM — desk_fn/db injectable); the thin
__main__ resolves the live desk (async -> asyncio.run) and routes the flags.

The runtime split is HONEST (see docs/operator-weekly-cycle.md): DATA (refresh, Task-1 enqueue) + MARK
run headlessly via launchd; the DESK/decision pass needs a CC session. This module imports NO opener and
NO live-broker order path — it only SUBMITS to the gate (the whole-file grep for the opener/broker
symbols is empty by design; the operator opens via paper_run's approve flow).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time
from datetime import date, timedelta

from catalyst_trader import db as _db
from catalyst_trader import kb, paper_ledger
from catalyst_trader.calendar import triggers
from catalyst_trader.desk import desk_queue
from catalyst_trader.desk.catalyst_context import make_catalyst_context
from catalyst_trader.desk.live_desk import run_one_catalyst_decision

try:  # `python -m pytest` puts repo-root on path (scripts.*); a direct `python scripts/x.py` puts scripts/ on path.
    import scripts.paper_run as paper_run
except ModuleNotFoundError:
    import paper_run

logger = logging.getLogger(__name__)

# The --status "upcoming catalysts" window reuses the trigger window's outer bound (C2 — no new
# literal): a verified catalyst 0..T2_MAX_DAYS out is what a drain is about to (or just did) act on.
_STATUS_WINDOW_DAYS = triggers.T2_MAX_DAYS


# --------------------------------------------------------------- the testable cores


def drain_desk(conn, *, desk_fn, as_of: str) -> dict:
    """Drain the queued desk-run requests: for each, run the desk (``desk_fn(conn, ticker, as_of)``)
    -> submit_decision -> mark_request. An 'enter' writes a paper_pending row and ZERO paper_position
    (the gate holds); a pass/no-decision submits nothing; an exception marks the request 'error' and
    the drain CONTINUES (one bad catalyst never sinks the batch). Returns {drained, submitted, errors}.

    This SUBMITS only and NEVER opens — the human gate (paper_run's approve flow) is the sole opener.
    """
    drained = submitted = errors = 0
    for req in desk_queue.list_queued(conn):
        ticker = req["ticker"]
        drained += 1
        t0 = time.monotonic()
        try:
            result = desk_fn(conn, ticker, as_of)
            pid = paper_run.submit_decision(conn, result, as_of=as_of)  # 'enter' -> gate; else None
            desk_queue.mark_request(conn, req["id"], "done", pending_id=pid)
            if pid is not None:
                submitted += 1
        except Exception as exc:  # a single bad catalyst is logged + skipped, never crashes the batch
            errors += 1
            desk_queue.mark_request(conn, req["id"], "error", pending_id=None)
            logger.warning("desk-run %s FAILED (%s) — marked error, continuing", ticker, exc)
        # Observability: the HONEST measured metric is wall-time; ~10-11s/call is the Slice-0 LLM
        # reference so the operator can sanity-check spend. (No fabricated call tally — runtime.py
        # exposes none.) 10-11s lives in the log string, not as a code constant (no new magic number).
        dt = time.monotonic() - t0
        logger.info("desk-run %s elapsed=%.1fs (~10-11s/LLM call, Slice-0) submitted=%d errors=%d",
                    ticker, dt, submitted, errors)
    return {"drained": drained, "submitted": submitted, "errors": errors}


def status(conn, *, as_of: str) -> dict:
    """Offline snapshot (no LLM/network): open positions, pending approvals, upcoming verified
    catalysts (event_date within the next T2_MAX_DAYS — C2), and queued desk runs. Prints each
    section and returns the four counts."""
    opens = paper_ledger.get_open_positions(conn)
    pending = conn.execute(
        "SELECT id, submitted_at FROM paper_pending WHERE status='pending' ORDER BY id"
    ).fetchall()
    horizon = (date.fromisoformat(as_of) + timedelta(days=_STATUS_WINDOW_DAYS)).isoformat()
    upcoming = conn.execute(
        "SELECT ticker, catalyst_type, event_date FROM catalyst "
        "WHERE status='verified' AND event_date >= ? AND event_date <= ? ORDER BY event_date",
        (as_of, horizon),
    ).fetchall()
    queued = desk_queue.list_queued(conn)

    print(f"WEEKLY STATUS  as_of={as_of}")
    print(f"  open positions    {len(opens)}")
    for p in opens:
        print(f"    #{p['id']} {p['ticker']} entry={p['entry_price']} exit_by={p['exit_by']}")
    print(f"  pending approvals {len(pending)}")
    for p in pending:
        print(f"    pending #{p['id']} submitted={p['submitted_at']}")
    print(f"  upcoming catalysts (<= {_STATUS_WINDOW_DAYS}d)  {len(upcoming)}")
    for c in upcoming:
        print(f"    {c['ticker']} {c['catalyst_type']} {c['event_date']}")
    print(f"  queued desk runs  {len(queued)}")
    for q in queued:
        print(f"    q#{q['id']} {q['ticker']} event={q['event_date']}")
    return {"open": len(opens), "pending": len(pending),
            "upcoming": len(upcoming), "queued": len(queued)}


def dry_run(conn) -> dict:
    """Offline full-loop proof (ZERO network/LLM): seed a T-2 verified catalyst -> register +
    detect_and_fire ENQUEUES -> drain_desk with a fake 'enter' -> submit -> assert the GATE HELD
    (pending > 0 AND open positions == 0). It STOPS there (B1): the approve -> open -> close tail is
    already proven by paper_run.dry_run (Slice 4); re-proving it here would duplicate Slice 4 and
    would break this module's whole-file no-opener invariant. Returns a summary; prints each step."""
    triggers._callbacks.clear()  # C1: no stale-conn callback before we register our own
    from catalyst_trader import store
    from catalyst_trader.models import (
        Catalyst, CatalystSource, CatalystType, DatePrecision, SourceOrigin,
        SourceType, Status, Uncertainty)
    from freezegun import freeze_time

    with freeze_time("2026-08-19T12:00:00Z"):  # pin now so 2026-08-21 sits exactly at T-2
        c = Catalyst(
            ticker="DRYX", catalyst_type=CatalystType.pdufa, event_date="2026-08-21",
            date_precision=DatePrecision.day, uncertainty_type=Uncertainty.firm,
            source_origin=SourceOrigin.curated_pdufa,
            sources=[CatalystSource(source_name="FDA", source_url="https://www.fda.gov/x",
                                    source_type=SourceType.primary, reported_date="2026-08-21",
                                    retrieved_at="2026-08-14T00:00:00Z")])
        cid = store.insert_catalyst(conn, c)
        conn.execute("UPDATE catalyst SET status=? WHERE id=?", (Status.verified.value, cid))
        conn.commit()
        desk_queue.register(conn)
        fired = triggers.detect_and_fire(conn)
    print(f"ENQUEUE       T-2 fired={len(fired)} -> queued={len(desk_queue.list_queued(conn))}")

    def _fake(conn, ticker, as_of):
        return paper_run._fake_enter_result(ticker, entry=10.0, exit_by="2026-08-28")

    drain = drain_desk(conn, desk_fn=_fake, as_of="2026-08-19")
    print(f"DRAIN         {drain}")
    pending = conn.execute(
        "SELECT COUNT(*) c FROM paper_pending WHERE status='pending'").fetchone()["c"]
    opens = len(paper_ledger.get_open_positions(conn))
    print(f"GATE CHECK    pending={pending}  open_positions={opens}")
    assert pending > 0 and opens == 0, "GATE VIOLATION: a drain must submit, never open"
    print("GATE HELD     pending written, ZERO positions opened (the inviolable human gate)")
    triggers._callbacks.clear()
    return {"fired": len(fired), "drain": drain, "pending": pending, "open_positions": opens}


# --------------------------------------------------------------- the live desk_fn (CC-only)


def _live_desk_fn(conn, ticker: str, as_of: str) -> dict:
    """The ONLY network+LLM path — runs ONLY inside a Claude Code session. Reproduces paper_run's
    live chain: catalyst context (RH quote override) -> run_one_catalyst_decision(live=True)."""
    embed = kb.default_embedder()
    hook = make_catalyst_context(embed=embed, cutoff=None, quote_override=paper_run._rh_quote_override)
    return asyncio.run(run_one_catalyst_decision(
        conn, embed, ticker, as_of=as_of, live=True, context_hook=hook))


# --------------------------------------------------------------- thin __main__


def main():
    ap = argparse.ArgumentParser(description="Auto-cadence runner for forward paper trading (7.8-S5).")
    ap.add_argument("--desk", action="store_true", help="drain the T-2 queue -> submit to the gate (CC only)")
    ap.add_argument("--mark", action="store_true", help="weekly headless pass: mark opens + close past exit_by")
    ap.add_argument("--status", action="store_true", help="offline snapshot (opens/pending/upcoming/queued)")
    ap.add_argument("--dry-run", action="store_true", help="offline full-loop proof, gate held (no network)")
    ap.add_argument("--db", default="catalyst.db", help="catalyst.db path (default: catalyst.db)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)

    if args.dry_run:
        conn = _db.connect(":memory:")  # isolated in-memory ledger — never touches the real db
        _db.migrate(conn)
        dry_run(conn)
        conn.close()
        return

    conn = _db.connect(args.db)
    _db.migrate(conn)
    try:
        as_of = date.today().isoformat()
        if args.desk:
            summary = drain_desk(conn, desk_fn=_live_desk_fn, as_of=as_of)
            print(f"desk drain: {summary}")
        elif args.mark:
            summary = paper_ledger.mark_open_positions(conn, as_of, quotes_fn=paper_ledger._rh_quote)
            print(f"weekly mark pass: {summary}")
        elif args.status:
            status(conn, as_of=as_of)
        else:
            ap.error("give one of --desk/--mark/--status/--dry-run")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
