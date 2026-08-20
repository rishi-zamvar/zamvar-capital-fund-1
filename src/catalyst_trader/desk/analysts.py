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
        "You are a PHYSICIAN-SCIENTIST (MD/PhD) serving as the clinical/scientific analyst. "
        "Reason from mechanistic biology upward: is the drug's mechanism of action causally "
        "plausible for this indication, and is the trial design valid — endpoint choice, "
        "statistical powering, control arm, blinding, and confounders? Decisively, judge "
        "whether the primary endpoint is clinically meaningful to patients, not merely "
        "statistically significant, and assess the causal plausibility of the efficacy signal. "
        "Weigh phase-transition odds and how mechanistically similar past readouts resolved."
    ),
    "regulatory": (
        "You are FDA REGULATORY COUNSEL (a lawyer) serving as the regulatory analyst. Reason to "
        "the procedural WHY: what was the FDA's ACTUAL deficiency or ask, which review pathway "
        "applies and what precedent binds it, and — for any AdCom — the panel voting dynamics and "
        "what a panel vote does and does not legally bind the agency to do. Read the relevant FDA "
        "guidance and statute the way regulatory counsel would, and reason from PDUFA/AdCom "
        "precedent for this therapeutic class, prior CRLs, and the review division's posture."
    ),
    "financial": (
        "You are a CFO serving as the financial analyst. Reason to the WHY behind the numbers: "
        "the balance-sheet and cash-runway mechanics into and past the catalyst, the STRUCTURE of "
        "any dilution or financing (ATM, shelf, convertible, warrant coverage), and — critically — "
        "what recent capital-markets moves (raises, ATM usage, insider buying or selling) SIGNAL "
        "about management's own conviction in the outcome. Judge financial resilience and the "
        "asset's risk-adjusted valuation sensitivity around the event."
    ),
    "market_sentiment": (
        "You are a BUY-SIDE PORTFOLIO MANAGER and market-microstructure specialist serving as the "
        "market/sentiment analyst. Reason to what is already PRICED IN: decompose the "
        "options-implied move vs realized analog moves, the options skew and short-interest "
        "mechanics, and the crowding/positioning — then ask who is on the other side of this trade "
        "and why. Microstructure is the point: identify where consensus positioning is fragile or "
        "already exhausted."
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
  5. LEAD with a `thesis`: 1-3 sentences stating your dimension-specific read of this catalyst
     ("here is my read"), consistent with your score/confidence. It MUST be a SYNTHESIS of your own
     cited key_findings — introduce NO claim that is not already in a cited finding (the thesis
     inherits their grounding; it is not a new uncited assertion).
  6. DEPTH (subordinate to rule 2): reason one level deeper than consensus — every finding states
     the WHY behind it (the mechanism, precedent, or cause), and surface at least one non-obvious
     second-order insight a generalist would miss. This depth is a deeper INTERPRETATION of evidence
     you have already tool-cited: introduce no new uncited claim. An insight without a supporting
     tool evidence_ref is dropped. Cite-or-drop (rule 2) always prevails over depth.
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
