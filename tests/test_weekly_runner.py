"""Weekly runner (WEEK-01, WEEK-05) — the thin cadence composition + the LEARN record seam.

Fully offline: run_structured is monkeypatched, run_desk is monkeypatched, and the price bars are
synthetic (no live FMP). The money-critical invariants under test:
  - run_portfolio threads the ~1% target into risk.assess (Plan-02 kwargs) WITHOUT touching the
    catalyst-only default path (byte-for-byte — the test_desk_portfolio run_portfolio suite stays green);
  - the statistical sleeve is capped at statistical_sleeve_cap * weekly_budget in a catalyst week (the
    moat is never crowded out) but NOT starved in a pure-statistical week;
  - the defensive book deploys instead of an empty week (no zero-trade weeks);
  - run_weekly composes scan -> shortlist -> desk -> book with ONE anchor for measurement + execution;
  - per-leg weekly outcomes persist as CITED KB outcome claims (cite-or-drop) for the Phase-10 LEARN loop.
"""

from datetime import date, timedelta

import pytest

from catalyst_trader import kb, store
from catalyst_trader.contracts import (
    DebateVerdict,
    EstimateVetting,
    Hedge,
    PortfolioContext,
    RiskAssessment,
    StrategyDossier,
    TradeProposal,
)
from catalyst_trader.desk import builder, orchestrator, portfolio, risk
from catalyst_trader.desk.portfolio import Candidate, PMDecision, PositionMemo, PreMortem

_KILL = ["a Complete Response Letter is issued", "label carve-out on the lead indication"]


# --- shared builders (mirror test_desk_portfolio) --------------------------------------------


def _hedge():
    return Hedge(instrument="equity_peer", ticker="RIVAL", payoff_direction=-1,
                 validated=True, covers="idiosyncratic", mechanism="same-indication competitor",
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


def _pm_seam(calls):
    memo = PositionMemo(memo="LLM memo body")
    pre = PreMortem(scenarios=["it lost because the CRL hit"])
    decision = PMDecision(verdict_summary="promote it", dissent_log=[], all_evidence_refs=[])

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


def _stat_cand(ticker, size=0.02, move=0.03):
    return Candidate(
        size_pct=size, expected_move=move, weight=size,
        payload={"weekly": True, "ticker": ticker, "thesis_type": "mean_reversion",
                 "trigger": "drop_le_-0.05", "p": 0.6, "mean_next": move,
                 "entry": 10.0, "exit_by_date": "2026-11-22"},
    )


def _defensive_cand(ticker, size=0.02):
    return Candidate(
        size_pct=size, expected_move=0.0001, weight=size,
        payload={"defensive": True, "ticker": ticker, "entry": 1.0, "exit_by_date": "2026-11-22"},
    )


def _is_weekly_leg(dossier):
    return dossier.trade.catalyst_id.startswith("weekly:")


# --- Task 1: run_portfolio threading -----------------------------------------------------------


async def test_target_return_threads_expected_move_into_assess(monkeypatch, load_fixture):
    """target_return set -> risk.assess gets target_return AND expected_move=proposal.expected_return_pct."""
    seen = {}
    risk_obj = _risk(load_fixture, _hedge())

    async def _b(conn, embed, verdict, catalyst, *, entry):
        return _proposal(hedge=None, size_pct=0.02)

    async def _a(conn, embed, proposal, catalyst, *, p_loss, gap, analog_gaps, prices,
                 target_return=None, expected_move=None):
        seen["target_return"] = target_return
        seen["expected_move"] = expected_move
        return risk_obj

    monkeypatch.setattr(builder, "build", _b)
    monkeypatch.setattr(risk, "assess", _a)
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam([]))

    await orchestrator.run_portfolio(None, None, [_item()], open_book=[], target_return=0.01)
    assert seen["target_return"] == 0.01
    assert seen["expected_move"] == 0.25   # proposal.expected_return_pct (net EV — DELIBERATE, not up_move)


async def test_defensive_book_deploys_when_nothing_promotes(monkeypatch):
    """No catalyst + defensive_book supplied -> the defensive legs come back as a book, never empty."""
    dossiers = await orchestrator.run_portfolio(
        None, None, [], open_book=[],
        defensive_book=[_defensive_cand("SGOV"), _defensive_cand("BIL")],
    )
    assert dossiers, "a no-signal week must never be empty"
    tickers = {d.trade.target_long for d in dossiers}
    assert tickers == {"SGOV", "BIL"}
    assert all(d.trade.hedge is None and d.which_risk_covered == "none" for d in dossiers)
    assert all(not d.trade.holds_through_catalyst for d in dossiers)  # one-week exit


async def test_extra_statistical_candidates_merged_into_book(monkeypatch, load_fixture):
    risk_obj = _risk(load_fixture, _hedge())

    async def _b(conn, embed, verdict, catalyst, *, entry):
        return _proposal(hedge=None, size_pct=0.02)

    async def _a(conn, embed, proposal, catalyst, *, p_loss, gap, analog_gaps, prices):
        return risk_obj

    monkeypatch.setattr(builder, "build", _b)
    monkeypatch.setattr(risk, "assess", _a)
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam([]))

    dossiers = await orchestrator.run_portfolio(
        None, None, [_item()], open_book=[],
        weekly_budget=0.10, target_weekly=10.0,
        extra_candidates=[_stat_cand("BOUNCE")],
    )
    weekly = [d for d in dossiers if _is_weekly_leg(d)]
    assert weekly and weekly[0].trade.target_long == "BOUNCE"
    assert weekly[0].trade.hedge is None            # single-leg statistical (no hedge)


async def test_statistical_sleeve_capped_in_catalyst_week_but_catalyst_promotes(monkeypatch, load_fixture):
    risk_obj = _risk(load_fixture, _hedge())

    async def _b(conn, embed, verdict, catalyst, *, entry):
        return _proposal(hedge=None, size_pct=0.02)

    async def _a(conn, embed, proposal, catalyst, *, p_loss, gap, analog_gaps, prices):
        return risk_obj

    monkeypatch.setattr(builder, "build", _b)
    monkeypatch.setattr(risk, "assess", _a)
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam([]))

    stat = [_stat_cand(f"S{i}", size=0.02) for i in range(4)]  # 0.08 combined, pre-cap
    dossiers = await orchestrator.run_portfolio(
        None, None, [_item()], open_book=[],
        weekly_budget=0.10, target_weekly=10.0, heat_cap=1e9,
        extra_candidates=stat, statistical_sleeve_cap=0.5,   # cap = 0.05
    )
    weekly = [d for d in dossiers if _is_weekly_leg(d)]
    catalyst = [d for d in dossiers if not _is_weekly_leg(d)]
    assert sum(d.trade.size_pct for d in weekly) <= 0.05 + 1e-9   # sleeve cap holds
    assert any(d.decision == "promote" for d in catalyst)          # catalyst engine not crowded out


async def test_pure_statistical_week_not_starved_by_cap(monkeypatch, load_fixture):
    stat = [_stat_cand(f"S{i}", size=0.02) for i in range(4)]  # 0.08 combined
    dossiers = await orchestrator.run_portfolio(
        None, None, [], open_book=[],   # NO catalyst candidates
        weekly_budget=0.10, target_weekly=10.0, heat_cap=1e9,
        extra_candidates=stat, statistical_sleeve_cap=0.5,   # cap must NOT apply (pure-statistical)
    )
    weekly = [d for d in dossiers if _is_weekly_leg(d)]
    assert sum(d.trade.size_pct for d in weekly) > 0.05   # cap NOT applied -> the book fills past 0.05
