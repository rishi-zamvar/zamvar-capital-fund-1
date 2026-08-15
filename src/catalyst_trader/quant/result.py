"""ToolResult — the reproducibility contract every quant tool returns (QUANT-01/QUANT-03).

Mirrors the anti-hallucination discipline of contracts/__init__.py: `extra="forbid"` (no
stray fields) plus `frozen=True` (immutable, auditable). `inputs` is a verbatim snapshot of
the exact call params so any emitted number is reproducible; `tool_version` identifies which
formula produced it — bump it whenever a formula changes.
"""

from pydantic import BaseModel, ConfigDict, Field


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)  # immutable + no stray fields
    tool: str
    tool_version: str  # QUANT-01 "versioned"; bump when a formula changes
    inputs: dict  # QUANT-03: verbatim call params (JSON-serializable)
    value: float | None = None  # primary scalar (None when the tool returns a matrix/dict)
    detail: dict = Field(default_factory=dict)  # tool-specific extras (p-value, matrix, flags)
