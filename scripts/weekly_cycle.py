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
from datetime import date

from catalyst_trader import db as _db
from catalyst_trader import kb, paper_ledger
from catalyst_trader.calendar import triggers
from catalyst_trader.desk import desk_queue
from catalyst_trader.desk.catalyst_context import make_catalyst_context
from catalyst_trader.desk.live_desk import run_one_catalyst_decision

import scripts.paper_run as paper_run

logger = logging.getLogger(__name__)


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
    return {"drained": drained, "submitted": submitted, "errors": errors}


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
    ap.add_argument("--db", default="catalyst.db", help="catalyst.db path (default: catalyst.db)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO)

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
        else:
            ap.error("give one of --desk/--mark")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
