---
phase: 01-data-integrity-catalyst-feed
plan: 05
subsystem: core
tags: [refresh, triggers, launchd, idempotent, freezegun, t-2, freshness, exclusion, tdd]

# Dependency graph
requires:
  - phase: 01-01
    provides: Catalyst/CatalystSource models + enums, db.connect/migrate + numbered-migration runner, pytest harness (db fixture, frozen_now)
  - phase: 01-03
    provides: providers/clinicaltrials.fetch_trial_readouts + load_sponsor_map, providers/fmp.fetch_earnings (RuntimeError on missing key)
  - phase: 01-04
    provides: store.insert_catalyst (atomic, dedup by external_ref), calendar/verify.verify_catalyst (+ inert now= hook), load_curated_pdufa, is_tradeable
provides:
  - "calendar/triggers.py — register_callback / detect_and_fire (T-2 seam, idempotent via trigger_event) / exclude_stale (48h near-event exclusion)"
  - "calendar/refresh.py — refresh() single idempotent daily entrypoint (providers -> store -> verify+restamp -> exclude -> fire) + main() for python -m"
  - "migrations/002_trigger_event.sql — trigger_event dedup table (UNIQUE catalyst_id+event_date)"
  - "com.zamvar.catalyst-refresh.plist — launchd daily schedule (07:30, RunAtLoad false, __REPO_ROOT__ tokens + install steps)"
affects: [universe, plan-06-curation, phase-04-workflow-1, backtest]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Idempotent daily entrypoint (Pattern 3): one refresh() re-fetches every provider, merges curated, re-verifies, restamps, excludes-stale, fires T-2 — safe to run repeatedly (dedup by external_ref)"
    - "Pluggable trigger seam: module-level callback registry, default logs; Workflow 1 registers the real launcher later — never built in Phase 1"
    - "Idempotent side-effect via a dedup marker row: trigger_event UNIQUE(catalyst_id, event_date) + INSERT OR IGNORE + rowcount check fires the callback exactly once"
    - "Precision-gated T-2: only day-precision catalysts fire; a month/quarter/year window is too wide to pin the T-2 boundary and is skipped (never spuriously fires)"
    - "launchd (not an in-process scheduler) for a once-daily reboot-safe job; not auto-loaded (installation is a user step)"

key-files:
  created:
    - src/catalyst_trader/calendar/triggers.py
    - src/catalyst_trader/calendar/refresh.py
    - src/catalyst_trader/migrations/002_trigger_event.sql
    - com.zamvar.catalyst-refresh.plist
    - tests/test_triggers.py
    - tests/test_refresh.py
  modified:
    - src/catalyst_trader/calendar/verify.py
    - tests/test_db.py

key-decisions:
  - "T-2 firing is day-precision only — a window (month/quarter/year) cannot pin the T-2 boundary, so it is skipped rather than fired on its window start (avoids trading a fabricated day)"
  - "Idempotency of the trigger uses a trigger_event dedup row (UNIQUE catalyst_id+event_date, INSERT OR IGNORE, fire only when rowcount>0) — a 2nd run same day, and the T-1 day after, both no-op"
  - "refresh restamps last_verified_at only on catalysts that RE-VERIFY as verified; a near-event catalyst that can no longer re-verify keeps its stale stamp and is then excluded — this is exactly the 'cannot be re-verified near its event -> excluded' safety rule"
  - "FMP degrade is caught at RuntimeError (the Plan-03 missing-key/error signal) inside refresh — CT.gov + curated always run; a missing key logs a warning and never crashes the daily job"
  - "curated PDUFA loader now carries a deterministic external_ref (curated:{ticker}:{type}:{date}) so daily re-runs dedup — curated rows had no NCTId/symbol and would otherwise duplicate on every refresh (idempotency correctness fix)"
  - "callback receives the sqlite catalyst row (carries the DB id Workflow 1 needs), not the hydrated model"
  - "tickers loaded from the latest included universe_snapshot if present, else the curated sponsor-map keys (seed_universe.csv is Plan 06)"

patterns-established:
  - "Idempotent orchestrator with injectable providers (real fns default, stub fns in tests) + freezegun-frozen now for deterministic time logic"
  - "Dedup-marker-row pattern for exactly-once side effects across repeated idempotent runs"

requirements-completed: [DATA-01, DATA-03, DATA-05]

# Metrics
duration: 15min
completed: 2026-08-14
---

# Phase 1 Plan 5: Idempotent Daily Refresh + T-2 Trigger Seam Summary

**The rolling calendar is now live and self-maintaining: one idempotent `refresh()` (launchd-run daily) merges CT.gov + FMP + curated PDUFA through the atomic store, re-verifies every active catalyst and restamps `last_verified_at`, excludes any near-event date it can no longer re-confirm within 48h, and fires a pluggable, dedup-guarded T-2 trigger seam — activating the previously-inert `verify_catalyst(now=...)` hook and building only the seam for Workflow 1, not Workflow 1 itself.**

## Performance
- **Duration:** ~15 min
- **Completed:** 2026-08-14
- **Tasks:** 3 (Tasks 1-2 TDD: RED test → GREEN impl; Task 3 config artifact)
- **Files created:** 6 · **modified:** 2
- **Tests:** full suite 158 → 171 green (+13 new: 6 triggers, 7 refresh)

## Accomplishments
- **T-2 trigger seam + 48h exclusion (`calendar/triggers.py`):** `detect_and_fire` fires a registered callback (default: log) exactly once for each verified day-precision catalyst 1-2 days out, recording a `trigger_event` dedup row so repeat runs never double-fire. `exclude_stale` sets `status='excluded'` on near-event catalysts whose `last_verified_at` is stale (or missing) — never deletes. `register_callback` is the Workflow-1 hook (Workflow 1 not built).
- **Idempotent daily refresh (`calendar/refresh.py`):** `refresh()` orchestrates CT.gov (always) + FMP (key-gated, RuntimeError-degrading) + curated PDUFA → `store.insert_catalyst` (dedup) → re-verify all active + restamp `last_verified_at` → `exclude_stale` → `detect_and_fire`, returning a counts summary. Two consecutive runs leave row counts stable. `main()` + `__main__` provide the `python -m catalyst_trader.calendar.refresh` entrypoint.
- **launchd schedule (`com.zamvar.catalyst-refresh.plist`):** daily 07:30, `RunAtLoad` false, `__REPO_ROOT__` placeholders with documented `sed`+`launchctl load` install steps, logs to `logs/`. `plutil -lint` clean.

## Task Commits
Tasks 1-2 committed atomically as TDD pairs (RED test → GREEN impl):

1. **Task 1: T-2 trigger seam + 48h staleness exclusion**
   - `91a82bd` (test) — failing trigger/staleness tests (freezegun)
   - `49cd78d` (feat) — triggers.py + migrations/002_trigger_event.sql
2. **Task 2: Idempotent daily refresh orchestrator**
   - `9c35e1c` (test) — failing refresh tests (idempotency + degrade + wiring)
   - `af03af0` (feat) — refresh.py + curated external_ref dedup fix (verify.py)
3. **Task 3: launchd daily schedule** — `c6bd166` (chore)

**Deviation fix:** `d4ad4cd` (fix) — db version tests track migration count (see Deviations)

## Files Created/Modified
- `src/catalyst_trader/calendar/triggers.py` — register_callback / detect_and_fire / exclude_stale; day-precision-gated T-2, dedup-row idempotency, never-delete exclusion.
- `src/catalyst_trader/calendar/refresh.py` — idempotent refresh() orchestrator + _load_tickers + main()/__main__.
- `src/catalyst_trader/migrations/002_trigger_event.sql` — trigger_event dedup table.
- `com.zamvar.catalyst-refresh.plist` — launchd LaunchAgent (daily 07:30, not auto-loaded).
- `tests/test_triggers.py` — 6 freezegun tests (T-2 boundary, idempotency, partial-date no-fire, 48h exclusion, never-delete).
- `tests/test_refresh.py` — 7 tests (idempotency, FMP degrade x2, T-2 fire wiring, exclude wiring, real-provider httpx pipeline, main() present).
- `src/catalyst_trader/calendar/verify.py` (modified) — curated loader now sets a deterministic external_ref for idempotent dedup.
- `tests/test_db.py` (modified) — version assertions track `db._pending()` count instead of hardcoded 1.

## Decisions Made
See frontmatter `key-decisions`. Headlines: day-precision-only T-2 firing; dedup-marker-row for exactly-once triggers; restamp-only-on-reverify so stale-near-event → excluded falls out naturally; RuntimeError-based FMP graceful degrade; deterministic curated external_ref for idempotency.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Curated PDUFA rows duplicated on every refresh (idempotency break)**
- **Found during:** Task 2 (idempotent refresh)
- **Issue:** `load_curated_pdufa` inserted catalysts with no `external_ref`; `store.insert_catalyst` dedups by `(ticker, external_ref)`, so each daily refresh would insert fresh duplicate curated rows — directly violating the plan's core idempotency truth.
- **Fix:** curated loader now sets `external_ref = f"curated:{ticker}:{catalyst_type}:{event_date}"`, a deterministic key the store dedups on.
- **Files modified:** `src/catalyst_trader/calendar/verify.py`
- **Verification:** `test_refresh_is_idempotent` (row count stable across two runs incl. a curated row); existing `test_load_curated_pdufa` still green.
- **Committed in:** `af03af0` (Task 2 commit)

**2. [Rule 1 - Bug] Two Plan-01 db tests hardcoded schema version 1**
- **Found during:** Full-suite verification (post Task 3)
- **Issue:** adding `002_trigger_event.sql` (required by this plan's trigger seam) bumped the schema version to 2; `test_migrate_records_version_one` and `test_migrate_is_idempotent` asserted `== 1` and failed.
- **Fix:** both tests now assert against `db._pending()[-1][0]` (highest migration on disk), so they track the migration count and won't break on future migrations.
- **Files modified:** `tests/test_db.py`
- **Verification:** full suite `171 passed`.
- **Committed in:** `d4ad4cd`

---

**Total deviations:** 2 auto-fixed (both Rule 1 - bug). **Impact:** both necessary for correctness (idempotency + suite integrity). No scope creep — migration 002 is the plan's required "writes a trigger row" mechanism.

## Issues Encountered
- FMP is key-gated by default (`settings.fmp_api_key`), so the idempotency test that injects an FMP stub had to pass `fmp_enabled=True` to exercise the FMP path — resolved by making `fmp_enabled` an explicit override of the key-presence default (already in the signature).

## Known Stubs
- `register_callback` seam has no real consumer yet — the default callback only logs. **Intentional:** Workflow 1 is out of scope for Phase 1; Phases 4+ register the real launcher. A `# ponytail` comment marks the notification hook point.
- `data/pdufa_curated.csv` still ships header + commented placeholders only (real rows are the **Plan 06** curation checkpoint); `refresh(main)` loads it to zero curated catalysts until then. `_load_tickers` falls back to sponsor-map keys until a `universe_snapshot` exists (Plan 06).
- launchd plist is **not auto-loaded** — installation (`sed` + `launchctl load`) is a documented user step; no live daily job runs until the user installs it.

## User Setup Required
None required now. To activate the daily job later: substitute `__REPO_ROOT__` and `launchctl load` the plist (steps documented in the plist header comment). No env vars needed for CT.gov + curated; set `FMP_API_KEY` to enable the earnings feed (absent = graceful degrade).

## Next Phase Readiness
- DATA-01 (three feeds merged into one calendar), DATA-03 (freshness/48h re-verify + exclusion), DATA-05 (T-2 flag + trigger seam) are complete. The verify.py `now=` hook is now active.
- Plan 06 (universe build + curation checkpoint) can now populate `universe_snapshot` (which `_load_tickers` will pick up) and fill `data/pdufa_curated.csv` + `ticker_sponsor_map.csv` with real, source-confirmed rows.
- Phase 4+ can `register_callback` to wire Workflow 1 onto the existing, already-firing seam.

## Self-Check: PASSED
All 6 created files + SUMMARY present; all 6 commits (91a82bd, 49cd78d, 9c35e1c, af03af0, c6bd166, d4ad4cd) exist in history. Full suite 171 passed.

---
*Phase: 01-data-integrity-catalyst-feed*
*Completed: 2026-08-14*
