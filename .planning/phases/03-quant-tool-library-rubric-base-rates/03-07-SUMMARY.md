---
phase: 03-quant-tool-library-rubric-base-rates
plan: 07
subsystem: quant
tags: [rubric, base-rates, tunable-config, citations, frame, tdd]
requires:
  - catalyst_trader.quant.result.ToolResult
provides:
  - "rubric.load_weights() → validated weights dict (8 keys, Σ≈1, per-weight [0,1])"
  - "rubric.score_rubric() → ToolResult (0–100 composite, PoS surfaced in detail)"
  - "base_rates.load_base_rates() → list[dict] with float-typed value + citation columns"
  - "base_rates.base_rate() → {value, source_name, source_url, quote}; raises on unknown/ambiguous key"
  - "data/rubric_weights.json (tunable 8-factor weights)"
  - "data/base_rates.csv (12 cited clinical base rates)"
affects:
  - "Phase 4 analyst desk scores names via score_rubric + anchors on base_rate"
  - "Phase 10 learning loop rewrites data/rubric_weights.json (load_weights guards a bad rewrite)"
tech_stack:
  added: []
  patterns:
    - "Weights/base-rates are DATA files (json/csv) read at call time, not magic numbers in code"
    - "Boundary validation raises ValueError (Pattern 2) — corrupt weights or unknown base-rate key never emit a number"
    - "Citation travels WITH the value (base_rate returns source_name/url/quote) — the KeyFinding.evidence_ref anti-hallucination discipline"
key_files:
  created:
    - data/rubric_weights.json
    - data/base_rates.csv
    - src/catalyst_trader/quant/rubric.py
    - src/catalyst_trader/quant/base_rates.py
    - tests/test_rubric.py
    - tests/test_base_rates.py
  modified: []
decisions:
  - "load_weights rejects any weight outside [0,1] (not just Σ≈1) — plan-checker addendum: the Phase-10 learning loop rewrites this file, so an unbounded negative/>1 weight could produce a nonsensical score even when the row sums to 1.0"
  - "base_rate raises on BOTH zero matches (unknown key) AND multiple matches (ambiguous) — no silent None and no arbitrary first-row pick; the caller must narrow phase/indication"
  - "score_rubric surfaces pos_factor + weights_version in detail so a composite is always traceable to which factor dominated and which weight-set version produced it"
metrics:
  duration: 4min
  completed: 2026-08-15
  tasks: 3
  files: 6
---

# Phase 3 Plan 7: Scoring Rubric + Clinical Base-Rates Summary

Shipped the 8-factor biotech scoring rubric as a tunable JSON config (FRAME-01/02) and the clinical base-rate table as a cited CSV (FRAME-03), each with a validating loader — `load_weights` rejects any corrupt learning-loop rewrite (missing factor, Σ≠1, or a weight outside [0,1]) before it can poison a score, and `base_rate` returns every number WITH its source (source_name/url/quote) and raises rather than return a silent None. TDD'd RED-first: 21 tests covering FRAME-01 composite, FRAME-02 file-edit-changes-score tunability, FRAME-03 value-with-citation, and every rejection path.

## What Was Built

- **`data/rubric_weights.json`** — `{version, weights}` with the 8 factors (pos 0.20, cash_runway 0.15, trial_design 0.15, endpoint_credibility 0.12, regulatory_precedent 0.12, pipeline_concentration 0.10, management 0.08, commercial 0.08; Σ=1.00). DATA, not code.
- **`data/base_rates.csv`** — 12 rows (`metric,phase,indication,value,source_name,source_url,quote`): Phase-I LoA 7.9% + oncology 3.4%, Ph2→3 28.9%, oncology transitions, per-phase PoS rules-of-thumb, prior-CRL −0.28, AdCom 0.90 — every row citable, matching the `pdufa_curated.csv` convention.
- **`quant/rubric.py`** — `load_weights()` (8-key presence + per-weight [0,1] + Σ≈1e-6 validation) and `score_rubric()` (composite = Σ(score·weight)·10 → 0–100; rejects unknown/missing factors and scores ∉[0,10]; PoS + weights_version in `detail`; verbatim `inputs` snapshot for QUANT-03).
- **`quant/base_rates.py`** — `load_base_rates()` (csv → row dicts, value cast float) and `base_rate(metric, phase, indication)` (filtered lookup returning value+citation, raising on unknown or ambiguous key).
- **RED-first suites** — `tests/test_rubric.py` (14 tests: happy composite/all-tens/all-zeros, Σ≠1 / missing / negative / >1 weight rejection, missing/unknown factor + out-of-range score rejection, QUANT-03 inputs, FRAME-02 tunability) and `tests/test_base_rates.py` (7 tests: typed rows, value-with-citation, oncology + CRL + AdCom rows, unknown-key + unknown-phase raise).

## Verification

- `pytest tests/test_rubric.py tests/test_base_rates.py -q` → 21 passed.
- `pytest -q` → 412 passed (2 pre-existing statsmodels ComplexWarnings from test_pairs.py, out of scope).

## Deviations from Plan

### Auto-added (plan-checker addendum, folded into plan)

**1. [Rule 2 - Missing critical validation] load_weights rejects out-of-range weights**
- **Requested by:** plan-checker addendum in the execution prompt.
- **Change:** `load_weights` now rejects any weight `< 0` or `> 1` (two dedicated tests: `test_load_weights_rejects_negative_weight`, `test_load_weights_rejects_weight_above_one`), both with rows that still sum to 1.0 to prove the Σ≈1 check alone is insufficient.
- **Why:** the Phase-10 learning loop rewrites this file programmatically; an unbounded negative/>1 weight could produce a nonsensical composite while passing a Σ check.
- **Files:** src/catalyst_trader/quant/rubric.py, tests/test_rubric.py
- **Commit:** 66a7320 (impl), 14a26e0 (tests)

## Known Stubs

None — both loaders read real shipped data files; no placeholder/mock data.

## Self-Check: PASSED
- data/rubric_weights.json, data/base_rates.csv, src/catalyst_trader/quant/rubric.py, src/catalyst_trader/quant/base_rates.py, tests/test_rubric.py, tests/test_base_rates.py — all present.
- Commits 5cf2d26, 14a26e0, 66a7320 — all in git log.
