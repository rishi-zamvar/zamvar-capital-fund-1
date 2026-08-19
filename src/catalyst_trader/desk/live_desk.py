"""desk/live_desk.py (7.8-S2) — run_one_catalyst_decision: the catalyst -> MDDecision chain.

Wires the ORPHANED independent diligence + MD reconciliation loop onto the Slice-1 dossier. `md.reconcile`
+ `run_diligence` were built + unit-tested but called from nowhere outside tests; this is the end-to-end
desk function that chains them, so one real catalyst produces an approvable go/no-go DECISION (an
MDDecision: enter/pass/escalate + round log), not just a StrategyDossier.

    _catalyst_dict -> run_desk -> catalyst_context -> run_portfolio
      -> IF promoted: make_diligence_inputs -> run_diligence -> reconcile item -> md.reconcile -> MDDecision
      -> ELSE (zero-trade): an honest no-DD/no-MD pass (a CORRECT outcome, not an error).

Every LLM seam is a function param (mirrors Slice-1 run_one's run_desk_fn/context_hook/run_portfolio_fn),
so the whole path is offline-testable; the live path is the only network + LLM and is operator-gated.

# ponytail: a linear chain + one promoted/zero-trade branch + item assembly. No orchestration class,
#           no new selection/sizing/DD/MD math — it only CALLS the shipped desk functions and routes.
"""

from __future__ import annotations

from .. import serving
from .catalyst_context import make_catalyst_context
from .diligence import run_diligence
from .diligence_inputs import make_diligence_inputs
from .md import reconcile
from .orchestrator import run_desk, run_portfolio
from .weekly import _catalyst_dict


def _no_trade(cat, verdict, reason, degraded=None) -> dict:
    """The honest no-decision result (no catalyst / no entry / nothing promoted) — a valid outcome."""
    return {"catalyst": cat, "verdict": verdict, "dossier": None, "dd": None, "decision": None,
            "rounds": [], "degraded_flags": degraded or [], "reason": reason}


async def run_one_catalyst_decision(
    conn, embed, ticker, *, as_of, live=False,
    run_desk_fn=run_desk, context_hook=None, run_portfolio_fn=run_portfolio,
    dd_inputs_fn=None, run_diligence_fn=run_diligence, reconcile_fn=reconcile, open_book=None,
) -> dict:
    """Run ONE catalyst for `ticker` through the desk to a reconciled MDDecision.

    Returns a result dict: {catalyst, verdict, dossier, dd, decision, rounds, degraded_flags, reason}.
    On the zero-trade / no-catalyst / no-entry paths, dd/decision are None and `reason` explains it —
    an honest pass, never an exception. cutoff = now (live) or the knowable point-in-time = as_of.
    """
    cutoff = None if live else as_of
    book = serving.asof(conn) if live else serving.asof(conn, cutoff)

    cat = _catalyst_dict(book, ticker, as_of)              # reuse weekly's knowability-gated picker
    if cat is None:
        return _no_trade(None, None, f"no upcoming catalyst for {ticker} in ({as_of}, +7d]")

    hook = context_hook or make_catalyst_context(embed=embed, cutoff=cutoff)
    verdict = await run_desk_fn(conn, cat)
    mc = await hook(conn, ticker, cat, as_of)
    entry = mc["entry"]
    risk_inputs = mc.get("risk_inputs", {})
    if entry is None:
        return _no_trade(cat, verdict, f"no entry price for {ticker} — leg skipped (honest degrade)")

    dossiers = await run_portfolio_fn(conn, embed, [{"verdict": verdict, "catalyst": cat, **mc}],
                                      open_book or [])
    dossier = dossiers[0] if dossiers else None
    if dossier is None or dossier.decision != "promote":
        # zero-trade: negative/no-promote is a CORRECT outcome (Slice-1 proved CAPR was rightly no-trade).
        return _no_trade(cat, verdict, "no trade promoted (zero-trade week is a valid outcome)")

    # --- promoted: build the DD inputs, run the sealed diligence, reconcile to an MDDecision ---
    build_inputs = dd_inputs_fn or make_diligence_inputs()
    pair = dossier.trade.hedge.ticker if dossier.trade.hedge else None   # single-leg -> None (Slice-1)
    dd_input, market_data, degraded = build_inputs(
        conn, ticker, cat, entry=entry, risk_inputs=risk_inputs,
        exit_by_date=dossier.trade.exit_by_date, pair=pair, as_of=as_of,
    )
    dd = await run_diligence_fn(conn, dd_input, market_data=market_data, embed=embed)

    item = {
        "verdict": verdict, "dossier": dossier, "dd": dd, "catalyst": cat,
        "dd_input": dd_input, "market_data": market_data, "open_book": open_book or [],
        "entry": entry, "risk_inputs": risk_inputs, "incoming_flags": [],
    }
    decision = await reconcile_fn(conn, embed, item)
    return {"catalyst": cat, "verdict": verdict, "dossier": dossier, "dd": dd,
            "decision": decision, "rounds": decision.round_log, "degraded_flags": degraded,
            "reason": None}
