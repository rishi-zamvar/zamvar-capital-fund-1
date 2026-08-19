"""tests/test_live_desk_decision.py (7.8-S2 Tasks 2+3) — the catalyst -> MDDecision chain.

run_one_catalyst_decision chains catalyst -> run_desk -> catalyst_context -> run_portfolio ->
(promoted?) -> make_diligence_inputs -> run_diligence -> md.reconcile -> MDDecision, with an honest
zero-trade short-circuit. Every LLM seam is injected -> the whole path is offline (no network/LLM).

Task 3 also exercises the --dry-run --with-dd print path via the harness _print_decision helper.
"""

from datetime import date, timedelta

from catalyst_trader import db as _db
from catalyst_trader.contracts import (
    DiligenceDossier,
    DiligenceInput,
    EstimateVetting,
    MDDecision,
    PortfolioContext,
    ReconciliationRound,
    StrategyDossier,
    TradeProposal,
)
from catalyst_trader.desk import runtime as _runtime
from catalyst_trader.desk.diligence_inputs import make_diligence_inputs
from catalyst_trader.desk.live_desk import run_one_catalyst_decision
from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    CatalystType,
    DatePrecision,
    DateType,
    SourceOrigin,
    SourceType,
    Status,
    Uncertainty,
)
from catalyst_trader.store import insert_catalyst

_KILL = ["a Complete Response Letter is issued"]


def _seed_catalyst(conn, ticker="ACME"):
    event_date = (date.today() + timedelta(days=3)).isoformat()
    cat = Catalyst(
        ticker=ticker, catalyst_type=CatalystType.pdufa, event_date=event_date,
        date_precision=DatePrecision.day, uncertainty_type=Uncertainty.firm,
        source_origin=SourceOrigin.curated_pdufa, external_ref=f"pdufa:{ticker}:{event_date}",
        status=Status.verified, last_verified_at="2026-01-01T00:00:00Z",
        sources=[CatalystSource(
            source_name="Federal Register", source_url="https://fr", source_type=SourceType.primary,
            reported_date=event_date, date_type=DateType.estimated,
            retrieved_at="2026-01-01T00:00:00Z")],
    )
    insert_catalyst(conn, cat)
    return event_date


async def _fake_desk(conn, catalyst):
    from catalyst_trader.contracts import DebateVerdict
    return DebateVerdict(thesis="likely approves", direction="positive", confidence=0.6,
                         bull_strongest_point="endpoint met", bear_strongest_point="cash tight",
                         kill_criteria=_KILL)


async def _fake_context(conn, ticker, catalyst, as_of):
    return {"entry": 100.0, "risk_inputs": {"p_loss": 0.4, "gap": 0.15,
            "analog_gaps": {"target_up": 0.2, "target_down": -0.3, "peer_up": 0.0,
                            "peer_down": 0.0, "w_target": 1.0, "w_peer": 0.0},
            "prices": {"target": [99.0, 100.0], "peer": []}}}


def _promote_dossier(decision="promote"):
    trade = TradeProposal(
        target_long="ACME", hedge=None, pair_rationale="honest single-leg", entry=100.0,
        exit_by_date="2026-09-01", stop_loss=45.0, take_profit=120.0, size_pct=0.02,
        expected_return_pct=0.2, holds_through_catalyst=True, catalyst_id="ACME:x",
        direction="positive",
        estimate_vetting=EstimateVetting(verdict="endorse", input_refs=["tool:x#1"], reasons=["ok"]),
        sl_advisory=True,
    )
    return StrategyDossier(
        decision=decision, trade=trade,
        portfolio_context=PortfolioContext(concentration=0.0, corr_to_open_positions=[],
                                           weekly_budget_remaining=0.08, portfolio_outcome={"net": 0.02}),
        verdict_summary="promote it", residual_net_long=0.02, which_risk_covered="none",
        position_memo="memo", pre_mortem=["CRL"], kill_criteria=_KILL,
    )


def _canned_dd(verdict="no_go"):
    return DiligenceDossier(
        verdict=verdict,
        per_dimension=[{"dimension": "options_move", "catalyst_id": "ACME:x", "passed": True,
                        "score": 0.1, "confidence": 0.6}],
        red_flags=["ownership gap"], strongest_disconfirming_evidence="thin precedent",
        all_evidence_refs=[], residual_risks=[],
    )


def _canned_decision(decision="pass"):
    rnd = ReconciliationRound(round=1, response_delta="clean", convergence={"cross_check_clean": True},
                              cross_check={"clean": True}, disposition="converged")
    return MDDecision(decision=decision, rationale="canned", round_log=[rnd])


async def _fake_portfolio_factory(dossier):
    async def _p(conn, embed, verdicts, open_book, **kw):
        return [dossier] if dossier is not None else []
    return _p


def _fake_dd_inputs():
    """Offline (DiligenceInput, market_data, degraded) — no CBOE/network (options_source -> None)."""
    return make_diligence_inputs(options_source=lambda t: None, trial_source=lambda t: None)


# --- Task 2 ---


async def test_promotedTrade_producesMDDecision():
    conn = _db.connect(":memory:"); _db.migrate(conn); _seed_catalyst(conn)
    try:
        async def _rdil(conn, dd_input, *, market_data, embed=None):
            return _canned_dd("no_go")

        async def _recon(conn, embed, item):
            return _canned_decision("pass")

        port = await _fake_portfolio_factory(_promote_dossier())
        out = await run_one_catalyst_decision(
            conn, None, "ACME", as_of=date.today().isoformat(), live=False,
            run_desk_fn=_fake_desk, context_hook=_fake_context, run_portfolio_fn=port,
            dd_inputs_fn=_fake_dd_inputs(), run_diligence_fn=_rdil, reconcile_fn=_recon,
        )
        assert isinstance(out["dd"], DiligenceDossier) and out["dd"].verdict == "no_go"
        assert isinstance(out["decision"], MDDecision)
        assert out["decision"].decision in ("enter", "pass", "escalate")
        assert len(out["rounds"]) == 1
        assert out["degraded_flags"]                    # ownership + financials carried forward
    finally:
        conn.close()


async def test_itemAssembledForReconcile():
    conn = _db.connect(":memory:"); _db.migrate(conn); _seed_catalyst(conn)
    captured = {}
    try:
        async def _rdil(conn, dd_input, *, market_data, embed=None):
            return _canned_dd()

        async def _recon(conn, embed, item):
            captured.update(item)
            return _canned_decision()

        port = await _fake_portfolio_factory(_promote_dossier())
        await run_one_catalyst_decision(
            conn, None, "ACME", as_of=date.today().isoformat(), live=False,
            run_desk_fn=_fake_desk, context_hook=_fake_context, run_portfolio_fn=port,
            dd_inputs_fn=_fake_dd_inputs(), run_diligence_fn=_rdil, reconcile_fn=_recon,
        )
        # the full md.py reconcile contract
        for key in ("verdict", "dossier", "dd", "catalyst", "dd_input", "market_data",
                    "open_book", "entry", "risk_inputs"):
            assert key in captured, f"missing reconcile item key: {key}"
        assert captured["catalyst"]["catalyst_id"] and captured["catalyst"]["catalyst_type"]
        assert isinstance(captured["dd_input"], DiligenceInput)
        assert captured["open_book"] == []
    finally:
        conn.close()


async def test_zeroTrade_shortCircuits():
    conn = _db.connect(":memory:"); _db.migrate(conn); _seed_catalyst(conn)
    calls = []
    try:
        async def _rdil(conn, dd_input, *, market_data, embed=None):
            calls.append("dd"); return _canned_dd()

        async def _recon(conn, embed, item):
            calls.append("recon"); return _canned_decision()

        port = await _fake_portfolio_factory(None)      # run_portfolio promotes NOTHING
        out = await run_one_catalyst_decision(
            conn, None, "ACME", as_of=date.today().isoformat(), live=False,
            run_desk_fn=_fake_desk, context_hook=_fake_context, run_portfolio_fn=port,
            dd_inputs_fn=_fake_dd_inputs(), run_diligence_fn=_rdil, reconcile_fn=_recon,
        )
        assert out["dd"] is None and out["decision"] is None
        assert out["reason"] and "no trade" in out["reason"].lower()
        assert calls == []                              # neither DD nor reconcile ran
    finally:
        conn.close()


async def test_killDossier_isZeroTrade():
    conn = _db.connect(":memory:"); _db.migrate(conn); _seed_catalyst(conn)
    calls = []
    try:
        async def _rdil(conn, dd_input, *, market_data, embed=None):
            calls.append("dd"); return _canned_dd()

        port = await _fake_portfolio_factory(_promote_dossier(decision="kill"))
        out = await run_one_catalyst_decision(
            conn, None, "ACME", as_of=date.today().isoformat(), live=False,
            run_desk_fn=_fake_desk, context_hook=_fake_context, run_portfolio_fn=port,
            dd_inputs_fn=_fake_dd_inputs(), run_diligence_fn=_rdil,
        )
        assert out["decision"] is None and calls == []
    finally:
        conn.close()


async def test_noCatalyst_returnsCleanly():
    conn = _db.connect(":memory:"); _db.migrate(conn)      # nothing seeded
    try:
        out = await run_one_catalyst_decision(
            conn, None, "NONE", as_of=date.today().isoformat(), live=False,
            run_desk_fn=_fake_desk, context_hook=_fake_context,
        )
        assert out["catalyst"] is None and out["decision"] is None
        assert "no upcoming catalyst" in out["reason"].lower()
    finally:
        conn.close()


async def test_fullyOffline(monkeypatch):
    # belt-and-suspenders: real run_structured raising proves every LLM seam is injected.
    async def _boom(*a, **k):
        raise AssertionError("run_structured must not fire — all seams injected")
    monkeypatch.setattr(_runtime, "run_structured", _boom)

    conn = _db.connect(":memory:"); _db.migrate(conn); _seed_catalyst(conn)
    try:
        async def _rdil(conn, dd_input, *, market_data, embed=None):
            return _canned_dd()

        async def _recon(conn, embed, item):
            return _canned_decision()

        port = await _fake_portfolio_factory(_promote_dossier())
        out = await run_one_catalyst_decision(
            conn, None, "ACME", as_of=date.today().isoformat(), live=False,
            run_desk_fn=_fake_desk, context_hook=_fake_context, run_portfolio_fn=port,
            dd_inputs_fn=_fake_dd_inputs(), run_diligence_fn=_rdil, reconcile_fn=_recon,
        )
        assert out["decision"].decision == "pass"
    finally:
        conn.close()


async def test_ddInputCarriesPair():
    conn = _db.connect(":memory:"); _db.migrate(conn); _seed_catalyst(conn)
    captured = {}
    try:
        async def _rdil(conn, dd_input, *, market_data, embed=None):
            return _canned_dd()

        async def _recon(conn, embed, item):
            captured["dd_input"] = item["dd_input"]
            return _canned_decision()

        port = await _fake_portfolio_factory(_promote_dossier())   # trade.hedge is None -> single-leg
        await run_one_catalyst_decision(
            conn, None, "ACME", as_of=date.today().isoformat(), live=False,
            run_desk_fn=_fake_desk, context_hook=_fake_context, run_portfolio_fn=port,
            dd_inputs_fn=_fake_dd_inputs(), run_diligence_fn=_rdil, reconcile_fn=_recon,
        )
        assert captured["dd_input"].pair is None
    finally:
        conn.close()


# --- Task 3: harness --dry-run --with-dd print path (offline) ---


def test_printDecision_promoted(capsys):
    from scripts.run_one_catalyst import _print_decision
    result = {"catalyst": {"ticker": "ACME", "catalyst_type": "pdufa", "event_date": "2026-08-22"},
              "verdict": None, "dossier": _promote_dossier(), "dd": _canned_dd("no_go"),
              "decision": _canned_decision("pass"), "rounds": _canned_decision("pass").round_log,
              "degraded_flags": ["ownership: insider_net unavailable"], "reason": None}
    _print_decision(result)
    out = capsys.readouterr().out
    assert "no_go" in out                       # DiligenceDossier verdict
    assert "pass" in out                        # MDDecision
    assert "rounds" in out.lower() and "1" in out   # round count
    assert "insider_net" in out                 # degrade flag surfaced


def test_printDecision_zeroTrade(capsys):
    from scripts.run_one_catalyst import _print_decision
    result = {"catalyst": None, "verdict": None, "dossier": None, "dd": None, "decision": None,
              "rounds": [], "degraded_flags": [], "reason": "no trade promoted (zero-trade week)"}
    _print_decision(result)
    out = capsys.readouterr().out
    assert "no trade promoted" in out.lower()
