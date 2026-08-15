---
phase: 04-analyst-desk-bull-bear-debate-workflow-1a
plan: 06
subsystem: desk
tags: [verifier, call-04, provenance, source-quote-or-drop, tdd]
requires:
  - "desk.evidence.resolve + quote_supported (Plan 02)"
  - "desk.runtime.run_structured seam (Plan 04)"
  - "contracts.DebateVerdict (Plan 01)"
provides:
  - "desk.verifier.enforce(conn, verdict, *, signals) -> DebateVerdict (raises VerdictUnsupportedError)"
  - "desk.verifier.SupportCheck (gated LLM semantic-judgment schema)"
  - "desk.verifier.VerdictUnsupportedError"
affects:
  - "Plan 07 orchestrator (runs enforce before finalizing the verdict)"
tech-stack:
  added: []
  patterns:
    - "Deterministic structural gate first, LLM only for load-bearing survivors (cost + trust)"
    - "tool: refs resolved-by-construction; kb: refs need quote-substring support"
key-files:
  created:
    - src/catalyst_trader/desk/verifier.py
    - tests/test_desk_verifier.py
    - tests/fixtures/agent_responses/verifier_support.json
  modified: []
decisions:
  - "load-bearing == the verdict's evidence_refs (the moderator only cites what backs the thesis) — the semantic gate runs on every structural survivor, never on a dropped ref"
  - "a kb: ref with no matching analyst claim is dropped (can't verify the quote) — money-safe conservative default"
  - "semantic check uses model=opus (strongest tier) — the load-bearing support judgment is where an LLM error is most expensive"
metrics:
  duration: 6min
  completed: 2026-08-15
  tasks: 1
  files: 3
---

# Phase 04 Plan 06: Fact-Check Verifier (source-quote-or-drop) Summary

CALL-04's reasoning-layer provenance gate: `desk.verifier.enforce` prunes a `DebateVerdict`'s `evidence_refs` to only claims with a resolvable, supporting source before finalize — deterministic structural resolution + quote-substring first, a gated opus semantic check only for the load-bearing survivors, and a hard `VerdictUnsupportedError` when all support is dropped.

## What was built

`enforce(conn, verdict, *, signals=None) -> DebateVerdict` runs three stages:

1. **Structural (deterministic, no LLM):** each `evidence_ref` is resolved via `desk.evidence.resolve`. Unresolvable → drop. A `kb:` ref must additionally pass `quote_supported(source, claim)` where the claim text is looked up from the analyst `key_findings` ref→claim table → drop if the cited quote isn't a substring of the source. A `tool:` ref (quant results AND KB `analog_query`/`query_playbooks`) is resolved-by-construction — passes with no KB lookup and no quote gate.
2. **Semantic (LLM, gated):** for each structural survivor, `run_structured(..., SupportCheck, model="opus")` judges whether the source substantively backs the claim; unsupported → drop. Never invoked for a ref already dropped structurally.
3. **Finalize gate:** no survivor → raise `VerdictUnsupportedError`. Otherwise return the verdict with `evidence_refs` pruned to survivors.

## CALL-04 regression guard

`test_kb_analog_tool_ref_survives` proves a verdict whose ONLY support is a KB-analog claim cited as `tool:analog_query#<hash>` (the exact ref shape 04-03 mints) survives structural resolution and reaches the semantic gate — it is NOT dropped as unresolvable. The companion `test_kb_analog_cited_as_kb_ref_would_be_dropped` shows the same analog cited as `kb:<catalyst_node_id>` IS dropped (a catalyst node is not an evidence_source) and blocks finalize — exactly why 04-03 mints `tool:` refs, not `kb:`.

## Tests (5, all offline)

- `test_source_quote_or_drop` — (a) supported kb: + (d) tool: survive; (b) unsupported kb: + (c) garbage dropped, no LLM for the drops.
- `test_kb_analog_tool_ref_survives` — CALL-04 guard: tool:analog_query ref survives structural + reaches semantic gate.
- `test_kb_analog_cited_as_kb_ref_would_be_dropped` — the contrast that justifies tool:-ref minting.
- `test_verifier_gates_finalize` — dropping all support raises `VerdictUnsupportedError`, no LLM spent.
- `test_semantic_check_only_for_load_bearing` — `run_structured` called once per structural survivor (opus), never for dropped refs.

`run_structured` is monkeypatched (patched response = `tests/fixtures/agent_responses/verifier_support.json`); zero live API.

## Deviations from Plan

None - plan executed exactly as written.

## Verification

- `grep "def enforce"` ✓ · `grep -E "resolve|quote_supported"` ✓ · `grep "run_structured"` ✓ · `grep "tool:analog_query"` in tests ✓
- `pytest tests/test_desk_verifier.py` → 5 passed
- Full suite: `pytest` → **495 passed** (2 pre-existing statsmodels ComplexWarnings in test_pairs, out of scope)

## Self-Check: PASSED
