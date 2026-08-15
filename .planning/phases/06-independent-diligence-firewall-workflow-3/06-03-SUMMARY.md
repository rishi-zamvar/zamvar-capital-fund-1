---
phase: 06-independent-diligence-firewall-workflow-3
plan: 03
subsystem: diligence desk — deterministic adversarial synthesizer + verdict-immutable narrative + cite-or-drop gate
tags: [firewall, diligence, synthesizer, adversarial, deterministic, money-critical, tdd, offline]
requires:
  - "catalyst_trader.contracts (AnalystSignal, DiligenceDossier, DiligenceInput, KeyFinding)"
  - "catalyst_trader.desk.evidence.resolve / quote_supported (reused verbatim)"
  - "catalyst_trader.desk.verifier.SupportCheck (pure model reuse — the enforce() gate is NEVER called)"
  - "catalyst_trader.desk.runtime.run_structured (the one SDK seam)"
  - "desk/diligence.py Wave-2 layer (DILIGENCE_PARAMS, gather_dimensions, prep seams)"
  - "tests/test_desk_diligence.py Wave-1/2 harness (_dd_router, _patch_dd_seam, DD_DIMENSIONS, MONEY_DIMS)"
provides:
  - "MONEY_TOUCHING frozenset (== harness MONEY_DIMS) — the money-scoped asymmetry set"
  - "dimension_passed(sig, *, params) — data-backed test, thresholds from params (missing-key-raises)"
  - "synthesize_verdict(findings, *, liquidity_zero, params) — the DETERMINISTIC go/no-go the LLM cannot touch"
  - "DiligenceNarrative — structurally verdict-free LLM narrative schema"
  - "_narrative + assemble_dossier — verdict stamped via model_copy (LLM cannot flip no_go->go)"
  - "enforce_dossier — cite-or-drop mirroring the verifier two-stage shape, reusing evidence primitives"
affects:
  - "Wave 4 (orchestrator run_diligence) wires gather_dimensions -> synthesize_verdict -> _narrative -> assemble_dossier -> enforce_dossier"
tech-stack:
  added: []
  patterns:
    - "Deterministic layer OWNS the money decision; LLM writes narrative only — the size_for_survival / risk.assess precedent applied to go/no-go"
    - "Verdict immutability by construction: the narrative schema has NO verdict field, so the LLM literally cannot emit a go/no-go; assemble_dossier model_copy-stamps the deterministic verdict"
    - "GO requires the FULL MONEY_TOUCHING set present AND data-backed AND non-zero liquidity — every other path defaults to no_go (asymmetry baked into the default branch)"
    - "Gate-by-mirroring: enforce_dossier copies verifier.enforce's structural+semantic shape and reuses evidence.resolve/quote_supported, but never calls the DebateVerdict-typed gate (a grep-gate enforces it)"
key-files:
  created: []
  modified:
    - "src/catalyst_trader/desk/diligence.py"
    - "tests/test_desk_diligence.py"
decisions:
  - "synthesize_verdict enforces PRESENCE of the full money set ({s.dimension for s in money} == MONEY_TOUCHING) before GO — the interfaces pseudocode's `money and all(passed)` alone would GO on a partial money set; the plan behavior (removing any money dim -> no_go) is authoritative, so presence-complete is the implemented rule"
  - "SupportCheck is imported from verifier (pure model reuse); the module never references the `verifier` namespace, so `verifier.enforce` cannot be called — the DebateVerdict-typed gate stays out"
  - "A NO-GO that loses ALL evidence support appends an AUDIT red flag (not raise) — the dossier still returns for the human gate, but the unsupported basis is surfaced, never silent"
  - "dimension_passed uses `score >= floor` and `confidence >= min_conf` (both inclusive); zero-cited-findings defense via bool(sig.key_findings) even though the AnalystSignal validator already guarantees >=1"
metrics:
  duration: ~10min
  completed: 2026-08-15
---

# Phase 6 Plan 3: Deterministic Adversarial Synthesizer + Verdict-Immutable Narrative Summary

The money-critical crux of the diligence firewall (DILIG-03): a pure `synthesize_verdict` that owns the go/no-go, an LLM narrative pass that structurally cannot flip it, and a `enforce_dossier` cite-or-drop gate that mirrors the verifier's two-stage shape while reusing only the `desk.evidence` primitives. One money-touching dimension failing — or zero-liquidity, or a missing money dim (a tie) — forces NO-GO; GO requires the full money set present AND data-backed. Thresholds read from `DILIGENCE_PARAMS` (missing-key-raises), no numeric literals in money code. Fully offline, TDD (failing test first each task).

## What Was Built

**Task 1 — deterministic synthesizer (commit 98f1a77)**
- `MONEY_TOUCHING = frozenset({financials, ownership_flow, options_move, hedge_revalidation, liquidity})` — pinned equal to the harness `MONEY_DIMS`.
- `dimension_passed(sig, *, params)`: `bool(sig.key_findings) and sig.score >= floor and sig.confidence >= min_conf`, floor/min_conf via direct param subscript (missing-key-raises).
- `synthesize_verdict(findings, *, liquidity_zero, params)`: asymmetric — (1) zero-liquidity -> no_go; (2) full money set must be present -> else no_go; (3) any present money dim not data-backed -> no_go; (4) only then go. The single place the verdict is decided.
- Exhaustive edge suite: each of the 5 money dims failing individually forces no_go (parametrized), GO requires all 5 present+backed, removing any -> no_go, non-money dim failure doesn't block, zero-liquidity hard-fails, empty money set (tie) -> no_go, params missing-key raises KeyError.

**Task 2 — verdict-immutable narrative + cite-or-drop gate (commit b01e004)**
- `DiligenceNarrative` (extra="forbid"): `strongest_disconfirming_evidence` + `red_flags` + `residual_risks` — NO `verdict` field.
- `_narrative(findings, verdict, *, model="opus")`: builds a prompt stating the verdict is FIXED and asks only for the adversarial narrative; returns a verdict-free `DiligenceNarrative` via `run_structured`.
- `assemble_dossier(findings, verdict, narrative, *, liquidity_zero, params)`: stamps the DETERMINISTIC verdict, serializes per-dimension (`model_dump` + `passed` flag), gathers `all_evidence_refs` from every finding — the model_copy money-overwrite guard.
- `enforce_dossier(conn, dossier, *, signals)`: STRUCTURAL (resolve; drop None; kb: refs must also pass quote_supported against the cited claim; tool: refs survive by construction) then SEMANTIC (gated opus SupportCheck per survivor). A no_go that loses ALL support appends an `AUDIT:` red flag. Returns `dossier.model_copy(update={all_evidence_refs, red_flags})`.

## Money-Critical Invariants Enforced (test-backed)

- ONE money-touching dimension failing -> NO-GO (parametrized over all 5).
- Zero-liquidity -> hard NO-GO regardless of other dimensions.
- A tie / missing money dim -> NO-GO (GO requires the full money set present AND data-backed).
- The LLM narrative cannot flip the verdict — the schema has no verdict field, and `assemble_dossier` overwrites via model_copy (`test_llm_narrative_cannot_override_verdict`, `test_narrative_schema_is_narrative_only`).
- Cite-or-drop: unresolvable dossier refs dropped, tool: refs survive by construction, kb: refs survive only when quote_supported; a no_go resting on all-unsupported evidence is flagged, not silently passed.
- Thresholds from params only — no numeric literal for score-floor/min-conf in any function body.
- `enforce_dossier` never calls the DebateVerdict-typed verifier gate (grep-gate clean).

## Deviations from Plan

**1. [Rule 1 — Correctness] synthesize_verdict enforces money-set PRESENCE before GO**
- **Found during:** Task 1 (`test_go_requires_all_money_dimensions_backed`).
- **Issue:** the interfaces-block pseudocode (`return "go" if money and all(passed) else "no_go"`) would return GO on a PARTIAL money set (e.g. 4 of 5 money dims present, all passing) — contradicting the plan behavior "removing any single money dim -> no_go" and the must-have "GO requires ALL money-touching dimensions data-backed".
- **Fix:** added the presence check `{s.dimension for s in money} != MONEY_TOUCHING -> no_go` before the pass check. Satisfies every listed behavior (one-fail, all-backed, tie/missing, empty, zero-liquidity, non-money).
- **Files modified:** src/catalyst_trader/desk/diligence.py.
- **Commit:** 98f1a77.

**2. [Rule 3 — grep-gate] reworded doc comments to keep the `verifier.enforce` grep-gate clean**
- The module imports only `SupportCheck` from verifier and never references the `verifier` namespace, so the DebateVerdict-typed gate is uncallable. Doc comments originally said "verifier.enforce"; reworded to "the verifier gate" so `grep "verifier\.enforce\b"` returns nothing (acceptance criterion).
- **Commit:** b01e004.

Both tasks touch the same two files; per the Wave-2 packaging note, the incremental additions were committed per-task (Task-1 additions in 98f1a77, Task-2 additions in b01e004) — each commit is individually green.

## Requirements Progressed

- DILIG-03 (adversarial synthesizer, rewards no-go, data-backed confidence -> DiligenceDossier) — the deterministic asymmetry, the verdict-immutable narrative, and the cite-or-drop gate are built and exhaustively offline-tested. (The `run_diligence` orchestrator wiring these together is Wave 4.)

## Verification

- `.venv/bin/python -m pytest tests/test_desk_diligence.py -q` -> 27 passed.
- `.venv/bin/python -m pytest -q` -> 683 passed (668 baseline + 15 new), 2 pre-existing statsmodels ComplexWarnings (out of scope). No regression.
- Acceptance greps: MONEY_TOUCHING frozenset with the 5 money keys; synthesize_verdict + dimension_passed present; score-floor/min-conf are param subscripts only (no literal in bodies); DiligenceNarrative/enforce_dossier/assemble_dossier/_narrative all present; `verifier.enforce\b` grep clean; evidence.resolve/quote_supported inside enforce_dossier; narrative schema has no verdict field.

## Notes for Downstream (Wave 4)

- Orchestrator flow: `gather_dimensions(conn, input, dimension_context=...)` -> `synthesize_verdict(findings, liquidity_zero=zero_liquidity(quote), params=DILIGENCE_PARAMS)` -> `_narrative(findings, verdict)` -> `assemble_dossier(findings, verdict, narrative, liquidity_zero=..., params=DILIGENCE_PARAMS)` -> `enforce_dossier(conn, dossier, signals=findings)`.
- A `None` prep result on a money dim (financials/ownership) must be turned into a FAILING money-dim signal (or a dropped dim) by Wave 4 so the presence/pass rule forces NO-GO — do NOT feed an empty-string context and let the agent invent a passing signal.
- `liquidity_zero` is the `zero_liquidity(quote)` boolean from Wave 2, threaded as the hard-fail flag.

## Self-Check: PASSED

- `src/catalyst_trader/desk/diligence.py` exists on disk.
- Commits present: 98f1a77 (Task 1), b01e004 (Task 2).
- SUMMARY.md written; all four Task-2 symbols + MONEY_TOUCHING/synthesize_verdict verified via grep.
