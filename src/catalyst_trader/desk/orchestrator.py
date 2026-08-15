"""Workflow-1a entry point: ``run_desk`` wires the analyst desk end-to-end.

catalyst -> four concurrent, source-cited analyst signals (``asyncio.gather``, isolated
SDK sessions) -> bounded bull/bear/moderator debate -> verifier-gated binary verdict.

A thin composition over the pieces built in Plans 03-06 — the only new logic is the
wiring: build the one in-process quant/KB MCP server, fan the analysts out, thread their
signals into the debate, then gate the verdict through source-quote-or-drop before it
finalizes. Every role call still routes through the ``desk.runtime.run_structured`` seam,
so the whole pipeline runs offline under test with zero live API.

# ponytail: the components are built; run_desk just threads them. No new logic, no config
#           object, no per-dimension registry — a gather + two awaits.
"""

import asyncio

from ..contracts import DebateVerdict
from . import MAX_ROUNDS, analysts, debate, verifier
from .tools import build_quant_server

DIMENSIONS = list(analysts.PROMPTS)  # clinical, regulatory, financial, market_sentiment

# The mcp__quant__* surface the analysts may call — the one "quant" server (desk.tools)
# wraps BOTH the quant and KB tools, so every allowed tool is quant-namespaced.
ALLOWED_TOOLS = [
    f"mcp__quant__{name}"
    for name in (
        "base_rate", "analog_query", "query_playbooks",
        "rnpv", "cash_runway", "implied_move", "correlation_beta",
    )
]


async def run_desk(conn, catalyst) -> DebateVerdict:
    """Run the full Workflow-1a desk for one catalyst and return the gated verdict.

    1. build the one in-process quant/KB MCP server (``conn`` captured in its closure);
    2. fan the four dimension analysts out concurrently (isolated sessions);
    3. run the bounded bull/bear/moderator debate over their signals;
    4. gate the verdict through the source-quote-or-drop verifier before returning.

    Raises ``verifier.VerdictUnsupportedError`` if no evidence survives the verifier —
    an unsupported verdict never finalizes.
    """
    srv = {"quant": build_quant_server(conn)}
    signals = await asyncio.gather(
        *[
            analysts.run_analyst(dim, catalyst, mcp_servers=srv, allowed_tools=ALLOWED_TOOLS)
            for dim in DIMENSIONS
        ]
    )
    verdict = await debate.run(signals, catalyst, rounds=MAX_ROUNDS)
    return await verifier.enforce(conn, verdict, signals=signals)
