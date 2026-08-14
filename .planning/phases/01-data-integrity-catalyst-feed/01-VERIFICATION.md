---
phase: 01-data-integrity-catalyst-feed
verified: 2026-08-14T20:18:12Z
status: passed
score: 5/5 must-haves verified (plus 1 expected human carry-forward)
---

# Phase 1: Data Integrity & Catalyst Feed Verification Report

**Phase Goal:** The system always knows what catalyst is coming, when, and how sure it is — with no date ever originating from an LLM's memory.
**Verified:** 2026-08-14T20:18:12Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | No catalyst date can originate from an LLM (provenance enforced at model + write-path) | ✓ VERIFIED | `models.py` `Catalyst._at_least_one_source` validator rejects `sources=[]`; `store.insert_catalyst` re-asserts `if not catalyst.sources: raise ValueError(...)` before any row is written, and rolls back on any mid-insert failure (`except Exception: conn.rollback(); raise`) |
| 2 | Uncertainty typing is precision-derived; a partial date can never be firm | ✓ VERIFIED | `dates.classify()`: `if parse_precision(raw_date) is not DatePrecision.day: return Uncertainty.window` runs unconditionally before any corroboration check. `tests/test_dates.py::test_month_or_year_date_is_never_firm` parametrizes every (source_count, date_type, raw) combination — 100 tests pass, all green |
| 3 | Two-source verification gate blocks tradeability; unverifiable dates excluded | ✓ VERIFIED | `verify.is_tradeable` = single predicate `status==verified`; `verify_catalyst` sets verified iff `len(agreeing)>=2 and has_primary`; `store.tradeable_catalysts` filters `WHERE status='verified'` — the only query-layer gate. `triggers.exclude_stale` sets `status='excluded'` (never deletes) when a near-event catalyst goes stale |
| 4 | date_type persisted per source and READ (not guessed) by verify | ✓ VERIFIED | `catalyst_source.date_type` column with CHECK constraint in `001_init.sql`; `verify_catalyst` reads `authoritative.date_type.value` from the actual DB-hydrated source row (primary-preferred) and passes it into `classify()` — no guess path exists |
| 5 | Idempotent daily refresh + 48h re-verify + T-2 trigger seam exist; Workflow 1 is NOT built | ✓ VERIFIED | `refresh.refresh()` dedups by `external_ref` (proven idempotent by `test_refresh.py -k idempot`); `triggers.exclude_stale` implements the 48h rule; `triggers.detect_and_fire` fires the pluggable seam once per (catalyst_id, event_date) via a `UNIQUE` constraint on `trigger_event`. `grep -rli "workflow.?1\|debate\|bull\|bear" src/` returns nothing — no Workflow-1 code exists |
| 6 | Point-in-time universe builder is append-only + retains delisted names | ✓ VERIFIED | `universe/build.py::build_snapshot` only executes `INSERT` (no `UPDATE`/`DELETE` on `universe_snapshot` anywhere in the file); delisted seed rows are written with `delisted=1` and `included` computed independently (reason `"delisted (retained for backtest)"`) — not filtered out |
| 7 | The full pytest suite passes | ✓ VERIFIED | `.venv/bin/pytest -q` → **179 passed** in 0.27s, zero failures/errors/skips |

**Score:** 7/7 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/catalyst_trader/models.py` | Catalyst/CatalystSource + enums, empty-sources validator | ✓ VERIFIED | `class Catalyst`, `field_validator("sources")` present and tested |
| `src/catalyst_trader/db.py` | migration runner | ✓ VERIFIED | `connect`/`migrate` idempotent, both migrations (001, 002) apply in order |
| `src/catalyst_trader/dates.py` | `parse_precision` + `classify` | ✓ VERIFIED | No `dateutil` import; 100 tests exercise every precision × date_type × corroboration combination |
| `src/catalyst_trader/providers/clinicaltrials.py` | CT.gov client, partial-date-aware, lead-sponsor filter | ✓ VERIFIED | `exports fetch_trial_readouts`; lead-sponsor exact-match filter (`if lead not in allowed_sponsors: return None`); `nextPageToken` pagination |
| `src/catalyst_trader/providers/fmp.py` | FMP earnings client, confirmed promotion | ✓ VERIFIED | Raises `RuntimeError("FMP_API_KEY not set")` on missing key, never a placeholder |
| `src/catalyst_trader/store.py` | atomic `insert_catalyst`, `tradeable_catalysts` | ✓ VERIFIED | Single-transaction insert + rollback-on-exception; dedup by `(ticker, external_ref)` |
| `src/catalyst_trader/calendar/verify.py` | two-source rule + curated PDUFA loader | ✓ VERIFIED | `verify_catalyst`, `is_tradeable`, `load_curated_pdufa` all present and correct |
| `src/catalyst_trader/cli.py` | ad-hoc injection through same pipeline | ✓ VERIFIED | `inject()` uses `store.insert_catalyst`, `source_origin=ad_hoc_user`, argparse (no new dep) |
| `src/catalyst_trader/calendar/refresh.py` | idempotent orchestrator | ✓ VERIFIED | Wires fetch → insert → verify → exclude_stale → detect_and_fire; graceful FMP degrade |
| `src/catalyst_trader/calendar/triggers.py` | T-2 seam + 48h exclusion | ✓ VERIFIED | `detect_and_fire` idempotent via `INSERT OR IGNORE` + `UNIQUE(catalyst_id, event_date)`; day-precision-only firing documented and enforced |
| `com.zamvar.catalyst-refresh.plist` | launchd daily schedule | ✓ VERIFIED | `plutil -lint` OK; `StartCalendarInterval` 07:30; not auto-loaded (deliberate) |
| `src/catalyst_trader/universe/build.py` | point-in-time builder | ✓ VERIFIED | `build_snapshot`, `universe_as_of` present; append-only by construction |
| `data/seed_universe.csv`, `data/ticker_sponsor_map.csv`, `data/pdufa_curated.csv` | curated data | ⚠️ EXPECTED CARRY-FORWARD | Templates ship with 2 labelled example rows (VRTX/REGN) for seed+sponsor map; `pdufa_curated.csv` is header-only. `data/README.md` documents this is a pending human task (money-critical, no-LLM-invented dates) — matches the phase's own blocking human-verify checkpoint design and the user's stated known carry-forward |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `db.py` | `migrations/*.sql` | numbered migration runner | ✓ WIRED | `migrate()` applies 001 and 002 in filename order, idempotent |
| `models.py` | `catalyst_source` rows | empty-sources validator | ✓ WIRED | Tested at both model and store layer (defense in depth) |
| `dates.py` | `models.py` | returns DatePrecision/Uncertainty enums | ✓ WIRED | `classify()` return type is `Uncertainty` member |
| `providers/clinicaltrials.py` | `dates.py` | `parse_precision`/`classify` on `primaryCompletionDateStruct` | ✓ WIRED | `_parse_study` calls both directly |
| `providers/clinicaltrials.py` | `data/ticker_sponsor_map.csv` | lead-sponsor exact-name filter | ✓ WIRED | `load_sponsor_map()` reads the CSV; filter applied before any Catalyst is built |
| `store.py` | `catalyst_source` table | one-transaction insert, reject empty | ✓ WIRED | Rollback-tested (`test_store.py -k "empty or orphan or source"` green) |
| `calendar/verify.py` | `dates.py` | `classify()` using real source_count/has_primary from DB rows | ✓ WIRED | Reads hydrated `catalyst.sources`, not provider-time assumptions |
| `cli.py` | `store.py` | ad-hoc injection uses `insert_catalyst` | ✓ WIRED | Same pipeline, tested unverified→not-tradeable path |
| `calendar/refresh.py` | providers + store + verify | fetch → insert → verify → exclude → trigger | ✓ WIRED | All five stages present in one function, each import used |
| `calendar/triggers.py` | registered Workflow-1 callback | pluggable seam (default: log) | ✓ WIRED (seam only) | `register_callback`/`_default_callback`; empty registry logs only — correctly NOT Workflow 1 |
| `universe/build.py` | `catalyst` table | catalyst-density count | ✓ WIRED | `_catalyst_density` runs a real `COUNT(*)` query, lexical ISO-date range |
| `universe/build.py` | `universe_snapshot` table | append-only insert | ✓ WIRED | No `UPDATE`/`DELETE` present; `test_universe.py -k "append or as_of or delisted or density"` green |

### Data-Flow Trace (Level 4)

Not applicable in the frontend sense (no UI in this phase), but the money-critical data-flow chain was traced end-to-end for the no-LLM-date invariant:

| Chain | Source | Produces Real Data | Status |
|-------|--------|---------------------|--------|
| CT.gov → Catalyst.sources → store → verify.uncertainty_type | Live CT.gov v2 API response parsed field-by-field, no static fallback | Yes (fixture-tested, mocked HTTP only in tests — no live calls masking it) | ✓ FLOWING |
| FMP → Catalyst.sources → store → verify.uncertainty_type | Live FMP calendar/confirmed endpoints, key-gated | Yes; missing key raises rather than returning `[]` silently | ✓ FLOWING |
| Curated PDUFA CSV → store → verify | File read, `#`-comment-aware; currently header-only (0 real rows) | No real data yet (expected — pending human curation) | ⚠️ STATIC (documented, expected) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full suite green | `.venv/bin/pytest -q` | 179 passed in 0.27s | ✓ PASS |
| Date classifier never returns firm for partial dates | `.venv/bin/pytest tests/test_dates.py -v` | 100/100 parametrized cases pass, incl. `test_month_or_year_date_is_never_firm` | ✓ PASS |
| Plist is valid and points at the refresh entrypoint | `plutil -lint com.zamvar.catalyst-refresh.plist` | OK | ✓ PASS |
| No Workflow-1 code exists | `grep -rli "workflow.?1\|debate\|bull\|bear" src/` | (no matches) | ✓ PASS |
| CLI ad-hoc injection help | `.venv/bin/python -m catalyst_trader.cli inject --help` | exits 0 (verified via prior test run in CI history; re-confirmed by store/CLI test suite) | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|-----------------|--------------|--------|----------|
| DATA-01 | 01-01, 01-03, 01-04, 01-05 | Rolling catalyst calendar (CT.gov + FMP + curated PDUFA) | ✓ SATISFIED | Providers + verify + refresh orchestration all wired and tested |
| DATA-02 | 01-04 | User can inject ad-hoc catalyst | ✓ SATISFIED | `cli.inject()` tested: unverified start, not tradeable, partial-date-as-window, invalid-date raises |
| DATA-03 | 01-04, 01-05 | Two-source verification + 48h re-verify; unverifiable dates excluded | ✓ SATISFIED | `verify_catalyst` two-source gate + `triggers.exclude_stale` 48h rule, both tested |
| DATA-04 | 01-02, 01-03, 01-04 | Uncertainty typed point-estimate vs. window, precision-derived | ✓ SATISFIED | `dates.classify` money-critical module, 100-case exhaustive test suite, no dateutil |
| DATA-05 | 01-05 | Flag T-2 catalysts, trigger Workflow 1 (seam only) | ✓ SATISFIED | `triggers.detect_and_fire` idempotent T-2 seam; Workflow 1 correctly NOT built |
| DATA-06 | 01-06 | ~20-name universe from explicit criteria, point-in-time | ✓ SATISFIED | `universe/build.py` append-only, delisted-retaining, criteria-scored; real data curation is the one expected carry-forward |

No orphaned requirements — REQUIREMENTS.md maps only DATA-01 through DATA-06 to Phase 1, and all six appear in at least one plan's `requirements` frontmatter field.

### Anti-Patterns Found

None blocking. Scanned all `src/catalyst_trader/**/*.py` for TODO/FIXME/XXX/HACK/placeholder/"not implemented" — the only matches are legitimate documentation comments (e.g. "this module leaves a documented `now` hook but does not implement that logic" — describing the deliberate Plan-05 freshness deferral, not a stub). No empty handlers, no hardcoded empty returns feeding real code paths, no fabricated dates anywhere in the parse/classify/verify chain.

### Human Verification Required

None beyond the phase's own designed checkpoint (already flagged transparently in-repo, not hidden):

### 1. Curate the three data files with real, source-cited entries

**Test:** Populate `data/seed_universe.csv` (~20-30 real tickers), `data/ticker_sponsor_map.csv` (verified against live CT.gov), and `data/pdufa_curated.csv` (real PDUFA/AdCom rows, each with a `source_url`) per `data/README.md`, then run `python -m catalyst_trader.calendar.refresh` and the `build_snapshot` example end-to-end.
**Expected:** Real tradeable catalysts appear after a second corroborating source is added; the universe snapshot reflects the real ~20-name book.
**Why human:** This is explicitly the phase's one money-critical, no-LLM-invented-date human task — the code path is fully built and tested, only the data is pending. This was called out by the user as a known, expected carry-forward, not a gap.

### Gaps Summary

No gaps. All 7 observable truths hold against the actual codebase, not just SUMMARY claims: the no-LLM-date invariant is enforced at both the pydantic model boundary and the atomic store write-path with rollback; the date-precision classifier structurally cannot return `firm` for a partial date (proven by 100 parametrized tests); the two-source verification gate is a single predicate (`status=='verified'`) with no bypass path; `date_type` is persisted per source row and read (never guessed) by verify; the daily refresh is idempotent and the T-2 trigger/48h staleness logic exist as a pluggable seam with zero Workflow-1 code; the universe builder is append-only and retains delisted names; and the full 179-test pytest suite passes with zero failures. The only incomplete item — real curated seed-universe/PDUFA data — is the phase's designed human checkpoint, transparently documented in `data/README.md` and the 01-06-SUMMARY.md, matching the carry-forward explicitly flagged by the user before this verification began.

---

*Verified: 2026-08-14T20:18:12Z*
*Verifier: Claude (gsd-verifier)*
