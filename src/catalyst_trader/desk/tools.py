"""The analyst tool surface (CALL-01): quant/ + kb.py exposed as ONE in-process SDK MCP
server ("quant"), with the DB connection captured in the closure. Analysts CALL these
tools and interpret the output — they never compute money-math themselves.

Every result carries a resolvable citation so a cited number is structural, not a memory:
  * quant ToolResult tools -> ``tool_ref(result)`` (the inputs snapshot IS the citation).
  * analog_query / query_playbooks -> a ``tool:<fn>#<inputs_hash>`` ref minted BY CONSTRUCTION
    over the call inputs. These return catalyst/playbook NODE ids, not evidence_source ids,
    so they are cited like any other tool — NEVER as ``kb:<id>`` (a kb: ref fails
    desk.evidence.resolve and the Plan-06 verifier would silently drop the claim, breaking
    CALL-04 for every KB-analog/playbook-cited claim).
  * base_rate -> an INLINE citation dict (source_name/source_url/quote), embedded in the payload.

Offline: analog_query uses kb.default_embedder() (force offline with CT_EMBEDDER=hash).

# ponytail: wrap the subset the four analyst dimensions actually use (RESEARCH), not the whole
#           toolbox. cointegration is a Pipeline-2 pair-selection tool; add here when a desk
#           analyst needs it.
"""

import json

from claude_agent_sdk import create_sdk_mcp_server, tool

from catalyst_trader import kb, quant

from . import evidence


def _content(payload: dict) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, default=str)}]}


def _result_content(result) -> dict:
    """A quant ToolResult -> cited JSON: its value/detail plus a resolvable tool: ref."""
    return _content({**result.model_dump(), "evidence_ref": evidence.tool_ref(result)})


def build_quant_tools(conn) -> list:
    """The @tool wrappers over quant + kb, DB conn captured in the closure. Returned as a list
    so tests can call each handler directly; build_quant_server wraps them into the MCP server."""

    @tool("base_rate", "Look up a cited clinical base rate (LoA, phase-transition, etc.)",
          {"metric": str, "phase": str, "indication": str})
    async def _base_rate(args):
        try:
            r = quant.base_rate(args["metric"], phase=args.get("phase"), indication=args.get("indication"))
        except ValueError as e:
            return _content({"error": str(e)})  # analyst sees "no base rate", never a fabricated number
        return _content({
            "value": r["value"],
            "citation": {"source_name": r["source_name"], "source_url": r["source_url"], "quote": r["quote"]},
        })

    @tool("analog_query", "Nearest past catalysts (structural filter + semantic KNN) with realized outcomes",
          {"context": str, "filters": dict, "k": int, "as_of": str})
    async def _analog_query(args):
        context, filters, k = args["context"], args.get("filters") or {}, args.get("k", 5)
        as_of = args.get("as_of")  # None = no no-look-ahead gate; the live cutoff wires in later
        rows = kb.analog_query(conn, kb.default_embedder(), context, filters, k, as_of=as_of)
        ref = evidence.tool_ref_for("analog_query", {"context": context, "filters": filters, "k": k, "as_of": as_of})
        return _content({"results": rows, "evidence_ref": ref})

    @tool("query_playbooks", "Scenario playbooks for a scenario_type, confidence-desc",
          {"scenario_type": str})
    async def _query_playbooks(args):
        scenario_type = args["scenario_type"]
        rows = kb.query_playbooks(conn, scenario_type)
        ref = evidence.tool_ref_for("query_playbooks", {"scenario_type": scenario_type})
        return _content({"results": rows, "evidence_ref": ref})

    @tool("rnpv", "Risk-adjusted NPV of a pipeline asset", {"cashflows": list, "discount_rate": float, "costs": list})
    async def _rnpv(args):
        return _result_content(quant.rnpv(args["cashflows"], args["discount_rate"], costs=args.get("costs")))

    @tool("cash_runway", "Months of cash at current burn (funded-past-catalyst flag)",
          {"cash_usd": float, "monthly_burn_usd": float, "months_to_catalyst": float})
    async def _cash_runway(args):
        return _result_content(quant.cash_runway(
            args["cash_usd"], args["monthly_burn_usd"], months_to_catalyst=args.get("months_to_catalyst")))

    @tool("implied_move", "Options-implied event move (straddle / IV method)",
          {"underlying_price": float, "call_mid": float, "put_mid": float, "iv": float, "days_to_event": int})
    async def _implied_move(args):
        return _result_content(quant.implied_move(
            args["underlying_price"], call_mid=args.get("call_mid"), put_mid=args.get("put_mid"),
            iv=args.get("iv"), days_to_event=args.get("days_to_event")))

    @tool("correlation_beta", "Pair correlation + beta of asset vs market returns",
          {"asset_returns": list, "market_returns": list})
    async def _correlation_beta(args):
        return _result_content(quant.correlation_beta(args["asset_returns"], args["market_returns"]))

    return [_base_rate, _analog_query, _query_playbooks, _rnpv, _cash_runway, _implied_move, _correlation_beta]


def build_quant_server(conn):
    """One in-process SDK MCP server named "quant" wrapping the deterministic quant/KB tools."""
    return create_sdk_mcp_server(name="quant", version="1.0.0", tools=build_quant_tools(conn))
