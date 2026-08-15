---
phase: 04-analyst-desk-bull-bear-debate-workflow-1a
plan: 03
subsystem: desk
tags: [claude-agent-sdk, sdk-mcp-server, tool-wrappers, evidence-ref, quant, kb, call-01, call-04]

# Dependency graph
requires:
  - phase: 03-quant-tool-library-rubric-base-rates
    provides: quant.* ToolResult tools (frozen inputs snapshot = citation) + base_rate cited dict
  - phase: 02-contracts-knowledge-base-skeleton
    provides: kb.analog_query/query_playbooks/default_embedder, EvidenceSource, insert_playbook
  - phase: 04-analyst-desk-bull-bear-debate-workflow-1a
    plan: 02
    provides: desk.evidence tool_ref/resolve; run_structured SDK seam
provides:
  - "build_quant_server(conn) -> one in-process SDK MCP server named 'quant' wrapping quant/ + kb.py"
  - "build_quant_tools(conn) -> list[SdkMcpTool] (test seam: call each handler directly)"
  - "desk.evidence.tool_ref_for(name, inputs) — mint a resolvable tool: ref for non-ToolResult tool calls"
affects: [04-04-debate, 04-06-verifier, 04-07-orchestrator]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "@tool + create_sdk_mcp_server: quant/KB wrapped as ONE in-process server, DB conn in closure"
    - "Analysts CALL tools + interpret; the number AND its citation come from the tool, never model memory (CALL-01)"
    - "analog_query/query_playbooks cited as tool:<fn>#<inputs_hash> (resolved-by-construction), NEVER kb: (CALL-04)"
    - "base_rate carries an INLINE citation dict (source_name/url/quote); base_rate-miss is an error payload"

key-files:
  created:
    - src/catalyst_trader/desk/tools.py
    - tests/test_desk_tools.py
  modified:
    - src/catalyst_trader/desk/evidence.py

key-decisions:
  - "tool_ref delegates to a new tool_ref_for(name, inputs) so the KB-query mint reuses the SAME stable hash (no fork)"
  - "analog_query inputs-hash = {context, filters, k} (conn/embed excluded); query_playbooks = {scenario_type}"
  - "Wrapped the RESEARCH analyst subset (base_rate, analog_query, query_playbooks, rnpv, cash_runway, implied_move, correlation_beta); cointegration/iv_crush left to Pipeline-2/when-needed (ponytail)"
  - "build_quant_tools() split out from build_quant_server() so handlers are directly callable in tests (no live MCP runtime)"
  - "analog_query handler uses kb.default_embedder(); tests force offline via CT_EMBEDDER=hash"

metrics:
  duration: 4min
  completed: 2026-08-15
  tasks: 1
  files: 3
---

# Phase 4 Plan 3: Analyst Quant/KB Tool Surface Summary

The analyst desk's tool surface: `quant/` + `kb.py` wrapped as ONE in-process Claude Agent SDK
MCP server (`build_quant_server(conn)`, name `"quant"`) via `@tool` + `create_sdk_mcp_server`,
with the DB connection captured in the closure. This makes CALL-01's "source-cited" structural —
the number and its citation come from the deterministic tool, not the model's memory. Analysts
call and interpret; they never compute money-math.

## What was built

- `desk/tools.py`:
  - `build_quant_tools(conn)` — seven `@tool` wrappers (base_rate, analog_query, query_playbooks,
    rnpv, cash_runway, implied_move, correlation_beta), DB conn in the closure. Returned as a list
    so tests call each handler coroutine directly (no live MCP runtime).
  - `build_quant_server(conn)` — wraps them into the SDK MCP server named `"quant"`.
  - Each handler returns the SDK content shape `{"content":[{"type":"text","text":<json>}]}` where
    the JSON carries the value/detail AND a resolvable `evidence_ref`.
- `desk/evidence.py`: added `tool_ref_for(name, inputs)` reusing the existing `_inputs_hash`;
  `tool_ref(result)` now delegates to it (single hash implementation).

## Citation contract (the CALL-04 guard)

- quant ToolResult tools -> `tool_ref(result)` (the inputs snapshot IS the citation).
- analog_query / query_playbooks -> `tool:analog_query#<hash>` / `tool:query_playbooks#<hash>`,
  minted BY CONSTRUCTION over the call inputs — NEVER `kb:<id>`. These return catalyst/playbook
  NODE ids, not evidence_source ids, so a `kb:` ref would fail `desk.evidence.resolve()` and the
  Plan-06 verifier would silently drop the claim. Tests assert each minted ref round-trips through
  `resolve()` (non-None), not merely that it's non-empty.
- base_rate -> an INLINE citation dict (source_name/source_url/quote) embedded in the payload;
  base_rate-miss returns `{"error": "no base rate ..."}` so the analyst sees "no source", never a
  hallucinated number.

## Tests (offline, TDD)

`tests/test_desk_tools.py` (8 tests): server builds with name `quant`; rnpv/cash_runway/
implied_move/correlation_beta return refs that resolve; base_rate inline citation has source_url +
quote; base_rate-miss is an error payload; analog_query + query_playbooks cited as `tool:` refs
(not `kb:`) that resolve — the CALL-04 regression guard; analog ref is stable across identical
inputs. Offline via `CT_EMBEDDER=hash` (fastembed is installed, so default_embedder would otherwise
load a semantic model / touch the network).

## Deviations from Plan

None - plan executed exactly as written. (Wrapped the RESEARCH-named analyst subset; cointegration/
iv_crush deferred per the plan's ponytail note — "wrap what the four dimensions actually need.")

## Verification

- `grep create_sdk_mcp_server src/catalyst_trader/desk/tools.py` — matches.
- `grep -E "tool_ref|tool:analog_query|tool:query_playbooks" tools.py` — matches.
- `grep "kb:" tools.py` — only a docstring line explaining it is NEVER minted; no code path mints kb:.
- `pytest tests/test_desk_tools.py` — 8 passed; full suite 478 passed, no network.

## Self-Check: PASSED
- FOUND: src/catalyst_trader/desk/tools.py
- FOUND: tests/test_desk_tools.py
- FOUND: commit 4b48818
