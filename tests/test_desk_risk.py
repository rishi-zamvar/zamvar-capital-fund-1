"""Risk desk (PORT-03 + HEDGE-01..04): the deterministic survival-sizing engine,
the honest per-catalyst inverse-hedge validator, and the 3-way Risk Committee.

Money-critical invariants under test:
  - size_for_survival has NO return-target parameter (1% can never be a sizing input).
  - a hedge is only validated when a -1 inverse peer passes conditional_payoff +
    cointegration + catalyst-clean THIS catalyst; every other case → None (honest fallback).
  - assess calls validate_hedge EXACTLY ONCE and threads that single result onto BOTH
    RiskAssessment.hedge (the object) AND hedge_valid (BLOCKER-1).
  - the size on the RiskAssessment is ALWAYS the size_for_survival quant output, never an LLM number.

Quant + KB run FOR REAL (deterministic); run_structured is monkeypatched → fully offline.
"""

import inspect

from catalyst_trader.desk import risk
from catalyst_trader.quant.sizing import risk_of_ruin


# ---------------------------------------------------------------------------
# Task 1 — size_for_survival
# ---------------------------------------------------------------------------


def test_no_return_target_parameter():
    """Structural anti-1%-coupling: the signature carries NO return/target/weekly param."""
    params = inspect.signature(risk.size_for_survival).parameters
    banned = ("target", "return", "weekly", "one_pct", "benchmark")
    for name in params:
        assert not any(b in name.lower() for b in banned), f"{name} couples sizing to a return target"


def test_chosen_size_is_survivable_and_is_the_largest():
    r = risk.size_for_survival(p_loss=0.45, gap=0.70, ruin_cap=0.02, per_event_cap=0.03)
    size = r.value
    # the chosen size actually clears the ruin cap
    assert risk_of_ruin(0.45, size, 0.70).value <= 0.02
    # ...and it is the LARGEST such size — one step up breaches the cap (unless clamped at the per-event cap)
    if risk.FLOOR < size < 0.03:
        assert risk_of_ruin(0.45, size + risk.STEP, 0.70).value > 0.02
    # the citation snapshot is carried for audit
    assert r.detail["ruin_at_size"] == risk_of_ruin(0.45, size, 0.70).value
    assert "risk_of_ruin" in r.detail


def test_size_clamped_to_per_event_cap():
    # a trivially safe bet (tiny p_loss) still never exceeds the per-event cap
    r = risk.size_for_survival(p_loss=0.001, gap=0.70, ruin_cap=0.02, per_event_cap=0.03)
    assert r.value <= 0.03


def test_higher_p_loss_never_increases_size():
    low = risk.size_for_survival(p_loss=0.20, gap=0.70).value
    high = risk.size_for_survival(p_loss=0.50, gap=0.70).value
    assert high <= low


def test_larger_gap_never_increases_size():
    small_gap = risk.size_for_survival(p_loss=0.40, gap=0.30).value
    big_gap = risk.size_for_survival(p_loss=0.40, gap=0.90).value
    assert big_gap <= small_gap


def test_no_size_clears_cap_returns_tiny_floor_not_error(monkeypatch):
    # Defensive fallback: when NO size clears the ruin cap (every risk_of_ruin > cap),
    # size_for_survival returns the tiny FLOOR, never raises. Stub risk_of_ruin so the
    # branch is exercised without an expensive long-horizon DP.
    from catalyst_trader.quant.result import ToolResult

    def _ruinous(*a, **k):
        return ToolResult(tool="risk_of_ruin", tool_version="1.0.0", inputs={}, value=0.99, detail={})

    monkeypatch.setattr(risk, "risk_of_ruin", _ruinous)
    r = risk.size_for_survival(p_loss=0.9, gap=0.9, ruin_cap=0.02)
    assert r.value == risk.FLOOR
    assert r.detail["ruin_at_size"] == 0.99  # snapshot is the floor's (breaching) ruin


def test_deterministic():
    a = risk.size_for_survival(p_loss=0.37, gap=0.70)
    b = risk.size_for_survival(p_loss=0.37, gap=0.70)
    assert a.value == b.value and a.detail == b.detail


# ---------------------------------------------------------------------------
# Task 2 — validate_hedge (honest per-catalyst inverse re-validation + fallback)
# ---------------------------------------------------------------------------

import numpy as np
import pytest

from catalyst_trader.contracts import Hedge
from catalyst_trader.kb import EvidenceSource, insert_hedge_peer
from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    CatalystType,
    DatePrecision,
    SourceOrigin,
    SourceType,
    Status,
    Uncertainty,
)
from catalyst_trader import store

_EV = [EvidenceSource(url="https://sec.gov/10k", retrieved_at="2026-08-14", snippet_hash="h")]

# Deterministic price series (rng seed 7): a cointegrated inverse peer + an independent walk.
_RNG = np.random.default_rng(7)
_TARGET_PX = list(100 + np.cumsum(_RNG.normal(0, 1, 60)))
_PEER_COINT_PX = list(np.array(_TARGET_PX) + _RNG.normal(0, 0.5, 60))
_PEER_NONCOINT_PX = list(100 + np.cumsum(_RNG.normal(0, 1, 60)))

# Analog gaps where the inverse peer materially improves the worst case (payoff test passes).
_GAPS_PASS = {
    "target_up": 0.30, "target_down": -0.70,
    "peer_up": 0.25, "peer_down": -0.10,
    "w_target": 0.5, "w_peer": 0.5,
}


def _prices(peer_px):
    return {"target": _TARGET_PX, "peer": peer_px}


def _peer_catalyst(ticker, event_date):
    return Catalyst(
        ticker=ticker,
        company_name=f"{ticker} Inc",
        catalyst_type=CatalystType.pdufa,
        event_date=event_date,
        date_precision=DatePrecision.day,
        uncertainty_type=Uncertainty.window,
        status=Status.verified,
        source_origin=SourceOrigin.curated_pdufa,
        sources=[CatalystSource(
            source_name="ClinicalTrials.gov", source_type=SourceType.primary,
            reported_date=event_date, retrieved_at="2026-08-14T00:00:00Z",
        )],
    )


CAT = {"ticker": "ACME", "event_date": "2026-11-15", "catalyst_id": "cat-1"}
ENTRY, EXIT = "2026-11-14", "2026-11-22"


def test_only_inverse_minus1_peer_is_a_candidate(db, embed):
    # a +1 co-move peer is never an idiosyncratic hedge (HEDGE-01)
    insert_hedge_peer(db, "ACME", "COMOV", "correlated long", +1, 0.8, _EV)
    out = risk.validate_hedge(db, embed, "ACME", CAT, ENTRY, EXIT, _GAPS_PASS, _prices(_PEER_COINT_PX))
    assert out is None


def test_no_peer_at_all_returns_none(db, embed):
    out = risk.validate_hedge(db, embed, "ACME", CAT, ENTRY, EXIT, _GAPS_PASS, _prices(_PEER_COINT_PX))
    assert out is None


def test_validated_inverse_hedge(db, embed):
    insert_hedge_peer(db, "ACME", "RIVAL", "same-indication competitor", -1, 0.82, _EV)
    out = risk.validate_hedge(db, embed, "ACME", CAT, ENTRY, EXIT, _GAPS_PASS, _prices(_PEER_COINT_PX))
    assert isinstance(out, Hedge)
    assert out.validated is True
    assert out.payoff_direction == -1
    assert out.covers == "idiosyncratic"
    assert out.instrument == "equity_peer"
    assert out.ticker == "RIVAL"


def test_not_cointegrated_returns_none(db, embed):
    insert_hedge_peer(db, "ACME", "RIVAL", "same-indication competitor", -1, 0.82, _EV)
    out = risk.validate_hedge(db, embed, "ACME", CAT, ENTRY, EXIT, _GAPS_PASS, _prices(_PEER_NONCOINT_PX))
    assert out is None  # cointegration is a necessary gate (PITFALLS #3)


def test_payoff_test_failure_returns_none(db, embed):
    insert_hedge_peer(db, "ACME", "RIVAL", "same-indication competitor", -1, 0.82, _EV)
    gaps = {**_GAPS_PASS, "peer_down": 0.0}  # peer has no downside → payoff gate fails
    out = risk.validate_hedge(db, embed, "ACME", CAT, ENTRY, EXIT, gaps, _prices(_PEER_COINT_PX))
    assert out is None


def test_catalyst_clean_disqualification(db, embed):
    insert_hedge_peer(db, "ACME", "RIVAL", "same-indication competitor", -1, 0.82, _EV)
    # RIVAL has its OWN catalyst inside our hold window → not catalyst-clean (HEDGE-03)
    store.insert_catalyst(db, _peer_catalyst("RIVAL", "2026-11-18"))
    out = risk.validate_hedge(db, embed, "ACME", CAT, ENTRY, EXIT, _GAPS_PASS, _prices(_PEER_COINT_PX))
    assert out is None


def test_peer_catalyst_outside_window_is_still_clean(db, embed):
    insert_hedge_peer(db, "ACME", "RIVAL", "same-indication competitor", -1, 0.82, _EV)
    store.insert_catalyst(db, _peer_catalyst("RIVAL", "2027-03-01"))  # far outside the hold
    out = risk.validate_hedge(db, embed, "ACME", CAT, ENTRY, EXIT, _GAPS_PASS, _prices(_PEER_COINT_PX))
    assert isinstance(out, Hedge) and out.validated is True


def test_fake_idiosyncratic_hedge_is_unrepresentable():
    # even if validate_hedge logic were bypassed, the contract refuses a fabricated hedge (HEDGE-01/04)
    with pytest.raises(ValueError):
        Hedge(instrument="equity_peer", ticker="RIVAL", payoff_direction=-1,
              validated=False, covers="idiosyncratic", mechanism="x", conditional_worst=-0.4)


# ---------------------------------------------------------------------------
# Task 3 — 3-way Risk Committee (assess) → RiskAssessment carrying the Hedge object
# ---------------------------------------------------------------------------

from types import SimpleNamespace

from catalyst_trader.contracts import RiskAssessment
from catalyst_trader.desk.risk import CommitteeView

PROPOSAL = SimpleNamespace(target_long="ACME", exit_by_date=EXIT)


def _seam(views, synthesis, calls):
    """Fake run_structured: record every call, dispatch on schema + role in the prompt."""

    async def _fake(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"):
        calls.append({"prompt": prompt, "schema": schema, "model": model})
        if schema is RiskAssessment:
            return synthesis
        for role, v in views.items():
            if role.upper() in prompt:
                return v
        return next(iter(views.values()))

    return _fake


def _committee_fixtures(load_fixture):
    views = {
        "aggressive": CommitteeView.model_validate(load_fixture("agent_responses/risk_aggressive")),
        "conservative": CommitteeView.model_validate(load_fixture("agent_responses/risk_conservative")),
        "neutral": CommitteeView.model_validate(load_fixture("agent_responses/risk_neutral")),
    }
    synthesis = RiskAssessment.model_validate(load_fixture("agent_responses/risk_synthesis"))
    return views, synthesis


def _seed_hedge(db):
    insert_hedge_peer(db, "ACME", "RIVAL", "same-indication competitor", -1, 0.82, _EV)


async def test_size_is_the_quant_output_not_the_llm(db, embed, load_fixture, monkeypatch):
    _seed_hedge(db)
    views, synthesis = _committee_fixtures(load_fixture)
    monkeypatch.setattr(risk, "run_structured", _seam(views, synthesis, []))

    out = await risk.assess(db, embed, PROPOSAL, CAT, p_loss=0.45, gap=0.70,
                            analog_gaps=_GAPS_PASS, prices=_prices(_PEER_COINT_PX))

    expected = risk.size_for_survival(0.45, 0.70, 0.02, 0.03).value
    assert out.recommended_size_pct == expected  # the size is ALWAYS the quant number
    assert out.recommended_size_pct != synthesis.recommended_size_pct  # never the LLM's fixture value


async def test_matrix_and_worst_are_the_conditional_payoff_wiring(db, embed, load_fixture, monkeypatch):
    _seed_hedge(db)
    views, synthesis = _committee_fixtures(load_fixture)
    monkeypatch.setattr(risk, "run_structured", _seam(views, synthesis, []))

    out = await risk.assess(db, embed, PROPOSAL, CAT, p_loss=0.45, gap=0.70,
                            analog_gaps=_GAPS_PASS, prices=_prices(_PEER_COINT_PX))

    from catalyst_trader.quant.pairs import conditional_payoff
    cp = conditional_payoff(0.30, -0.70, 0.25, -0.10, 0.5, 0.5)
    assert out.conditional_payoff_matrix == cp.detail["matrix"]
    assert out.conditional_worst == cp.value
    assert out.ruin_at_size == risk_of_ruin(0.45, out.recommended_size_pct, 0.70).value


async def test_hedge_object_is_carried_and_hedge_valid_consistent(db, embed, load_fixture, monkeypatch):
    _seed_hedge(db)
    views, synthesis = _committee_fixtures(load_fixture)
    monkeypatch.setattr(risk, "run_structured", _seam(views, synthesis, []))

    out = await risk.assess(db, embed, PROPOSAL, CAT, p_loss=0.45, gap=0.70,
                            analog_gaps=_GAPS_PASS, prices=_prices(_PEER_COINT_PX))

    assert isinstance(out.hedge, Hedge)  # the actual OBJECT, not just a bool (BLOCKER-1)
    assert out.hedge.ticker == "RIVAL"
    assert out.hedge_valid is True
    assert out.hedge_valid == (out.hedge is not None and out.hedge.validated)


async def test_validate_hedge_called_exactly_once(db, embed, load_fixture, monkeypatch):
    _seed_hedge(db)
    views, synthesis = _committee_fixtures(load_fixture)
    monkeypatch.setattr(risk, "run_structured", _seam(views, synthesis, []))

    real = risk.validate_hedge
    calls = {"n": 0}
    sentinel = Hedge(instrument="equity_peer", ticker="RIVAL", payoff_direction=-1,
                     validated=True, covers="idiosyncratic", mechanism="m", conditional_worst=-0.4)

    def _spy(*a, **k):
        calls["n"] += 1
        return sentinel

    monkeypatch.setattr(risk, "validate_hedge", _spy)
    out = await risk.assess(db, embed, PROPOSAL, CAT, p_loss=0.45, gap=0.70,
                            analog_gaps=_GAPS_PASS, prices=_prices(_PEER_COINT_PX))

    assert calls["n"] == 1  # BLOCKER-1: validate_hedge runs ONCE, no double-validation
    assert out.hedge is sentinel  # that single result is threaded onto RiskAssessment.hedge
    assert real is not None


async def test_fallback_no_hedge_carries_none(db, embed, load_fixture, monkeypatch):
    # +1 co-move peer only → no validated inverse hedge → None + hedge_valid False (honest fallback)
    insert_hedge_peer(db, "ACME", "COMOV", "correlated long", +1, 0.8, _EV)
    views, synthesis = _committee_fixtures(load_fixture)
    monkeypatch.setattr(risk, "run_structured", _seam(views, synthesis, []))

    out = await risk.assess(db, embed, PROPOSAL, CAT, p_loss=0.45, gap=0.70,
                            analog_gaps=_GAPS_PASS, prices=_prices(_PEER_COINT_PX))

    assert out.hedge is None
    assert out.hedge_valid is False


async def test_committee_is_three_isolated_views_plus_opus_synthesis(db, embed, load_fixture, monkeypatch):
    _seed_hedge(db)
    views, synthesis = _committee_fixtures(load_fixture)
    calls = []
    monkeypatch.setattr(risk, "run_structured", _seam(views, synthesis, calls))

    await risk.assess(db, embed, PROPOSAL, CAT, p_loss=0.45, gap=0.70,
                      analog_gaps=_GAPS_PASS, prices=_prices(_PEER_COINT_PX))

    view_calls = [c for c in calls if c["schema"] is CommitteeView]
    synth_calls = [c for c in calls if c["schema"] is RiskAssessment]
    assert len(view_calls) == 3  # aggressive / conservative / neutral, isolated
    assert all(c["model"] == "sonnet" for c in view_calls)
    assert len(synth_calls) == 1 and synth_calls[0]["model"] == "opus"
    prompts = " ".join(c["prompt"].upper() for c in view_calls)
    assert "AGGRESSIVE" in prompts and "CONSERVATIVE" in prompts and "NEUTRAL" in prompts
