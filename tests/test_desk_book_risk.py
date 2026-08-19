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


# ---------------------------------------------------------------------------
# Task 2 — the guarded attach pass in run_portfolio (money path SACRED)
# ---------------------------------------------------------------------------

from catalyst_trader import kb  # noqa: E402
from catalyst_trader.contracts import DebateVerdict, Hedge, RiskAssessment  # noqa: E402
from catalyst_trader.desk import builder, orchestrator, risk  # noqa: E402
from catalyst_trader.desk.portfolio import PMDecision, PositionMemo, PreMortem  # noqa: E402


def _hedge():
    return Hedge(instrument="equity_peer", ticker="RIVAL", payoff_direction=-1,
                 validated=True, covers="idiosyncratic", mechanism="same-indication competitor",
                 conditional_worst=-0.35)


def _risk(load_fixture, hedge=None, *, size=0.02):
    base = RiskAssessment.model_validate(load_fixture("agent_responses/risk_synthesis"))
    return base.model_copy(update={"recommended_size_pct": size, "hedge": hedge,
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
        calls.append({"schema": schema, "model": model})
        if schema is PositionMemo:
            return memo
        if schema is PreMortem:
            return pre
        if schema is PMDecision:
            return decision
        raise AssertionError(f"unexpected schema {schema!r}")

    return _fake


def _patch_desk(monkeypatch, *, build_fn, risk_obj):
    async def _a(conn, embed, proposal, catalyst, *, p_loss, gap, analog_gaps, prices):
        return risk_obj

    monkeypatch.setattr(builder, "build", build_fn)
    monkeypatch.setattr(risk, "assess", _a)
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam([]))
    # kb.hedge_profile is bound by run_portfolio as the corr_source; keep it offline (no DB).
    monkeypatch.setattr(kb, "hedge_profile", lambda conn, t: None)


async def test_promoted_dossier_carries_portfolio_outcome(monkeypatch, load_fixture):
    async def _b(conn, embed, verdict, catalyst, *, entry):
        return _statistical_proposal("ACME", expected=0.25, size=0.02)

    _patch_desk(monkeypatch, build_fn=_b, risk_obj=_risk(load_fixture, _hedge()))
    dossiers = await orchestrator.run_portfolio(None, None, [_item()], open_book=[])
    promoted = [d for d in dossiers if d.decision == "promote"]
    assert promoted, "the survivable leg should promote"
    for d in promoted:
        out = d.portfolio_context.portfolio_outcome
        assert isinstance(out, dict)
        for key in ("gross_exposure", "concentration", "scenarios", "risk"):
            assert key in out
    for d in dossiers:
        if d.decision == "kill":
            assert d.portfolio_context.portfolio_outcome is None   # kill dossiers untouched


async def test_high_ruin_book_surfaces_risk_of_ruin(monkeypatch, load_fixture):
    # a reconciled proposal implying a large worst-case loss (big down_move, low p_positive).
    async def _b(conn, embed, verdict, catalyst, *, entry):
        return _catalyst_proposal("ACME", up=0.05, down=0.95, p=0.05, size=0.02)

    _patch_desk(monkeypatch, build_fn=_b, risk_obj=_risk(load_fixture, None, size=0.02))
    dossiers = await orchestrator.run_portfolio(None, None, [_item()], open_book=[])
    promoted = [d for d in dossiers if d.decision == "promote"]
    assert promoted
    ror = promoted[0].portfolio_context.portfolio_outcome["risk"]["risk_of_ruin"]
    assert ror is not None and ror > 0    # a large modelled loss surfaces a portfolio risk-of-ruin


async def test_attach_off_yields_none(monkeypatch, load_fixture):
    async def _b(conn, embed, verdict, catalyst, *, entry):
        return _statistical_proposal("ACME", expected=0.25, size=0.02)

    _patch_desk(monkeypatch, build_fn=_b, risk_obj=_risk(load_fixture, _hedge()))
    dossiers = await orchestrator.run_portfolio(None, None, [_item()], open_book=[],
                                                attach_book_risk=False)
    assert dossiers
    for d in dossiers:
        assert d.portfolio_context.portfolio_outcome is None   # opt-out attaches nothing


async def test_empty_book_no_outcome_no_crash(monkeypatch):
    async def _none_build(conn, embed, verdict, catalyst, *, entry):
        return None   # every candidate passes -> nothing promotes, defensive_book=None

    monkeypatch.setattr(builder, "build", _none_build)
    monkeypatch.setattr(kb, "hedge_profile", lambda conn, t: None)
    dossiers = await orchestrator.run_portfolio(None, None, [_item(), _item()], open_book=[])
    assert dossiers == []   # zero-trade week: no promoted book, guard skips, no crash


async def test_conn_none_book_still_attaches_no_crash(monkeypatch, load_fixture):
    # BLOCKER fix: with conn=None the corr_source binding must NOT call kb.hedge_profile(None, t)
    # (that would AttributeError). The guard binds corr_source=None -> engine idiosyncratic fallback.
    def _boom(conn, t):
        raise AssertionError("kb.hedge_profile must not be called when conn is None")

    async def _b(conn, embed, verdict, catalyst, *, entry):
        return _statistical_proposal("ACME", expected=0.25, size=0.02)

    monkeypatch.setattr(builder, "build", _b)
    monkeypatch.setattr(kb, "hedge_profile", _boom)

    async def _a(conn, embed, proposal, catalyst, *, p_loss, gap, analog_gaps, prices):
        return _risk(load_fixture, _hedge())

    monkeypatch.setattr(risk, "assess", _a)
    monkeypatch.setattr(portfolio, "run_structured", _pm_seam([]))

    dossiers = await orchestrator.run_portfolio(None, None, [_item()], open_book=[])  # conn=None
    promoted = [d for d in dossiers if d.decision == "promote"]
    assert promoted and isinstance(promoted[0].portfolio_context.portfolio_outcome, dict)


async def test_attach_never_resizes_promoted_legs(monkeypatch, load_fixture):
    # MONEY-PATH GUARD: the attach mutates only portfolio_context, never the trade -> select_book
    # sizing is byte-for-byte identical with attach ON vs OFF.
    async def _b(conn, embed, verdict, catalyst, *, entry):
        return _statistical_proposal("ACME", expected=0.25, size=0.02)

    _patch_desk(monkeypatch, build_fn=_b, risk_obj=_risk(load_fixture, _hedge(), size=0.02))
    off = await orchestrator.run_portfolio(None, None, [_item()], open_book=[], attach_book_risk=False)
    on = await orchestrator.run_portfolio(None, None, [_item()], open_book=[], attach_book_risk=True)
    off_sizes = [d.trade.size_pct for d in off if d.decision == "promote"]
    on_sizes = [d.trade.size_pct for d in on if d.decision == "promote"]
    assert off_sizes == on_sizes and off_sizes    # identical promoted sizes — the READ never resizes


# --- integration: run_weekly rides the outcome on the dossiers with NO weekly.py change --------

from datetime import date, timedelta  # noqa: E402

from catalyst_trader import store  # noqa: E402
from catalyst_trader.desk.weekly import run_weekly  # noqa: E402


def _syn_bars(returns, *, start=1000.0, vol=2_000_000.0, first="2020-01-06"):
    d = date.fromisoformat(first)
    out = [{"week_end": d.isoformat(), "close": start, "volume": vol}]
    close = start
    for r in returns:
        close *= 1.0 + r
        d += timedelta(days=7)
        out.append({"week_end": d.isoformat(), "close": close, "volume": vol})
    return out


def _osc(n, amp=0.02):
    return [amp if i % 2 == 0 else -amp for i in range(n)]


def _seed_universe(db, tickers, as_of):
    for tk in tickers:
        db.execute(
            "INSERT INTO universe_snapshot "
            "(as_of_date,ticker,included,delisted,criteria_json,reason,recorded_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (as_of, tk, 1, 0, "{}", None, as_of),
        )
    db.commit()


async def test_run_weekly_book_carries_outcome(db):
    """run_weekly returns run_portfolio's dossier list unchanged -> promoted legs auto-carry the
    outcome with ZERO change to weekly.py (conn=db is a REAL conn; kb.hedge_profile -> None, no crash)."""
    elig = [0.03 if i % 2 == 0 else -0.06 for i in range(120)]
    store.upsert_bars(db, "XBI", _syn_bars(_osc(120)))
    store.upsert_bars(db, "ELIG", _syn_bars(elig))
    as_of = _syn_bars(elig)[-1]["week_end"]
    _seed_universe(db, ["ELIG"], as_of)

    dossiers = await run_weekly(db, None, as_of, open_book=[], params=kb.load_params(db, "weekly"))
    promoted = [d for d in dossiers if d.decision == "promote"]
    assert promoted, "every week produces a book"
    assert all(isinstance(d.portfolio_context.portfolio_outcome, dict) for d in promoted)
