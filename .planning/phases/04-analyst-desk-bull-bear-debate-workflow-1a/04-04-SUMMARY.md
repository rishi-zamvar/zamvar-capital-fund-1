---
phase: 04-analyst-desk-bull-bear-debate-workflow-1a
plan: 04
subsystem: desk
tags: [analysts, call-01, run-structured, source-cited, sonnet-tier, mcp-quant, offline-tdd]

# Dependency graph
requires:
  - phase: 04-analyst-desk-bull-bear-debate-workflow-1a
    plan: 02
    provides: desk.runtime.run_structured SDK seam (output_format json_schema -> model_validate boundary)
  - phase: 04-analyst-desk-bull-bear-debate-workflow-1a
    plan: 03
    provides: build_quant_server(conn) — ONE "quant" MCP server; every tool is mcp__quant__*
  - phase: 02-contracts-knowledge-base-skeleton
    provides: AnalystSignal / KeyFinding contracts (>=1 sourced finding required at the boundary)
provides:
  - "desk.analysts.run_analyst(dimension, catalyst, *, mcp_servers, allowed_tools, model=sonnet) -> AnalystSignal"
  - "desk.analysts.PROMPTS — four dimension job strings + build_prompt() assembling the call-tools/cite rules"
  - "Four recorded schema-valid AnalystSignal fixtures for offline replay"
affects: [04-05-debate, 04-06-verifier, 04-07-orchestrator]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Analyst layer = 4 job strings + 1 build_prompt + 1 run_analyst seam call (no prompt-registry, no per-dimension classes)"
    - "Prompts MANDATE calling mcp__quant__* for every number/base-rate/analog and citing the returned evidence_ref — never LLM arithmetic (CALL-01)"
    - "Model tier configured once (default sonnet) on run_analyst, not hard-coded per call site"
    - "run_analyst never imports desk.tools — orchestrator injects mcp_servers + allowed_tools (keeps this plan parallel to Plan 03)"

key-files:
  created:
    - src/catalyst_trader/desk/analysts.py
    - tests/fixtures/agent_responses/clinical_signal.json
    - tests/fixtures/agent_responses/regulatory_signal.json
    - tests/fixtures/agent_responses/financial_signal.json
    - tests/fixtures/agent_responses/market_sentiment_signal.json
    - tests/test_desk_analysts.py
  modified: []

key-decisions:
  - "There is NO mcp__kb__* namespace — every tool is mcp__quant__* (single quant server wraps quant+KB); prompt wording + a grep guard enforce it"
  - "_get() reads ticker/company/type/date/catalyst_id from either a Catalyst model OR a plain dict — orchestrator supplies either shape"
  - "Uncited-rejected test runs through the REAL run_structured (only SDK query faked) so it exercises the actual model_validate boundary, and asserts the exact pydantic.ValidationError, not a blind Exception"
  - "Fixtures cite tool:<fn>#<hash> refs only — consistent with Plan-03's CALL-04 rule (analog/playbook are tool: refs, never kb:)"

metrics:
  duration: 4min
  completed: 2026-08-15
  tasks: 1
  files: 6
---

# Phase 4 Plan 4: Analyst Layer (four source-cited AnalystSignals) Summary

The analyst layer for CALL-01: four dimension-specific prompts (Clinical, Regulatory, Financial,
Market/Sentiment) and one `run_analyst()` that calls the `run_structured` seam bound to the
`AnalystSignal` schema. Each analyst interprets tool output and emits a source-cited signal; the
schema boundary rejects any uncited/invalid payload. Analysts are the evidence producers the
Bull/Bear debate (Plan 05) consumes.

## What was built

- `desk/analysts.py`:
  - `PROMPTS` — a dict of four dimension -> job string (clinical, regulatory, financial,
    market_sentiment).
  - `build_prompt(dimension, catalyst)` — assembles the job + the HARD rules (call the relevant
    `mcp__quant__*` tool for ANY number/base-rate/rNPV/runway/implied-move/analog/playbook and cite
    the returned evidence_ref; never compute or recall; fill `unknowns`; emit the exact dimension
    token, ticker, catalyst_id, and a bounded score/confidence) + the catalyst context. Reads the
    catalyst as either a `models.Catalyst` or a plain dict via `_get()`.
  - `async def run_analyst(dimension, catalyst, *, mcp_servers=None, allowed_tools=None,
    model="sonnet") -> AnalystSignal` — builds the prompt and calls `run_structured` with the
    `AnalystSignal` schema, threading the caller-injected server/tool-names and the cheaper
    `sonnet` tier. Does NOT import `desk.tools` (orchestrator injects the server).
- Four recorded fixtures (`tests/fixtures/agent_responses/{clinical,regulatory,financial,
  market_sentiment}_signal.json`) — each a schema-valid AnalystSignal with >=1 cited finding and a
  non-empty `unknowns` list, for offline replay.

## Tests (offline, TDD)

`tests/test_desk_analysts.py` (7 tests):
- Parametrized over the four dimensions: with `run_structured` faked to return the matching
  recorded fixture, `run_analyst` returns an `AnalystSignal` whose `.dimension` equals the token,
  every finding has a non-empty `evidence_ref`, and `unknowns` is non-empty.
- Sonnet tier + tool injection: a capturing fake asserts `model="sonnet"`, and that the caller's
  `mcp_servers`/`allowed_tools`/`AnalystSignal` schema are threaded into the seam.
- Prompt guard: `build_prompt` contains `mcp__quant__`, the dimension token, and the ticker.
- `test_uncited_finding_rejected`: a recorded payload with `key_findings=[]` is rejected — run
  through the REAL `run_structured` (only the SDK `query` faked), asserting the exact
  `pydantic.ValidationError`. Proves the boundary, not a stub.

## Deviations from Plan

None - plan executed exactly as written.

(One in-test fix during GREEN: the fake `run_structured` helper's return variable was named
`model`, shadowing its own `model="sonnet"` kwarg — renamed to `signal`. A test-harness bug caught
by RED, not a code deviation.)

## Verification

- `grep "async def run_analyst" analysts.py` — matches (line 86).
- `grep -E "clinical|regulatory|financial|market_sentiment" analysts.py` — all four tokens present.
- `grep "mcp__quant__" analysts.py` — 5 matches (prompts instruct tool use).
- `grep "mcp__kb__" analysts.py` — 0 (that namespace does not exist).
- `grep 'model: str = "sonnet"' analysts.py` — matches (line 92).
- `ruff check` — all checks passed.
- `pytest tests/test_desk_analysts.py` — 7 passed; full suite **485 passed**, no network.

## Self-Check: PASSED
- FOUND: src/catalyst_trader/desk/analysts.py
- FOUND: tests/test_desk_analysts.py
- FOUND: tests/fixtures/agent_responses/clinical_signal.json
- FOUND: tests/fixtures/agent_responses/regulatory_signal.json
- FOUND: tests/fixtures/agent_responses/financial_signal.json
- FOUND: tests/fixtures/agent_responses/market_sentiment_signal.json
- FOUND: commit 4128df7 (test)
- FOUND: commit 2eb2c40 (feat)
