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

from .. import kb
from ..contracts import DebateVerdict, PortfolioContext, StrategyDossier
from ..quant.portfolio import concentration
from . import MAX_ROUNDS, analysts, builder, debate, risk, verifier
from .portfolio import (
    Candidate,
    author_memo,
    author_pre_mortem,
    book_to_portfolio_inputs,
    build_weekly_leg_dossier,
    pm_decide,
    select_book,
)
from .portfolio_builder import build_portfolio
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


async def run_desk(conn, catalyst, *, extra_context: str | None = None) -> DebateVerdict:
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
    verdict = await debate.run(signals, catalyst, rounds=MAX_ROUNDS, extra_context=extra_context)
    return await verifier.enforce(conn, verdict, signals=signals)


def _cap_sleeve(stat, cap):
    """Cap the combined statistical-sleeve book-weight at `cap`, keeping the HIGHEST-efficiency legs
    (drop the lowest-efficiency until they fit) so statistical legs can never crowd out the catalyst
    engine (the moat). Efficiency = expected_move/size_pct, the same rank select_book uses."""
    ranked = sorted(stat, key=lambda c: (c.expected_move / c.size_pct) if c.size_pct else 0.0,
                    reverse=True)
    kept, used = [], 0.0
    for c in ranked:
        if used + c.book_weight() > cap:
            continue  # this leg would breach the sleeve cap — drop it (lowest-efficiency drop first)
        kept.append(c)
        used += c.book_weight()
    return kept


async def run_portfolio(
    conn, embed, verdicts, open_book, *,
    weekly_budget: float = 0.10, heat_cap: float = 1.0, target_weekly: float = 0.01,
    target_return: float | None = None, defensive_book=None, extra_candidates=None,
    statistical_sleeve_cap: float | None = None, extra_context: str | None = None,
    attach_book_risk: bool = True,
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
        # extra_context=None -> the kwarg is omitted (byte-for-byte the pre-6.7 builder call).
        build_kw = {} if extra_context is None else {"extra_context": extra_context}
        proposal = await builder.build(conn, embed, verdict, catalyst, entry=item["entry"], **build_kw)
        if proposal is None:
            continue  # below-min size / rejected estimate -> no trade this leg (zero-trade allowed)

        ri = item["risk_inputs"]
        # WEEK-04: with target_return set, size TOWARD the ~1% target within the survival cap and thread
        # expected_move=proposal.expected_return_pct (the blended net EV) — DELIBERATE per plan (matches
        # the Candidate.expected_move semantics select_book aggregates on; NOT research's raw up_move).
        # target_return=None -> the kwargs are omitted entirely (byte-for-byte the Phase-5 catalyst path).
        assess_kw = {} if target_return is None else {
            "target_return": target_return,
            "expected_move": proposal.expected_return_pct,
        }
        assessment = await risk.assess(
            conn, embed, proposal, catalyst,
            p_loss=ri["p_loss"], gap=ri["gap"],
            analog_gaps=ri["analog_gaps"], prices=ri["prices"], **assess_kw,
        )
        # RECONCILE (BLOCKER-1): the Risk Committee's ruin-capped size + validated hedge win.
        proposal = proposal.model_copy(update={
            "size_pct": assessment.recommended_size_pct,
            "hedge": assessment.hedge,
        })
        reconciled.append({"verdict": verdict, "proposal": proposal, "risk": assessment})

    # SELECT toward ~1% by selection only (never resizing a leg above its survival size).
    catalyst_candidates = [
        Candidate(size_pct=c["proposal"].size_pct, expected_move=c["proposal"].expected_return_pct,
                  weight=c["proposal"].size_pct, payload=c)
        for c in reconciled
    ]
    # WEEK-01: single-leg statistical Candidates ride the SAME select_book pass (shared budget + heat).
    # Sleeve cap (research §4.5 knob #4): ONLY in a catalyst week, cap the combined statistical book-weight
    # at statistical_sleeve_cap * weekly_budget so the statistical sleeve never crowds out the catalyst
    # engine. A pure-statistical week (no catalyst candidates) is NOT capped — the cap must never starve it.
    stat = list(extra_candidates or [])
    if statistical_sleeve_cap is not None and catalyst_candidates and stat:
        stat = _cap_sleeve(stat, statistical_sleeve_cap * weekly_budget)
    candidates = catalyst_candidates + stat
    promoted, _agg = select_book(candidates, open_book, weekly_budget, heat_cap, target_weekly,
                                 defensive_book=defensive_book)
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

    # WEEK-01: promoted single-leg statistical + defensive-cash legs (payload is a bare thesis/defensive
    # dict, NOT a reconciled {verdict,proposal,risk} item) are surfaced deterministically — no LLM.
    for cand in promoted:
        pl = cand.payload
        if isinstance(pl, dict) and "proposal" not in pl:
            dossiers.append(build_weekly_leg_dossier(
                cand, concentration_val=book_conc, weekly_budget=weekly_budget,
                budget_used=budget_used, promoted_weights=promoted_weights,
            ))

    # WHOLE-BOOK RISK READ (7.8-pf2): run build_portfolio ONCE over the promoted book and hang the
    # resulting PortfolioOutcome on each promoted dossier's portfolio_context. This is a READ appended
    # AFTER select_book + every pm_decide/build_weekly_leg_dossier call, so the money path (selection
    # + sizing) is byte-for-byte unchanged — the outcome never resizes or reorders a leg.
    if attach_book_risk:
        promoted_dossiers = [d for d in dossiers if d.decision == "promote"]
        if promoted_dossiers:
            # corr_source mirrors the MCP tool (tools.py) — kb.hedge_profile bound to conn. With
            # conn=None (offline callers) bind None instead so the engine falls back to idiosyncratic
            # correlation; kb.hedge_profile(None, t) would AttributeError on None.execute(...).
            corr_source = (lambda t: kb.hedge_profile(conn, t)) if conn is not None else None
            positions, assumptions = book_to_portfolio_inputs(
                promoted_dossiers, corr_source=corr_source)
            outcome = build_portfolio(positions, assumptions).model_dump()
            for d in promoted_dossiers:
                d.portfolio_context = d.portfolio_context.model_copy(
                    update={"portfolio_outcome": outcome})
    return dossiers
