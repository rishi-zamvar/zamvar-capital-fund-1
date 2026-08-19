"""scripts/run_one_catalyst.py (7.8-S1) — the one-catalyst harness, offline wiring proof.

The Nyquist automated verify for the harness: run_one threads ONE catalyst through
run_desk -> catalyst_context -> run_portfolio and prints a StrategyDossier, WITHOUT any live call.
run_desk_fn / context_hook / run_portfolio_fn are all injected (the --dry-run seam, C1), so no LLM /
network / real analog read fires. Also proves the honest entry=None skip returns None (no leg).
"""

from datetime import date, timedelta

from catalyst_trader import db as _db
from catalyst_trader.contracts import (
    DebateVerdict,
    EstimateVetting,
    PortfolioContext,
    StrategyDossier,
    TradeProposal,
)
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
from scripts.run_one_catalyst import run_one

_KILL = ["a Complete Response Letter is issued"]


def _seed_catalyst(conn, ticker="ACME"):
    """A verified PDUFA inside the upcoming (today, +7d] hold week, knowable well before today."""
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


def _verdict():
    return DebateVerdict(thesis="ACME PDUFA likely approves", direction="positive", confidence=0.6,
                         bull_strongest_point="endpoint met", bear_strongest_point="cash tight",
                         kill_criteria=_KILL)


def _dossier():
    trade = TradeProposal(
        target_long="ACME", hedge=None, pair_rationale="long ACME, honest single-leg (no inverse peer)",
        entry=100.0, exit_by_date="2026-11-22", stop_loss=45.0, take_profit=120.0,
        size_pct=0.02, expected_return_pct=0.2, holds_through_catalyst=True, catalyst_id="ACME:x",
        direction="positive",
        estimate_vetting=EstimateVetting(verdict="endorse", input_refs=["tool:x#1"], reasons=["ok"]),
        sl_advisory=True,
    )
    return StrategyDossier(
        decision="promote", trade=trade,
        portfolio_context=PortfolioContext(concentration=0.0, corr_to_open_positions=[],
                                           weekly_budget_remaining=0.08, portfolio_outcome={"net": 0.02}),
        verdict_summary="promote it", residual_net_long=0.02, which_risk_covered="none",
        position_memo="memo", pre_mortem=["it lost because the CRL hit"], kill_criteria=_KILL,
    )


async def _fake_run_desk(conn, catalyst):
    return _verdict()


async def _fake_context(conn, ticker, catalyst, as_of):
    return {"entry": 100.0, "risk_inputs": {"p_loss": 0.4, "gap": 0.15,
                                            "analog_gaps": {}, "prices": {"target": [1.0], "peer": []}}}


async def test_givenSeededCatalyst_whenRunOneOffline_thenPrintsDossierNoLiveCall(capsys):
    conn = _db.connect(":memory:")
    _db.migrate(conn)
    try:
        _seed_catalyst(conn)

        async def _fake_portfolio(conn, embed, verdicts, open_book):
            assert len(verdicts) == 1 and verdicts[0]["entry"] == 100.0
            assert "risk_inputs" in verdicts[0] and verdicts[0]["catalyst"]["ticker"] == "ACME"
            return [_dossier()]

        out = await run_one(conn, None, "ACME", live=False, run_desk_fn=_fake_run_desk,
                            context_hook=_fake_context, run_portfolio_fn=_fake_portfolio)
        assert out is not None and len(out) == 1
        assert out[0].trade.target_long == "ACME"
        printed = capsys.readouterr().out
        assert "ACME" in printed and "promote" in printed
    finally:
        conn.close()


async def test_givenEntryNone_whenRunOneOffline_thenHonestSkipReturnsNone(capsys):
    conn = _db.connect(":memory:")
    _db.migrate(conn)
    try:
        _seed_catalyst(conn)

        async def _skip_context(conn, ticker, catalyst, as_of):
            return {"entry": None, "risk_inputs": {}}

        async def _must_not_run(*a, **k):
            raise AssertionError("run_portfolio must not run when entry is None")

        out = await run_one(conn, None, "ACME", live=False, run_desk_fn=_fake_run_desk,
                            context_hook=_skip_context, run_portfolio_fn=_must_not_run)
        assert out is None
        assert "skip" in capsys.readouterr().out.lower()
    finally:
        conn.close()


async def test_givenNoCatalyst_whenRunOneOffline_thenReturnsNone(capsys):
    conn = _db.connect(":memory:")
    _db.migrate(conn)
    try:
        out = await run_one(conn, None, "NONE", live=False, run_desk_fn=_fake_run_desk,
                            context_hook=_fake_context)
        assert out is None
        assert "no upcoming catalyst" in capsys.readouterr().out.lower()
    finally:
        conn.close()
