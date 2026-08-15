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
    DiligenceInput,
    EstimateVetting,
    Hedge,
    MDDecision,
    ReconciliationRound,
    RetriggerFlag,
    RiskAssessment,
    StrategyDossier,
    TradeProposal,
    WeeklyFlag,
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


# --- DiligenceInput: the firewall boundary (DILIG-01) ------------------------------
# The firewall is a pydantic + type-signature property, not a runtime check: extra="forbid"
# makes any Workflow-1/2 reasoning field UNREPRESENTABLE, so a leaked DebateVerdict/
# TradeProposal/thesis is a model_validate error, not a policy violation (the Hedge.covers
# move applied to the input boundary).


def valid_diligence_input() -> dict:
    return {
        "ticker": "ACME",
        "catalyst": {
            "catalyst_id": "cat-001",
            "catalyst_type": "pdufa",
            "event_date": "2026-11-28",
        },
    }


def test_diligence_input_firewall_field_disjoint():
    """DiligenceInput field names share NOTHING with any Workflow-1/2 artifact — no
    Pipeline-1/2 reasoning can be structurally carried across the firewall."""
    workflow_fields = (
        set(DebateVerdict.model_fields)
        | set(TradeProposal.model_fields)
        | set(StrategyDossier.model_fields)
        | set(RiskAssessment.model_fields)
    )
    assert set(DiligenceInput.model_fields).isdisjoint(workflow_fields)


def test_diligence_input_rejects_workflow_reasoning():
    # a Workflow-1 thesis field is unrepresentable (extra="forbid")
    payload = valid_diligence_input()
    payload["thesis"] = "positive readout likely"
    with pytest.raises(ValidationError):
        DiligenceInput.model_validate(payload)

    # a verdict-shaped field (direction) is likewise rejected
    payload = valid_diligence_input()
    payload["direction"] = "positive"
    with pytest.raises(ValidationError):
        DiligenceInput.model_validate(payload)

    # pair is a BARE TICKER string — a Hedge object as pair is rejected (str | None)
    payload = valid_diligence_input()
    payload["pair"] = Hedge.model_validate(valid_hedge())
    with pytest.raises(ValidationError):
        DiligenceInput.model_validate(payload)


def test_diligence_input_valid_minimal():
    obj = DiligenceInput.model_validate(valid_diligence_input())
    assert obj.ticker == "ACME"
    assert obj.pair is None  # defaults to None
    # pair as a bare peer ticker validates
    obj2 = DiligenceInput(
        ticker="ACME",
        catalyst={"catalyst_id": "cat-001", "catalyst_type": "pdufa", "event_date": "2026-11-28"},
        pair="XYZ",
    )
    assert obj2.pair == "XYZ"


def test_diligence_dossier_has_residual_risks():
    payload = valid_diligence_dossier()
    payload["residual_risks"] = ["net-long beta exposure"]
    obj = DiligenceDossier.model_validate(payload)
    assert obj.residual_risks == ["net-long beta exposure"]
    # defaults to [] when omitted
    assert DiligenceDossier.model_validate(valid_diligence_dossier()).residual_risks == []


# --- RetriggerFlag: the gap-not-answer firewall INTO WF-1/2 (RECON-02/06) ----------
# The firewall is a TYPE FACT (mirrors DiligenceInput): extra="forbid" + the ABSENCE of
# any answer-shaped field (direction/confidence/size/verdict) makes handing the debate a
# conclusion UNREPRESENTABLE — a smuggled answer is a ValidationError at construction.


def valid_retrigger_flag() -> dict:
    return {
        "target": "catalyst_call",
        "finding": "primary endpoint powered on OS, not PFS — DD found the SAP",
        "evidence_ref": "kb:ev_sap_001",
        "why_material": "an OS miss flips the verdict direction the debate called positive",
    }


def test_retriggerflag_valid():
    obj = RetriggerFlag.model_validate(valid_retrigger_flag())
    assert obj.target == "catalyst_call"
    assert obj.finding
    assert obj.evidence_ref == "kb:ev_sap_001"


@pytest.mark.parametrize(
    "answer_field",
    ["direction", "confidence", "size", "verdict", "recommended_direction"],
)
def test_retriggerflag_forbids_answer(answer_field):
    """RECON-06 firewall: ANY answer-shaped field is a ValidationError (extra='forbid'
    + no such field exists) — you cannot hand the debate a conclusion."""
    payload = valid_retrigger_flag()
    payload[answer_field] = "positive"
    with pytest.raises(ValidationError):
        RetriggerFlag.model_validate(payload)


def test_retriggerflag_bad_target_rejected():
    payload = valid_retrigger_flag()
    payload["target"] = "diligence"  # only catalyst_call / portfolio_build are routable
    with pytest.raises(ValidationError):
        RetriggerFlag.model_validate(payload)


@pytest.mark.parametrize("field", ["finding", "why_material", "evidence_ref"])
@pytest.mark.parametrize("bad", ["", "   "])
def test_retriggerflag_rejects_empty(field, bad):
    payload = valid_retrigger_flag()
    payload[field] = bad
    with pytest.raises(ValidationError):
        RetriggerFlag.model_validate(payload)


# --- WeeklyFlag: the gap-not-answer flag UP to the MD (RECON-08 / WEEK-06) ----------
# Same gap-not-answer shape as RetriggerFlag AND additionally NO target — the weekly
# refresh surfaces a gap; the MD decides route-or-log and (if routing) picks the target.


def valid_weekly_flag() -> dict:
    return {
        "ticker": "ACME",
        "flag_type": "quant",
        "finding": "cash runway dropped below 2 quarters vs baseline of 5",
        "evidence_ref": "tool:cash_runway#abc123",
        "why_material": "a financing overhang materially changes the sizing bucket",
    }


def test_weeklyflag_valid():
    obj = WeeklyFlag.model_validate(valid_weekly_flag())
    assert obj.ticker == "ACME"
    assert obj.flag_type == "quant"
    assert obj.finding


@pytest.mark.parametrize("field", ["verdict", "direction", "action", "target"])
def test_weeklyflag_forbids_answer_and_target(field):
    """RECON-08/WEEK-06 firewall: an answer-shaped field OR a pre-assigned target is a
    ValidationError — WeeklyFlag carries the GAP, the MD assigns the route."""
    payload = valid_weekly_flag()
    payload[field] = "catalyst_call" if field == "target" else "positive"
    with pytest.raises(ValidationError):
        WeeklyFlag.model_validate(payload)


def test_weeklyflag_bad_flag_type_rejected():
    payload = valid_weekly_flag()
    payload["flag_type"] = "technical"  # only quant / qual
    with pytest.raises(ValidationError):
        WeeklyFlag.model_validate(payload)


@pytest.mark.parametrize("field", ["ticker", "finding", "why_material", "evidence_ref"])
@pytest.mark.parametrize("bad", ["", "   "])
def test_weeklyflag_rejects_empty(field, bad):
    payload = valid_weekly_flag()
    payload[field] = bad
    with pytest.raises(ValidationError):
        WeeklyFlag.model_validate(payload)


# --- ReconciliationRound: one immutable per-round audit record (RECON-04/08) --------


def valid_reconciliation_round() -> dict:
    return {
        "round": 1,
        "md_flags": [valid_retrigger_flag()],
        "logged_flags": [valid_weekly_flag()],
        "response_delta": "debate re-ran on the SAP finding; verdict flipped to negative",
        "convergence": {"stable_verdict": False, "no_new_flags": False},
        "cross_check": {"catalyst_id": "cat-001", "net_long": 0.02},
        "disposition": "continue",
    }


def test_reconciliationround_valid():
    obj = ReconciliationRound.model_validate(valid_reconciliation_round())
    assert obj.round == 1
    assert isinstance(obj.md_flags[0], RetriggerFlag)
    assert obj.disposition == "continue"


def test_reconciliationround_extra_field_rejected():
    payload = valid_reconciliation_round()
    payload["hallucinated"] = "nope"
    with pytest.raises(ValidationError):
        ReconciliationRound.model_validate(payload)


def test_reconciliationround_bad_disposition_rejected():
    payload = valid_reconciliation_round()
    payload["disposition"] = "escalate"  # not a round disposition
    with pytest.raises(ValidationError):
        ReconciliationRound.model_validate(payload)


def test_reconciliationround_logged_flags():
    """logged_flags is the unactioned-flag home (RECON-08/WEEK-06): a list[WeeklyFlag]
    the MD chose NOT to action — logged, never forced. Defaults empty."""
    obj = ReconciliationRound.model_validate(valid_reconciliation_round())
    assert isinstance(obj.logged_flags[0], WeeklyFlag)
    payload = valid_reconciliation_round()
    del payload["md_flags"]
    del payload["logged_flags"]
    obj2 = ReconciliationRound.model_validate(payload)
    assert obj2.md_flags == []
    assert obj2.logged_flags == []


# --- MDDecision: the MD's sole output record, STANDALONE (RECON-04/05/07/08) --------


def valid_md_decision() -> dict:
    return {
        "decision": "enter",
        "rationale": "verdict survived reconciliation; hedge validated inverse THIS catalyst",
        "accepted_residuals": ["net-long beta priced via half-size"],
        "dissent_preserved": ["bear: financing overhang unresolved"],
        "round_log": [valid_reconciliation_round()],
    }


def test_mddecision_enter_valid():
    obj = MDDecision.model_validate(valid_md_decision())
    assert obj.decision == "enter"
    assert obj.blocker_class is None
    assert obj.recommended_resolution is None
    assert isinstance(obj.round_log[0], ReconciliationRound)


def test_mddecision_escalation_requires_resolution():
    """RECON-07 completed-staff-work: an escalation MUST carry BOTH blocker_class and
    recommended_resolution, else ValidationError."""
    # missing both
    payload = valid_md_decision()
    payload["decision"] = "escalate"
    with pytest.raises(ValidationError):
        MDDecision.model_validate(payload)
    # blocker_class only
    payload = valid_md_decision()
    payload["decision"] = "escalate"
    payload["blocker_class"] = "data_gap"
    with pytest.raises(ValidationError):
        MDDecision.model_validate(payload)
    # recommended_resolution only
    payload = valid_md_decision()
    payload["decision"] = "escalate"
    payload["recommended_resolution"] = "pull the AdCom briefing doc"
    with pytest.raises(ValidationError):
        MDDecision.model_validate(payload)
    # both present -> constructs
    payload = valid_md_decision()
    payload["decision"] = "escalate"
    payload["blocker_class"] = "data_gap"
    payload["recommended_resolution"] = "pull the AdCom briefing doc"
    obj = MDDecision.model_validate(payload)
    assert obj.decision == "escalate"
    assert obj.blocker_class == "data_gap"


@pytest.mark.parametrize("decision", ["enter", "pass"])
@pytest.mark.parametrize(
    "extra", [{"blocker_class": "mandate"}, {"recommended_resolution": "do X"}]
)
def test_mddecision_escalation_only_fields(decision, extra):
    payload = valid_md_decision()
    payload["decision"] = decision
    payload.update(extra)
    with pytest.raises(ValidationError):
        MDDecision.model_validate(payload)


def test_mddecision_carries_residuals_and_dissent():
    """RECON-05: accepted_residuals + dissent_preserved round-trip verbatim; round_log is
    a list[ReconciliationRound]."""
    obj = MDDecision.model_validate(valid_md_decision())
    assert obj.accepted_residuals == ["net-long beta priced via half-size"]
    assert obj.dissent_preserved == ["bear: financing overhang unresolved"]
    assert all(isinstance(r, ReconciliationRound) for r in obj.round_log)


def test_mddecision_not_a_strategydossier_field():
    """MDDecision is STANDALONE — never a StrategyDossier field (regression guard)."""
    assert "md_decision" not in StrategyDossier.model_fields
    for name, field in StrategyDossier.model_fields.items():
        assert field.annotation is not MDDecision, name
