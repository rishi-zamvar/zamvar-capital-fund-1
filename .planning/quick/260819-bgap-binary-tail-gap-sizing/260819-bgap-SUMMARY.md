---
phase: quick-260819-bgap
plan: 01
subsystem: quant-sizing / desk
tags: [money-path, sizing, risk-of-ruin, binary-catalyst, BGAP-01]
requires:
  - statistics.quantiles (stdlib)
  - quant/sizing.risk_of_ruin, desk/risk.size_for_survival
provides:
  - quant/sizing.binary_survival_gap (tail-gap selector)
  - kb params: binary_catalyst_types, binary_gap_percentile, binary_gap_default
  - catalyst_context binary-vs-median gap branch
affects:
  - desk/catalyst_context risk_inputs["gap"] -> size_for_survival for BINARY catalysts
tech-stack:
  added: []
  patterns: [pure-fn-with-injected-params, params-not-magic-literals, honest-degrade-to-prior]
key-files:
  created: []
  modified:
    - src/catalyst_trader/quant/sizing.py
    - src/catalyst_trader/kb.py
    - src/catalyst_trader/desk/catalyst_context.py
    - tests/test_sizing.py
    - tests/test_desk_catalyst_context.py
decisions:
  - "BINARY catalysts size against the TAIL analog down-move (max(90th-pctile, 0.70)), never the median"
  - "The conservative binary prior is the codebase's canonical 0.70/-70% belief, NOT base_rates crl_penalty (a probability, not a price move)"
  - "binary_gap_percentile=90 labeled UNCALIBRATED; only bites when observed history is strictly worse than the 0.70 floor"
metrics:
  duration: ~25m
  completed: 2026-08-19
---

# Phase quick-260819-bgap Plan 01: Binary-Catalyst Tail-Gap Survival Sizing Fix Summary

Fixed a money-critical under-estimate of the survival gap for BINARY catalysts (PDUFA / AdCom / trial readout): `catalyst_context` set `gap = median(down_moves)` for every catalyst, so a binary event whose true downside is a 30-70% gap-down was sized against the ~8.5% median analog move — oversizing ~5-7x into ruin. Binary catalysts now size against the tail (or the conservative 0.70 prior); the non-binary (earnings/conference) path is byte-for-byte unchanged.

## What shipped

**Task 1 — `binary_survival_gap` + PARAMS** (`e7c9f4d`)
- `quant/sizing.py::binary_survival_gap(down_moves, *, percentile, default) -> max(tail_percentile, default)`. Pure fn: reuses `statistics.quantiles(n=100, method="inclusive")[percentile-1]`, guards `len(down_moves) >= 2` (else falls back to `default` — quantiles needs ≥2 points), no magic literal in the body beyond the structural `n=100`.
- `kb.py` BOOTSTRAP_DEFAULT["weekly"] gained three knobs (direct-subscript, missing-key-raises):
  - `binary_catalyst_types = ["pdufa", "adcom", "trial_readout"]`
  - `binary_gap_percentile = 90`  (labeled **UNCALIBRATED** inline, matching the `field.*` knobs)
  - `binary_gap_default = 0.70`  (the codebase's canonical binary down-gap: matches `sizing.py` "-70%" + the `gap=0.70` `risk_of_ruin` / `size_for_survival` defaults)

**Task 2 — wire into `catalyst_context`** (`5e8f0f9`)
- Branch on `catalyst["catalyst_type"] in w["binary_catalyst_types"]`: BINARY → `binary_survival_gap(...)`; NON-binary → the existing `median(down_moves) if down_moves else abs(w["hard_veto_drop"])` expression, byte-for-byte. `analog_gaps` target_up/down untouched on both branches (only `gap` changes on the binary path).

## The safety property: `max(tail, 0.70)`

The gap can only ever move UP from the conservative prior:
- **Optimistic/thin history can NEVER pull the gap below 0.70.** A cluster of small analog down-moves (median ~8.5%, 90th-pctile ~45%) still floors to 0.70 — the position cannot be over-sized.
- **Genuinely-worse observed history pushes the gap ABOVE 0.70.** If the 90th-pctile of real analog down-moves exceeds 0.70, that higher tail is kept (strictly more conservative).
- **Thin coverage (0-1 down-moves) → 0.70**, never a crash, never a too-small median.

This is monotone-safe: `binary_survival_gap` output ≥ 0.70 always, and a larger gap yields a smaller survival size, so a binary catalyst can never be under-gapped.

## The two updated bug-encoding tests (and why)

The old suite asserted the BUG for a PDUFA (`_CATALYST`, catalyst_type="pdufa") catalyst:
1. `test_givenFakeSourcesWithMixedAnalogs...` asserted `gap == 0.25` (median of [0.2, 0.3]). PDUFA is binary → now floors to 0.70, so this assertion had to change. Per plan-check C-note, **flipped the fixture to `earnings`** so a genuine NON-binary path is pinned byte-for-byte (`gap == median([0.2,0.3]) == 0.25`), renamed `test_givenNonBinaryEarningsWithMixedAnalogs...`. This is the regression guard proving the non-binary path is unchanged.
2. `test_givenNoAnalogs...` asserted `gap == abs(hard_veto_drop) == 0.15` for a PDUFA. PDUFA + empty analogs is exactly the thin-binary case → now 0.70. **Rewrote to `test_givenBinaryThinAnalogs...`** asserting `gap == binary_gap_default (0.70)` and `!= 0.15`, and added a sibling `test_givenNonBinaryNoAnalogs...` that keeps the byte-for-byte `abs(hard_veto_drop)` fallback for earnings.

Both old assertions encoded the under-sizing bug; leaving them would have pinned the bug in place.

## Worked example (the fix in numbers)

Analog down-moves `[0.05, 0.08, 0.10, 0.60]` (median 0.09, 90th-pctile 0.45), `p_loss = 0.5`, `per_event_cap = 0.5` (widened so the survival ceiling, not the per-event cap, binds):

| Path | gap used | `size_for_survival` |
| --- | --- | --- |
| **Before (median bug)** | 0.09 | **0.500** (oversized) |
| **After (binary)** | max(0.45, 0.70) = **0.70** | **0.0955** |

The binary catalyst is now sized ~5.2x smaller. And at the chosen 0.0955 size, `risk_of_ruin(p_loss=0.5, size_pct=0.0955, gap=0.60) = 0.0051 <= ruin_cap (0.02)` — a -60% tail is survivable within the ruin cap. The median-gap 0.500 size would be catastrophic on the same -60% tail.

## Backward-compat proof

- Named verify suites (`test_desk_catalyst_context`, `test_desk_risk`, `test_desk_book_risk`, `test_sizing`): **124 passed**.
- Full suite: **1749 passed, 1 xfailed** — plus **1 pre-existing unrelated failure** (`test_weekly_cycle.py::test_module_contains_no_opener_or_broker_call`), confirmed failing with all BGAP changes stashed; both that test and its `scripts/weekly_cycle.py` target are UNTRACKED slice-5 files with zero overlap with this change. Logged to `deferred-items.md`, not fixed (scope boundary).
- The non-binary gap path is asserted byte-for-byte via the flipped earnings fixtures. Only the binary catalyst gap changed.
- No new magic literals: percentile, default, and the binary type set all live in kb params (missing-key raises). No new data source; reuses analog down-moves + stdlib `quantiles`. No fabrication: the prior cites the existing 0.70/-70% codebase belief, not the misusable `base_rates.crl_penalty`.

## Deviations from Plan

None — plan executed as written. One pre-existing, unrelated test failure was discovered and logged to `deferred-items.md` per the scope boundary (not introduced by this plan).

## Test counts

- `tests/test_sizing.py`: 69 passed (added 7 `binary_survival_gap` tests + 1 kb-params test).
- `tests/test_desk_catalyst_context.py`: 12 passed (2 bug-encoding tests rewritten, 4 new binary/regression/e2e tests added).

## Self-Check: PASSED
- `src/catalyst_trader/quant/sizing.py::binary_survival_gap` — present.
- kb params `binary_gap_default` / `binary_gap_percentile` / `binary_catalyst_types` — present.
- `catalyst_context.py` binary branch calling `binary_survival_gap` — present.
- Commits `e7c9f4d`, `5e8f0f9` — in `git log`.
