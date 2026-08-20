"""The analyst layer (07.9): four one-pager lens prompts + run_analyst(), all offline.

run_analyst maps each dimension to its lens report class (REPORT_FOR) and binds THAT
class at the run_structured seam. These tests (a) prove each dimension emits a schema-valid,
source-cited lens report (run_structured faked to return the recorded lens fixture) and
binds its lens class at the seam, (b) prove sonnet-tier + caller-injected mcp_servers/
allowed_tools are threaded, (c) prove the one-pager prompt carries the guideline's ordered
section headers + the Plain-Language HARD RULES while preserving cite-or-drop/persona/depth,
and (d) prove the schema boundary rejects an uncited payload through the *real* run_structured
(only the SDK `query` faked). No live API anywhere.
"""

import json
import types

import pytest
from pydantic import ValidationError

from catalyst_trader.contracts import (
    AnalystReportBase,
    ClinicalReport,
    FinancialReport,
    MarketReport,
    RegulatoryReport,
)
from catalyst_trader.desk import analysts, runtime

DIMENSIONS = ["clinical", "regulatory", "financial", "market_sentiment"]
FIXTURE = {
    "clinical": "clinical_signal",
    "regulatory": "regulatory_signal",
    "financial": "financial_signal",
    "market_sentiment": "market_sentiment_signal",
}
REPORT_FOR = {
    "clinical": ClinicalReport,
    "regulatory": RegulatoryReport,
    "financial": FinancialReport,
    "market_sentiment": MarketReport,
}

CATALYST = {
    "ticker": "ACME",
    "company_name": "Acme Therapeutics",
    "catalyst_type": "pdufa",
    "event_date": "2026-11-28",
    "catalyst_id": "cat-001",
}


def _fake_run_structured_returning(report, captured=None):
    async def _fake(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"):
        if captured is not None:
            captured["prompt"] = prompt
            captured["schema"] = schema
            captured["mcp_servers"] = mcp_servers
            captured["allowed_tools"] = allowed_tools
            captured["model"] = model
        return report

    return _fake


@pytest.mark.parametrize("dimension", DIMENSIONS)
async def test_each_dimension_emits_cited_lens_report(dimension, monkeypatch, load_fixture):
    lens = REPORT_FOR[dimension]
    recorded = lens.model_validate(load_fixture(f"agent_responses/{FIXTURE[dimension]}"))
    captured = {}
    monkeypatch.setattr(analysts, "run_structured", _fake_run_structured_returning(recorded, captured))

    out = await analysts.run_analyst(dimension, CATALYST)

    # returns the correct lens report class AND bound that class at the seam (the schema split)
    assert isinstance(out, lens)
    assert isinstance(out, AnalystReportBase)
    assert captured["schema"] is lens
    # base interface preserved (the debate/verifier contract)
    assert out.dimension == dimension
    assert out.key_findings and all(f.evidence_ref for f in out.key_findings)
    assert out.thesis.strip()   # the bottom line
    assert out.unknowns          # analysts must surface explicit gaps


async def test_sonnet_tier_and_tool_injection_threaded(monkeypatch, load_fixture):
    rep = ClinicalReport.model_validate(load_fixture("agent_responses/clinical_signal"))
    captured = {}
    monkeypatch.setattr(analysts, "run_structured", _fake_run_structured_returning(rep, captured))

    servers = {"quant": object()}
    tools = ["mcp__quant__base_rate", "mcp__quant__analog_query"]
    await analysts.run_analyst("clinical", CATALYST, mcp_servers=servers, allowed_tools=tools)

    assert captured["model"] == "sonnet"  # cheaper tier, configured not hard-coded per call
    assert captured["mcp_servers"] is servers
    assert captured["allowed_tools"] is tools
    assert captured["schema"] is ClinicalReport   # bound the lens class, NOT AnalystSignal


async def test_prompt_mandates_quant_tools_and_dimension_token():
    prompt = analysts.build_prompt("clinical", CATALYST)
    assert "mcp__quant__" in prompt  # must CALL tools, not compute
    assert "clinical" in prompt
    assert "ACME" in prompt


@pytest.mark.parametrize("dimension", DIMENSIONS)
async def test_prompt_mandates_grounded_thesis(dimension):
    # CALL-01: every dimension prompt instructs a thesis SYNTHESIZED from its own cited findings.
    prompt = analysts.build_prompt(dimension, CATALYST)
    assert "thesis" in prompt
    assert "cited key_findings" in prompt  # grounded-in-own-findings phrasing


# Each dimension must read as a distinct, named top-expert voice (not a generic job label).
PERSONA_KEYWORD = {
    "clinical": "clinically meaningful",
    "regulatory": "regulatory counsel",
    "financial": "CFO",
    "market_sentiment": "microstructure",
}


@pytest.mark.parametrize("dimension", DIMENSIONS)
async def test_prompt_has_expert_persona(dimension):
    prompt = analysts.build_prompt(dimension, CATALYST)
    assert PERSONA_KEYWORD[dimension] in prompt


# The guideline §1-4 ORDERED section headers each one-pager must lay out.
SECTION_HEADERS = {
    "clinical": ["Bottom Line", "Trial Design", "Efficacy", "Safety", "Key Scientific Risk"],
    "regulatory": ["Application", "AdCom", "Label", "Probability of Approval"],
    "financial": ["Runway", "rNPV", "Insider"],
    "market_sentiment": ["Expected Move", "Implied", "Short Interest", "Asymmetry"],
}


@pytest.mark.parametrize("dimension", DIMENSIONS)
async def test_prompt_carries_ordered_section_headers(dimension):
    prompt = analysts.build_prompt(dimension, CATALYST)
    for header in SECTION_HEADERS[dimension]:
        assert header in prompt, f"{dimension} one-pager missing section header {header!r}"


@pytest.mark.parametrize("dimension", DIMENSIONS)
async def test_prompt_has_plain_language_hard_rules(dimension):
    # §5 Plain-Language Standard, enforced as HARD RULES in every one-pager.
    prompt = analysts.build_prompt(dimension, CATALYST).lower()
    assert "define" in prompt                  # (a) define every term inline
    assert "gets context" in prompt            # (b) every number gets context...
    assert "benchmark" in prompt               # ...vs a benchmark
    assert "lead with the bottom line" in prompt  # (c) bottom line first
    assert "leave" in prompt and "null" in prompt  # unavailable numbers left null, never fabricated


@pytest.mark.parametrize("dimension", DIMENSIONS)
async def test_depth_directive_is_cite_or_drop_subordinate(dimension):
    prompt = analysts.build_prompt(dimension, CATALYST)
    assert "one level deeper" in prompt
    assert "second-order" in prompt
    assert "no new uncited claim" in prompt
    assert "evidence_ref" in prompt and "dropped" in prompt
    assert "cite-or-drop" in prompt
    assert "cited key_findings" in prompt


async def test_uncited_finding_rejected(monkeypatch, load_fixture):
    # A recorded payload with zero key_findings must be rejected at the schema boundary —
    # proven through the REAL run_structured (only the SDK query faked), exercising the actual
    # model_validate trust boundary on the LENS report, not a stub.
    bad = load_fixture("agent_responses/clinical_signal")
    bad["key_findings"] = []

    async def _fake_query(*, prompt, options):
        yield types.SimpleNamespace(result=json.dumps(bad))

    monkeypatch.setattr(runtime, "query", _fake_query)

    with pytest.raises(ValidationError):  # >=1 sourced finding, on ClinicalReport
        await analysts.run_analyst("clinical", CATALYST)
