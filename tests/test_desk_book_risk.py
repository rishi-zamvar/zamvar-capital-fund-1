"""Phase 7.8-pf2 (PORT-01) — the whole-BOOK risk read wired into weekly assembly.

`build_portfolio` (the stateless what-if engine) is exposed today only as an analyst MCP
tool; it does NOT run when the desk assembles the weekly book. This suite covers the pure
adapter (`book_to_portfolio_inputs`) that maps the assembled promoted book's TradeProposals
into the engine's (positions, assumptions) contract, plus the guarded attach pass in
`run_portfolio` that runs the engine once after select_book and hangs the resulting
PortfolioOutcome on each promoted dossier's portfolio_context.

Money-critical invariants under test (all OFFLINE — run_structured + kb.hedge_profile are
monkeypatched, no conn/LLM/network):
  - the adapter reads per-name moves from what the desk ALREADY computed (catalyst leg ->
    exit_plan.ev_flip; statistical/defensive leg -> expected_return_pct, engine defaults rest);
  - only TARGET legs are mapped (the outcome is a TARGET-LEG exposure read, NOT whole-book
    gross — the long/long hedge peer carries no size_pct this phase);
  - a duplicate ticker across two promoted legs AGGREGATES (sums) its size_pct into ONE position;
  - the attach pass is a READ appended after the book is chosen — select_book selection/sizing is
    byte-for-byte unchanged, the outcome never resizes or reorders a leg;
  - attach_book_risk=False and an empty/zero-trade book attach NO outcome and never raise;
  - conn=None falls back to the engine's idiosyncratic-correlation behavior (no crash) — the
    guard that keeps the existing null-conn offline suites green;
  - the sector-shock default is PARAMS-driven (BOOK_RISK_PARAMS, direct-subscript, missing-key-raises).
"""

import pytest

from catalyst_trader.contracts import (
    EstimateVetting,
    PortfolioContext,
    StrategyDossier,
    TradeProposal,
)
from catalyst_trader.desk import exit_plan as ep
from catalyst_trader.desk import portfolio
from catalyst_trader.desk.portfolio import BOOK_RISK_PARAMS, book_to_portfolio_inputs
from catalyst_trader.desk.portfolio_builder import build_portfolio

_KILL = ["a Complete Response Letter is issued"]


def _catalyst_proposal(ticker, *, up, down, p, size, direction="positive"):
    """A catalyst leg carrying an ExitPlan whose ev_flip = up/down/p (the desk's per-name moves)."""
    plan = ep.build_exit_plan(
        entry=100.0, up_move=up, down_move=down, p_positive=p, holds_through=True,
        stop=90.0, target=100.0 * (1 + up), exit_by_date="2026-11-22",
        kill_criteria=_KILL, direction=direction, has_hedge=False,
    )
    return TradeProposal(
        target_long=ticker, hedge=None, pair_rationale="long leg",
        entry=100.0, exit_by_date="2026-11-22", stop_loss=90.0, take_profit=120.0,
        size_pct=size, expected_return_pct=up * p - down * (1 - p), kb_analogs=[],
        holds_through_catalyst=True, catalyst_id=f"cat-{ticker}", direction=direction,
        estimate_vetting=EstimateVetting(verdict="endorse", input_refs=["tool:x#1"], reasons=["ok"]),
        sl_advisory=True, exit_plan=plan,
    )


def _statistical_proposal(ticker, *, expected, size, direction="positive"):
    """A single-leg statistical/defensive leg: no exit_plan, only expected_return_pct."""
    return TradeProposal(
        target_long=ticker, hedge=None, pair_rationale="single-leg statistical",
        entry=10.0, exit_by_date="2026-11-22", stop_loss=0.0, take_profit=0.0,
        size_pct=size, expected_return_pct=expected, kb_analogs=[],
        holds_through_catalyst=False, catalyst_id=f"weekly:statistical:{ticker}", direction=direction,
        estimate_vetting=EstimateVetting(verdict="endorse", input_refs=["tool:x#1"], reasons=["ok"]),
        sl_advisory=True,
    )


def _dossier(trade, *, decision="promote"):
    """Wrap a TradeProposal in a minimal promoted StrategyDossier for adapter tests."""
    return StrategyDossier(
        decision=decision, trade=trade,
        portfolio_context=PortfolioContext(
            concentration=0.0, corr_to_open_positions=[], weekly_budget_remaining=0.10),
        verdict_summary="v", dissent_log=[], all_evidence_refs=[],
        residual_net_long=0.0, which_risk_covered="none",
        position_memo="m", pre_mortem=["p"], kill_criteria=_KILL,
    )


# ---------------------------------------------------------------------------
# Task 1 — the pure adapter book_to_portfolio_inputs + the PortfolioContext field
# ---------------------------------------------------------------------------


def test_adapter_maps_multi_proposal_book():
    # a catalyst leg (exit_plan ev_flip up 0.30 / down 0.20 / p 0.6) + a statistical leg (no exit_plan).
    cat = _catalyst_proposal("ACME", up=0.30, down=0.20, p=0.6, size=0.03)
    stat = _statistical_proposal("BOUNCE", expected=0.03, size=0.02)
    positions, assumptions = book_to_portfolio_inputs([_dossier(cat), _dossier(stat)])

    by_ticker = {p["ticker"]: p for p in positions}
    assert set(by_ticker) == {"ACME", "BOUNCE"}
    assert by_ticker["ACME"] == {"ticker": "ACME", "side": "long", "size_pct": 0.03}
    assert by_ticker["BOUNCE"] == {"ticker": "BOUNCE", "side": "long", "size_pct": 0.02}

    # catalyst name: up/down/p read straight off exit_plan.ev_flip
    assert assumptions["ACME"] == {"expected_move": 0.30, "down_move": 0.20, "p_positive": 0.6}
    # statistical name: only expected_move — down_move/p_positive OMITTED (engine defaults them)
    assert assumptions["BOUNCE"] == {"expected_move": 0.03}


def test_adapter_short_side_from_negative_direction():
    prop = _statistical_proposal("BEAR", expected=0.04, size=0.02, direction="negative")
    positions, _ = book_to_portfolio_inputs([_dossier(prop)])
    assert positions[0]["side"] == "short"


def test_adapter_aggregates_duplicate_ticker():
    # C2: same name in a catalyst sleeve AND a statistical sleeve -> ONE position, SUMMED size_pct
    # (build_portfolio's weights_by_ticker dict would silently keep the LAST leg otherwise).
    cat = _catalyst_proposal("DUPE", up=0.30, down=0.20, p=0.6, size=0.03)
    stat = _statistical_proposal("DUPE", expected=0.03, size=0.02)
    positions, assumptions = book_to_portfolio_inputs([_dossier(cat), _dossier(stat)])

    dupe = [p for p in positions if p["ticker"] == "DUPE"]
    assert len(dupe) == 1                                   # collapsed to a single position
    assert dupe[0]["size_pct"] == pytest.approx(0.05)       # 0.03 + 0.02 aggregated, not last-wins
    # the richer exit_plan-derived moves win over the bare statistical expected_move
    assert assumptions["DUPE"] == {"expected_move": 0.30, "down_move": 0.20, "p_positive": 0.6}


def test_adapter_sets_sector_shock_default():
    prop = _statistical_proposal("ACME", expected=0.03, size=0.02)
    _, assumptions = book_to_portfolio_inputs([_dossier(prop)])
    assert assumptions["sector_shock"] == BOOK_RISK_PARAMS["default_sector_shock"]

    _, passed = book_to_portfolio_inputs([_dossier(prop)], sector_shock=-0.25)
    assert passed["sector_shock"] == -0.25                  # caller value wins when supplied


def test_adapter_passes_corr_source_through():
    prop = _statistical_proposal("ACME", expected=0.03, size=0.02)

    def _fake_corr(_t):
        return None

    _, with_src = book_to_portfolio_inputs([_dossier(prop)], corr_source=_fake_corr)
    assert with_src["corr_source"] is _fake_corr

    _, without = book_to_portfolio_inputs([_dossier(prop)])
    assert "corr_source" not in without                    # absent -> engine treats as idiosyncratic


def test_adapter_accepts_bare_proposals():
    # reusable outside run_portfolio: a list[TradeProposal] maps identically to a list[StrategyDossier].
    cat = _catalyst_proposal("ACME", up=0.30, down=0.20, p=0.6, size=0.03)
    from_bare = book_to_portfolio_inputs([cat])
    from_dossier = book_to_portfolio_inputs([_dossier(cat)])
    assert isinstance(cat, TradeProposal)
    assert from_bare == from_dossier


def test_adapter_output_feeds_engine():
    # the produced contract is VALID for the engine (offline, no mock) -> a real PortfolioOutcome.
    cat = _catalyst_proposal("ACME", up=0.30, down=0.20, p=0.6, size=0.03)
    stat = _statistical_proposal("BOUNCE", expected=0.03, size=0.02)
    positions, assumptions = book_to_portfolio_inputs([_dossier(cat), _dossier(stat)])
    outcome = build_portfolio(positions, assumptions).model_dump()
    for key in ("gross_exposure", "net_exposure", "concentration", "scenarios", "risk"):
        assert key in outcome


def test_portfolio_context_outcome_field_defaults_none():
    ctx = PortfolioContext(concentration=0.25, corr_to_open_positions=[], weekly_budget_remaining=0.08)
    assert ctx.portfolio_outcome is None                   # additive field defaults None
