---
phase: 06-independent-diligence-firewall-workflow-3
plan: 02
subsystem: diligence desk — adversarial dimension layer + prep seams
tags: [firewall, diligence, dimensions, adversarial, hedge, options, tdd, offline]
requires:
  - "catalyst_trader.contracts (AnalystSignal, DiligenceInput)"
  - "catalyst_trader.desk.runtime.run_structured (the one SDK seam)"
  - "catalyst_trader.desk.tools.build_quant_server"
  - "catalyst_trader.desk.risk.validate_hedge"
  - "catalyst_trader.quant.options.implied_move"
  - "tests/test_desk_diligence.py Wave-1 harness (_dd_router, _patch_dd_seam, DD_DIMENSIONS, DD_INPUT)"
provides:
  - "desk/diligence.py dimension layer: DILIGENCE_PROMPTS (8 adversarial) + build_dimension_prompt + run_dimension + gather_dimensions"
  - "Deterministic prep seams: options_context / options_liquid / zero_liquidity / financials_context / ownership_context / trial_stats_context / hedge_context"
  - "DILIGENCE_PARAMS — the single, seed-proof diligence threshold source"
  - "desk/risk.py::validate_hedge candidate_peer keyword-only extension (backward-compatible)"
affects:
  - "Wave 3 (synthesizer) reads gather_dimensions output + MONEY_DIMS asymmetry"
  - "Wave 4 (orchestrator) builds the dimension_context dict from the prep seams + a None prep forcing money-dim NO-GO"
tech-stack:
  added: []
  patterns:
    - "Analyst-desk mirror (not reuse): own PROMPTS + sibling run_dimension because run_analyst hard-refs the 4-dim analysts.PROMPTS"
    - "Firewall as a prompt property: build_dimension_prompt interpolates ONLY DiligenceInput fields — no Workflow-1/2 token is in scope"
    - "Prep seams return a None sentinel on missing money-dim data (distinct from the always-present options context) so an ungrounded money dim can be forced NO-GO downstream"
    - "Backward-compatible signature extension via a trailing keyword-only param defaulting to the prior behavior (candidate_peer=None == Phase-5)"
key-files:
  created:
    - "src/catalyst_trader/desk/diligence.py"
  modified:
    - "src/catalyst_trader/desk/risk.py"
    - "tests/test_desk_diligence.py"
    - "tests/test_desk_risk.py"
decisions:
  - "diligence.py MIRRORS analysts.py rather than importing run_analyst (which hard-refs analysts.PROMPTS/4 dims) — a sibling run_dimension over the same run_structured seam"
  - "DILIGENCE_PARAMS is module-level in desk/diligence.py, read via direct subscript (missing-key-raises); NOT kb.load_params (post-seed strategy dict has no diligence key) and NOT added to the KB bootstrap default/CSV"
  - "options illiquid degrades (tag none/illiquid + LOW confidence + do-not-trust-IV), never a hard fail; only zero_liquidity (no bid/volume/oi) is the hard-fail signal — an inline boolean, not a new quant tool"
  - "hedge_context re-runs validate_hedge independently scoped to input.pair (candidate_peer) with input.ticker as target — a bare ticker, never a Workflow-2 Hedge; None result is the HEDGE-04 size-tiny/exit fallback"
  - "candidate_peer added as trailing keyword-only on validate_hedge; None preserves Phase-5 behavior exactly (no-regression test present); the Phase-5 caller at risk.assess untouched"
metrics:
  duration: ~12min
  completed: 2026-08-15
---

# Phase 6 Plan 2: Adversarial DD Dimensions + Prep Seams Summary

The 8-dimension adversarial diligence layer in `desk/diligence.py` — a mirror of the analyst desk that tries to KILL a promoted trade from raw sources. It carries its own `DILIGENCE_PROMPTS` (8 locked adversarial keys), a firewall-clean `build_dimension_prompt` (reads ONLY `DiligenceInput` fields), a sibling `run_dimension`/`gather_dimensions` fan-out over the one `run_structured` seam, and the deterministic prep seams (options graceful degradation, financials/ownership/trial raw-data with a None sentinel, and an INDEPENDENT `validate_hedge` re-run scoped to the promoted peer). Thresholds live in a module-level `DILIGENCE_PARAMS` that survives the seeded fitted-params path. Fully offline, TDD.

## What Was Built

**Task 1 — 8 adversarial dimensions (commit d7f3894)**
- `DILIGENCE_PROMPTS`: 8 entries on the LOCKED keys (trial_stats, regulatory, financials, ownership_flow, options_move, hedge_revalidation, liquidity, historical_analog), each an adversarial "find why this FAILS" job tailored to its source.
- `build_dimension_prompt(dimension, input, *, extra_context="")`: raises on unknown dimension; interpolates only `input.ticker` + `input.catalyst` facts (via `_get`) + `input.pair`; mandates `Emit \`dimension\` EXACTLY as "{dimension}"` and the hard tool-use/cite-or-drop rules. Contains none of {thesis, bull_strongest_point, direction, kill_criteria} — the firewall input has no reasoning to leak.
- `run_dimension` (sibling of `analysts.run_analyst`) + `gather_dimensions(conn, input, *, dimension_context=None)`: one `asyncio.gather` over the 8 keys, threading `build_quant_server(conn)` + the shared `ALLOWED_TOOLS` + per-dimension `extra_context`.

**Task 2 — prep seams + candidate-peer hedge + DILIGENCE_PARAMS (commits d7f3894 diligence + 35d58ef risk)**
- `DILIGENCE_PARAMS = {"diligence": {options_max_spread, options_min_oi, dimension_score_floor, dimension_min_conf}}` — single threshold source, direct-subscript reads, decoupled from the KB fitted-params seam.
- `zero_liquidity(quote)` (inline hard-fail bool) + `options_liquid(quote, *, params)` (§1.9 gate, param subscripts, no numeric literals in body) + `options_context(...)` (illiquid → tag `none/illiquid` + LOW conf + no-junk-IV; liquid → `options_data: ok` + straddle-preferred implied move).
- `financials_context` / `ownership_context` / `trial_stats_context`: carry raw/pre-computed figures + cite/tool instructions; return `None` on missing data (the money-dim NO-GO sentinel for Wave 4).
- `hedge_context(conn, embed, input, *, entry, exit_by_date, analog_gaps, prices)`: independent `validate_hedge(..., candidate_peer=input.pair)` re-run; reports the `Hedge | None`; None → HEDGE-04 fallback text.
- `desk/risk.py::validate_hedge` gains trailing keyword-only `candidate_peer: str | None = None` filtering the -1 peers to the requested one; `None` == Phase-5 behavior.

## Deviations from Plan

None functional. One packaging note (not a behavior change): both tasks touch `desk/diligence.py` and `tests/test_desk_diligence.py`. Since those shared files can't be split across commits non-interactively, the full diligence module + all its tests landed in the Task-1 commit (d7f3894) and the Task-2 commit (35d58ef) carries the Task-2-exclusive files (`risk.py` + `test_desk_risk.py`). Both commits are individually green.

## Requirements Progressed

- DILIG-02 (multi-dimensional DD from raw sources) — the 8 adversarial dimension agents + their deterministic prep seams are built and offline-tested; each dimension emits a source-cited AnalystSignal via one fan-out. (Synthesizer + orchestrator remain Waves 3-4.)

## Money-Critical Invariants Enforced (test-backed)

- 8 dimensions fan out via a single `asyncio.gather` (gather-spy asserts exactly one fan-out of 8).
- Prompts provably firewall-clean (no Workflow-1/2 token).
- Options degrade on illiquid (tag + LOW conf + no fabricated IV); only zero-liquidity hard-fails.
- Money-dim prep seams return None on missing data (distinct from the always-present options context).
- DILIGENCE_PARAMS survives `seed_fitted_params` (`"diligence" not in kb.load_params(...)`).
- Hedge dimension independently re-validates `input.pair` (candidate_peer); Phase-5 `validate_hedge` unchanged (no-regression test present).

## Verification

- `.venv/bin/python -m pytest tests/test_desk_diligence.py tests/test_desk_risk.py -q` → 36 passed.
- `.venv/bin/python -m pytest -q` → 668 passed (654 baseline + 14 new), 2 pre-existing statsmodels ComplexWarnings (out of scope). No regression.
- Acceptance greps: DILIGENCE_PROMPTS present; dim-key set matches locked keys; `asyncio.gather` inside gather_dimensions; all 7 seams present; no `load_params`/`BOOTSTRAP_DEFAULT` reference; `candidate_peer` in risk.py + `candidate_peer=input.pair` in hedge_context; options thresholds are param subscripts only.

## Notes for Downstream (Waves 3-4)

- `gather_dimensions` accepts a `dimension_context: dict[str,str]` — Wave 4 builds it from the prep seams: `{"options_move": options_context(...), "financials": financials_context(...), "ownership_flow": ownership_context(...), "trial_stats": trial_stats_context(...), "hedge_revalidation": hedge_context(...)}`.
- A `None` prep result (financials/ownership/trial) is the sentinel for an ungrounded money dim — Wave 4 decides how it forces the money dim to fail (do NOT push an empty string into a money-dim context).
- Wave 3's synthesizer MONEY_TOUCHING frozenset must equal `MONEY_DIMS` from the harness; `DILIGENCE_PARAMS["diligence"]` supplies `dimension_score_floor` / `dimension_min_conf` for `dimension_passed`.

## Self-Check: PASSED

- `src/catalyst_trader/desk/diligence.py` exists on disk.
- Commits present: d7f3894 (Task 1), 35d58ef (Task 2).
- `DILIGENCE_PROMPTS`, `DILIGENCE_PARAMS`, all 7 prep seams, and `candidate_peer` verified via grep.
