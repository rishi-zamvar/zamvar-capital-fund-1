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
    }


def valid_trade_proposal() -> dict:
    return {
        "target_long": "XYZ",
        "hedge_long": "ABC",
        "pair_rationale": "direct competitor on the same indication",
        "entry": 12.50,
        "exit_by_date": "2026-09-01",
        "stop_loss": 11.00,
        "take_profit": 14.00,
        "size_pct": 1.0,
        "expected_return_pct": 1.2,
        "kb_analogs": ["playbook_pdufa_01"],
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
