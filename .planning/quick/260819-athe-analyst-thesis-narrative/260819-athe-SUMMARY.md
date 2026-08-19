---
phase: quick-260819-athe
plan: 01
subsystem: desk (analysts / diligence / debate) + contracts
tags: [CALL-01, analyst-signal, thesis, debate, diligence]
requires: [AnalystSignal, analysts.build_prompt, diligence.build_dimension_prompt, debate._evidence_context]
provides: [AnalystSignal.thesis, grounded-thesis prompt rule, thesis-led debate context]
affects: [contracts, desk.analysts, desk.diligence, desk.debate]
tech-stack:
  added: []
  patterns: [required-non-empty-field (Field min_length=1, mirrors KeyFinding.evidence_ref), verdict-immutable-narrative reuse]
key-files:
  created: []
  modified:
    - src/catalyst_trader/contracts/__init__.py
    - src/catalyst_trader/desk/analysts.py
    - src/catalyst_trader/desk/diligence.py
    - src/catalyst_trader/desk/debate.py
    - tests/test_contracts.py
    - tests/test_desk_analysts.py
    - tests/test_desk_diligence.py
    - tests/test_desk_verifier.py
    - tests/test_desk_debate.py
    - tests/fixtures/agent_responses/*_signal.json (13)
decisions:
  - "thesis is REQUIRED + non-empty (Field min_length=1), not optional-with-default — forces the model to emit a read on every signal; extra=forbid already blocks silent skips."
  - "Grounding is inherited from key_findings, NOT a new verification pass — verifier.py untouched (the thesis mints no evidence_ref)."
  - "The DD firewall leak-test dropped 'thesis' from its forbidden tuple: thesis is now a legitimate shared AnalystSignal field, not a Workflow-1/2 verdict concept."
metrics:
  duration: ~20m
  completed: 2026-08-19
---

# Quick 260819-athe: Analyst Thesis Narrative Summary

Every `AnalystSignal` now LEADS with a required, non-empty `thesis` — a 1-3 sentence
dimension-specific "here is my read of this catalyst" synthesized from the signal's own cited
key_findings — and the bull/bear/moderator debate argues those four stated theses instead of
reconstructing a view from scattered findings.

## What shipped

**Task 1 — required grounded thesis (commit 72d0890)**
- `contracts.AnalystSignal.thesis: str = Field(min_length=1)` — required, non-empty (mirrors
  `KeyFinding.evidence_ref`). A missing or empty thesis is rejected at `model_validate`.
- HARD RULE 5 (identical text) added to BOTH `analysts.build_prompt` and
  `diligence.build_dimension_prompt`: "LEAD with a `thesis` … a SYNTHESIS of your own cited
  key_findings — introduce NO claim that is not already in a cited finding (the thesis inherits
  their grounding; it is not a new uncited assertion)."
- All 8 DD dimensions share the `AnalystSignal` schema via `run_structured`, so the shared DD
  prompt instructs the field too.

**Task 2 — debate consumption (commit 4a94be3)**
- `debate._evidence_context` now leads each signal with a `[dim] THESIS: <thesis>` line, then the
  score/confidence + findings/unknowns. One additive change: `evidence` flows unchanged into
  `_side_prompt` (bull + bear) and `_moderator_prompt`, so all three consumers inherit the thesis
  with no signature change and no new call.

## The 18 construction sites updated

- **In-code (5):** `test_desk_debate.py` SIGNALS[0] (clinical) + SIGNALS[1] (financial);
  `test_desk_verifier.py::_signal`; `test_desk_diligence.py::_sig`;
  **`test_contracts.py::valid_analyst_signal()`** (the plan-check B1 dict builder the raw
  `AnalystSignal(` grep missed — feeds `model_validate` in `test_valid_payload_validates`).
- **Fixtures (13)** in `tests/fixtures/agent_responses/`: the 4 analyst signals
  (`clinical`, `regulatory`, `financial`, `market_sentiment`), `sample_analyst_signal`, and the
  8 `dd_*_signal` files — each given a 1-3 sentence thesis coherent with its dimension/score/findings.

## The grounded-thesis rule (analysts + DD dims)

Identical rule 5 in `analysts.build_prompt` (4 analyst dims) and `diligence.build_dimension_prompt`
(8 DD dims). Grounding is inheritance: the thesis restates only what the signal's already-cited,
cite-or-drop `key_findings` say, so it carries their grounding and mints no new `evidence_ref`.
Because it adds no evidence_ref, `verifier.enforce` (which gates `DebateVerdict.evidence_refs`) needs
no change — and was left untouched. Money/sizing/deterministic paths untouched (narrative-only).

## The debate consumption

`_evidence_context` per-signal block changed from a single score line to:

```
[clinical] THESIS: The science supports a positive readout: the pivotal endpoint was met with strong significance.
  score=+0.50 confidence=0.60
  - Phase 3 endpoint met p<0.001  (cite: tool:base_rate#a1b2c3)
  - UNKNOWN: secondary endpoint durability not reported
```

Bull, bear, and moderator prompts all read this shared string, so the debate reasons from the four
stated theses.

## Example: an analyst signal now leading with a thesis

`clinical_signal.json` (score 0.55, confidence 0.62):

> **thesis:** "The science supports a positive readout: Phase 3 LoA sits above the oncology mean and
> two structurally similar prior readouts hit their primary endpoint."
> key_findings: [Phase 3 LoA above oncology mean (tool:base_rate#a1b2c3); two similar prior readouts
> hit primary (tool:analog_query#d4e5f6)]

The thesis synthesizes exactly the two cited findings — no new uncited claim.

## Deviations from Plan

**1. [Rule 3 - Blocking] DD firewall leak-test conflicted with the new field.**
- **Found during:** Task 1 (RED run).
- **Issue:** `test_desk_diligence.py::test_dimension_prompt_reads_only_firewall_fields` asserted
  `"thesis" not in prompt` — but rule 5 legitimately puts "thesis" in the DD prompt.
- **Fix:** dropped `"thesis"` from the leaked tuple with a comment (it is now a shared AnalystSignal
  field, not a Workflow-1/2 verdict concept). The real WF-1/2 leaks —
  `bull_strongest_point`, `direction`, `kill_criteria` — remain asserted-absent.
- **Files modified:** `tests/test_desk_diligence.py`.
- **Commit:** 72d0890.

This was flagged in the incoming prompt's plan-check (extends B1). No other deviations.

## Backward-compat proof

- No `AnalystSignal` is persisted to DB or serialized to disk outside tests (in-memory
  orchestrator → debate → verifier), so the blast radius was exactly the 18 sites, all updated.
- Full offline suite green (run_structured monkeypatched everywhere; no live LLM):
  **1761 passed, 1 xfailed** (pre-existing `test_backtest_latency_sweep` deferred-wiring xfail).
  Baseline before the change was 1760 passed / 1 xfailed; the +1 is Task 2's new test.
- verifier.py and all deterministic money/sizing code unchanged.

## Test counts

- RED (Task 1): 34 failing before implementation → 144 passing in scoped verify after GREEN.
- RED (Task 2): 1 failing → 13 passing in scoped verify after GREEN.
- Full suite: 1761 passed, 1 xfailed, ~33s.

## Self-Check: PASSED
- Files present: contracts/__init__.py, desk/{analysts,diligence,debate}.py, 13 fixtures, 5 test files — all modified and staged.
- Commits present: 72d0890 (Task 1), 4a94be3 (Task 2).
