"""The analyst layer (CALL-01): four dimension-specific prompts + one run_analyst().

Each analyst INTERPRETS tool output and emits a source-cited AnalystSignal; it never
computes or recalls a figure. Every number, base rate, or analog MUST come from a
`mcp__quant__*` tool call and be cited by the evidence_ref the tool returns — the one
quant MCP server (built in desk.tools, name "quant") wraps BOTH the quant AND KB tools,
so every tool is a quant-namespaced tool and there is no separate KB tool namespace. The
schema boundary (AnalystSignal, via the
run_structured seam) rejects any uncited / malformed payload, so a hallucinated,
citation-free finding never reaches the debate.

# ponytail: 4 job strings + 1 prompt builder + 1 seam call. No prompt-registry, no
#           per-dimension classes — a dict and an f-string are the whole layer.
"""

from ..contracts import AnalystSignal
from .runtime import run_structured

# Each analyst's job. The shared rules (call tools, cite, fill unknowns, emit the token)
# live in build_prompt so they can't drift per-dimension.
PROMPTS = {
    "clinical": (
        "You are the CLINICAL/SCIENTIFIC analyst. Judge whether the underlying science and "
        "trial design support a positive readout: endpoint strength, phase-transition odds, "
        "mechanism, and how structurally similar past readouts resolved."
    ),
    "regulatory": (
        "You are the REGULATORY analyst. Judge approval/label risk: PDUFA/AdCom precedent for "
        "this therapeutic class, prior CRLs, review-division posture, and analog regulatory "
        "outcomes for comparable filings."
    ),
    "financial": (
        "You are the FINANCIAL analyst. Judge financial resilience around the event: cash "
        "runway vs the catalyst, dilution risk, and the asset's risk-adjusted valuation "
        "sensitivity."
    ),
    "market_sentiment": (
        "You are the MARKET/SENTIMENT analyst. Judge how the event is already positioned: "
        "options-implied move vs realized analog moves, short interest, and crowding — is the "
        "expected outcome already priced in?"
    ),
}


def _get(catalyst, key, default=""):
    """Read a field from a Catalyst model OR a plain dict — orchestrator supplies either."""
    if isinstance(catalyst, dict):
        return catalyst.get(key, default)
    return getattr(catalyst, key, default)


def build_prompt(dimension: str, catalyst) -> str:
    """Assemble the full analyst prompt: job + hard tool-use/citation rules + catalyst context."""
    if dimension not in PROMPTS:
        raise ValueError(f"unknown analyst dimension: {dimension!r} (expected one of {list(PROMPTS)})")

    ticker = _get(catalyst, "ticker")
    company = _get(catalyst, "company_name") or ticker
    ctype = _get(catalyst, "catalyst_type")
    event_date = _get(catalyst, "event_date")
    catalyst_id = _get(catalyst, "catalyst_id")

    return f"""{PROMPTS[dimension]}

CATALYST UNDER ANALYSIS
  ticker:       {ticker}
  company:      {company}
  catalyst:     {ctype}
  event date:   {event_date}
  catalyst_id:  {catalyst_id}

HARD RULES (a source-cited signal, never LLM arithmetic):
  1. For ANY number, base rate, rNPV, runway, implied move, playbook, or historical analog,
     you MUST CALL the relevant `mcp__quant__*` tool (e.g. mcp__quant__base_rate,
     mcp__quant__rnpv, mcp__quant__cash_runway, mcp__quant__implied_move,
     mcp__quant__analog_query, mcp__quant__query_playbooks). NEVER compute, estimate, or
     recall a figure from memory — the quant/KB tools are the only source of numbers and analogs.
  2. Every key_finding MUST carry the exact evidence_ref the tool returned. A finding you
     cannot cite from a tool result does not go in the signal (cite-or-drop).
  3. Fill `unknowns` with the explicit gaps a tool could not close — an empty unknowns list
     means you did not look hard enough.
  4. Emit `dimension` EXACTLY as "{dimension}", with ticker "{ticker}" and catalyst_id
     "{catalyst_id}", and a score in [-1, 1] (bearish..bullish) with a calibrated confidence in [0, 1].
"""


async def run_analyst(
    dimension: str,
    catalyst,
    *,
    mcp_servers: dict | None = None,
    allowed_tools: list[str] | None = None,
    model: str = "sonnet",
) -> AnalystSignal:
    """Run one dimension analyst and return its validated, source-cited AnalystSignal.

    The caller (orchestrator) injects the quant MCP server + allowed `mcp__quant__*` tool
    names — this module never imports desk.tools, keeping it parallel to that plan. Runs on
    the cheaper `sonnet` tier by default (configured here, not hard-coded at each call site).
    Raises pydantic.ValidationError if the model returns an uncited/invalid payload.
    """
    prompt = build_prompt(dimension, catalyst)
    return await run_structured(
        prompt,
        AnalystSignal,
        mcp_servers=mcp_servers,
        allowed_tools=allowed_tools,
        model=model,
    )
