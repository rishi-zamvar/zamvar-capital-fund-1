---
phase: 01-data-integrity-catalyst-feed
plan: 01
subsystem: database
tags: [python, sqlite, pydantic, pydantic-settings, pytest, httpx, freezegun, clinicaltrials-gov, fmp]

# Dependency graph
requires: []
provides:
  - Installable src-layout Python package (catalyst-trader 0.1.0) with pinned deps
  - Env-first pydantic-settings config (FMP key, freshness tunables) — no hardcoded secrets
  - Single-file SQLite store + idempotent numbered-migration runner + schema_version tracking
  - Full Phase-1 schema (catalyst, catalyst_source, universe_snapshot, schema_version) with CHECK + FK constraints
  - pydantic domain models (Catalyst/CatalystSource/UniverseSnapshot + 7 enums) enforcing the no-LLM-date invariant
  - pytest harness: migrated in-memory db fixture, fixture-loader, frozen-clock helper
  - Live-captured CT.gov v2 fixtures (partial-date, full-date, collaborator) + documented-shape FMP fixtures
affects: [01-02, 01-03, 01-04, 01-05, 01-06, phase-2-knowledge-base]

# Tech tracking
tech-stack:
  added: [httpx==0.28.1, pydantic==2.13.4, pydantic-settings, pytest==9.1.1, pytest-httpx==0.36.2, freezegun==1.5.5, pytest-cov, ruff]
  patterns: [src-layout package, numbered-SQL-migrations + schema_version row, provenance-enforced models, TDD tests-before-logic, offline recorded API fixtures]

key-files:
  created:
    - pyproject.toml
    - src/catalyst_trader/config.py
    - src/catalyst_trader/db.py
    - src/catalyst_trader/models.py
    - src/catalyst_trader/migrations/001_init.sql
    - tests/conftest.py
    - tests/fixtures/ (CT.gov + FMP JSON + README)
  modified: []

key-decisions:
  - "No-LLM-date invariant enforced at the pydantic boundary: Catalyst.sources may not be empty"
  - "date_type persisted per source (estimated/actual) so verify.py re-derives uncertainty, never guesses (DATA-04)"
  - "Migration runner (db.py) records schema_version — the .sql file does not self-record — keeping application idempotent"
  - "FMP fixtures are documented-shape (no key present); flagged in README for live re-confirm before the Plan 03 parser"

patterns-established:
  - "Numbered migrations/NNN_*.sql applied in order, guarded by a schema_version row — carries unchanged into Phase 2"
  - "Providers/models attach provenance so a date physically cannot be stored without a named source"
  - "TDD: failing tests committed first (RED), then implementation (GREEN)"
  - "Offline deterministic tests via recorded fixtures + freezegun; CI never hits live APIs"

requirements-completed: [DATA-01]

# Metrics
duration: 5min
completed: 2026-08-14
---

# Phase 1 Plan 01: Project Skeleton, Schema & Domain Models Summary

**src-layout catalyst-trader package with an idempotent SQLite migration runner, the full 4-table Phase-1 schema, provenance-enforced pydantic models (a Catalyst cannot exist without a named source), and live-captured CT.gov v2 fixtures including a genuine month-only partial date.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-08-14T19:25:00Z
- **Completed:** 2026-08-14T19:30:45Z
- **Tasks:** 3
- **Files modified:** 15 created

## Accomplishments
- Installable editable package (`pip install -e '.[dev]'`) with pinned deps; `pytest -q` green (22 tests)
- Full Phase-1 schema migrates idempotently to version 1 — all four tables with CHECK + FK constraints
- pydantic models bake in the no-LLM-date invariant (empty `sources` rejected at construction) and persist per-source `date_type` (DATA-04)
- Real CT.gov v2 fixtures captured live (partial `2010-03`, full `2024-06-12`, university-lead collaborator) + documented-shape FMP fixtures flagged for live re-confirm

## Task Commits

Each task was committed atomically:

1. **Task 1: Project skeleton (pyproject, package, config)** — `ef59f9b` (feat)
2. **Task 2: SQLite store, migration runner, domain models** — `03d59e0` (test/RED) → `d75b476` (feat/GREEN)
3. **Task 3: Wave 0 fixtures + shared conftest** — `ebda505` (test)

_TDD Task 2 produced a RED commit (failing tests) then a GREEN commit (implementation)._

## Files Created/Modified
- `pyproject.toml` — PEP 621 src-layout project, pinned deps, pytest/ruff config
- `.gitignore` — venv, caches, `*.db`, `.env`, `*.live.json`
- `src/catalyst_trader/config.py` — pydantic-settings env-first config
- `src/catalyst_trader/db.py` — `connect()` (FK on, Row factory) + idempotent `migrate()`
- `src/catalyst_trader/models.py` — Catalyst/CatalystSource/UniverseSnapshot + 7 enums + empty-sources validator
- `src/catalyst_trader/migrations/001_init.sql` — 4-table schema with all constraints
- `tests/conftest.py` — `db` fixture, `load_fixture`, `frozen_now`
- `tests/test_db.py`, `tests/test_models.py`, `tests/test_fixtures.py` — 22 tests
- `tests/fixtures/*.json` + `README.md` — CT.gov (live) + FMP (documented-shape) fixtures

## Decisions Made
- Enforced the no-LLM-date invariant in the model layer (pydantic validator) rather than only at the DB write path — fails fast at the type boundary.
- Migration runner owns version recording (not the SQL file) so re-running `migrate()` is a no-op.
- Selected a Vertex-**lead** study for the partial/full fixtures and a university-lead study for the collaborator fixture to make the sponsor-fuzziness gotcha explicit.

## Deviations from Plan

None — plan executed exactly as written. FMP key was absent (expected per plan), so FMP fixtures were built to the documented shape and flagged in `tests/fixtures/README.md` for live re-confirmation before the Plan 03 parser, exactly as the plan's Task 3 specifies.

## Issues Encountered
- A `db` fixture named the same as the `db` module caused an import shadow in conftest — resolved by importing the module as `_db`.
- A freezegun test failed when `datetime` was imported inside the frozen `with` block — resolved by importing at module level (freezegun patches already-imported symbols).

## Known Stubs
- `tests/fixtures/fmp_earnings_calendar.json` / `fmp_earnings_confirmed.json` are **documented-shape, not live** (no `FMP_API_KEY` at capture time). This is intentional per the plan; the README flags that exact field names MUST be re-confirmed against a live pull before the Plan 03 FMP parser is trusted (RESEARCH Open Question #1). Not blocking for this plan's goal (skeleton + schema + models + CT.gov fixtures).

## User Setup Required
None for this plan. To make FMP earnings ingestion (Plan 03) work, provision `FMP_API_KEY` in the environment / `.env` and re-capture the FMP fixtures live (steps in `tests/fixtures/README.md`).

## Next Phase Readiness
- Plans 02–06 inherit a correct, provenance-enforced foundation: the schema, models, migration runner, and test harness are all in place.
- The CT.gov fixtures (with a genuine month-only date) are ready for the partial-date-aware parser in a later plan.
- Open follow-up: live FMP fixture capture once a key is available.

---
*Phase: 01-data-integrity-catalyst-feed*
*Completed: 2026-08-14*

## Self-Check: PASSED
All claimed files exist on disk and all four task commits (ef59f9b, 03d59e0, d75b476, ebda505) are present in git history.
