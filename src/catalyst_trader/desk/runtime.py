"""The single SDK seam. Every agent call in the desk goes through
`run_structured`; nothing else touches `claude_agent_sdk`. Tests monkeypatch
`query` (this module's binding) with a recorded response, so the whole suite
runs offline with zero live Anthropic calls.

The contract's json_schema is bound to `output_format` so the model must emit
valid JSON for that role, and `model_validate` rejects anything that slips
through — the trust boundary lives on the return line, not in the caller.
"""

import json
from typing import Type

from claude_agent_sdk import ClaudeAgentOptions, query
from pydantic import BaseModel, ValidationError


async def _attempt(prompt: str, opts: ClaudeAgentOptions, schema: Type[BaseModel]) -> BaseModel:
    result_text = None
    async for message in query(prompt=prompt, options=opts):
        # the final ResultMessage carries the structured text in `.result`
        if getattr(message, "result", None) is not None:
            result_text = message.result
    if result_text is None:
        raise ValueError("run_structured: query produced no result message")
    return schema.model_validate(json.loads(result_text))


async def run_structured(
    prompt: str,
    schema: Type[BaseModel],
    *,
    mcp_servers: dict | None = None,
    allowed_tools: list[str] | None = None,
    model: str = "sonnet",
) -> BaseModel:
    """Run one agent role and return its validated contract model.

    Raises pydantic.ValidationError (schema-violating) or json.JSONDecodeError
    (malformed) rather than ever returning a bad model. Retries exactly once on a
    ValidationError (cheap re-roll; models occasionally emit a stray field).
    """
    opts = ClaudeAgentOptions(
        output_format={"type": "json_schema", "schema": schema.model_json_schema()},
        mcp_servers=mcp_servers or {},
        allowed_tools=allowed_tools or [],  # no "Agent" tool: desk fan-out is Python, never SDK subagents
        model=model,
    )
    try:
        return await _attempt(prompt, opts, schema)
    except ValidationError:
        return await _attempt(prompt, opts, schema)  # ponytail: one retry, no backoff machinery
