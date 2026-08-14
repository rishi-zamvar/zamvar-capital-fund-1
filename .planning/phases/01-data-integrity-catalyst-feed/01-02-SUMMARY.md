---
phase: 01-data-integrity-catalyst-feed
plan: 02
subsystem: database
tags: [dates, precision, uncertainty, tdd, pydantic, catalyst]

# Dependency graph
requires:
  - phase: 01-01
    provides: DatePrecision/Uncertainty enums in models.py, pytest harness, .venv
provides:
  - "parse_precision(raw) -> DatePrecision: shape+calendar-validated, never coerces partial dates"
  - "classify(raw_date, date_type, source_count, has_primary) -> Uncertainty: precision-driven uncertainty typing (DATA-04)"
  - "Structural guarantee: a month/year-only source date can never classify as firm"
affects: [clinicaltrials-provider, fmp-provider, verify, refresh, triggers]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Precision from raw-string shape via regex + calendar validation — never dateutil fuzzy parse"
    - "Uncertainty DERIVED from source precision + corroboration, not judgement"

key-files:
  created:
    - src/catalyst_trader/dates.py
    - tests/test_dates.py
  modified: []

key-decisions:
  - "Partial dates (YYYY-MM, YYYY) are ALWAYS window — corroboration is checked only after precision, so firm is structurally unreachable from a partial date"
  - "date_type normalized with .upper() so persisted lowercase DB values and raw API values classify identically"
  - "No dateutil — fuzzy parse fills missing components with today's date (total-loss vector)"

patterns-established:
  - "Money-critical date path: length/shape check the raw string, validate as real calendar value, map to precision enum; store raw string untouched"
  - "TDD: exhaustive parametrized invariant suite written RED before implementation"

requirements-completed: [DATA-04]

# Metrics
duration: 5min
completed: 2026-08-14
---

# Phase 1 Plan 2: Precision-Driven Date + Uncertainty Classifier Summary

**`parse_precision` + `classify` derive a catalyst's date precision and uncertainty type from the source data's own precision — a month-only date (`2027-04`) is structurally incapable of ever classifying as `firm`, guarding the total-loss partial-date-coercion vector.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-08-14T19:33:39Z
- **Completed:** 2026-08-14T19:40:00Z
- **Tasks:** 2
- **Files modified:** 2 (both created)

## Accomplishments
- Exhaustive, parametrized RED test suite (9 test functions → 100 expanded cases) written and failing before any implementation
- `parse_precision`: shape-checks the raw string and validates it as a real calendar value; raises `ValueError` on malformed/impossible input; never coerces a partial to a day
- `classify`: month/year → `window` unconditionally; full-day ESTIMATED → `firm` iff (≥2 sources ∧ primary) else `window`; full-day ACTUAL → `firm` iff (≥2 sources ∧ primary) else `soft`; `date_type` case-insensitive
- The load-bearing invariant is proven by a 4-axis parametrized test: no combination of (partial date × date_type × source_count × has_primary) yields `firm`

## Task Commits

Each task committed atomically (TDD RED → GREEN):

1. **Task 1: RED — exhaustive date-precision + uncertainty suite** - `44888c0` (test)
2. **Task 2: GREEN — implement parse_precision + classify** - `88ab76f` (feat, includes RED-test correction)

_No REFACTOR commit needed — GREEN implementation was already minimal._

## Files Created/Modified
- `src/catalyst_trader/dates.py` - `parse_precision` + `classify`; precision-driven, no dateutil, `# ponytail:` tuning note
- `tests/test_dates.py` - exhaustive partial-date/precision/uncertainty suite (parametrized invariant + malformed-raises + no-coercion round-trip)

## Decisions Made
- Precision is checked BEFORE corroboration in `classify`, so `firm` is unreachable for any non-day precision — enforced by construction, not by a downstream guard.
- Used `datetime.date.fromisoformat` only to *validate* a full-day string (rejects `2027-02-30`); never to *construct* a date from a partial string.
- `date_type.upper()` normalization so the persisted lowercase DB `date_type` ('estimated'/'actual') and raw CT.gov API values ('ESTIMATED'/'ACTUAL') classify identically.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected a flawed RED-test assertion**
- **Found during:** Task 2 (GREEN)
- **Issue:** `test_parse_precision_returns_enum_not_datetime` asserted `not hasattr(result, "day")` to prove the result was not a `datetime.date`. But `DatePrecision` members are named `day`/`month`/`year`, and Enum members expose sibling members as attributes (`DatePrecision.month.day` resolves to `DatePrecision.day`), so the assertion was always False — a bad test, not a real behavior.
- **Fix:** Replaced the `hasattr` check with `not isinstance(result, (datetime.date, datetime.datetime))`, which correctly expresses the intent (parse_precision never returns a coerced date object).
- **Files modified:** tests/test_dates.py
- **Verification:** Full suite 100 passed in the dates file; 122 passed across the project.
- **Committed in:** `88ab76f` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug — in a test authored during this plan)
**Impact on plan:** Test-only correction; the implementation contract and behavior are exactly as specified. No scope creep.

## Issues Encountered
None beyond the deviation above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `classify` is the canonical uncertainty-typing seam every downstream plan calls: the CT.gov provider (partial-date parse), FMP provider, and `verify.py` (which re-derives uncertainty from the primary-preferred source's persisted `date_type`).
- No blockers. DATA-04 satisfied and structurally enforced.

---
*Phase: 01-data-integrity-catalyst-feed*
*Completed: 2026-08-14*

## Self-Check: PASSED

All created files exist on disk; both task commits (`44888c0`, `88ab76f`) present in git history.
