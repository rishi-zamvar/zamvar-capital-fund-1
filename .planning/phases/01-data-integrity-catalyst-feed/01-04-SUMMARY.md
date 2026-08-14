---
phase: 01-data-integrity-catalyst-feed
plan: 04
subsystem: core
tags: [store, verify, two-source, provenance, tradeable-gate, curated-pdufa, cli, ad-hoc, tdd]

# Dependency graph
requires:
  - phase: 01-01
    provides: Catalyst/CatalystSource pydantic models + enums, db.connect/migrate, 001_init.sql schema, pytest harness + db fixture
  - phase: 01-02
    provides: dates.parse_precision + dates.classify (canonical precision/uncertainty seam)
provides:
  - "store.insert_catalyst — atomic catalyst+sources write in one transaction, rollback on failure, dedup by (ticker, external_ref)"
  - "store.get_catalyst + store.tradeable_catalysts — hydrating readers; tradeable_catalysts is the status='verified' query gate"
  - "calendar/verify.py verify_catalyst — two-source rule + uncertainty re-derivation from the most-authoritative source date_type"
  - "calendar/verify.py is_tradeable — the single tradeable predicate (status=='verified')"
  - "calendar/verify.py load_curated_pdufa — curated CSV rows enter the same insert->verify pipeline"
  - "cli.py inject — ad-hoc user catalyst through the identical pipeline (starts unverified, one secondary source)"
  - "data/pdufa_curated.csv — hand-curated PDUFA/AdCom template (header + commented placeholders; real rows in Plan 06)"
affects: [refresh, triggers, universe, plan-05-refresh, plan-06-curation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Atomic write-path: insert_catalyst writes catalyst + N source rows in one transaction, rollback+re-raise on any failure — no date reaches the DB without provenance"
    - "Single tradeable gate: is_tradeable(c) = c.status == Status.verified, queried at the store via tradeable_catalysts — never a boolean scattered across callers"
    - "Uncertainty re-derived (never judged): verify reads the most-authoritative (primary-preferred) agreeing source's persisted date_type and passes it to classify()"
    - "One ingestion->verify pipeline for every origin (provider, curated CSV, ad-hoc CLI) — user dates cannot bypass the two-source rule"

key-files:
  created:
    - src/catalyst_trader/store.py
    - src/catalyst_trader/calendar/__init__.py
    - src/catalyst_trader/calendar/verify.py
    - src/catalyst_trader/cli.py
    - data/pdufa_curated.csv
    - tests/test_store.py
    - tests/test_verify.py
    - tests/test_cli.py
  modified: []

key-decisions:
  - "Atomicity via explicit try/commit + except/rollback+re-raise (not `with conn:`) so the rollback is visible and the acceptance grep is honest; PRAGMA foreign_keys already ON from db.connect"
  - "Dedup by (ticker, external_ref) UPDATEs the catalyst and REPLACES its source rows (idempotent re-fetch); corroborating sources are added via a separate path (Plan 05 refresh), not by re-inserting the same ref"
  - "verify_catalyst only transitions unverified<->verified; it never resurrects an excluded/resolved catalyst (guards the terminal states)"
  - "Most-authoritative source = prefer a primary agreeing row, else the first agreeing row — its date_type drives classify(); verify never guesses ESTIMATED vs ACTUAL"
  - "Curated PDUFA + ad-hoc both default date_type='estimated' (an announced/target date is not a realized 'actual'); 'actual' is reserved for confirmed-realized sources"
  - "verify_catalyst carries an unused `now` hook param — the 48h near-event exclusion belongs to Plan 05's refresh, documented but not implemented here"
  - "store._v() coerces enums->value at the DB boundary and passes plain strings through, so a model_construct bypass hits the SQLite CHECK rather than corrupting a row"

patterns-established:
  - "Provenance-enforced atomic persistence (store.insert_catalyst) — the physical mechanism behind the no-LLM-date invariant"
  - "Single computed tradeable predicate (is_tradeable) as the only downstream gate"

requirements-completed: [DATA-02]

# Metrics
duration: 10min
completed: 2026-08-14
---

# Phase 1 Plan 4: Trust-Enforcement Core (Store + Verify + CLI) Summary

**The money-critical trust root is now mechanical: a date physically cannot reach the DB without a source row in the same transaction, tradeability is one computed predicate (>=2 agreeing sources incl >=1 primary), uncertainty is re-derived from each source's own persisted precision (never guessed), and curated-PDUFA + ad-hoc-user origins both flow through the identical insert->verify pipeline — no origin can produce a tradeable date without corroboration.**

## Performance
- **Duration:** ~10 min
- **Completed:** 2026-08-14
- **Tasks:** 3 (all TDD: RED test → GREEN impl)
- **Files created:** 8
- **Tests:** full suite 134 → 158 green (+24 new: 7 store, 12 verify, 5 cli)

## Accomplishments
- **Atomic write-path (`store.py`):** `insert_catalyst` writes the catalyst row + all source rows in one transaction, rolls back + re-raises on any mid-insert failure, rejects a sourceless catalyst before any write, and dedups idempotently by `(ticker, external_ref)`. `get_catalyst` / `tradeable_catalysts` hydrate back to models; `tradeable_catalysts` is the `status='verified'` query gate.
- **Two-source verify (`calendar/verify.py`):** `verify_catalyst` counts agreeing sources, requires >=1 primary, re-derives uncertainty from the most-authoritative source's `date_type` via `classify()`, and persists status+uncertainty. `is_tradeable` is the single `status=='verified'` predicate. Terminal states (excluded/resolved) are never resurrected.
- **Curated PDUFA loader:** `load_curated_pdufa` parses the CSV (skipping blank/comment lines), builds one catalyst + one source per row (default `date_type='estimated'`), and inserts through the same `insert_catalyst` path — starting unverified, needing a 2nd source.
- **Ad-hoc CLI (`cli.py`):** stdlib `argparse`, `inject` + `verify` subcommands, importable `inject()`. User catalysts start unverified with one secondary source, partial dates preserved as window, invalid dates raise (no fabrication) — same pipeline, no bypass.

## Task Commits
Each task committed atomically (TDD: RED test → GREEN impl):

1. **Task 1: Atomic persistence write-path (store.py)**
   - `83d98ef` (test) — failing store tests
   - `1dae9e6` (feat) — store.py (insert_catalyst, get_catalyst, tradeable_catalysts)
2. **Task 2: Two-source verify + tradeable gate + curated PDUFA loader**
   - `e8553ac` (test) — failing verify tests
   - `5f39573` (feat) — calendar/verify.py + calendar/__init__.py + data/pdufa_curated.csv
3. **Task 3: Ad-hoc catalyst injection CLI**
   - `13a5ead` (test) — failing cli tests
   - `024182d` (feat) — cli.py

## Files Created
- `src/catalyst_trader/store.py` — atomic insert + hydrating readers + tradeable query gate.
- `src/catalyst_trader/calendar/__init__.py` — package init (empty).
- `src/catalyst_trader/calendar/verify.py` — two-source rule, uncertainty re-derivation, is_tradeable, curated PDUFA loader.
- `src/catalyst_trader/cli.py` — ad-hoc injection + manual verify (argparse, importable inject()).
- `data/pdufa_curated.csv` — hand-curated PDUFA/AdCom template (header + commented placeholders).
- `tests/test_store.py`, `tests/test_verify.py`, `tests/test_cli.py` — 24 new tests.

## Verification
- `.venv/bin/pytest tests/test_store.py tests/test_verify.py tests/test_cli.py -q` → 24 passed.
- Full suite: `158 passed`.
- No code path persists a date without a source row (empty-sources rejected at model + write path; atomicity test proves rollback leaves zero orphan rows).
- Tradeable == verified == (>=2 agreeing sources incl >=1 primary): single/no-primary/one-disagrees all stay unverified; two agreeing + primary → verified.
- Uncertainty re-derived from source `date_type`: identical single-source full-day → estimated=window, actual=soft; month-only with two primaries still window; corroborated full-day primary → firm.
- Ad-hoc + curated both flow through verify: ad-hoc starts unverified and only verifies after a 2nd primary source is added; curated CSV rows load as `curated_pdufa`, unverified, `date_type=estimated`.
- All grep + `--help` acceptance criteria for all three tasks pass.

## Deviations from Plan
**None — plan executed exactly as written.** (Rules 1–4 not triggered; no auth gates.)

One documented interface refinement (not a deviation from intent): `inject()` and `verify_catalyst()` take the DB connection as their first argument so tests call them directly against the `db` fixture without a subprocess — exactly as the plan's "expose an importable inject()" instruction requires.

## Known Stubs
- `data/pdufa_curated.csv` contains only the header and COMMENTED-OUT placeholder example rows — intentionally no real PDUFA dates (the executor must not invent them from memory). Real, source-confirmed rows are filled during the **Plan 06 curation checkpoint**. `load_curated_pdufa` loads it to zero catalysts until then. Not a blocker for Plan 04's goal (the loader is exercised by a tmp-path CSV in `test_load_curated_pdufa`).
- `verify_catalyst(now=...)` freshness hook is present but inert — the 48h near-event re-verify/exclusion is **Plan 05 refresh** (DATA-03's re-verify half remains open there; the two-source + exclusion half is complete here).

## Self-Check: PASSED
All 8 created files present; all 6 task commits (83d98ef, 1dae9e6, e8553ac, 5f39573, 13a5ead, 024182d) exist in history.
