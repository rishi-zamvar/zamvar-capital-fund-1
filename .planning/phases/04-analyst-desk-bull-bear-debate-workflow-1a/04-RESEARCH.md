# Phase 4: Analyst Desk + Bull/Bear Debate (Workflow 1a) - Research

**Researched:** 2026-08-14
**Domain:** Multi-agent orchestration on the Claude Agent SDK (Python) — analyst fan-out → isolated bull/bear debate → binary verdict, all source-grounded
**Confidence:** HIGH (SDK API verified against current official docs; existing contracts/tools read from source)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Runtime:** Claude Agent SDK (Python) for headless/scheduled orchestration (the T-2 trigger can't rely on an interactive session). Share `.claude/agents/` role defs where practical.
- **Borrow TradingAgents' *structure*** (bounded debate loop + manager synthesis + reflect-on-outcome memory) — re-express as our own agents. Do NOT vendor its LangGraph runtime.
- **Structured outputs via the Phase-2 `contracts` models** (`AnalystSignal`, `DebateVerdict`).
- **Agents never do money arithmetic** — analysts CALL the Phase-3 quant tools (rNPV, base-rate, implied-move, etc.) and interpret; they never compute.
- **Every claim is source-cited or dropped** — a fact-check verifier enforces this before the verdict finalizes.
- **Bull and Bear reason in REAL context isolation** — not fake consensus; the debate must name the losing side's strongest point.
- **Flat orchestrator → analyst fan-out** (no deep nesting).
- **Binary verdict + calibrated confidence + explicit kill/falsification criteria. NO sizing/positioning** (that's Phase 5).
- **Full TDD; agent logic tested with mocked/recorded LLM responses** — deterministic + offline, no live API in pytest.

### Claude's Discretion
Discuss skipped. Module layout (`desk/` vs `agents/`), exact debate-round cap, how the quant/KB tools are surfaced to agents, and the test-mocking seam are Claude's call — recommendations below.

### Deferred Ideas (OUT OF SCOPE)
Trade construction, hedge selection, sizing, positioning = Phase 5. Iteration/reflection loop + calibration scoring over time = Phase 10. This phase stops at the `DebateVerdict`.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CALL-01 | Four analysts (Clinical, Regulatory, Financial, Market) produce structured, source-cited signals | Analyst layer §2 + Code Example 2 (per-analyst `query()` with `output_format=AnalystSignal.model_json_schema()`, quant/KB tools via SDK MCP server); contract `AnalystSignal` already enforces ≥1 sourced `key_finding` |
| CALL-02 | Bull and Bear build opposing cases in **real context isolation** | §3 + Pattern 1 — separate `query()` calls, fresh session each (SDK: "each subagent runs in its own fresh conversation; only its final message returns"), orchestrator threads only shared evidence, never the other side's transcript |
| CALL-03 | Debate manager runs **bounded** rounds, emits **binary** verdict + **calibrated confidence** + **explicit falsification/kill criteria** | §4 + Pattern 1. **GAP: `DebateVerdict` is missing a `kill_criteria` field and `direction` is an unconstrained `str`** — must extend the contract (see Open Q1). Confidence anchored to `base_rate`/analog outcomes, not vibes |
| CALL-04 | Fact-check verifier enforces **source-quote-or-drop** on every claim | §5 + Pattern 3 — deterministic ref-resolve + quote-substring check in Python (KB `EvidenceSource`), LLM only for semantic support; runs before verdict finalizes |
</phase_requirements>

## Summary

This is the first agentic pipeline, and the cleanest way to build it is the **least agentic** one: the orchestrator is **plain async Python**, not an LLM deciding when to delegate. It calls the Agent SDK's `query()` once per role — four analysts (concurrently via `asyncio.gather`), then a bounded bull↔bear loop, then a moderator, then a verifier — threading a state dict between them exactly as TradingAgents threads its graph state. Each `query()` opens a fresh, isolated session, which *is* the real context isolation CALL-02 needs, and makes the "subagents can't nest" worry moot: nothing nests because the desk never uses the Agent tool for fan-out. Every agent emits a Pydantic contract via the SDK's `output_format` JSON-schema mode, so a hallucinated key or missing citation is rejected at `model_validate`, not trusted.

**One stale assumption to correct:** the CLAUDE.md/ARCHITECTURE "subagents can't nest" line is out of date. The current SDK *does* let subagents spawn subagents (default depth 3, capped via `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`). The flat fan-out is still the right design — but because we orchestrate in Python for determinism and testability, not because the SDK forbids nesting. Nothing in the plan changes; the *reason* does.

**Two contract gaps block CALL-03 as written:** `DebateVerdict` has no `kill_criteria`/falsification field and its `direction` is an unconstrained `str`. Both must be added (the contract's own comment says "extend a model when a layer needs a field"). Analysts also need the quant/KB functions surfaced as SDK tools (`@tool` + `create_sdk_mcp_server`, DB conn captured in the closure).

**Primary recommendation:** Build `desk/` as a Python asyncio orchestrator that calls `query()` per role with `output_format` bound to the (extended) contract schemas; wrap `quant/` + `kb.py` as one in-process SDK MCP server; test everything by monkeypatching a single `run_structured()` seam against recorded JSON fixtures — zero live API in the suite.

## Standard Stack

Stack is settled (STACK.md). Only the Phase-4-relevant surface, with versions verified against the local `pyproject.toml` + current SDK docs.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `claude-agent-sdk` (Python) | latest, Python ≥3.10 | Headless agent runtime: `query()`, `AgentDefinition`, `output_format`, `@tool`, `create_sdk_mcp_server` | Locked. Native structured output + in-process MCP tools + fresh-session isolation. **NOT yet in `pyproject.toml` — Wave 0 must add it to `[project.dependencies]`.** |
| `pydantic` | 2.13.4 (installed) | Contract models + `model_json_schema()` for `output_format` + `model_validate()` at the boundary | Already the anti-hallucination spine in `contracts/` and `quant/result.py`. |
| existing `catalyst_trader.quant` | in-repo | Deterministic money-math the analysts call (never compute) | `base_rate`, `rnpv`, `cash_runway`, `implied_move`, `iv_crush`, `correlation_beta`, `cointegration`, `score_rubric` — all return `ToolResult`/dict with a verbatim inputs snapshot = the citation. |
| existing `catalyst_trader.kb` | in-repo | `analog_query(conn, embed, context, filters, k)`, `base_rate` provenance, `query_playbooks` | Gives analysts cited analogs + base rates; every KB claim carries a `:CITES` EvidenceSource. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` + `pytest-httpx` + `freezegun` | 9.1.1 / 0.36.2 / 1.5.5 (installed) | Test harness; freeze `now()` for T-2 logic; block any stray HTTP | Every test. |
| `asyncio` (stdlib) | — | `query()` is async; `asyncio.gather` fans out the 4 analysts concurrently | Orchestrator core. |

**Installation (Wave 0):**
```bash
# add to [project.dependencies] in pyproject.toml, then:
pip install claude-agent-sdk
```

**Version verification:** `pyproject.toml` pins pydantic 2.13.4, pytest 9.1.1 (verified by reading the file). `claude-agent-sdk` is **not currently a dependency** — confirm the resolved version at install time (`pip show claude-agent-sdk`); docs reference features from Python SDK v0.2.127+ / Claude Code v2.1.219+ (depth/concurrency/budget caps). UNVERIFIED: exact pinned version to use — pin whatever `pip install` resolves and record it.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Python-orchestrated `query()` per role | LLM-driven `agents={...}` + Agent-tool delegation | Agent-tool delegation is non-deterministic (model *decides* to delegate), harder to test, and re-introduces the nesting/concurrency-cap questions. Python orchestration is the ponytail-correct, testable default. Keep `.claude/agents/*.md` as human-readable role docs / interactive-CC parity, but the SDK path drives from Python. |
| Extend `DebateVerdict` | New separate verdict model | Contract comment explicitly says extend-when-needed; downstream Phase-5 already imports `DebateVerdict`. Extend it. |

## Architecture Patterns

### Recommended Project Structure
```
src/catalyst_trader/
└── desk/                    # new — the Workflow-1a orchestrator
    ├── __init__.py          # run_desk(conn, catalyst) -> DebateVerdict  (public entry)
    ├── runtime.py           # run_structured(prompt, schema, tools, model) — the ONE SDK seam (mockable)
    ├── tools.py             # @tool wrappers over quant/ + kb.py → create_sdk_mcp_server("quant", conn)
    ├── analysts.py          # 4 analyst prompts + run_analyst(dimension, catalyst, tools) -> AnalystSignal
    ├── debate.py            # bounded bull/bear loop + moderator -> DebateVerdict
    └── verifier.py          # source-quote-or-drop check (deterministic + optional LLM support-check)
.claude/agents/             # optional: human-readable role defs, parity with interactive CC
```
`ponytail: one module tree, one SDK seam. Don't build an agent-registry/factory abstraction for 7 fixed roles — 7 functions + 4 prompt strings is the whole desk.`

### Pattern 1: Bounded adversarial debate with a Python-driven loop
**What:** The orchestrator (plain Python) runs analysts concurrently, then a `for round in range(MAX_ROUNDS)` loop alternating bull/bear `query()` calls, then one moderator `query()`. Each side's `query()` is a fresh session and receives **only** the shared `AnalystSignal[]` + the *text* of the opposing side's prior argument — never the opposing agent's transcript or scratchpad. That is the real isolation (SDK: "each subagent runs in its own fresh conversation, with no parent conversation... only its final message returns").
**When to use:** the whole research layer.
**Trade-offs:** + deterministic, testable, truly isolated; − N rounds = N×2 LLM calls (cap `MAX_ROUNDS` at 2 — TradingAgents' `max_debate_rounds`; small book, cost-bound not throughput-bound).

### Pattern 2: Structured output as the trust boundary
**What:** Every role `query()` sets `output_format={"type": "json_schema", "schema": Model.model_json_schema()}`; the orchestrator then `Model.model_validate(json.loads(result))`. `extra="forbid"` + bounded fields + required `evidence_ref` reject a bad payload before any downstream layer sees it.
**When:** every agent call.
**Trade-offs:** + schema is the contract, enforced not requested; − the model must produce valid JSON (retry once on validation error — cheap).

### Pattern 3: Provenance / source-quote-or-drop verifier
**What:** Before finalizing, resolve every `evidence_ref` in the verdict against the KB `EvidenceSource` (url + retrieved-at + snippet-hash + quote). The *structural* half — ref resolves, quote is a substring of the source snippet — is plain Python and needs no LLM. Only the *semantic* half ("does this quote actually support this claim") needs a model call, and only for load-bearing claims.
**When:** CALL-04 gate before the verdict returns.
**Trade-offs:** + most of the check is free + deterministic; − dropping a load-bearing claim may force a re-run (acceptable on real money).

### Anti-Patterns to Avoid
- **LLM-driven fan-out via the Agent tool** for the fixed 7-role desk: non-deterministic, re-opens nesting/concurrency caps, hard to unit-test. Orchestrate in Python.
- **Sharing one conversation/`ClaudeSDKClient` across bull + bear**: launders consensus, kills CALL-02. Separate `query()` calls only.
- **Analysts computing numbers in-prompt**: violates the hard constraint. They call `mcp__quant__*` tools and cite the `ToolResult` (tool + inputs snapshot + version).
- **Trusting the model's confidence as a vibe**: anchor it to `base_rate`/analog outcomes (see CALL-03).
- **Live API calls in pytest**: every test must run offline via the `run_structured` mock.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Structured JSON from the model | Regex/parse free text + hand-validate | SDK `output_format` json_schema + `pydantic.model_validate` | SDK enforces schema server-side; pydantic rejects the rest. |
| Exposing quant/KB fns to agents | Custom prompt-injection of tool docs | `@tool` + `create_sdk_mcp_server` (in-process MCP) | First-party, typed, no subprocess; conn captured in closure. |
| Money math inside the agent | Any arithmetic in a prompt | `catalyst_trader.quant` tools | Deterministic, versioned, reproducible (`ToolResult.inputs`); the hard constraint. |
| Base rates / analogs | LLM "recalling" a success rate | `quant.base_rate` / `kb.analog_query` | Both raise/return-empty rather than hallucinate; carry citations. |
| Context isolation | Manual "please ignore the other side" prompt | Separate `query()` sessions | Isolation is structural (fresh session), not a polite request. |
| Debate loop / state threading | A graph engine (LangGraph) | A Python `for` loop + a dict | TradingAgents' loop is ~a bounded counter + a manager call. Don't vendor a runtime. |

**Key insight:** the "agent framework" here is a 150-line async orchestrator. The heavy lifting (validation, tools, provenance) already exists in Phases 1–3; Phase 4 wires them, it doesn't rebuild them.

## Common Pitfalls

### Pitfall 1: `output_format` is per-query, not per-agent-definition
**What goes wrong:** trying to attach different schemas to `agents={...}` entries. `output_format` lives on `ClaudeAgentOptions` for the whole `query()`.
**Why it happens:** conflating the programmatic-subagent API with the Python-orchestration approach.
**How to avoid:** one `query()` per role, each with its own `output_format` = that role's contract schema. (Another reason to orchestrate in Python.)
**Warning signs:** wanting a single `query()` to emit four different `AnalystSignal`s.

### Pitfall 2: `.claude/agents/` files won't load in the SDK without `setting_sources`
**What goes wrong:** role `.md` files silently ignored.
**Why:** the SDK loads filesystem settings only when `setting_sources` includes `"project"`; programmatic `agents=`/prompts take precedence anyway.
**How to avoid:** drive role prompts from Python (pass the prompt string to `query()`); treat `.claude/agents/*.md` as documentation/interactive-parity, not the SDK source of truth. If you *do* want them loaded, set `setting_sources=["project"]`.

### Pitfall 3: `DebateVerdict` can't express CALL-03 as-is
**What goes wrong:** no field for falsification/kill criteria; `direction` accepts any string, so "binary" isn't enforced.
**How to avoid:** extend the contract (Open Q1) — add `kill_criteria: list[str]` (non-empty), constrain `direction: Literal["positive", "negative"]`. Add the tests first (TDD).
**Warning signs:** the verdict validates but has no kill criteria.

### Pitfall 4: sqlite-vec extension loading in the test process
**What goes wrong:** KB `analog_query` needs the sqlite-vec extension; macOS system Python often disables `enable_load_extension`.
**Why:** noted in STACK.md version-compat.
**How to avoid:** the existing `tests/conftest.py` `db` fixture already migrates an in-memory DB and KB tests already pass — reuse that fixture; the offline `hash_embed` embedder (`embed` fixture) keeps analog tests deterministic with no model download.

### Pitfall 5: confidence as vibes (CALL-03 "calibrated")
**What goes wrong:** the model emits `confidence: 0.9` ungrounded.
**How to avoid:** require confidence to be justified against a cited `base_rate` value and/or the realized outcomes of `analog_query` hits, and to fall when `unknowns[]` is non-empty. Full calibration *scoring* (Brier over realized outcomes) is Phase 10 — out of scope; here, elicit-and-ground only.

## Code Examples

Verified against current official SDK docs (see Sources). Illustrative — adapt field names to the repo.

### Example 1: The one SDK seam (`runtime.run_structured`) — the mock point
```python
# src/catalyst_trader/desk/runtime.py
import json
from typing import Type
from pydantic import BaseModel
from claude_agent_sdk import query, ClaudeAgentOptions

async def run_structured(
    prompt: str,
    schema: Type[BaseModel],
    *,
    mcp_servers: dict | None = None,
    allowed_tools: list[str] | None = None,
    model: str = "sonnet",
) -> BaseModel:
    """Single choke point for every agent call. Tests monkeypatch THIS with recorded JSON —
    nothing else touches the SDK, so the suite runs offline."""
    opts = ClaudeAgentOptions(
        output_format={"type": "json_schema", "schema": schema.model_json_schema()},
        mcp_servers=mcp_servers or {},
        allowed_tools=allowed_tools or [],
        model=model,
        # ponytail: no Agent tool in allowed_tools -> desk never spawns subagents; fan-out is Python.
    )
    result_text = None
    async for message in query(prompt=prompt, options=opts):
        if hasattr(message, "result"):
            result_text = message.result
    return schema.model_validate(json.loads(result_text))  # boundary rejection lives here
```

### Example 2: Quant/KB tools as an in-process SDK MCP server
```python
# src/catalyst_trader/desk/tools.py
import json
from claude_agent_sdk import tool, create_sdk_mcp_server
from catalyst_trader import quant, kb

def build_quant_server(conn):
    @tool("base_rate", "Look up a cited clinical base rate", {"metric": str, "phase": str, "indication": str})
    async def _base_rate(args):
        r = quant.base_rate(args["metric"], phase=args.get("phase"), indication=args.get("indication"))
        return {"content": [{"type": "text", "text": json.dumps(r)}]}  # value + source_name/url/quote

    @tool("analog_query", "Nearest past catalysts + realized outcomes", {"context": str, "filters": dict})
    async def _analog(args):
        rows = kb.analog_query(conn, kb.default_embedder(), args["context"], args["filters"])
        return {"content": [{"type": "text", "text": json.dumps(rows)}]}

    # ... rnpv, cash_runway, implied_move, correlation_beta similarly (each returns ToolResult -> json)
    return create_sdk_mcp_server(name="quant", version="1.0.0", tools=[_base_rate, _analog])
# analyst call: allowed_tools=["mcp__quant__base_rate", "mcp__quant__analog_query", ...]
```

### Example 3: Analyst fan-out (concurrent) + bounded debate (Python loop)
```python
# src/catalyst_trader/desk/__init__.py  (sketch)
import asyncio
from catalyst_trader.contracts import AnalystSignal, DebateVerdict
from .runtime import run_structured
from .tools import build_quant_server
from . import analysts, debate, verifier

MAX_ROUNDS = 2  # TradingAgents max_debate_rounds; cost-bound

async def run_desk(conn, catalyst) -> DebateVerdict:
    srv = {"quant": build_quant_server(conn)}
    tools = ["mcp__quant__base_rate", "mcp__quant__analog_query"]  # + others per dimension
    signals: list[AnalystSignal] = await asyncio.gather(*[
        run_structured(analysts.prompt(dim, catalyst), AnalystSignal, mcp_servers=srv, allowed_tools=tools)
        for dim in ("clinical", "regulatory", "financial", "market_sentiment")
    ])  # 4 fresh isolated sessions, concurrent
    verdict = await debate.run(signals, catalyst, rounds=MAX_ROUNDS)  # bull/bear/moderator, isolated
    return verifier.enforce(conn, verdict)  # source-quote-or-drop before returning (CALL-04)
```

### Example 4: Deterministic test — recorded responses, no live API
```python
# tests/test_desk_analysts.py
import pytest
from catalyst_trader.contracts import AnalystSignal
from catalyst_trader.desk import analysts

@pytest.mark.asyncio
async def test_clinical_analyst_emits_sourced_signal(monkeypatch, load_fixture):
    recorded = load_fixture("agent_responses/clinical_signal")  # canned JSON dict
    async def fake_run_structured(prompt, schema, **kw):
        return schema.model_validate(recorded)
    monkeypatch.setattr("catalyst_trader.desk.analysts.run_structured", fake_run_structured)
    sig = await analysts.run_analyst("clinical", catalyst=..., tools=[])
    assert sig.dimension == "clinical"
    assert sig.key_findings and all(f.evidence_ref for f in sig.key_findings)  # CALL-01 cite-or-drop
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| "SDK subagents can't nest" (STACK.md / ARCHITECTURE / inference.net guide) | Subagents **can** nest; depth capped by `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` (default 3, set 1 to disable) | Claude Code ~v2.1.198+ | Flat fan-out is a *design choice* (we orchestrate in Python), not an SDK limit. No plan change; corrects the rationale. |
| Agent tool named `"Task"` | Renamed `"Agent"` (both still appear in some fields) | Claude Code v2.1.63 | Only matters if you detect delegation; we don't delegate. |
| `claude-code-sdk` | `claude-agent-sdk` (`pip install claude-agent-sdk`) | 2025 rename | Use the new package name. |

**Deprecated/outdated:**
- Treating "no nested subagents" as a hard constraint — stale.
- Any plan to vendor TradingAgents/LangGraph — explicitly rejected (borrow structure only).

## Open Questions

1. **`DebateVerdict` contract extension (blocks CALL-03).** 
   - What we know: current fields are `thesis, direction(str), confidence, bull_strongest_point, bear_strongest_point, unresolved_dissent[], evidence_refs[]`. No kill/falsification field; `direction` unconstrained.
   - What's unclear: exact field name/shape.
   - Recommendation: add `kill_criteria: list[str]` (require non-empty via a validator, mirroring `AnalystSignal._at_least_one_sourced_finding`) and constrain `direction: Literal["positive", "negative"]` for binary. TDD: write the contract tests first. Low risk — additive; Phase-5 consumers gain a field.

2. **How the verifier resolves an `evidence_ref`.** 
   - What we know: KB `EvidenceSource` carries url + retrieved-at + snippet-hash + quote; `insert_claim` links claims to sources.
   - What's unclear: whether `evidence_ref` strings emitted by analysts are KB node ids, source ids, or free strings.
   - Recommendation: standardize `evidence_ref` to a KB `EvidenceSource` id (or a `tool:<name>#<inputs-hash>` for quant-derived claims) so the verifier can resolve deterministically. Decide in Wave 0 with the contract extension.

3. **`dimension` value alignment.** `AnalystSignal.dimension` is a free `str`; ARCHITECTURE uses `clinical|regulatory|financial|market_sentiment`. 
   - Recommendation: keep `str` but have analysts emit those four exact tokens; assert on them in tests. (Optionally tighten to `Literal` — low priority.)

4. **Model tiering (cost).** 
   - Recommendation (from ARCHITECTURE scaling note): cheaper model (`sonnet`/`haiku`) for the 4 analysts, strongest (`opus`) for moderator + verifier where judgment is load-bearing. Confirm against TOKEN-NOTES.md directives when planning.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `claude-agent-sdk` (Python pkg) | All agent calls | ✗ (not in pyproject) | — | **Blocking — Wave 0 must add + install.** |
| Claude Code CLI / auth on host | SDK subprocess runtime | Assumed (interactive CC in use) | — | Tests never call it (mocked); only live runs need it. |
| `pydantic` 2.13.4 | contracts + schema | ✓ | 2.13.4 | — |
| `pytest`/`pytest-httpx`/`freezegun` | test suite | ✓ | 9.1.1 / 0.36.2 / 1.5.5 | — |
| `sqlite-vec` | KB analog_query | ✓ | ≥0.1.9 | offline `hash_embed` for tests |
| existing `quant/` + `kb.py` + `contracts/` | tools + shapes | ✓ | in-repo | — |

**Missing dependencies with no fallback:**
- `claude-agent-sdk` — add to `[project.dependencies]` and `pip install` in Wave 0. Everything else exists.

**Missing dependencies with fallback:**
- Live model auth — not needed for the offline test suite (the `run_structured` mock replaces it).

## Validation Architecture

Nyquist validation is enabled (`config.json workflow.nyquist_validation: true`).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (+ pytest-httpx 0.36.2, freezegun 1.5.5) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths=["tests"]`, `addopts="-ra"`) |
| Quick run command | `pytest tests/test_desk_*.py -x` |
| Full suite command | `pytest -q` |
| Async note | `query()` is async → add `pytest-asyncio` (or `anyio`) in Wave 0; **not currently a dev dep** — Wave 0 gap. |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CALL-01 | 4 analysts each emit a schema-valid, ≥1-sourced `AnalystSignal`; dimensions correct | unit (mocked model) | `pytest tests/test_desk_analysts.py -x` | ❌ Wave 0 |
| CALL-01 | Uncited finding is rejected at the boundary | unit | `pytest tests/test_desk_analysts.py::test_uncited_finding_rejected -x` | ❌ Wave 0 |
| CALL-02 | Bull & Bear run as separate isolated sessions; neither receives the other's transcript (only prior-argument text + shared signals) | unit (assert on `run_structured` call args) | `pytest tests/test_desk_debate.py::test_bull_bear_context_isolation -x` | ❌ Wave 0 |
| CALL-02 | Debate is bounded to `MAX_ROUNDS` calls | unit (count mock invocations) | `pytest tests/test_desk_debate.py::test_debate_is_bounded -x` | ❌ Wave 0 |
| CALL-02 | Moderator verdict names the losing side's strongest point | unit | `pytest tests/test_desk_debate.py::test_verdict_names_losing_side -x` | ❌ Wave 0 |
| CALL-03 | Verdict `direction` is binary (`positive`/`negative`), non-binary rejected | unit (contract) | `pytest tests/test_contracts.py::test_debate_verdict_direction_binary -x` | ⚠️ extend `test_contracts.py` |
| CALL-03 | Verdict carries non-empty `kill_criteria`; empty rejected | unit (contract) | `pytest tests/test_contracts.py::test_debate_verdict_requires_kill_criteria -x` | ⚠️ extend `test_contracts.py` |
| CALL-03 | Confidence is grounded in a cited base_rate/analog, not free-floating | unit | `pytest tests/test_desk_debate.py::test_confidence_is_grounded -x` | ❌ Wave 0 |
| CALL-03 | No sizing/positioning fields leak into the verdict | unit | `pytest tests/test_desk_debate.py::test_no_positioning_in_verdict -x` | ❌ Wave 0 |
| CALL-04 | Verifier drops a claim whose `evidence_ref` doesn't resolve / quote doesn't support | unit | `pytest tests/test_desk_verifier.py::test_source_quote_or_drop -x` | ❌ Wave 0 |
| CALL-04 | Verifier runs before the verdict returns (dropping a load-bearing claim blocks finalize) | unit | `pytest tests/test_desk_verifier.py::test_verifier_gates_finalize -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_desk_*.py tests/test_contracts.py -x`
- **Per wave merge:** `pytest -q`
- **Phase gate:** full suite green before `/gsd:verify-work`.

### Wave 0 Gaps
- [ ] Add `claude-agent-sdk` to `[project.dependencies]`; `pip install`; record resolved version.
- [ ] Add `pytest-asyncio` (or `anyio`) to `[project.optional-dependencies].dev` for `async def` tests.
- [ ] Extend `contracts/DebateVerdict`: `kill_criteria: list[str]` (non-empty validator) + `direction: Literal["positive","negative"]`; add tests to `tests/test_contracts.py`.
- [ ] `tests/fixtures/agent_responses/*.json` — recorded model outputs per role (clinical/regulatory/financial/market signal, bull, bear, moderator, verifier) for offline replay.
- [ ] `tests/test_desk_analysts.py`, `test_desk_debate.py`, `test_desk_verifier.py` — new suites (monkeypatch `run_structured`).
- [ ] Standardize `evidence_ref` format so the verifier can resolve it against the KB (Open Q2).

## Sources

### Primary (HIGH confidence)
- Claude Agent SDK — Subagents (SDK): https://code.claude.com/docs/en/agent-sdk/subagents — `AgentDefinition` fields, programmatic vs filesystem defs, **nesting + depth/concurrency/budget caps**, fresh-session isolation, "only final message returns," Agent-tool rename.
- Claude Agent SDK — Python reference: https://code.claude.com/docs/en/agent-sdk/python — `query()`, `ClaudeSDKClient`, `ClaudeAgentOptions` (`agents`, `mcp_servers`, `allowed_tools`, `setting_sources`, `output_format`), `@tool`, `create_sdk_mcp_server`, `output_format` json_schema.
- In-repo source (read directly): `contracts/__init__.py` (AnalystSignal/DebateVerdict shapes + validators), `quant/__init__.py` + `quant/result.py` (tool surface, ToolResult), `kb.py` (`analog_query`, `base_rate` provenance), `calendar/triggers.py` (`register_callback` T-2 seam), `tests/conftest.py` (db/embed/frozen fixtures), `pyproject.toml` (versions), `data/base_rates.csv` (available metrics).
- `.planning/REQUIREMENTS.md` — CALL-01..04 exact text.

### Secondary (MEDIUM confidence)
- `.planning/research/ARCHITECTURE.md` + STACK.md (CLAUDE.md) — org chart, TradingAgents borrow-not-fork, contract set, model tiering. (Corrected on the "can't nest" point above.)
- TradingAgents (borrowed structure only): https://github.com/TauricResearch/TradingAgents — `max_debate_rounds`, manager synthesis, state dict.

### Tertiary (LOW confidence / flagged)
- Exact `claude-agent-sdk` version to pin — UNVERIFIED; resolve at `pip install`.

## Metadata

**Confidence breakdown:**
- SDK API (query/output_format/@tool/isolation/nesting): HIGH — current official docs, read in full.
- Existing contracts/tools/KB surface: HIGH — read from source.
- Contract-gap findings (kill_criteria, binary direction): HIGH — read the model definition directly.
- Exact SDK version + evidence_ref format convention: LOW/MEDIUM — resolve in Wave 0.

**Research date:** 2026-08-14
**Valid until:** ~2026-09-14 (SDK is fast-moving — re-verify the subagents/python doc pages if planning slips a month; the nesting/caps behavior changed within recent point releases).
