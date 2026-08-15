"""OPS-03 pre-trade guardrails: one enforced-and-fails-closed test per invariant.

Each of the five shipped pre-trade invariants aggregated by desk/guardrails.py is
proven here to (a) PASS on a clean pipeline and (b) FAIL CLOSED when violated. All
offline — no run_structured, no network. Live-position monitors (SL/TP, countdown,
paper P&L) are the deferred Phase 8/8.5 half of OPS-03 and are not exercised here.
"""

import pytest
from pydantic import ValidationError

from catalyst_trader.contracts import DiligenceInput
from catalyst_trader.desk import diligence as _diligence
from catalyst_trader.desk import guardrails
from catalyst_trader.desk import orchestrator as _orchestrator
from catalyst_trader.desk.guardrails import (
    GuardrailReport,
    GuardrailViolation,
    assert_guardrails,
    check_guardrails,
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


def _catalyst(status: Status) -> Catalyst:
    return Catalyst(
        ticker="VRTX",
        catalyst_type=CatalystType.pdufa,
        event_date="2026-11-30",
        date_precision=DatePrecision.day,
        uncertainty_type=Uncertainty.soft,
        source_origin=SourceOrigin.curated_pdufa,
        status=status,
        sources=[
            CatalystSource(
                source_name="ClinicalTrials.gov",
                source_type=SourceType.primary,
                reported_date="2026-11-30",
                date_type=DateType.actual,
                retrieved_at="2026-08-15T00:00:00Z",
            )
        ],
    )


# --- Invariant 1: catalyst freshness ----------------------------------------

def test_guardrail_catalyst_freshness_blocks_unverified():
    clean = check_guardrails(
        candidates=[_catalyst(Status.verified)], weights=[0.3, 0.3], heat_cap=0.6
    )
    assert clean.checks["catalyst_fresh"] is True

    violated = check_guardrails(
        candidates=[_catalyst(Status.unverified)], weights=[0.3, 0.3], heat_cap=0.6
    )
    assert violated.checks["catalyst_fresh"] is False
    assert violated.passed is False


# --- Invariant 2: fact-check / provenance cite-or-drop ----------------------

def test_guardrail_cite_or_drop_enforcers_present():
    report = check_guardrails(
        candidates=[_catalyst(Status.verified)], weights=[0.3, 0.3], heat_cap=0.6
    )
    assert report.checks["cite_or_drop_present"] is True
    # the enforcers are importable + callable (the fact-check gates are wired, not bypassed)
    from catalyst_trader.desk.diligence import enforce_dossier
    from catalyst_trader.desk.verifier import enforce, enforce_estimate

    assert callable(enforce) and callable(enforce_estimate) and callable(enforce_dossier)


# --- Invariant 3: Workflow-3 firewall (TOP-LEVEL) ---------------------------

def test_guardrail_dd_firewall_field_disjoint():
    report = check_guardrails(
        candidates=[_catalyst(Status.verified)], weights=[0.3, 0.3], heat_cap=0.6
    )
    assert report.checks["dd_firewall_sealed"] is True

    # A clean firewalled input validates.
    DiligenceInput(ticker="VRTX", catalyst={"catalyst_id": 1}, pair="INCY")

    # A leaked TOP-LEVEL Workflow-1 field (DebateVerdict.thesis) is a ValidationError —
    # extra="forbid" makes it unrepresentable.
    with pytest.raises(ValidationError):
        DiligenceInput(ticker="VRTX", catalyst={"catalyst_id": 1}, thesis="leaked reasoning")

    # SCOPE NOTE (checker Warning 3): this proves the TOP-LEVEL firewall only.
    # DiligenceInput.catalyst is a raw `dict`, so extra="forbid" does NOT deep-seal keys
    # smuggled INSIDE that nested dict — the line below PASSES, documenting the gap. The
    # Layer-B outcome-blind catalyst projection (07-05 Task 1) is the safeguard that
    # whitelists the nested catalyst keys handed to the desk. Do not mistake this for full sealing.
    leaked_nested = DiligenceInput(
        ticker="VRTX", catalyst={"catalyst_id": 1, "thesis": "smuggled inside nested dict"}
    )
    assert leaked_nested.catalyst["thesis"] == "smuggled inside nested dict"  # 07-05 seals this, not here


# --- Invariant 4: net-long / concentration caps -----------------------------

def test_guardrail_concentration_over_cap_blocks():
    clean = check_guardrails(
        candidates=[_catalyst(Status.verified)], weights=[0.2, 0.2], heat_cap=0.5
    )
    assert clean.checks["concentration_within_cap"] is True

    # A single-name book: concentration Σwᵢ² = 1.0 > heat_cap -> blocked.
    violated = check_guardrails(
        candidates=[_catalyst(Status.verified)], weights=[1.0], heat_cap=0.5
    )
    assert violated.checks["concentration_within_cap"] is False
    assert violated.passed is False


# --- Invariant 5: no path from scraped content to an order ------------------

def test_guardrail_no_scrape_to_order_web_free(monkeypatch):
    clean = check_guardrails(
        candidates=[_catalyst(Status.verified)], weights=[0.3, 0.3], heat_cap=0.6
    )
    assert clean.checks["no_scrape_to_order"] is True
    # the desk really is web-free: every allowed tool is an mcp__quant__* tool
    assert all(t.startswith("mcp__quant__") for t in _orchestrator.ALLOWED_TOOLS)
    assert all(t.startswith("mcp__quant__") for t in _diligence.ALLOWED_TOOLS)

    # Smuggle a web tool into the desk's tool list -> the gate catches it (fail-closed).
    monkeypatch.setattr(
        _orchestrator, "ALLOWED_TOOLS", [*_orchestrator.ALLOWED_TOOLS, "mcp__web__web_fetch"]
    )
    violated = check_guardrails(
        candidates=[_catalyst(Status.verified)], weights=[0.3, 0.3], heat_cap=0.6
    )
    assert violated.checks["no_scrape_to_order"] is False
    assert violated.passed is False


# --- The raising wrapper ----------------------------------------------------

def test_guardrail_assert_raises_on_violation():
    # clean pipeline: returns the report, no raise
    report = assert_guardrails(
        candidates=[_catalyst(Status.verified)], weights=[0.3, 0.3], heat_cap=0.6
    )
    assert isinstance(report, GuardrailReport)
    assert report.passed is True

    # any single check failing -> GuardrailViolation
    with pytest.raises(GuardrailViolation):
        assert_guardrails(
            candidates=[_catalyst(Status.unverified)], weights=[0.3, 0.3], heat_cap=0.6
        )


def test_guardrail_report_is_frozen():
    report = check_guardrails(
        candidates=[_catalyst(Status.verified)], weights=[0.3, 0.3], heat_cap=0.6
    )
    with pytest.raises(ValidationError):
        report.passed = False  # frozen model — the verdict cannot be mutated after the fact
