"""ToolResult contract suite (QUANT-01 versioned + QUANT-03 inputs snapshot).

Every quant tool returns a ToolResult that carries a verbatim, immutable snapshot of the
exact inputs it was called with — the reproducibility/audit spine. Mirrors the
`extra="forbid"` discipline in contracts/__init__.py: a stray field, a mutation, or a
missing version is rejected, not silently accepted. Pure pydantic — no fixtures.
"""

import json

import pytest
from pydantic import ValidationError

from catalyst_trader.quant.result import ToolResult


def test_inputs_snapshot_preserved():
    r = ToolResult(
        tool="t", tool_version="1.0.0", inputs={"a": 1, "b": 2}, value=3.0
    )
    assert r.inputs == {"a": 1, "b": 2}
    assert r.tool == "t"
    assert r.tool_version == "1.0.0"
    assert r.value == 3.0


def test_result_is_immutable():
    r = ToolResult(tool="t", tool_version="1.0.0", inputs={}, value=1.0)
    with pytest.raises(ValidationError):
        r.value = 9.0  # frozen=True -> mutation rejected


def test_extra_field_forbidden():
    with pytest.raises(ValidationError):
        ToolResult(tool="t", tool_version="1.0.0", inputs={}, bogus=1)


def test_roundtrips_through_json():
    r = ToolResult(
        tool="cointegration",
        tool_version="1.0.0",
        inputs={"a": [1.0, 2.0], "b": [3.0, 4.0]},
        value=0.03,
        detail={"cointegrated": True, "t_stat": -4.2},
    )
    restored = ToolResult(**json.loads(json.dumps(r.model_dump())))
    assert restored == r


def test_value_optional_for_matrix_tools():
    r = ToolResult(
        tool="t",
        tool_version="1.0.0",
        inputs={},
        detail={"matrix": [[1, 2], [3, 4]]},
    )
    assert r.value is None
    assert r.detail["matrix"] == [[1, 2], [3, 4]]


def test_version_required():
    with pytest.raises(ValidationError):
        ToolResult(tool="t", inputs={}, value=1.0)


def test_detail_defaults_empty():
    r = ToolResult(tool="t", tool_version="1.0.0", inputs={})
    assert r.detail == {}
