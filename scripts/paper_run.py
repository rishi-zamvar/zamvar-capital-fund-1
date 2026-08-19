"""scripts/paper_run.py (7.8-S4) — the operator harness for forward PAPER trading.

The minimal operator surface this slice (the full iOS/FastAPI gate is Phase 9):

    paper_run.py <TICKER>          run ONE catalyst -> MDDecision; if 'enter', SUBMIT for approval
                                   and print the dossier + pending id + the exact approve/reject cmds.
                                   NOTHING opens here — the human gate is the ONLY opener.
    paper_run.py --approve <id>    approve a pending decision -> open the paper position
    paper_run.py --reject  <id>    reject a pending decision -> nothing opens
    paper_run.py --mark            the weekly pass: mark every open + close any past exit_by
    paper_run.py --dry-run         offline proof of the whole submit->approve->open->mark->close loop

`submit_decision` / `dry_run` are the TESTABLE cores (no network/LLM); the thin __main__ resolves the
live decision (C5: run_one_catalyst_decision is async -> asyncio.run) and routes the flags.

PAPER ONLY: no live-broker order path is imported or called here (Phase 11 is strictly last).
# ponytail: argparse + a handful of branches; reuses run_one_catalyst.py's structure, no new framework.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date
from types import SimpleNamespace

from catalyst_trader import db as _db
from catalyst_trader import kb, paper_ledger
from catalyst_trader.desk.catalyst_context import make_catalyst_context
from catalyst_trader.desk.live_desk import run_one_catalyst_decision
from catalyst_trader.providers import robinhood


# --------------------------------------------------------------- the testable cores


def submit_decision(conn, result: dict, *, as_of: str) -> int | None:
    """If the decision is 'enter', SUBMIT its params for operator approval and print the gate surface;
    return the pending id. A non-'enter' (pass/escalate/None) prints the honest reason and submits
    NOTHING (returns None). This NEVER opens a position — approve_pending is the only opener."""
    params = paper_ledger.position_params_from_decision(result, as_of=as_of)
    if params is None:
        dec = result.get("decision")
        verdict = getattr(dec, "decision", None) or "no-decision"
        print(f"NO SUBMIT        decision={verdict} — {result.get('reason') or 'not an enter'}")
        return None
    pid = paper_ledger.submit_for_approval(conn, params)
    print("=" * 72)
    print(f"PENDING APPROVAL id={pid}  {params['ticker']}  entry={params['entry']}  "
          f"size_pct={params['size_pct']}  exit_by={params['exit_by']}")
    print(f"  direction      {params['direction']}   held_through={params['held_through']}")
    print(f"  evidence       {params['evidence_refs']}")
    print(f"  APPROVE ->      paper_run.py --approve {pid}")
    print(f"  REJECT  ->      paper_run.py --reject {pid}")
    print("  (nothing is open until you approve — the inviolable human gate)")
    print("=" * 72)
    return pid


def _fake_enter_result(ticker: str, *, entry: float, exit_by: str):
    """An offline canned 'enter' decision result (SimpleNamespace duck-types the dossier/trade the
    lifecycle reads) — the --dry-run seam, ZERO network/LLM."""
    trade = SimpleNamespace(
        target_long=ticker, entry=entry, size_pct=0.02, exit_by_date=exit_by,
        holds_through_catalyst=True, catalyst_id="dry-cat-1", direction="positive",
    )
    dossier = SimpleNamespace(trade=trade, all_evidence_refs=["tool:weekly_base_rate#dryrun"])
    return {"decision": SimpleNamespace(decision="enter"), "dossier": dossier, "reason": None}


def dry_run(conn) -> dict:
    """Drive the WHOLE loop offline: fake 'enter' -> submit -> approve -> open -> mark -> close.

    Seeds an injected exit-by action bar so the past-exit_by mark pass closes at the reused pessimistic
    fill (byte-identical to the backtest). Returns a summary dict; prints each step.
    """
    from catalyst_trader.store import upsert_bars

    as_of, exit_by = "2026-08-14", "2026-08-21"
    upsert_bars(conn, "DRYX", [
        {"week_end": as_of, "open": 9.8, "high": 10.3, "low": 9.5, "close": 10.0, "volume": 4000},
        {"week_end": exit_by, "open": 12.0, "high": 13.0, "low": 11.0, "close": 12.5, "volume": 5000},
    ])
    result = _fake_enter_result("DRYX", entry=10.0, exit_by=exit_by)
    pid = submit_decision(conn, result, as_of=as_of)
    pos_id = paper_ledger.approve_pending(conn, pid)
    print(f"APPROVED         pending {pid} -> position {pos_id} (open)")
    # a mark BEFORE exit_by marks unrealized; the mark AT/AFTER exit_by closes at the action bar.
    mark_summary = paper_ledger.mark_open_positions(conn, as_of)
    print(f"MARK  {as_of}   {mark_summary}")
    close_summary = paper_ledger.mark_open_positions(conn, "2026-08-28")  # a late weekly pass
    print(f"MARK  2026-08-28   {close_summary}")
    pos = conn.execute("SELECT status, close_price, realized_ret FROM paper_position WHERE id=?",
                       (pos_id,)).fetchone()
    print(f"CLOSED           status={pos['status']}  fill={pos['close_price']}  "
          f"realized_ret={pos['realized_ret']}")
    return {"pending_id": pid, "position_id": pos_id,
            "mark_summary": mark_summary, "close_summary": close_summary}


def _rh_quote_override(ticker):
    """--live entry override: RH get_equity_quotes last, or None (degrades to the cache-first close).
    mcp_call is None here (no broker MCP wired into this harness) -> degrades to None by design."""
    return (robinhood.quotes_rt([ticker]) or {}).get(ticker, {}).get("last")


# --------------------------------------------------------------- thin __main__


def main():
    ap = argparse.ArgumentParser(description="Operator harness for forward paper trading (7.8-S4).")
    ap.add_argument("ticker", nargs="?", help="run ONE catalyst for this ticker -> submit for approval")
    ap.add_argument("--approve", type=int, metavar="ID", help="approve a pending decision -> open")
    ap.add_argument("--reject", type=int, metavar="ID", help="reject a pending decision -> nothing")
    ap.add_argument("--mark", action="store_true", help="weekly pass: mark opens + close past exit_by")
    ap.add_argument("--dry-run", action="store_true", help="offline proof of the whole loop (no network)")
    ap.add_argument("--db", default="catalyst.db", help="catalyst.db path (default: catalyst.db)")
    args = ap.parse_args()

    if args.dry_run:
        # self-contained offline proof — an isolated in-memory ledger, never touches the real db.
        conn = _db.connect(":memory:")
        _db.migrate(conn)
        dry_run(conn)
        conn.close()
        return

    conn = _db.connect(args.db)
    _db.migrate(conn)
    try:
        if args.approve is not None:
            pos_id = paper_ledger.approve_pending(conn, args.approve)
            print(f"approved pending {args.approve} -> position {pos_id}" if pos_id
                  else f"pending {args.approve} not approvable (already resolved / absent)")
        elif args.reject is not None:
            paper_ledger.reject_pending(conn, args.reject)
            print(f"rejected pending {args.reject} — nothing opened")
        elif args.mark:
            summary = paper_ledger.mark_open_positions(
                conn, date.today().isoformat(), quotes_fn=paper_ledger._rh_quote)
            print(f"weekly mark pass: {summary}")
        elif args.ticker:
            embed = kb.default_embedder()
            as_of = date.today().isoformat()
            hook = make_catalyst_context(embed=embed, cutoff=None, quote_override=_rh_quote_override)
            result = asyncio.run(run_one_catalyst_decision(   # C5: async -> asyncio.run
                conn, embed, args.ticker, as_of=as_of, live=True, context_hook=hook))
            if result.get("reason"):
                print(f"NO DECISION      {result['reason']}")
            submit_decision(conn, result, as_of=as_of)
        else:
            ap.error("give a TICKER, or one of --approve/--reject/--mark/--dry-run")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
