"""MOCK-SCENARIO DEMO — run the REAL agents on a controlled bullish scenario, full visibility.

Constructs a near-term catalyst on a real, data-rich ticker (ARWR: $69M cash, cached bars, dense KB
analogs) and runs the FULL live pipeline with every stage printed:
  4 analyst signals -> bull/bear debate -> verdict -> builder dossier -> (if promoted) 8-dim DD -> MD.
Agents decide HONESTLY (DD is adversarial; may still NO-GO). This is a demonstration, not a trade.
"""
import asyncio, json
from datetime import date, timedelta
from catalyst_trader import db, kb
from catalyst_trader.desk import analysts, debate, verifier
from catalyst_trader.desk.orchestrator import build_quant_server, ALLOWED_TOOLS, DIMENSIONS, run_portfolio
from catalyst_trader.desk.catalyst_context import make_catalyst_context
from catalyst_trader.desk.diligence_inputs import make_diligence_inputs
from catalyst_trader.desk.diligence import run_diligence
from catalyst_trader.desk.md import reconcile

TICKER = "ARWR"
AS_OF = date.today().isoformat()
EVENT = (date.today() + timedelta(days=3)).isoformat()
CAT = {"ticker": TICKER, "catalyst_type": "trial_readout", "event_date": EVENT,
       "catalyst_id": f"{TICKER}:{EVENT}"}


def line(c="="): print(c * 78)


async def main():
    conn = db.connect("catalyst.db"); db.migrate(conn)
    embed = kb.default_embedder()
    line(); print(f"MOCK SCENARIO — {TICKER} trial_readout, event {EVENT} (as_of {AS_OF})"); line()

    # 1. the four dimension analysts (each cites quant/KB tools, cite-or-drop)
    srv = {"quant": build_quant_server(conn)}
    signals = await asyncio.gather(*[
        analysts.run_analyst(dim, CAT, mcp_servers=srv, allowed_tools=ALLOWED_TOOLS) for dim in DIMENSIONS
    ])
    print("\n--- ANALYST SIGNALS ---")
    for dim, s in zip(DIMENSIONS, signals):
        d = s.model_dump()
        print(f"[{dim}] " + json.dumps({k: d.get(k) for k in list(d)[:6]}, default=str)[:600])

    # 2. bull/bear/moderator debate -> gated verdict
    verdict = await debate.run(signals, CAT, rounds=2)
    verdict = await verifier.enforce(conn, verdict, signals=signals)
    print("\n--- DEBATE VERDICT ---")
    print(f"direction={verdict.direction}  confidence={verdict.confidence}")
    print(f"thesis: {verdict.thesis}")
    print(f"bull:   {verdict.bull_strongest_point}")
    print(f"bear:   {verdict.bear_strongest_point}")
    print(f"kill:   {verdict.kill_criteria}")

    # 3. market context + builder -> dossier
    hook = make_catalyst_context(embed=embed, cutoff=None)
    mc = await hook(conn, TICKER, CAT, AS_OF)
    print(f"\n--- CONTEXT ---  entry={mc['entry']}  risk_inputs={mc.get('risk_inputs')}")
    if mc["entry"] is None:
        print("no entry price — stop."); return
    dossiers = await run_portfolio(conn, embed, [{"verdict": verdict, "catalyst": CAT, **mc}], [])
    dossier = dossiers[0] if dossiers else None
    if not dossier or dossier.decision != "promote":
        print("\n--- BUILDER ---  NO TRADE PROMOTED (honest zero-trade; agents declined).")
        return
    t = dossier.trade
    print(f"\n--- DOSSIER (promoted) ---  {t.direction} {t.target_long}  size={t.size_pct:.4f} entry={t.entry} "
          f"hedge={t.hedge.ticker if t.hedge else 'None'}  exit_by={t.exit_by_date}")
    print(f"  rationale: {t.pair_rationale}")

    # 4. independent diligence (8 dims) + MD reconciliation
    dd_input, market_data, degraded = make_diligence_inputs()(
        conn, TICKER, CAT, entry=t.entry, risk_inputs=mc["risk_inputs"],
        exit_by_date=t.exit_by_date, pair=(t.hedge.ticker if t.hedge else None), as_of=AS_OF)
    dd = await run_diligence(conn, dd_input, market_data=market_data, embed=embed)
    print(f"\n--- DILIGENCE (independent firewall) ---  verdict={dd.verdict}")
    for dm in dd.per_dimension:
        print(f"  {dm.get('dimension')}: passed={dm.get('passed')} score={dm.get('score')}")
    print(f"  red_flags: {dd.red_flags}")
    if degraded: print(f"  degraded: {degraded}")
    item = {"verdict": verdict, "dossier": dossier, "dd": dd, "catalyst": CAT, "dd_input": dd_input,
            "market_data": market_data, "open_book": [], "entry": t.entry,
            "risk_inputs": mc["risk_inputs"], "incoming_flags": []}
    decision = await reconcile(conn, embed, item)
    print(f"\n--- MD DECISION ---  {decision.decision}")
    print(f"  rationale: {decision.rationale}")
    print(f"  rounds: {len(decision.round_log)}")
    line()


asyncio.run(main())
