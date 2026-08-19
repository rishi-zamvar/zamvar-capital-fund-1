"""desk/portfolio.py (PORT-01/04/05 + HEDGE-05 + OPS-01/02): the book selector, the PM
promote/kill pass, and the position memo + pre-mortem authored SEPARATELY from approval.

Two responsibilities, both deterministic where money is involved:
  - `select_book` aggregates the week's survivable legs toward ~1% by SELECTION ONLY — it may
    drop/reorder legs under the weekly budget + concentration heat cap, but it can NEVER resize
    a leg above its `size_for_survival` output. 1% is a book-level SELECTION outcome, never a leg
    sizing input; a zero-trade week (empty promote) is a valid success, not an error (PORT-01/04).
  - `author_memo` + `author_pre_mortem` are their OWN run_structured calls, produced BEFORE and
    SEPARATELY from `pm_decide` (author != approver, OPS-01/02). `pm_decide` (opus) reads the memo
    + pre-mortem + risk + context and emits the StrategyDossier, with residual net-long + which
    risk is covered set DETERMINISTICALLY from the RECONCILED proposal.hedge (HEDGE-05).

# ponytail: `select_book` is the ONE genuinely new bit of portfolio math — it composes the
#           existing quant.concentration/exposure constraint tools; the PM/memo/pre-mortem seam
#           mirrors builder.py (narrow LLM schema, deterministic assembly), no base classes.
"""

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from ..contracts import EstimateVetting, PortfolioContext, StrategyDossier, TradeProposal
from ..quant.portfolio import concentration, exposure
from .runtime import run_structured


# No magic literals: the sector-shock default lives here, read by DIRECT SUBSCRIPT so a missing
# key RAISES (mirrors portfolio_builder.PARAMS / quant correlations PARAMS).
BOOK_RISK_PARAMS = {"default_sector_shock": -0.10}  # XBI down-shock magnitude for the stress read


def _leg_moves(t: TradeProposal):
    """(per-name assumption dict, from_exit_plan). A catalyst leg's up/down/p come straight off the
    RECONCILED proposal's exit_plan.ev_flip (what the desk ALREADY computed); a statistical/defensive
    leg has no exit_plan, so only expected_return_pct is available and the engine defaults down_move/p."""
    if t.exit_plan is not None:
        f = t.exit_plan.ev_flip
        return {"expected_move": f.upside, "down_move": f.downside, "p_positive": f.p}, True
    return {"expected_move": t.expected_return_pct}, False


def book_to_portfolio_inputs(book, *, corr_source=None, sector_shock=None):
    """Map the assembled promoted book (list[StrategyDossier] OR list[TradeProposal]) into
    build_portfolio's (positions, assumptions). PURE: no conn, no network, no LLM.

    Per-name moves come from what the desk ALREADY computed (see `_leg_moves`). Only the TARGET legs
    are mapped as positions — the committed weekly book == the target sizes (select_book budgets
    targets, never peers), so a targets-only read IS the correct TARGET-LEG exposure/concentration.
    The hedge's diversification enters through corr_source (kb.hedge_profile: peer corr + XBI beta ->
    correlation-adjusted vol + sector-shock beta). The attached outcome is therefore a TARGET-LEG risk
    read, NOT a whole-book gross: the long/long hedge peer is real deployed capital but carries no
    size_pct/move this phase, so it is correctly excluded (fabricating peer notional would violate
    no-fabrication).

    A ticker appearing in two promoted legs (e.g. a catalyst leg + a statistical-sleeve leg on the same
    name) AGGREGATES its size_pct into ONE position — build_portfolio's weights_by_ticker dict would
    otherwise silently keep only the LAST leg and under-count exposure.

    # ponytail: no fabricated peer move distribution — the desk carries none this phase. Upgrade path
    #           needs BOTH a peer move estimate AND a peer size_pct; then add pos["hedge"] +
    #           assumptions[peer] ADDITIVELY (targets-only stays correct until both land).
    """
    trades = [d.trade if isinstance(d, StrategyDossier) else d for d in book]
    positions: list[dict] = []
    pos_by_ticker: dict[str, dict] = {}
    assumptions: dict = {}
    from_exit: dict[str, bool] = {}
    for t in trades:
        ticker = t.target_long
        moves, is_exit = _leg_moves(t)
        if ticker in pos_by_ticker:
            pos_by_ticker[ticker]["size_pct"] += t.size_pct           # aggregate duplicate legs
            if is_exit and not from_exit[ticker]:
                assumptions[ticker] = moves                           # richer exit_plan moves win
                from_exit[ticker] = True
            continue
        side = "long" if t.direction == "positive" else "short"
        pos = {"ticker": ticker, "side": side, "size_pct": t.size_pct}
        pos_by_ticker[ticker] = pos
        positions.append(pos)
        assumptions[ticker] = moves
        from_exit[ticker] = is_exit

    assumptions["sector_shock"] = (
        sector_shock if sector_shock is not None else BOOK_RISK_PARAMS["default_sector_shock"]
    )
    if corr_source is not None:
        assumptions["corr_source"] = corr_source
    return positions, assumptions


@dataclass
class Candidate:
    """A survivable leg offered to `select_book`. `size_pct` is the RECONCILED survival size
    (never resized upward); `expected_move` is the estimator EV used only for aggregation/ranking;
    `weight` is the signed book weight for the heat-cap math (defaults to +size_pct, a long);
    `payload` carries the caller's own object (e.g. the (proposal, risk) pair) through selection."""

    size_pct: float
    expected_move: float
    weight: float | None = None
    payload: object = None

    def book_weight(self) -> float:
        return self.size_pct if self.weight is None else self.weight


def select_book(candidates, open_book, weekly_budget, heat_cap, target_weekly=0.01,
                *, defensive_book=None):
    """Greedily include survivable legs (best expected_move/size first) toward ~`target_weekly`
    aggregate expected return, subject to the weekly budget + a concentration heat cap over the
    COMBINED (promoted + open) book.

    NEVER resizes a leg: legs are only included or dropped. If survivable legs cannot reach the
    target, the book stays below it (no forced upsizing).

    WEEK-03 — no zero-trade weeks: if nothing clears the bar AND a `defensive_book` (a prebuilt
    list[Candidate] of cash-like anchors) is supplied, that defensive book is deployed instead of
    an empty week. With `defensive_book=None` (default) the empty/zero-trade catalyst path is
    preserved byte-for-byte (a zero-trade week stays a valid success — PORT-01/04).

    Returns (promoted_subset, aggregate_expected_return) where aggregate = Σ(size_pct·expected_move).
    """
    open_weights = [ob["weight"] for ob in open_book]
    ranked = sorted(
        candidates,
        key=lambda c: (c.expected_move / c.size_pct) if c.size_pct else 0.0,
        reverse=True,
    )

    promoted: list[Candidate] = []
    aggregate = 0.0
    budget_used = 0.0
    for c in ranked:
        if aggregate >= target_weekly:
            break  # the book already clears ~1% by selection — never over-trade to a quota
        if budget_used + c.size_pct > weekly_budget:
            continue  # would breach the weekly budget — drop, don't shrink
        combined = open_weights + [x.book_weight() for x in promoted] + [c.book_weight()]
        if concentration(combined).value > heat_cap:
            continue  # too concentrated over the combined book — drop this leg
        promoted.append(c)
        budget_used += c.size_pct
        aggregate += c.size_pct * c.expected_move

    if not promoted and defensive_book is not None:
        # WEEK-03: no cell cleared the bar -> deploy the defensive book (cash-like anchors),
        # never an empty week. defensive_book is a prebuilt list[Candidate].
        return list(defensive_book), sum(c.size_pct * c.expected_move for c in defensive_book)
    return promoted, aggregate


def build_weekly_leg_dossier(cand, *, concentration_val, weekly_budget, budget_used,
                             promoted_weights) -> StrategyDossier:
    """Deterministically wrap a promoted single-leg statistical / defensive-cash Candidate into a
    StrategyDossier (WEEK-01). NO LLM: these legs carry no bull/bear debate — a statistical leg is a
    measured base-rate edge, a defensive leg is a cash anchor. Both are ALWAYS single-leg (hedge None,
    which_risk_covered="none" — the Phase-5 size-tiny/no-hedge fallback) and ALWAYS exit at the one-week
    horizon (holds_through_catalyst=False). The Candidate.payload carries the leg's facts.

    # ponytail: no run_structured here — spending an opus PM call on an SGOV cash anchor is waste;
    #           the catalyst PM flow is untouched, these legs are just surfaced in the book.
    """
    pl = cand.payload or {}
    ticker = pl.get("ticker", "?")
    defensive = bool(pl.get("defensive"))
    kind = "defensive" if defensive else pl.get("thesis_type", "statistical")
    label = (
        "defensive cash-like anchor (no-signal week)" if defensive
        else f"single-leg {kind} weekly leg (measured base-rate edge)"
    )
    refs = [pl["base_rate_ref"]] if pl.get("base_rate_ref") else []
    trade = TradeProposal(
        target_long=ticker,
        hedge=None,                                    # single-leg (Phase-5 no-hedge fallback)
        pair_rationale=label + " — no inverse peer",
        entry=float(pl.get("entry", 1.0)),
        exit_by_date=pl["exit_by_date"],
        stop_loss=0.0, take_profit=0.0,
        size_pct=cand.size_pct,
        expected_return_pct=cand.expected_move,
        holds_through_catalyst=False,                   # ALWAYS exit at the one-week horizon
        catalyst_id=f"weekly:{kind}:{ticker}",          # synthetic marker (no catalyst behind it)
        direction="positive",
        estimate_vetting=EstimateVetting(
            verdict="endorse", input_refs=refs,
            reasons=["weekly base-rate leg (single-leg, one-week exit)"],
        ),
        sl_advisory=True,
    )
    net = exposure(promoted_weights).detail["net"] if promoted_weights else 0.0
    ctx = PortfolioContext(
        concentration=concentration_val,
        corr_to_open_positions=[],
        weekly_budget_remaining=max(0.0, weekly_budget - budget_used),
    )
    return StrategyDossier(
        decision="promote",
        trade=trade,
        portfolio_context=ctx,
        verdict_summary=label,
        dissent_log=[],
        all_evidence_refs=refs,
        residual_net_long=net,
        which_risk_covered="none",
        position_memo=label,
        pre_mortem=["one-week horizon exit regardless of path"],
        kill_criteria=pl.get("kill_criteria") or ["exit at the one-week horizon"],
    )


# ---------------------------------------------------------------------------
# PM promote/kill pass + memo + pre-mortem (author != approver, OPS-01/02)
# ---------------------------------------------------------------------------

# Narrow LLM schemas — mirror builder.BuilderNarrative: the model authors prose only, every
# deterministic field (trade, size, hedge, residual, coverage) is assembled in code and can
# never be injected by the model.


class PositionMemo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memo: str


class PreMortem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenarios: list[str]


class PMDecision(BaseModel):
    """The ONLY fields the PM (opus) authors — the narrative. decision, trade, size, hedge,
    residual net-long, coverage, memo, pre-mortem, and kill_criteria are all set deterministically."""

    model_config = ConfigDict(extra="forbid")
    verdict_summary: str
    dissent_log: list[str] = []
    all_evidence_refs: list[str] = []


def _which_risk_covered(hedge) -> str:
    """HEDGE-05: which risk the RECONCILED hedge actually covers. Derived from validated +
    payoff_direction + instrument (NOT trusted from a `covers` string), so an unvalidated or
    None hedge can never surface as covering the idiosyncratic binary."""
    if hedge is None:
        return "none"
    if hedge.instrument == "inverse_etf":
        return "sector_beta"  # LABD covers sector beta only, never the idiosyncratic binary
    if hedge.validated and hedge.payoff_direction == -1:
        return "idiosyncratic"
    return "none"


def _memo_prompt(proposal: TradeProposal, kill_criteria, risk) -> str:
    return f"""You are authoring the POSITION MEMO for a single-leg biotech catalyst trade (you are the
AUTHOR, not the approver — a separate PM signs off later). State the thesis, entry/exit, the ADVISORY
SL/TP (a held-through stop is gap-exposed — max loss is the estimated down-move, NOT the stop distance),
which risk is covered by the hedge, and the kill criteria that would falsify the thesis.

TARGET          {proposal.target_long} (direction {proposal.direction})
ENTRY / EXIT    {proposal.entry} / {proposal.exit_by_date}
SIZE            {proposal.size_pct} (survival-sized; 1% is never a leg input)
HEDGE           {proposal.hedge.ticker if proposal.hedge else 'NONE (honest fallback)'} -> covers {_which_risk_covered(proposal.hedge)}
HELD THROUGH    {proposal.holds_through_catalyst} (SL advisory: {proposal.sl_advisory})
RESIDUAL RISKS  {'; '.join(getattr(risk, 'residual_risks', []) or [])}
KILL CRITERIA   {'; '.join(kill_criteria)}

Write `memo` as the prose position memo carrying those points.
"""


def _pre_mortem_prompt(proposal: TradeProposal, risk) -> str:
    return f"""You are running the PRE-MORTEM for a biotech catalyst trade: ASSUME THE POSITION LOST — now
enumerate WHY. Reason from the downside stress scenarios and residual risks; each scenario is a concrete
way this specific trade could have lost.

TARGET          {proposal.target_long} (direction {proposal.direction})
HEDGE           {proposal.hedge.ticker if proposal.hedge else 'NONE'} -> covers {_which_risk_covered(proposal.hedge)}
STRESS          {'; '.join(getattr(risk, 'downside_stress_scenarios', []) or [])}
RESIDUAL RISKS  {'; '.join(getattr(risk, 'residual_risks', []) or [])}

Emit `scenarios`: the list of loss post-mortems ("assume it lost — here is why").
"""


def _pm_prompt(proposal: TradeProposal, risk, memo, pre_mortem, ctx: PortfolioContext, decision: str) -> str:
    return f"""You are the PM / GP making the PROMOTE-or-KILL call over this candidate's fit in the week's
portfolio. You did NOT author the memo or pre-mortem below — you EVALUATE them. The decision has been set
to `{decision}` by the deterministic book selector (survival size + weekly budget + concentration cap);
write the narrative that justifies portfolio fit, log any dissent, and cite the evidence.

MEMO            {memo}
PRE-MORTEM      {'; '.join(pre_mortem)}
PORTFOLIO       concentration={ctx.concentration} weekly_budget_remaining={ctx.weekly_budget_remaining}
HEDGE COVERS    {_which_risk_covered(proposal.hedge)}

Emit verdict_summary + dissent_log + all_evidence_refs only.
"""


async def author_memo(proposal: TradeProposal, kill_criteria: list[str], risk) -> str:
    """OPS-01: the position memo, authored in its OWN run_structured call (separate from + before
    the PM decision). Carries kill_criteria + which risk is covered + the residual risks."""
    out = await run_structured(_memo_prompt(proposal, kill_criteria, risk), PositionMemo, model="sonnet")
    return out.memo


async def author_pre_mortem(proposal: TradeProposal, risk) -> list[str]:
    """OPS-02: the pre-mortem ("assume it lost — why"), its OWN run_structured call."""
    out = await run_structured(_pre_mortem_prompt(proposal, risk), PreMortem, model="sonnet")
    return out.scenarios


async def pm_decide(
    conn, embed, proposal: TradeProposal, risk, memo: str, pre_mortem: list[str],
    portfolio_context: PortfolioContext, *, decision: str, kill_criteria: list[str],
    promoted_weights: list[float],
) -> StrategyDossier:
    """The PM promote/kill pass (opus): reads the memo + pre-mortem + risk + portfolio context and
    emits the StrategyDossier. `decision` is fixed by the deterministic book selector (author !=
    approver — the PM authors only the narrative). residual_net_long + which_risk_covered are set
    DETERMINISTICALLY from the RECONCILED proposal.hedge and the promoted book (HEDGE-05)."""
    view = await run_structured(
        _pm_prompt(proposal, risk, memo, pre_mortem, portfolio_context, decision),
        PMDecision, model="opus",
    )
    net = exposure(promoted_weights).detail["net"] if promoted_weights else 0.0
    return StrategyDossier(
        decision=decision,
        trade=proposal,
        portfolio_context=portfolio_context,
        verdict_summary=view.verdict_summary,
        dissent_log=view.dissent_log,
        all_evidence_refs=view.all_evidence_refs,
        residual_net_long=net,
        which_risk_covered=_which_risk_covered(proposal.hedge),
        position_memo=memo,
        pre_mortem=pre_mortem,
        kill_criteria=kill_criteria,
    )
