"""Portfolio layer (PORT-01/04/05 + HEDGE-05 + OPS-01/02): the book selector, the PM
promote/kill pass (memo + pre-mortem authored SEPARATELY from approval), and the
run_portfolio composition that reconciles the Risk Committee's authoritative outputs onto
each proposal BEFORE selection (BLOCKER-1).

Money-critical invariants under test:
  - select_book aggregates toward ~1% by SELECTION ONLY — it drops/reorders legs but NEVER
    resizes a leg above its size_for_survival output (1% is book-level, never a leg input);
    a zero-trade week (empty promote) is a valid success, not an error.
  - the position memo + pre-mortem are authored in run_structured calls SEPARATE from and
    BEFORE the PM decision call (author != approver, OPS-01/02).
  - the dossier states residual net-long (gross >= |net|) and which risk is covered, derived
    from the RECONCILED proposal.hedge (an unvalidated/None hedge can never report idiosyncratic).
  - run_portfolio reconciles risk.recommended_size_pct + risk.hedge onto the proposal BEFORE
    select_book — the builder's preliminary size/hedge are never what gets promoted (BLOCKER-1).

Quant + KB run FOR REAL (deterministic); run_structured is monkeypatched -> fully offline.
"""

import pytest

from catalyst_trader.desk import portfolio
from catalyst_trader.desk.portfolio import Candidate, select_book
from catalyst_trader.quant.portfolio import concentration


# ---------------------------------------------------------------------------
# Task 1 — select_book (aggregate to ~1% by selection; never resize above survival)
# ---------------------------------------------------------------------------


def _cand(size_pct, expected_move, weight=None):
    return Candidate(size_pct=size_pct, expected_move=expected_move, weight=weight,
                     payload=(size_pct, expected_move))


def test_select_book_aggregates_toward_one_pct():
    # three efficient legs; the selector adds them until the ~1% aggregate is reached.
    cands = [_cand(0.03, 0.25), _cand(0.03, 0.25), _cand(0.03, 0.25)]
    promoted, agg = select_book(cands, open_book=[], weekly_budget=1.0, heat_cap=1.0)
    assert agg >= 0.01                       # reached the ~1% book target by selection
    assert 0 < len(promoted) <= len(cands)   # picked a subset, did not need all/none
    assert agg == pytest.approx(sum(c.size_pct * c.expected_move for c in promoted))


def test_select_book_never_resizes_above_survival_size():
    # STRUCTURAL: every promoted leg's size_pct is EXACTLY its input survival size — never larger.
    cands = [_cand(0.03, 0.40), _cand(0.02, 0.30)]
    inputs = {id(c): c.size_pct for c in cands}
    promoted, _ = select_book(cands, open_book=[], weekly_budget=1.0, heat_cap=1.0)
    for c in promoted:
        assert c.size_pct == inputs[id(c)]   # unchanged — selection only, no upsizing


def test_select_book_ranks_by_efficiency_first():
    lo = _cand(0.03, 0.05)   # low expected_move / size
    hi = _cand(0.03, 0.60)   # high expected_move / size
    promoted, _ = select_book([lo, hi], open_book=[], weekly_budget=1.0, heat_cap=1.0)
    assert promoted[0] is hi   # the most efficient leg is selected first


def test_select_book_respects_weekly_budget():
    cands = [_cand(0.03, 0.05), _cand(0.03, 0.05)]  # inefficient so target never short-circuits
    promoted, _ = select_book(cands, open_book=[], weekly_budget=0.03, heat_cap=1.0)
    assert sum(c.size_pct for c in promoted) <= 0.03  # budget cap honored -> only one fits


def test_select_book_heat_cap_drops_a_leg():
    # two big single-name weights; the heat cap (Herfindahl) refuses the second.
    cands = [_cand(0.5, 0.30), _cand(0.5, 0.30)]
    promoted, _ = select_book(cands, open_book=[], weekly_budget=1.0, heat_cap=0.3)
    assert len(promoted) == 1                        # [0.5] Herfindahl 0.25 ok; [0.5,0.5] 0.5 > cap
    assert concentration([c.book_weight() for c in promoted]).value <= 0.3


# INVERTED in Phase 6.5 (WEEK-03): no zero-trade weeks. When nothing clears the bar AND a
# defensive_book is supplied, the week is a DEFENSIVE book, not empty. (was
# test_select_book_zero_trade_when_nothing_clears_budget + test_select_book_empty_candidates_is_zero_trade
# — both original zero-trade scenarios preserved below as parametrized cases.)
@pytest.mark.parametrize("candidates,weekly_budget", [
    ([], 1.0),                       # (a) empty candidates -> nothing to promote
    ([_cand(0.03, 0.20)], 0.0),      # (b) candidates present but zero budget -> nothing clears
])
def test_select_book_no_signal_yields_defensive_book(candidates, weekly_budget):
    defensive = [_cand(0.01, 0.02), _cand(0.01, 0.02)]  # cash-like anchors (SGOV/BIL-style)
    promoted, agg = select_book(candidates, open_book=[], weekly_budget=weekly_budget,
                                heat_cap=1.0, defensive_book=defensive)
    assert promoted == defensive     # the defensive book is deployed, never an empty week
    assert agg == pytest.approx(sum(c.size_pct * c.expected_move for c in defensive))


def test_select_book_no_signal_defensive_none_stays_zero_trade():
    """Catalyst path preserved: defensive_book=None (default) keeps the empty/zero-trade week."""
    assert select_book([], open_book=[], weekly_budget=1.0, heat_cap=1.0) == ([], 0.0)
    promoted, agg = select_book([_cand(0.03, 0.20)], open_book=[], weekly_budget=0.0, heat_cap=1.0)
    assert promoted == [] and agg == 0.0


def test_select_book_heat_cap_uses_combined_book_with_open_positions():
    # an already-heavy open book pushes the combined Herfindahl over the cap -> nothing new fits.
    cands = [_cand(0.5, 0.30)]
    promoted, _ = select_book(cands, open_book=[{"ticker": "OPEN", "weight": 0.9, "catalyst_id": "c0"}],
                              weekly_budget=1.0, heat_cap=0.5)
    assert promoted == []   # [0.9, 0.5] Herfindahl 1.06 > 0.5 -> the candidate is dropped


# ---------------------------------------------------------------------------
# Task 2 — PM pass + memo + pre-mortem (author != approver) -> StrategyDossier
# ---------------------------------------------------------------------------

from catalyst_trader.contracts import (
    EstimateVetting,
    Hedge,
    PortfolioContext,
    RiskAssessment,
    StrategyDossier,
    TradeProposal,
)
from catalyst_trader.desk.portfolio import (
    PMDecision,
    PositionMemo,
    PreMortem,
    author_memo,
    author_pre_mortem,
    pm_decide,
)

_KILL = ["a Complete Response Letter is issued", "label carve-out on the lead indication"]


def _hedge(instrument="equity_peer", validated=True, payoff=-1, covers="idiosyncratic"):
    return Hedge(instrument=instrument, ticker="RIVAL", payoff_direction=payoff,
                 validated=validated, covers=covers, mechanism="same-indication competitor",
                 conditional_worst=-0.35)


def _proposal(hedge=None, size_pct=0.02):
    return TradeProposal(
        target_long="ACME", hedge=hedge, pair_rationale="long ACME, RIVAL inverse hedge",
        entry=100.0, exit_by_date="2026-11-22", stop_loss=45.0, take_profit=120.0,
        size_pct=size_pct, expected_return_pct=0.25, kb_analogs=["n1"],
        holds_through_catalyst=True, catalyst_id="cat-1", direction="positive",
        estimate_vetting=EstimateVetting(verdict="endorse", input_refs=["tool:x#1"], reasons=["ok"]),
        sl_advisory=True,
    )


def _risk(load_fixture, hedge=None):
    base = RiskAssessment.model_validate(load_fixture("agent_responses/risk_synthesis"))
    return base.model_copy(update={"recommended_size_pct": 0.02, "hedge": hedge,
                                   "hedge_valid": hedge is not None and hedge.validated})


def _pctx():
    return PortfolioContext(concentration=0.25, corr_to_open_positions=[], weekly_budget_remaining=0.08)


def _pm_seam(calls):
    """Fake run_structured for the portfolio module: record every call, dispatch by schema."""
    memo = PositionMemo(memo="LLM memo body")
    pre = PreMortem(scenarios=["it lost because the CRL hit", "sector read-through sank both"])
    decision = PMDecision(verdict_summary="promote it", dissent_log=["hedge fragility"],
                          all_evidence_refs=["tool:size_for_survival#a"])

    async def _fake(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"):
        calls.append({"prompt": prompt, "schema": schema, "model": model})
        if schema is PositionMemo:
            return memo
        if schema is PreMortem:
            return pre
        if schema is PMDecision:
            return decision
        raise AssertionError(f"unexpected schema {schema!r}")

    return _fake


async def test_memo_and_premortem_authored_separately_from_pm(monkeypatch, load_fixture):
    calls = []
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam(calls))
    prop, risk = _proposal(_hedge()), _risk(load_fixture, _hedge())

    await author_memo(prop, _KILL, risk)
    await author_pre_mortem(prop, risk)
    await pm_decide(None, None, prop, risk, "memo", ["s1"], _pctx(),
                    decision="promote", kill_criteria=_KILL, promoted_weights=[0.02])

    schemas = [c["schema"] for c in calls]
    assert schemas == [PositionMemo, PreMortem, PMDecision]   # separate calls, memo+pre-mortem FIRST
    pm_idx = schemas.index(PMDecision)
    assert schemas.index(PositionMemo) < pm_idx and schemas.index(PreMortem) < pm_idx  # author != approver
    assert calls[pm_idx]["model"] == "opus"   # the PM decision is the opus call


async def test_author_memo_returns_the_llm_memo_string(monkeypatch, load_fixture):
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam([]))
    out = await author_memo(_proposal(_hedge()), _KILL, _risk(load_fixture, _hedge()))
    assert out == "LLM memo body"


async def test_author_pre_mortem_returns_scenarios_list(monkeypatch, load_fixture):
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam([]))
    out = await author_pre_mortem(_proposal(_hedge()), _risk(load_fixture, _hedge()))
    assert out == ["it lost because the CRL hit", "sector read-through sank both"]


async def test_residual_net_long_is_exposure_net_and_gross_ge_abs_net(monkeypatch, load_fixture):
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam([]))
    weights = [0.02, 0.03]
    dossier = await pm_decide(None, None, _proposal(_hedge()), _risk(load_fixture, _hedge()),
                              "memo", ["s1"], _pctx(), decision="promote",
                              kill_criteria=_KILL, promoted_weights=weights)
    from catalyst_trader.quant.portfolio import exposure
    exp = exposure(weights)
    assert dossier.residual_net_long == exp.detail["net"]        # HEDGE-05 wiring
    assert exp.value >= abs(dossier.residual_net_long)           # gross >= |net| (Pitfall C, never netted away)


async def test_which_risk_covered_idiosyncratic_from_validated_inverse(monkeypatch, load_fixture):
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam([]))
    dossier = await pm_decide(None, None, _proposal(_hedge()), _risk(load_fixture, _hedge()),
                              "m", ["s"], _pctx(), decision="promote",
                              kill_criteria=_KILL, promoted_weights=[0.02])
    assert dossier.which_risk_covered == "idiosyncratic"


async def test_which_risk_covered_sector_beta_from_inverse_etf(monkeypatch, load_fixture):
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam([]))
    labd = _hedge(instrument="inverse_etf", covers="sector_beta")
    dossier = await pm_decide(None, None, _proposal(labd), _risk(load_fixture, labd),
                              "m", ["s"], _pctx(), decision="promote",
                              kill_criteria=_KILL, promoted_weights=[0.02])
    assert dossier.which_risk_covered == "sector_beta"


async def test_which_risk_covered_none_when_no_hedge(monkeypatch, load_fixture):
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam([]))
    dossier = await pm_decide(None, None, _proposal(None), _risk(load_fixture, None),
                              "m", ["s"], _pctx(), decision="kill",
                              kill_criteria=_KILL, promoted_weights=[])
    assert dossier.which_risk_covered == "none"      # honest fallback: no hedge covers nothing


async def test_dossier_kill_criteria_carried_and_non_empty(monkeypatch, load_fixture):
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam([]))
    dossier = await pm_decide(None, None, _proposal(_hedge()), _risk(load_fixture, _hedge()),
                              "the memo body", ["scenario a"], _pctx(), decision="promote",
                              kill_criteria=_KILL, promoted_weights=[0.02])
    assert dossier.kill_criteria == _KILL and dossier.kill_criteria     # non-empty (contract-enforced)
    assert dossier.position_memo == "the memo body"                     # the authored memo is read in
    assert dossier.pre_mortem == ["scenario a"]                         # the pre-mortem is read in
    assert isinstance(dossier, StrategyDossier) and dossier.trade is not None


# ---------------------------------------------------------------------------
# Task 3 — run_portfolio (builder -> risk -> RECONCILE -> select_book -> PM) + zero-trade
# ---------------------------------------------------------------------------

from catalyst_trader.contracts import DebateVerdict
from catalyst_trader.desk import builder, orchestrator, risk


def _verdict():
    return DebateVerdict(thesis="ACME PDUFA likely approves", direction="positive", confidence=0.6,
                         bull_strongest_point="endpoint met", bear_strongest_point="cash tight",
                         kill_criteria=_KILL)


def _item(entry=100.0):
    return {
        "verdict": _verdict(),
        "catalyst": {"ticker": "ACME", "event_date": "2026-11-15", "catalyst_id": "cat-1",
                     "event_date_end": "2026-11-22", "catalyst_type": "pdufa"},
        "entry": entry,
        "risk_inputs": {"p_loss": 0.4, "gap": 0.55, "analog_gaps": {}, "prices": {}},
    }


def _patch_build_assess(monkeypatch, *, prelim_size, risk_obj):
    """Canned builder.build (preliminary size, hedge None) + risk.assess (authoritative outputs).
    Isolates run_portfolio's RECONCILE -> select -> PM composition (build/assess are tested in 05-06/04)."""
    async def _b(conn, embed, verdict, catalyst, *, entry):
        return _proposal(hedge=None, size_pct=prelim_size)   # builder: PRELIMINARY size, hedge None

    async def _a(conn, embed, proposal, catalyst, *, p_loss, gap, analog_gaps, prices):
        return risk_obj

    monkeypatch.setattr(builder, "build", _b)
    monkeypatch.setattr(risk, "assess", _a)


async def test_run_portfolio_reconciles_risk_size_not_builder_preliminary(monkeypatch, load_fixture):
    # BLOCKER-1: the builder's preliminary 0.005 is OVERWRITTEN by risk.recommended_size_pct (0.02).
    risk_obj = _risk(load_fixture, _hedge())   # recommended_size_pct 0.02
    _patch_build_assess(monkeypatch, prelim_size=0.005, risk_obj=risk_obj)
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam([]))

    dossiers = await orchestrator.run_portfolio(None, None, [_item()], open_book=[])
    promoted = [d for d in dossiers if d.decision == "promote"]
    assert promoted, "the survivable leg should promote"
    assert promoted[0].trade.size_pct == 0.02      # the Risk Committee's ruin-capped size
    assert promoted[0].trade.size_pct != 0.005     # NOT the builder's preliminary estimate


async def test_run_portfolio_reconciles_validated_hedge_surfaces_idiosyncratic(monkeypatch, load_fixture):
    h = _hedge()
    risk_obj = _risk(load_fixture, h)
    _patch_build_assess(monkeypatch, prelim_size=0.02, risk_obj=risk_obj)  # builder hedge None
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam([]))

    dossiers = await orchestrator.run_portfolio(None, None, [_item()], open_book=[])
    promoted = [d for d in dossiers if d.decision == "promote"][0]
    assert promoted.trade.hedge is h                       # the Risk-validated OBJECT reconciled on
    assert promoted.which_risk_covered == "idiosyncratic"  # derived from the reconciled hedge


async def test_run_portfolio_none_hedge_can_never_report_idiosyncratic(monkeypatch, load_fixture):
    risk_obj = _risk(load_fixture, None)   # no validated hedge -> honest fallback
    _patch_build_assess(monkeypatch, prelim_size=0.02, risk_obj=risk_obj)
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam([]))

    dossiers = await orchestrator.run_portfolio(None, None, [_item()], open_book=[])
    for d in dossiers:
        assert d.trade.hedge is None
        assert d.which_risk_covered != "idiosyncratic"


async def test_run_portfolio_full_week_composition(monkeypatch, load_fixture):
    risk_obj = _risk(load_fixture, _hedge())
    _patch_build_assess(monkeypatch, prelim_size=0.02, risk_obj=risk_obj)
    calls = []
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam(calls))

    dossiers = await orchestrator.run_portfolio(None, None, [_item(), _item()], open_book=[])
    assert len(dossiers) == 2 and all(isinstance(d, StrategyDossier) for d in dossiers)
    # author != approver AT COMPOSITION: memo + pre-mortem calls precede the FIRST PM decision.
    schemas = [c["schema"] for c in calls]
    assert schemas.count(PMDecision) == 2
    first_pm = schemas.index(PMDecision)
    assert PositionMemo in schemas[:first_pm] and PreMortem in schemas[:first_pm]


async def test_run_portfolio_passes_extra_context(monkeypatch, load_fixture):
    """06.7-02 (RECON-03): run_portfolio threads extra_context THROUGH to each builder.build."""
    captured = []

    async def _b(conn, embed, verdict, catalyst, *, entry, extra_context=None):
        captured.append(extra_context)
        return _proposal(hedge=None, size_pct=0.02)

    async def _a(conn, embed, proposal, catalyst, *, p_loss, gap, analog_gaps, prices):
        return _risk(load_fixture, _hedge())

    monkeypatch.setattr(builder, "build", _b)
    monkeypatch.setattr(risk, "assess", _a)
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam([]))

    await orchestrator.run_portfolio(None, None, [_item(), _item()], open_book=[],
                                     extra_context="GP: reconsider the runway gap")
    assert captured == ["GP: reconsider the runway gap", "GP: reconsider the runway gap"]

    captured.clear()
    await orchestrator.run_portfolio(None, None, [_item()], open_book=[])  # default -> None
    assert captured == [None]


async def test_run_portfolio_zero_trade_week_all_pass_returns_empty(monkeypatch):
    async def _none_build(conn, embed, verdict, catalyst, *, entry):
        return None   # every candidate passes (below-min / rejected estimate)

    monkeypatch.setattr(builder, "build", _none_build)
    dossiers = await orchestrator.run_portfolio(None, None, [_item(), _item()], open_book=[])
    assert dossiers == []   # a zero-trade week is a valid success, not an error


async def test_run_portfolio_all_kill_when_budget_zero_is_valid(monkeypatch, load_fixture):
    risk_obj = _risk(load_fixture, _hedge())
    _patch_build_assess(monkeypatch, prelim_size=0.02, risk_obj=risk_obj)
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam([]))

    dossiers = await orchestrator.run_portfolio(None, None, [_item()], open_book=[], weekly_budget=0.0)
    assert dossiers and all(d.decision == "kill" for d in dossiers)  # promoted nothing -> all-kill, valid
