---
phase: 04-analyst-desk-bull-bear-debate-workflow-1a
plan: 05
subsystem: desk
tags: [debate, call-02, call-03, bull-bear, context-isolation, moderator, debate-verdict, offline-tdd]

# Dependency graph
requires:
  - phase: 04-analyst-desk-bull-bear-debate-workflow-1a
    plan: 02
    provides: desk.runtime.run_structured SDK seam (the single monkeypatch point)
  - phase: 02-contracts-knowledge-base-skeleton
    plan: 01
    provides: DebateVerdict contract (binary direction Literal + non-empty kill_criteria) + AnalystSignal
provides:
  - "desk.debate.run(signals, catalyst, rounds=MAX_ROUNDS) -> DebateVerdict via isolated bull/bear/moderator calls"
  - "desk.debate.Argument — 2-field internal side schema (shareable argument + private scratchpad)"
  - "Three recorded fixtures: bull_argument, bear_argument, moderator_verdict (binary + kill_criteria)"
affects: [04-06-verifier, 04-07-orchestrator]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Real context isolation: bull/bear are SEPARATE run_structured sessions; only the opponent's FINAL argument text is threaded, never the private scratchpad"
    - "Argument.scratchpad is the isolation-testability seam — a private field that is never passed across sides"
    - "Bounded debate: for _ in range(rounds) => exactly 2*rounds side calls; moderator counted separately (schema-based)"
    - "Model tiering: bull/bear on sonnet, moderator on opus (strongest tier for the synthesis)"
    - "Offline TDD: faked run_structured dispatches on schema (Argument vs DebateVerdict) + role token in prompt"

# Key files
key-files:
  created:
    - src/catalyst_trader/desk/debate.py
    - tests/test_desk_debate.py
    - tests/fixtures/agent_responses/bull_argument.json
    - tests/fixtures/agent_responses/bear_argument.json
    - tests/fixtures/agent_responses/moderator_verdict.json
  modified: []

# Decisions
decisions:
  - "Bull/bear isolation is enforced by threading only Argument.argument (shareable) and never Argument.scratchpad (private) — the scratchpad field exists precisely so the isolation test has something that must NOT cross sides"
  - "Bull opens; bear replies to the fresh bull case within the round; bull's next round replies to the prior bear case — a real debate, not two monologues, while staying context-isolated"
  - "Moderator prompt hard-requires anchoring confidence to a cited base_rate/analog and lowering it per unresolved unknown — grounded calibration, not vibes (CALL-03)"
  - "No-positioning is guarded structurally: extra='forbid' blocks stray keys AND a test asserts DebateVerdict.model_fields is disjoint from a positioning denylist (intent guard for Phase-5 boundary)"

# Metrics
metrics:
  duration: 8min
  completed: 2026-08-15
  tasks: 1
  files: 5
---

# Phase 04 Plan 05: Bull/Bear Debate + Moderator Verdict Summary

Python-driven bounded bull<->bear debate in REAL context isolation (each side a separate `run_structured` session, threaded only the opponent's final argument text) plus an opus-tier moderator that synthesizes a binary `DebateVerdict` — grounded confidence, non-empty kill criteria, and both sides' strongest point (naming the loser), with zero sizing/positioning. CALL-02 + CALL-03 satisfied at the component level.

## What Was Built

- **`desk/debate.py`** — `async def run(signals, catalyst, rounds=MAX_ROUNDS) -> DebateVerdict`:
  - `_evidence_context()` flattens the AnalystSignals (findings + evidence_refs + unknowns) into the shared context both sides reason over.
  - Bounded loop `for _ in range(rounds)`: BULL then BEAR, each a distinct `run_structured` invocation (`model="sonnet"`). Each side's prompt carries the shared signals + ONLY the opponent's prior FINAL `argument` text — never the transcript/scratchpad.
  - One MODERATOR call (`model="opus"`) bound to `DebateVerdict`: prompt requires binary direction, confidence anchored to a cited base_rate/analog and lowered per unknown, non-empty kill_criteria, both strongest points, and NO positioning.
  - `Argument` — a minimal 2-field internal schema (`argument` shareable + `scratchpad` private) that makes the isolation guarantee testable.
- **`tests/test_desk_debate.py`** — five behaviors: context isolation, boundedness (`2*MAX_ROUNDS` side calls; halving rounds halves calls), losing-side-named, grounded confidence (prompt + evidence_refs), no-positioning denylist.
- **Three fixtures** — `bull_argument`, `bear_argument` (each with a distinctive private scratchpad the opponent must never see), `moderator_verdict` (binary direction + non-empty kill_criteria per the extended contract).

## Deviations from Plan

None - plan executed exactly as written.

## Verification

- `grep "async def run"` / `range(rounds)` + `MAX_ROUNDS` / `model="opus"` — all match.
- `pytest tests/test_desk_debate.py` — 5 passed.
- Full suite: **490 passed** (2 pre-existing statsmodels ComplexWarnings in test_pairs.py — out of scope). No live API.

## Self-Check: PASSED

- FOUND: src/catalyst_trader/desk/debate.py
- FOUND: tests/test_desk_debate.py
- FOUND: tests/fixtures/agent_responses/{bull_argument,bear_argument,moderator_verdict}.json
- FOUND commit 9deb873 (test), 4620463 (feat)
