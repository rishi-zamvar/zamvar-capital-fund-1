"""Workflow-1a entry point: ``run_desk`` wires the analyst desk end-to-end.

catalyst -> four concurrent, source-cited analyst signals (``asyncio.gather``, isolated
SDK sessions) -> bounded bull/bear/moderator debate -> verifier-gated binary verdict.

A thin composition over the pieces built in Plans 03-06 — the only new logic is the
wiring: build the one in-process quant/KB MCP server, fan the analysts out, thread their
signals into the debate, then gate the verdict through source-quote-or-drop before it
finalizes. Every role call still routes through the ``desk.runtime.run_structured`` seam,
so the whole pipeline runs offline under test with zero live API.

# ponytail: the components are built; run_desk just threads them. No new logic, no config
#           object, no per-dimension registry — a gather + two awaits.
"""

import asyncio

from ..contracts import DebateVerdict, PortfolioContext, StrategyDossier
from ..quant.portfolio import concentration
from . import MAX_ROUNDS, analysts, builder, debate, risk, verifier
from .portfolio import (
    Candidate,
    author_memo,
    author_pre_mortem,
    pm_decide,
    select_book,
)
from .tools import build_quant_server

DIMENSIONS = list(analysts.PROMPTS)  # clinical, regulatory, financial, market_sentiment

# The mcp__quant__* surface the analysts may call — the one "quant" server (desk.tools)
# wraps BOTH the quant and KB tools, so every allowed tool is quant-namespaced.
ALLOWED_TOOLS = [
    f"mcp__quant__{name}"
    for name in (
        "base_rate", "analog_query", "query_playbooks",
        "rnpv", "cash_runway", "implied_move", "correlation_beta",
    )
]


async def run_desk(conn, catalyst) -> DebateVerdict:
    """Run the full Workflow-1a desk for one catalyst and return the gated verdict.

    1. build the one in-process quant/KB MCP server (``conn`` captured in its closure);
    2. fan the four dimension analysts out concurrently (isolated sessions);
    3. run the bounded bull/bear/moderator debate over their signals;
    4. gate the verdict through the source-quote-or-drop verifier before returning.

    Raises ``verifier.VerdictUnsupportedError`` if no evidence survives the verifier —
    an unsupported verdict never finalizes.
    """
    srv = {"quant": build_quant_server(conn)}
    signals = await asyncio.gather(
        *[
            analysts.run_analyst(dim, catalyst, mcp_servers=srv, allowed_tools=ALLOWED_TOOLS)
            for dim in DIMENSIONS
        ]
    )
    verdict = await debate.run(signals, catalyst, rounds=MAX_ROUNDS)
    return await verifier.enforce(conn, verdict, signals=signals)


async def run_portfolio(
    conn, embed, verdicts, open_book, *,
    weekly_budget: float = 0.10, heat_cap: float = 1.0, target_weekly: float = 0.01,
) -> list[StrategyDossier]:
    """Workflow-1b entry point: turn the week's calls into ONE recommended portfolio (PORT-01).

    Each element of `verdicts` is a work item bundling the DebateVerdict with the market context the
    builder/risk desks need (the desk has no price/analog feed this phase — the caller supplies it,
    exactly as 05-06 carries `entry`):
        {"verdict": DebateVerdict, "catalyst": {...}, "entry": float,
         "risk_inputs": {"p_loss", "gap", "analog_gaps", "prices"}}

    Composition: builder.build -> risk.assess -> RECONCILE -> select_book -> memo/pre-mortem -> PM.

    RECONCILIATION (BLOCKER-1): immediately after `risk.assess` and BEFORE select_book, the Risk
    Committee's authoritative outputs OVERWRITE the builder's preliminary size/hedge —
    `proposal.model_copy(update={"size_pct": recommended_size_pct, "hedge": hedge})`. From here on
    select_book, the memo/pre-mortem, and pm_decide all read the RECONCILED proposal. `validate_hedge`
    is NOT called again here — its single result already lives on `risk.hedge` (per 05-04).

    A zero-trade week (every candidate passes/kills) is a valid success, NOT an error (PITFALLS #5).
    """
    reconciled = []
    for item in verdicts:
        verdict, catalyst = item["verdict"], item["catalyst"]
        proposal = await builder.build(conn, embed, verdict, catalyst, entry=item["entry"])
        if proposal is None:
            continue  # below-min size / rejected estimate -> no trade this leg (zero-trade allowed)

        ri = item["risk_inputs"]
        assessment = await risk.assess(
            conn, embed, proposal, catalyst,
            p_loss=ri["p_loss"], gap=ri["gap"],
            analog_gaps=ri["analog_gaps"], prices=ri["prices"],
        )
        # RECONCILE (BLOCKER-1): the Risk Committee's ruin-capped size + validated hedge win.
        proposal = proposal.model_copy(update={
            "size_pct": assessment.recommended_size_pct,
            "hedge": assessment.hedge,
        })
        reconciled.append({"verdict": verdict, "proposal": proposal, "risk": assessment})

    # SELECT toward ~1% by selection only (never resizing a leg above its survival size).
    candidates = [
        Candidate(size_pct=c["proposal"].size_pct, expected_move=c["proposal"].expected_return_pct,
                  weight=c["proposal"].size_pct, payload=c)
        for c in reconciled
    ]
    promoted, _agg = select_book(candidates, open_book, weekly_budget, heat_cap, target_weekly)
    promoted_ids = {id(c.payload) for c in promoted}
    promoted_weights = [ob["weight"] for ob in open_book] + [c.book_weight() for c in promoted]
    budget_used = sum(c.size_pct for c in promoted)
    book_conc = concentration(promoted_weights).value if promoted_weights else 0.0

    # PM promote/kill pass — memo + pre-mortem authored BEFORE and SEPARATE from the decision.
    dossiers = []
    for c in reconciled:
        proposal, assessment, verdict = c["proposal"], c["risk"], c["verdict"]
        memo = await author_memo(proposal, verdict.kill_criteria, assessment)
        pre_mortem = await author_pre_mortem(proposal, assessment)
        decision = "promote" if id(c) in promoted_ids else "kill"
        ctx = PortfolioContext(
            concentration=book_conc,
            corr_to_open_positions=[],  # ponytail: no per-position price feed until the Phase-8 ledger
            weekly_budget_remaining=max(0.0, weekly_budget - budget_used),
        )
        dossiers.append(await pm_decide(
            conn, embed, proposal, assessment, memo, pre_mortem, ctx,
            decision=decision, kill_criteria=verdict.kill_criteria, promoted_weights=promoted_weights,
        ))
    return dossiers
