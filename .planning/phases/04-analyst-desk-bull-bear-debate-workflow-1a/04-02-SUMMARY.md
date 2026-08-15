---
phase: 04-analyst-desk-bull-bear-debate-workflow-1a
plan: 02
subsystem: testing
tags: [claude-agent-sdk, pytest-asyncio, structured-output, pydantic, evidence-ref, kb]

# Dependency graph
requires:
  - phase: 02-contracts-knowledge-base-skeleton
    provides: AnalystSignal/DebateVerdict contracts, kb.get_node/insert_claim, EvidenceSource
  - phase: 03-quant-tool-library-rubric-base-rates
    provides: ToolResult (frozen inputs snapshot = the citation)
provides:
  - "run_structured() — the single SDK seam every desk role call routes through"
  - "MAX_ROUNDS=2 debate cap constant"
  - "evidence_ref mint/resolve helpers (kb:<id> and tool:<name>#<hash>)"
  - "quote_supported() deterministic substring gate (source-quote-or-drop, structural half)"
  - "recorded-JSON-fixture offline replay harness for all agent tests"
affects: [04-03-analysts, 04-04-debate, 04-05-tools, 04-06-verifier, 04-07-orchestrator]

# Tech tracking
tech-stack:
  added: [claude-agent-sdk==0.2.139, pytest-asyncio]
  patterns:
    - "One SDK seam: run_structured is the ONLY claude_agent_sdk touchpoint; tests monkeypatch it (or its query binding)"
    - "output_format json_schema bound to the contract; model_validate is the trust boundary on the return line"
    - "evidence_ref: kb:<node_id> resolves via KB, tool:<name>#<hash> resolved-by-construction"

key-files:
  created:
    - src/catalyst_trader/desk/__init__.py
    - src/catalyst_trader/desk/runtime.py
    - src/catalyst_trader/desk/evidence.py
    - tests/test_desk_runtime.py
    - tests/test_desk_evidence.py
    - tests/fixtures/agent_responses/sample_analyst_signal.json
    - tests/fixtures/agent_responses/README.md
  modified:
    - pyproject.toml

key-decisions:
  - "claude-agent-sdk pinned to 0.2.139 (resolved at install; RESEARCH flagged version as UNVERIFIED)"
  - "asyncio_mode=auto so async def tests need no per-test marker"
  - "run_structured retries once on ValidationError only (no backoff) — malformed JSON propagates immediately"
  - "tool_ref hashes json.dumps(inputs, sort_keys=True) -> order-independent, reproducible 12-hex ref"
  - "resolve() returns None for a kb: ref pointing at a non-evidence_source node — verifier drops the claim"

patterns-established:
  - "Offline replay: one JSON fixture per recorded role response; tests monkeypatch run_structured or desk.runtime.query"
  - "Structural-vs-semantic split: evidence.py does deterministic resolution + substring gate; LLM support-check deferred to Plan 06 verifier"

requirements-completed: [CALL-01, CALL-04]

# Metrics
duration: 4min
completed: 2026-08-15
---

# Phase 4 Plan 2: Async Foundation (SDK seam + evidence_ref) Summary

**The single `run_structured()` SDK seam (output_format json_schema → pydantic model_validate), the `evidence_ref` mint/resolve module (`kb:<id>` via KB, `tool:<name>#<hash>` by-construction), and the recorded-JSON-fixture harness that makes every Wave-2 agent test run offline.**

## Performance

- **Duration:** ~4 min
- **Completed:** 2026-08-15
- **Tasks:** 3
- **Files modified:** 8 (7 created, 1 modified)

## Accomplishments
- Added `claude-agent-sdk==0.2.139` + `pytest-asyncio`; `asyncio_mode=auto` configured.
- `desk/runtime.py`: `run_structured()` — the ONLY SDK touchpoint. Binds the contract's json_schema to `output_format`, iterates `query()`, returns `schema.model_validate(json.loads(result))`. Bad payloads raise at the boundary; one retry on ValidationError.
- `desk/evidence.py`: `kb_ref`/`tool_ref` mint, `resolve()` (kb: via `kb.get_node` evidence_source-only, tool: resolved-by-construction, garbage → None), and `quote_supported()` case/whitespace-insensitive substring gate.
- Recorded-fixture replay harness proven: `sample_analyst_signal.json` + README documenting the two monkeypatch points. No live Anthropic call in the suite.

## Task Commits

1. **Task 1: Add deps + pin SDK version** - `a93c362` (chore)
2. **Task 2: run_structured seam + package init** - `5d16869` (test) → `73085fa` (feat)
3. **Task 3: evidence_ref mint + resolve** - `00b32f9` (test) → `1a3c3c6` (feat)

_TDD tasks committed test → feat._

## Files Created/Modified
- `pyproject.toml` - claude-agent-sdk + pytest-asyncio deps, asyncio_mode=auto
- `src/catalyst_trader/desk/__init__.py` - package marker + MAX_ROUNDS=2
- `src/catalyst_trader/desk/runtime.py` - run_structured() SDK seam
- `src/catalyst_trader/desk/evidence.py` - evidence_ref mint/resolve + quote gate
- `tests/test_desk_runtime.py` - seam tests (validated model, bad-payload reject, options passthrough, retry)
- `tests/test_desk_evidence.py` - mint/resolve/quote tests
- `tests/fixtures/agent_responses/sample_analyst_signal.json` - replay fixture
- `tests/fixtures/agent_responses/README.md` - replay convention

## Decisions Made
- Verified the installed SDK exposes `query`, `ClaudeAgentOptions` (with `output_format`), and `ResultMessage.result` before implementing — matched RESEARCH Example 1 exactly.
- `run_structured` captures the last message with a non-None `.result` (the final ResultMessage) rather than assuming a single message.
- Resolved RESEARCH Open Q2: `evidence_ref` format standardized as `kb:<evidence_source_node_id>` and `tool:<tool_name>#<inputs_hash>`.

## Deviations from Plan
None - plan executed exactly as written.

## Issues Encountered
- No `pip`/`python` on PATH; used the repo `.venv` (`.venv/bin/python`, Python 3.14.6) for install and test runs. No code impact.

## Known Stubs
None.

## User Setup Required
None - the test suite is fully offline (SDK mocked). Live desk runs will need Claude Code auth on the host, but no test does.

## Next Phase Readiness
- Wave-2 plans (analysts, debate, tools, verifier) can now monkeypatch `run_structured`, cite via `desk.evidence`, and resolve refs deterministically.
- Full suite green: 470 passed. (2 pre-existing statsmodels ComplexWarnings in test_pairs.py — out of scope.)

---
*Phase: 04-analyst-desk-bull-bear-debate-workflow-1a*
*Completed: 2026-08-15*

## Self-Check: PASSED

All 7 files present; all 5 task commits found.
