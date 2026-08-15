"""run_structured() is the single SDK seam. These tests prove it (a) parses a
recorded response into a validated model, (b) rejects a bad payload at the
boundary, and (c) threads output_format/mcp_servers/allowed_tools/model into
ClaudeAgentOptions — all with the SDK's `query` monkeypatched, so no live API."""

import json
import types

import pytest

from catalyst_trader.contracts import AnalystSignal
from catalyst_trader.desk import runtime


def _fake_query_yielding(result_text, captured=None):
    """Build a fake `query` that records the options it was called with and
    yields one message whose `.result` is `result_text`."""

    async def _fake_query(*, prompt, options):
        if captured is not None:
            captured["prompt"] = prompt
            captured["options"] = options
        yield types.SimpleNamespace(result=result_text)

    return _fake_query


async def test_returns_validated_model_from_recorded_response(monkeypatch, load_fixture):
    recorded = load_fixture("agent_responses/sample_analyst_signal")
    monkeypatch.setattr(runtime, "query", _fake_query_yielding(json.dumps(recorded)))

    sig = await runtime.run_structured("prompt", AnalystSignal)

    assert isinstance(sig, AnalystSignal)
    assert sig.dimension == "clinical"
    assert sig.key_findings and all(f.evidence_ref for f in sig.key_findings)


async def test_schema_violating_payload_raises(monkeypatch):
    # valid JSON, but missing required fields -> pydantic rejects at the boundary
    bad = json.dumps({"dimension": "clinical"})
    monkeypatch.setattr(runtime, "query", _fake_query_yielding(bad))

    with pytest.raises(Exception):
        await runtime.run_structured("prompt", AnalystSignal)


async def test_malformed_json_raises(monkeypatch):
    monkeypatch.setattr(runtime, "query", _fake_query_yielding("not json {"))

    with pytest.raises(Exception):
        await runtime.run_structured("prompt", AnalystSignal)


async def test_options_passthrough(monkeypatch, load_fixture):
    recorded = load_fixture("agent_responses/sample_analyst_signal")
    captured = {}
    monkeypatch.setattr(runtime, "query", _fake_query_yielding(json.dumps(recorded), captured))

    servers = {"quant": object()}
    tools = ["mcp__quant__base_rate"]
    await runtime.run_structured(
        "prompt", AnalystSignal, mcp_servers=servers, allowed_tools=tools, model="opus"
    )

    opts = captured["options"]
    assert opts.model == "opus"
    assert opts.mcp_servers == servers
    assert opts.allowed_tools == tools
    assert opts.output_format["type"] == "json_schema"
    assert opts.output_format["schema"] == AnalystSignal.model_json_schema()
    # desk never spawns subagents — the Agent tool must not leak into allowed_tools
    assert "Agent" not in opts.allowed_tools


async def test_retries_once_on_validation_error(monkeypatch, load_fixture):
    recorded = load_fixture("agent_responses/sample_analyst_signal")
    good = json.dumps(recorded)
    bad = json.dumps({"dimension": "clinical"})
    payloads = [bad, good]

    async def _flaky_query(*, prompt, options):
        yield types.SimpleNamespace(result=payloads.pop(0))

    monkeypatch.setattr(runtime, "query", _flaky_query)

    sig = await runtime.run_structured("prompt", AnalystSignal)
    assert isinstance(sig, AnalystSignal)
    assert not payloads  # both attempts consumed
