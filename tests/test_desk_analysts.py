"""The analyst layer: four dimension prompts + run_analyst(), all offline.

run_analyst calls the run_structured seam bound to AnalystSignal. These tests
(a) prove each dimension emits a schema-valid, source-cited signal (run_structured
faked to return the recorded fixture), (b) prove sonnet-tier + caller-injected
mcp_servers/allowed_tools are threaded into the seam, and (c) prove the schema
boundary rejects an uncited payload (through the *real* run_structured, with only
the SDK `query` faked). No live API anywhere.
"""

import json
import types

import pytest
from pydantic import ValidationError

from catalyst_trader.contracts import AnalystSignal
from catalyst_trader.desk import analysts, runtime

DIMENSIONS = ["clinical", "regulatory", "financial", "market_sentiment"]
FIXTURE = {
    "clinical": "clinical_signal",
    "regulatory": "regulatory_signal",
    "financial": "financial_signal",
    "market_sentiment": "market_sentiment_signal",
}

CATALYST = {
    "ticker": "ACME",
    "company_name": "Acme Therapeutics",
    "catalyst_type": "pdufa",
    "event_date": "2026-11-28",
    "catalyst_id": "cat-001",
}


def _fake_run_structured_returning(signal, captured=None):
    async def _fake(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"):
        if captured is not None:
            captured["prompt"] = prompt
            captured["schema"] = schema
            captured["mcp_servers"] = mcp_servers
            captured["allowed_tools"] = allowed_tools
            captured["model"] = model
        return signal

    return _fake


@pytest.mark.parametrize("dimension", DIMENSIONS)
async def test_each_dimension_emits_cited_signal(dimension, monkeypatch, load_fixture):
    recorded = load_fixture(f"agent_responses/{FIXTURE[dimension]}")
    sig = AnalystSignal.model_validate(recorded)
    monkeypatch.setattr(analysts, "run_structured", _fake_run_structured_returning(sig))

    out = await analysts.run_analyst(dimension, CATALYST)

    assert isinstance(out, AnalystSignal)
    assert out.dimension == dimension
    assert out.key_findings and all(f.evidence_ref for f in out.key_findings)
    assert out.unknowns  # analysts must surface explicit gaps


async def test_sonnet_tier_and_tool_injection_threaded(monkeypatch, load_fixture):
    sig = AnalystSignal.model_validate(load_fixture("agent_responses/clinical_signal"))
    captured = {}
    monkeypatch.setattr(analysts, "run_structured", _fake_run_structured_returning(sig, captured))

    servers = {"quant": object()}
    tools = ["mcp__quant__base_rate", "mcp__quant__analog_query"]
    await analysts.run_analyst("clinical", CATALYST, mcp_servers=servers, allowed_tools=tools)

    assert captured["model"] == "sonnet"  # cheaper tier, configured not hard-coded per call
    assert captured["mcp_servers"] is servers
    assert captured["allowed_tools"] is tools
    assert captured["schema"] is AnalystSignal


async def test_prompt_mandates_quant_tools_and_dimension_token():
    prompt = analysts.build_prompt("clinical", CATALYST)
    assert "mcp__quant__" in prompt  # must CALL tools, not compute
    assert "clinical" in prompt
    assert "ACME" in prompt


@pytest.mark.parametrize("dimension", DIMENSIONS)
async def test_prompt_mandates_grounded_thesis(dimension):
    # CALL-01: every dimension prompt instructs a thesis SYNTHESIZED from its own cited findings
    # (no new uncited claim) — grounding is inherited, not a new verification pass.
    prompt = analysts.build_prompt(dimension, CATALYST)
    assert "thesis" in prompt
    assert "cited key_findings" in prompt  # grounded-in-own-findings phrasing


# Each dimension must read as a distinct, named top-expert voice (not a generic job label).
PERSONA_KEYWORD = {
    "clinical": "clinically meaningful",  # physician-scientist: clinical vs statistical significance
    "regulatory": "regulatory counsel",   # the FDA-lawyer voice
    "financial": "CFO",                   # the CFO voice
    "market_sentiment": "microstructure", # buy-side PM / microstructure voice
}


@pytest.mark.parametrize("dimension", DIMENSIONS)
async def test_prompt_has_expert_persona(dimension):
    # Each analyst reasons to the WHY as a distinct named expert, carrying a
    # dimension-specific keyword no other persona would use.
    prompt = analysts.build_prompt(dimension, CATALYST)
    assert PERSONA_KEYWORD[dimension] in prompt


@pytest.mark.parametrize("dimension", DIMENSIONS)
async def test_depth_directive_is_cite_or_drop_subordinate(dimension):
    # The shared DEPTH DIRECTIVE mandates one-level-deeper WHY + a second-order insight,
    # but is EXPLICITLY subordinate to cite-or-drop: depth is a deeper INTERPRETATION of
    # already-tool-cited evidence, never a new uncited claim.
    prompt = analysts.build_prompt(dimension, CATALYST)
    # depth mandate present
    assert "one level deeper" in prompt
    assert "second-order" in prompt
    # subordination clause — both halves of the guardrail
    assert "no new uncited claim" in prompt
    assert "evidence_ref" in prompt and "dropped" in prompt
    # preserved: cite-or-drop (rule 2) + grounded thesis (rule 5) survive verbatim
    assert "cite-or-drop" in prompt
    assert "cited key_findings" in prompt


async def test_uncited_finding_rejected(monkeypatch, load_fixture):
    # A recorded payload with zero key_findings must be rejected at the schema
    # boundary — proven through the REAL run_structured (only the SDK query faked),
    # so this exercises the actual model_validate trust boundary, not a stub.
    bad = load_fixture("agent_responses/clinical_signal")
    bad["key_findings"] = []

    async def _fake_query(*, prompt, options):
        yield types.SimpleNamespace(result=json.dumps(bad))

    monkeypatch.setattr(runtime, "query", _fake_query)

    with pytest.raises(ValidationError):  # the exact boundary error: >=1 sourced finding
        await analysts.run_analyst("clinical", CATALYST)
