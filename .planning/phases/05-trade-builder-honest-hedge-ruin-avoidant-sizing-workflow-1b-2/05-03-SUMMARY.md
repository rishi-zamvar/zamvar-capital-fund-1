---
phase: 05-trade-builder-honest-hedge-ruin-avoidant-sizing-workflow-1b-2
plan: 03
subsystem: knowledge-base / param-seam
tags: [params, provenance, versioning, bootstrap, moat]
requires:
  - kb.insert_playbook / query_playbooks (Phase-2 playbook node)
  - kb.EvidenceSource + insert_claim (mandatory-citation invariant)
  - data/base_rates.csv (cited-CSV convention mirrored)
provides:
  - kb.load_params(conn, catalyst_type)  # the frozen model-fit param seam
  - kb.seed_fitted_params(conn, csv_path=None)  # cited bootstrap loader
  - kb.BOOTSTRAP_DEFAULT  # the ONLY literal param set
  - data/fitted_params_bootstrap.csv  # cited per-type bootstrap (estimator + sl_tp + builder)
affects:
  - 05-06 trade builder (reads params["builder"] via load_params — thresholds homed here)
  - 05-02 estimator + SL/TP tools (params passed IN from load_params)
  - Phase 9 refit loop (replaces the SOURCE behind load_params, no rewrite)
tech-stack:
  added: []
  patterns:
    - "params fitted-from-data, never hand-tuned literals (assumptions-are-the-moat)"
    - "versioning via the playbook confidence column (higher shadows lower)"
    - "a fitted param set is itself a CITED claim (cite-or-drop)"
key-files:
  created:
    - data/fitted_params_bootstrap.csv
    - tests/test_kb_params.py
  modified:
    - src/catalyst_trader/kb.py
decisions:
  - "load_params is the ONE frozen seam Phase-9's refit loop replaces the SOURCE of; the quant tools + builder stay pure (params passed IN), the DB read lives in load_params."
  - "BOOTSTRAP_DEFAULT is the ONLY literal param set allowed; returned as a deep copy on the cold path so a caller can't poison the module-level default."
  - "The builder group (min_tradeable_size, log_growth_margin, runup_capture_frac) is homed in BOOTSTRAP_DEFAULT + the CSV — never literals in the builder body (WARNING fix; 05-06 depends on it)."
  - "Bootstrap rows seeded at confidence 0.3 so any later, better fit shadows them automatically (versioning), no schema change."
metrics:
  duration: 8min
  tasks: 2
  files: 3
  tests_added: 12
  completed: 2026-08-15
---

# Phase 5 Plan 03: Model-Fit Parameter Seam Summary

The model-fit parameter seam: `kb.load_params(conn, catalyst_type)` returns the highest-confidence
`fitted_params:<type>` playbook's strategy dict (versioned via the confidence column), or a labeled
`BOOTSTRAP_DEFAULT` when none exists — plus `seed_fitted_params` which writes one CITED bootstrap
param set per catalyst type from `data/fitted_params_bootstrap.csv` so the estimator/SL-TP tools AND
the trade builder are parameterized honestly from trade #1.

## What Was Built

- **`kb.load_params`** — the frozen seam. `query_playbooks(f"fitted_params:{type}")` (confidence-desc)
  → `[0]["strategy"]`, else a deep copy of `BOOTSTRAP_DEFAULT`. Only the SOURCE of params evolves
  (Phase 9); the quant tools + builder stay pure (dict passed IN).
- **`kb.BOOTSTRAP_DEFAULT`** — the ONLY literal param set: `estimator` + `sl_tp` + `builder` +
  `fit_source`. The builder group (`min_tradeable_size`, `log_growth_margin`, `runup_capture_frac`)
  is homed here, resolving the WARNING that the builder must never hard-code its thresholds.
- **`data/fitted_params_bootstrap.csv`** — one cited row per catalyst type (pdufa, ph3_readout,
  conference, earnings) with all three param groups + `fit_source` + evidence URL/snippet. Values are
  honest bootstrap heuristics derived from `base_rates.csv` + published per-type gap studies, labeled
  as such (refit in Phase 9).
- **`kb.seed_fitted_params`** — reads the CSV, builds the strategy dict per row, and inserts one
  cited `fitted_params:<type>` playbook via `insert_playbook` (routed through `insert_claim`, so the
  mandatory-citation invariant holds). Cite-or-drop: a row missing its evidence URL raises. Seeded at
  confidence 0.3 so a later fit shadows it.

## Reuse (no new schema)

Reuses the Phase-2 `playbook` node verbatim (namespaced `fitted_params:<type>`), `insert_playbook`,
`query_playbooks`, `EvidenceSource`, and the `data/base_rates.csv` cited-CSV convention. NO new
node/table type, NO migration, NO refit loop (Phase 9 slots in behind the frozen seam).

## Deviations from Plan

None — plan executed exactly as written. One small addition beyond the plan text (Rule 2, correctness):
`load_params` returns a `copy.deepcopy` on the cold path and `seed_fitted_params` enforces cite-or-drop
on a missing evidence URL, each covered by a dedicated test — both guard the money-critical param path.

## Verification

- `.venv/bin/python -m pytest tests/test_kb_params.py -q` → 12 passed
- `.venv/bin/python -m pytest -q` → 576 passed (564 baseline + 12 new), no regression, no migration added
- Acceptance greps all pass (load_params, BOOTSTRAP_DEFAULT, min_tradeable_size in kb.py + CSV; CSV exists with fit_source + builder cols)
- The 2 warnings are pre-existing statsmodels ComplexWarnings in test_pairs.py (out of scope)

## Known Stubs

None. Bootstrap CSV values are labeled honest heuristics (not stubs) — cited and functional from trade
#1; the Phase-9 refit loop replaces them via the confidence-column versioning already wired here.

## Self-Check: PASSED
- FOUND: src/catalyst_trader/kb.py (load_params, seed_fitted_params, BOOTSTRAP_DEFAULT)
- FOUND: data/fitted_params_bootstrap.csv
- FOUND: tests/test_kb_params.py (12 tests)
- FOUND commits: f81f0d4, 7634710, 8c62755, 35975f8
