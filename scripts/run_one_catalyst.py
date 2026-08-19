"""scripts/run_one_catalyst.py (7.8-S1) — the one-catalyst live-run harness (walking skeleton).

Runs ONE real biotech catalyst through the LIVE agentic desk end-to-end and prints a hand-checkable
StrategyDossier:

    run_desk(conn, cat)                       -- the four-analyst debate -> gated verdict
      -> catalyst_context(conn, ticker, ...)  -- the point-in-time {entry, risk_inputs} feed (7.8-S1)
      -> run_portfolio(...)                   -- builder -> risk -> reconcile -> select -> PM
      -> StrategyDossier(s)                   -- direction / size / hedge / rationale / portfolio_outcome

``run_one`` is the TESTABLE core (every live dependency is injectable); the thin ``__main__``:
  --dry-run  (default): inject a fake run_desk + fake context + fake run_portfolio -> pure-offline
             wiring proof, NO LLM / network (C1: run_portfolio itself fires live LLM inside risk.assess,
             so it MUST be injected to be genuinely offline).
  --live:    real run_desk + real make_catalyst_context + optional RH real-time entry override —
             operator-gated (a real LLM run inside a Claude Code session, ANTHROPIC_API_KEY unset).

DD/MD are DEFERRED to Slice 2. This is glue — one work-item through the shipped desk, no new
selection/sizing math.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date

from catalyst_trader import db as _db
from catalyst_trader import kb, serving
from catalyst_trader.desk.catalyst_context import make_catalyst_context
from catalyst_trader.desk.orchestrator import run_desk, run_portfolio
from catalyst_trader.desk.weekly import _catalyst_dict
from catalyst_trader.providers import robinhood


def _print_dossiers(dossiers) -> None:
    if not dossiers:
        print("run_portfolio returned an EMPTY book (zero-trade week is a valid outcome).")
        return
    for d in dossiers:
        t = d.trade
        po = d.portfolio_context.portfolio_outcome
        print("=" * 72)
        print(f"DECISION         {d.decision}  ({t.target_long})")
        print(f"DIRECTION        {t.direction}")
        print(f"SIZE_PCT         {t.size_pct:.4f}   (survival-capped)")
        print(f"ENTRY            {t.entry}")
        print(f"HEDGE            {t.hedge.ticker if t.hedge else 'None (honest single-leg)'}")
        print(f"WHICH_RISK       {d.which_risk_covered}")
        print(f"RESIDUAL_NET     {d.residual_net_long:.4f}")
        print(f"PAIR_RATIONALE   {t.pair_rationale}")
        print(f"VERDICT_SUMMARY  {d.verdict_summary}")
        print(f"PORTFOLIO_OUTCOME {po}")
    print("=" * 72)


def _rh_quote_override(ticker):
    """The --live real-time entry override: RH get_equity_quotes last, or None (degrades to close).
    mcp_call is None here (no broker MCP wired into this harness), so it degrades to None by design —
    the cache-first close carries the entry. Frugal: the only network is the operator-gated live run."""
    quotes = robinhood.quotes_rt([ticker])
    return (quotes or {}).get(ticker, {}).get("last")


async def run_one(conn, embed, ticker, *, live, run_desk_fn=run_desk, context_hook=None,
                  run_portfolio_fn=run_portfolio):
    """Run ONE catalyst for `ticker` through the desk and print/return the StrategyDossier book.

    Returns the dossier list, or None on an honest skip (no upcoming catalyst / no entry price).
    cutoff = now (live) or the catalyst's knowable point-in-time = as_of (backtest pick).
    """
    as_of = date.today().isoformat()
    cutoff = None if live else as_of          # live = now; backtest pick = knowable at as_of
    book = serving.asof(conn) if live else serving.asof(conn, cutoff)

    cat = _catalyst_dict(book, ticker, as_of)   # reuse weekly's knowability-gated picker (no dup)
    if cat is None:
        print(f"no upcoming catalyst for {ticker} in ({as_of}, +7d] — nothing to run.")
        return None

    hook = context_hook or make_catalyst_context(
        embed=embed, cutoff=cutoff,
        quote_override=(_rh_quote_override if live else None),
    )

    verdict = await run_desk_fn(conn, cat)
    mc = await hook(conn, ticker, cat, as_of)
    if mc["entry"] is None:
        print(f"no entry price for {ticker} — leg skipped (honest degrade, no fabricated fill).")
        return None

    dossiers = await run_portfolio_fn(
        conn, embed, [{"verdict": verdict, "catalyst": cat, **mc}], open_book=[],
    )
    _print_dossiers(dossiers)
    return dossiers


def _fake_desk_and_context():
    """The --dry-run offline seam: a canned verdict + context + a canned dossier from run_portfolio,
    so the wiring runs with ZERO live LLM / network (C1 — run_portfolio would otherwise fire LLM)."""
    from catalyst_trader.contracts import (
        DebateVerdict,
        EstimateVetting,
        PortfolioContext,
        StrategyDossier,
        TradeProposal,
    )

    kill = ["a Complete Response Letter is issued"]

    async def _desk(conn, catalyst):
        return DebateVerdict(thesis="DRY-RUN thesis", direction="positive", confidence=0.6,
                             bull_strongest_point="dry", bear_strongest_point="run", kill_criteria=kill)

    async def _context(conn, ticker, catalyst, as_of):
        return {"entry": 100.0, "risk_inputs": {"p_loss": 0.4, "gap": 0.15, "analog_gaps": {},
                                                "prices": {"target": [1.0], "peer": []}}}

    async def _portfolio(conn, embed, verdicts, open_book):
        v = verdicts[0]
        trade = TradeProposal(
            target_long=v["catalyst"]["ticker"], hedge=None,
            pair_rationale="DRY-RUN canned single-leg", entry=v["entry"], exit_by_date="dry",
            stop_loss=45.0, take_profit=120.0, size_pct=0.02, expected_return_pct=0.2,
            holds_through_catalyst=True, catalyst_id=v["catalyst"]["catalyst_id"], direction="positive",
            estimate_vetting=EstimateVetting(verdict="endorse", input_refs=["tool:x#1"], reasons=["dry"]),
            sl_advisory=True,
        )
        return [StrategyDossier(
            decision="promote", trade=trade,
            portfolio_context=PortfolioContext(concentration=0.0, corr_to_open_positions=[],
                                               weekly_budget_remaining=0.08,
                                               portfolio_outcome={"note": "dry-run canned"}),
            verdict_summary="DRY-RUN wiring proof", residual_net_long=0.02, which_risk_covered="none",
            position_memo="dry", pre_mortem=["dry-run"], kill_criteria=kill)]

    return _desk, _context, _portfolio


def main():
    ap = argparse.ArgumentParser(description="Run ONE catalyst through the live desk (7.8-S1).")
    ap.add_argument("ticker")
    ap.add_argument("--live", action="store_true",
                    help="real run_desk + real hook (operator-gated LLM run). Default = --dry-run.")
    ap.add_argument("--db", default="catalyst.db", help="catalyst.db path (default: catalyst.db)")
    args = ap.parse_args()

    conn = _db.connect(args.db)
    _db.migrate(conn)
    try:
        if args.live:
            embed = kb.default_embedder()
            asyncio.run(run_one(conn, embed, args.ticker, live=True))
        else:
            desk, context, portfolio = _fake_desk_and_context()
            asyncio.run(run_one(conn, None, args.ticker, live=False, run_desk_fn=desk,
                                context_hook=context, run_portfolio_fn=portfolio))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
