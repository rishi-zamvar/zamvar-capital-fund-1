"""Contract-boundary suite: every inter-layer pydantic contract accepts a well-formed
payload and rejects a malformed one (extra key / missing evidence_ref / out-of-range
score+confidence / bad Literal verdict / broken nested contract). This is the
anti-hallucination boundary — an LLM that hallucinates a key, drops a citation, or emits
an out-of-range score is rejected by model_validate, not trusted."""

import pytest
from pydantic import ValidationError

from catalyst_trader.contracts import (
    AnalystSignal,
    DebateVerdict,
    DiligenceDossier,
    EstimateVetting,
    Hedge,
    RiskAssessment,
    StrategyDossier,
    TradeProposal,
)


# --- valid payload builders (one per contract) -----------------------------------


def valid_analyst_signal() -> dict:
    return {
        "dimension": "clinical",
        "ticker": "XYZ",
        "catalyst_id": "cat_2026_001",
        "score": 0.4,
        "confidence": 0.7,
        "key_findings": [
            {"claim": "primary endpoint met", "evidence_ref": "ev_ct_001", "source_url": "https://clinicaltrials.gov/x"}
        ],
        "kb_analogs_queried": ["playbook_pdufa_01"],
        "unknowns": ["long-term safety"],
    }


def valid_debate_verdict() -> dict:
    return {
        "thesis": "positive readout likely",
        "direction": "positive",
        "confidence": 0.65,
        "bull_strongest_point": "strong phase-2 signal",
        "bear_strongest_point": "underpowered trial",
        "unresolved_dissent": ["endpoint interpretation"],
        "evidence_refs": ["ev_ct_001", "ev_10q_002"],
        "kill_criteria": ["drug misses primary endpoint p>0.05"],
    }


def valid_trade_proposal() -> dict:
    return {
        "target_long": "XYZ",
        "hedge": valid_hedge(),
        "pair_rationale": "direct competitor on the same indication",
        "entry": 12.50,
        "exit_by_date": "2026-09-01",
        "stop_loss": 11.00,
        "take_profit": 14.00,
        "size_pct": 1.0,
        "expected_return_pct": 1.2,
        "kb_analogs": ["playbook_pdufa_01"],
        "holds_through_catalyst": True,
        "catalyst_id": "cat_2026_001",
        "direction": "positive",
        "estimate_vetting": valid_estimate_vetting(),
        "sl_advisory": True,
    }


def valid_risk_assessment() -> dict:
    return {
        "downside_stress_scenarios": ["CRL, -40%"],
        "hedge_correlation_estimate": 0.72,
        "correlation_source": "60d price history",
        "liquidity_check": "ADV supports ~1% size",
        "event_vol_estimate": 0.55,
        "aggressive_view": "size up",
        "conservative_view": "size down",
        "neutral_view": "size as planned",
        "residual_risks": ["gap risk overnight"],
        "conditional_payoff_matrix": {"target_down_peer_up": -0.35},
        "conditional_worst": -0.35,
        "hedge": valid_hedge(),
        "hedge_valid": True,
        "recommended_size_pct": 0.8,
        "ruin_at_size": 0.01,
    }


def valid_strategy_dossier() -> dict:
    return {
        "decision": "promote",
        "trade": valid_trade_proposal(),
        "portfolio_context": {
            "concentration": 0.15,
            "corr_to_open_positions": [0.1, 0.3],
            "weekly_budget_remaining": 0.8,
        },
        "verdict_summary": "hedged pair fits the book",
        "dissent_log": ["bear: crowding risk"],
        "all_evidence_refs": ["ev_ct_001"],
        "residual_net_long": 0.6,
        "which_risk_covered": "idiosyncratic",
        "position_memo": "own the readout, hedged by the direct competitor",
        "pre_mortem": ["assume it lost: the hedge co-moved on a class-wide selloff"],
        "kill_criteria": ["drug misses primary endpoint p>0.05"],
    }


def valid_diligence_dossier() -> dict:
    return {
        "verdict": "go",
        "per_dimension": [{"dimension": "liquidity", "result": "pass"}],
        "red_flags": [],
        "strongest_disconfirming_evidence": "prior CRL on same mechanism",
        "all_evidence_refs": ["ev_ct_001"],
    }


CONTRACTS = [
    (AnalystSignal, valid_analyst_signal),
    (DebateVerdict, valid_debate_verdict),
    (TradeProposal, valid_trade_proposal),
    (RiskAssessment, valid_risk_assessment),
    (StrategyDossier, valid_strategy_dossier),
    (DiligenceDossier, valid_diligence_dossier),
]


# --- good payloads validate --------------------------------------------------------


@pytest.mark.parametrize("model, builder", CONTRACTS)
def test_valid_payload_validates(model, builder):
    obj = model.model_validate(builder())
    assert obj is not None


# --- extra/hallucinated key is rejected on every contract --------------------------


@pytest.mark.parametrize("model, builder", CONTRACTS)
def test_extra_field_rejected(model, builder):
    payload = builder()
    payload["hallucinated_field"] = 1
    with pytest.raises(ValidationError):
        model.model_validate(payload)


# --- AnalystSignal / KeyFinding anti-hallucination boundary ------------------------


def test_key_finding_empty_evidence_ref_rejected():
    payload = valid_analyst_signal()
    payload["key_findings"][0]["evidence_ref"] = ""
    with pytest.raises(ValidationError):
        AnalystSignal.model_validate(payload)


def test_analyst_signal_empty_key_findings_rejected():
    payload = valid_analyst_signal()
    payload["key_findings"] = []
    with pytest.raises(ValidationError):
        AnalystSignal.model_validate(payload)


@pytest.mark.parametrize("score", [1.5, -1.5])
def test_analyst_signal_out_of_range_score_rejected(score):
    payload = valid_analyst_signal()
    payload["score"] = score
    with pytest.raises(ValidationError):
        AnalystSignal.model_validate(payload)


def test_analyst_signal_out_of_range_confidence_rejected():
    payload = valid_analyst_signal()
    payload["confidence"] = 1.2
    with pytest.raises(ValidationError):
        AnalystSignal.model_validate(payload)


# --- composite contracts: Literal + nested validation ------------------------------


def test_strategy_dossier_bad_decision_rejected():
    payload = valid_strategy_dossier()
    payload["decision"] = "maybe"
    with pytest.raises(ValidationError):
        StrategyDossier.model_validate(payload)


def test_strategy_dossier_malformed_nested_trade_rejected():
    payload = valid_strategy_dossier()
    del payload["trade"]["stop_loss"]
    with pytest.raises(ValidationError):
        StrategyDossier.model_validate(payload)


def test_diligence_dossier_bad_verdict_rejected():
    payload = valid_diligence_dossier()
    payload["verdict"] = "perhaps"
    with pytest.raises(ValidationError):
        DiligenceDossier.model_validate(payload)


# --- DebateVerdict: binary direction + explicit kill criteria (CALL-03) ------------


def test_debate_verdict_direction_binary():
    for good in ("positive", "negative"):
        payload = valid_debate_verdict()
        payload["direction"] = good
        assert DebateVerdict.model_validate(payload).direction == good
    for bad in ("neutral", "up"):
        payload = valid_debate_verdict()
        payload["direction"] = bad
        with pytest.raises(ValidationError):
            DebateVerdict.model_validate(payload)


def test_debate_verdict_requires_kill_criteria():
    payload = valid_debate_verdict()
    payload["kill_criteria"] = []
    with pytest.raises(ValidationError):
        DebateVerdict.model_validate(payload)
    payload["kill_criteria"] = ["drug misses primary endpoint p>0.05"]
    assert DebateVerdict.model_validate(payload).kill_criteria


def test_debate_verdict_valid_binary_with_kill_criteria():
    obj = DebateVerdict.model_validate(valid_debate_verdict())
    assert obj.direction in ("positive", "negative")
    assert obj.kill_criteria


# --- Hedge: honest-hedge structural invariants (HEDGE-01/04, locked decision #4) ---


def valid_hedge() -> dict:
    return {
        "instrument": "equity_peer",
        "ticker": "ABC",
        "payoff_direction": -1,
        "validated": True,
        "covers": "idiosyncratic",
        "mechanism": "direct competitor on the same indication",
        "conditional_worst": -0.35,
    }


def test_hedge_validated_inverse_peer_covers_idiosyncratic():
    obj = Hedge.model_validate(valid_hedge())
    assert obj.covers == "idiosyncratic"
    assert obj.payoff_direction == -1 and obj.validated


def test_hedge_unvalidated_cannot_claim_idiosyncratic():
    payload = valid_hedge()
    payload["validated"] = False
    with pytest.raises(ValidationError):
        Hedge.model_validate(payload)


def test_hedge_co_move_peer_cannot_claim_idiosyncratic():
    payload = valid_hedge()
    payload["payoff_direction"] = 1  # co-moves — not a hedge
    with pytest.raises(ValidationError):
        Hedge.model_validate(payload)


def test_hedge_inverse_etf_is_sector_beta_only():
    payload = valid_hedge()
    payload["instrument"] = "inverse_etf"
    payload["ticker"] = "LABD"
    payload["covers"] = "idiosyncratic"  # illegal: LABD covers sector_beta only
    with pytest.raises(ValidationError):
        Hedge.model_validate(payload)


def test_hedge_inverse_etf_sector_beta_valid():
    payload = valid_hedge()
    payload["instrument"] = "inverse_etf"
    payload["ticker"] = "LABD"
    payload["covers"] = "sector_beta"
    obj = Hedge.model_validate(payload)
    assert obj.covers == "sector_beta"


def test_hedge_put_option_not_executable_v1():
    payload = valid_hedge()
    payload["instrument"] = "put_option"
    with pytest.raises(ValidationError):
        Hedge.model_validate(payload)


def test_hedge_fallback_shape_valid():
    # unvalidated equity_peer covering nothing — the fallback shape (HEDGE-04)
    payload = valid_hedge()
    payload["validated"] = False
    payload["covers"] = "none"
    obj = Hedge.model_validate(payload)
    assert obj.covers == "none" and not obj.validated


def test_hedge_extra_field_rejected():
    payload = valid_hedge()
    payload["fake"] = 1
    with pytest.raises(ValidationError):
        Hedge.model_validate(payload)


# --- EstimateVetting: the estimate gate verdict (§7) -------------------------------


def valid_estimate_vetting() -> dict:
    return {
        "verdict": "endorse",
        "input_refs": ["tool:implied_move#abc", "kb:analog_001"],
        "dropped_inputs": [],
        "reasons": ["all inputs cited and comparable"],
        "uncertainty_widened": False,
    }


def test_estimate_vetting_endorse_valid():
    obj = EstimateVetting.model_validate(valid_estimate_vetting())
    assert obj.verdict == "endorse"


def test_estimate_vetting_bad_verdict_rejected():
    payload = valid_estimate_vetting()
    payload["verdict"] = "maybe"
    with pytest.raises(ValidationError):
        EstimateVetting.model_validate(payload)


def test_estimate_vetting_extra_field_rejected():
    payload = valid_estimate_vetting()
    payload["fake"] = 1
    with pytest.raises(ValidationError):
        EstimateVetting.model_validate(payload)


# --- Extended TradeProposal / RiskAssessment / StrategyDossier (Workflow-1b) --------


def test_trade_proposal_carries_validated_hedge_object():
    obj = TradeProposal.model_validate(valid_trade_proposal())
    assert isinstance(obj.hedge, Hedge)
    assert obj.estimate_vetting.verdict == "endorse"
    assert obj.direction == "positive"


def test_trade_proposal_none_hedge_is_the_fallback_path():
    payload = valid_trade_proposal()
    payload["hedge"] = None  # HEDGE-04 fallback: no valid inverse peer
    obj = TradeProposal.model_validate(payload)
    assert obj.hedge is None


def test_trade_proposal_old_hedge_long_key_rejected():
    payload = valid_trade_proposal()
    payload["hedge_long"] = "ABC"  # the removed field
    with pytest.raises(ValidationError):
        TradeProposal.model_validate(payload)


def test_risk_assessment_carries_hedge_object():
    obj = RiskAssessment.model_validate(valid_risk_assessment())
    assert isinstance(obj.hedge, Hedge)  # the OBJECT, not merely hedge_valid (BLOCKER-1)
    assert obj.hedge_valid is True
    assert obj.recommended_size_pct == 0.8


def test_risk_assessment_none_hedge_round_trips():
    payload = valid_risk_assessment()
    payload["hedge"] = None
    payload["hedge_valid"] = False
    obj = RiskAssessment.model_validate(payload)
    assert obj.hedge is None and obj.hedge_valid is False


def test_strategy_dossier_carries_workflow_1b_fields():
    obj = StrategyDossier.model_validate(valid_strategy_dossier())
    assert obj.which_risk_covered == "idiosyncratic"
    assert obj.residual_net_long == 0.6
    assert obj.pre_mortem and obj.position_memo


def test_strategy_dossier_empty_kill_criteria_rejected():
    payload = valid_strategy_dossier()
    payload["kill_criteria"] = []
    with pytest.raises(ValidationError):
        StrategyDossier.model_validate(payload)
