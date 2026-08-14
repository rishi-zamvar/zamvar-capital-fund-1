---
phase: 01-data-integrity-catalyst-feed
plan: 03
subsystem: api
tags: [clinicaltrials, fmp, httpx, pytest-httpx, providers, provenance, catalyst, tdd]

# Dependency graph
requires:
  - phase: 01-01
    provides: Catalyst/CatalystSource pydantic models + enums, config.settings, pytest/pytest-httpx harness, captured fixtures
  - phase: 01-02
    provides: dates.parse_precision + dates.classify (the canonical precision/uncertainty seam)
provides:
  - "providers/clinicaltrials.py fetch_trial_readouts — CT.gov v2 date-window search, nested parse, lead-sponsor filter, partial-date-aware"
  - "providers/fmp.py fetch_earnings — earnings calendar + confirmed endpoints, confirmed->actual promotion marker"
  - "providers/base.py Provider protocol + ProviderRecord alias (Pattern 1: provenance attached, never a bare date)"
  - "data/ticker_sponsor_map.csv starter template (ticker -> exact legal leadSponsor name)"
affects: [verify, refresh, triggers, universe, plan-06-curation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Provider returns list[Catalyst] with exactly one CatalystSource attached — a date cannot leave a provider without a named source (Pattern 1)"
    - "date_type (ESTIMATED/ACTUAL, confirmed/estimated) persisted per source so verify re-derives uncertainty without guessing (DATA-04)"
    - "Offline provider tests via pytest-httpx recorded fixtures — no live network in the suite"

key-files:
  created:
    - src/catalyst_trader/providers/__init__.py
    - src/catalyst_trader/providers/base.py
    - src/catalyst_trader/providers/clinicaltrials.py
    - src/catalyst_trader/providers/fmp.py
    - data/ticker_sponsor_map.csv
    - tests/test_clinicaltrials.py
    - tests/test_fmp.py
  modified: []

key-decisions:
  - "CT.gov attribution is by curated exact lead-sponsor name, inverting the sponsor_map (ticker -> [legal names]); collaborator/university studies are dropped, not flagged"
  - "FMP 'confirmed' is expressed as CatalystSource.date_type=actual rather than a new model field — reuses the DATA-04 seam verify already reads (no schema change)"
  - "Providers reuse dates.classify unchanged; single-source ACTUAL/confirmed -> soft, single-source ESTIMATED/calendar -> window (firm only reachable after corroboration in verify)"
  - "Missing FMP_API_KEY raises RuntimeError — no placeholder key, no silent empty; caller (refresh) degrades gracefully"
  - "First HTTP request never sleeps (spacing applied only between subsequent requests) — keeps single-page tests instant without touching settings"

patterns-established:
  - "Pattern 1 (provenance-attached records): every provider function returns Catalyst objects with their CatalystSource already populated"
  - "ProviderRecord is aliased to Catalyst rather than wrapped — the model already carries sources, so a wrapper would be redundant"

requirements-completed: [DATA-01, DATA-04]

# Metrics
duration: 5min
completed: 2026-08-14
---

# Phase 1 Plan 3: CT.gov + FMP Catalyst Providers Summary

**The two auto-feed providers (ClinicalTrials.gov v2 trial readouts + FMP earnings) emit typed catalyst records with provenance physically attached — honoring both verified CT.gov gotchas (month-only dates survive as window, collaborator studies are not misattributed) — fully tested offline against the captured fixtures.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-08-14T19:43:37Z
- **Completed:** 2026-08-14T19:47:00Z
- **Tasks:** 2
- **Files created:** 7

## Accomplishments
- CT.gov v2 client: date-window study search (`AREA[PrimaryCompletionDate]RANGE[...]`), `nextPageToken` pagination, nested-path parse, curated lead-sponsor filter, partial dates routed through `dates.classify` (never coerced to a day).
- FMP client: calendar + confirmed endpoints, confirmed symbols promoted via `date_type=actual`, env-only key that fails loudly when absent.
- Both providers attach a `CatalystSource` (name + url + date_type + retrieved_at) to every record — the no-LLM-date invariant is enforced at the provider boundary, not just the model.
- 12 new offline tests (7 CT.gov + 5 FMP), full suite 122 -> 134 green; ruff clean.

## Task Commits

Each task committed atomically (TDD: RED test → GREEN impl):

1. **Task 1: Provider protocol + ClinicalTrials.gov v2 client**
   - `b13d8d0` (test) — failing CT.gov tests
   - `db566de` (feat) — base.py + clinicaltrials.py + ticker_sponsor_map.csv
2. **Task 2: FMP earnings-calendar + confirmed client**
   - `ef571e7` (test) — failing FMP tests
   - `cf94bb2` (feat) — fmp.py

## Files Created/Modified
- `src/catalyst_trader/providers/base.py` — Provider protocol + ProviderRecord alias (Pattern 1 documentation).
- `src/catalyst_trader/providers/clinicaltrials.py` — `fetch_trial_readouts` + `load_sponsor_map`; nested CT.gov v2 parse, lead-sponsor filter, pagination, spacing.
- `src/catalyst_trader/providers/fmp.py` — `fetch_earnings`; calendar+confirmed merge, confirmed->actual marker, missing-key guard.
- `data/ticker_sponsor_map.csv` — starter ticker->legal-sponsor map (VRTX, REGN); requires Plan 06 human curation.
- `tests/test_clinicaltrials.py`, `tests/test_fmp.py` — fixture-driven offline suites (pytest-httpx).

## Verification
- `.venv/bin/pytest tests/test_clinicaltrials.py tests/test_fmp.py -q` → 12 passed.
- Full suite: `134 passed`.
- Partial CT.gov date (`2010-03`) survives as `date_precision=month` / `uncertainty=window`, `event_date` uncoerced.
- Collaborator study (lead = Virginia Commonwealth University) returns `[]` under a VRTX-only sponsor map.
- FMP confirmed (VRTX/REGN) → `date_type=actual`; calendar-only (SRPT/BMRN) → `estimated`; missing key raises `RuntimeError`.
- All grep acceptance criteria for both tasks pass.

## Deviations from Plan

**1. [Plan-prose vs fixture reality] Full-date fixture is ACTUAL, not ESTIMATED**
- **Found during:** Task 1.
- **Issue:** The plan's behavior note said the full-date fixture yields `uncertainty=window (single-source ESTIMATED)`, but the captured `ctgov_full_date.json` is `type=ACTUAL`. Under the canonical `dates.classify`, a single-source ACTUAL day is `soft`, not `window`.
- **Resolution:** Tested the truthful classifier outcome (`date_precision=day`, `date_type=actual`, `uncertainty=soft`) rather than the plan's assumed value. The classifier (Plan 02) is canonical and unchanged; this is a doc/fixture mismatch, not a code bug.
- **Files:** tests/test_clinicaltrials.py. **Commit:** b13d8d0.

**2. [Ponytail simplification] ProviderRecord aliased, not wrapped; FMP "confirmed" reuses date_type**
- The plan floated a `ProviderRecord` dataclass and a `confirmed` marker. `Catalyst` already carries `sources`, and `CatalystSource.date_type` already encodes estimated/actual (the exact signal verify reads). Aliasing `ProviderRecord = Catalyst` and expressing confirmed as `date_type=actual` avoids a redundant wrapper and a schema change. No behavior lost.

## Known Stubs
- `data/ticker_sponsor_map.csv` is a 2-row starter template (VRTX, REGN), intentionally incomplete — full ~20-name curation is the Plan 06 human checkpoint. Documented in-file and in key-decisions. Not a blocker for Plan 03's goal (the parser + filter are exercised by the fixtures).

## Self-Check: PASSED

All 8 created files present; all 4 task commits (b13d8d0, db566de, ef571e7, cf94bb2) exist in history.
