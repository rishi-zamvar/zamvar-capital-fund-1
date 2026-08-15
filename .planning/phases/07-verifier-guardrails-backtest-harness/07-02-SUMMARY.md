---
phase: 07-verifier-guardrails-backtest-harness
plan: 02
subsystem: backtest
tags: [backtest, point-in-time, survivorship-free, look-ahead, gap-open-fill, slippage, data-latency, offline-fixture]

# Dependency graph
requires:
  - phase: 01-data-integrity-catalyst-feed
    provides: store.bars_asof/upsert_bars (week_end <= as_of guard, delisted retained), store.tradeable_catalysts (status-only, NO date guard), store.insert_catalyst, universe.build.universe_as_of/build_snapshot (append-only cohorts), models.Catalyst.last_verified_at
  - phase: 06.5-weekly-strategy-correction
    provides: desk/weekly.py::_catalyst_dict (the as_of < event_date <= hold_end window pattern reused by build_event_set)
provides:
  - backtest package (src/catalyst_trader/backtest/) — the foundation the Layer-A engine (07-04) + Layer-B replay (07-05) compose
  - build_event_set — per-week (as_of, universe, catalysts, has_bars) records; point-in-time + survivorship-free + catalyst last_verified_at-filtered (BACK-01)
  - fill_price — pessimistic gap-open far-side fill + tunable slippage haircut + halted/delisted/zero-vol/zero-quote skip (BACK-04)
  - effective_asof — the tunable data-latency transform feeding all point-in-time reads (operator directive)
  - tests/synth_history.py::seed_history — the offline synthetic-history fixture every backtest test seeds through
affects: [07-04, 07-05, backtest-harness, go-no-go-gate]

# Tech tracking
tech-stack:
  added: []  # numpy (already present) + stdlib only — NO new dependency
  patterns:
    - "The event-set builder reads bars/universe ONLY through the shipped <= as_of guards and reads catalysts through tradeable_catalysts THEN a mandatory last_verified_at <= effective_asof post-filter — the one point-in-time guard the store does not provide for itself"
    - "The pessimistic fill fills a held-through binary at the gap-open far side, never the SL (a stop is jumped by the gap) — the anti-optimistic-backtest invariant"
    - "effective_asof shifts the as_of ARGUMENT back per data class and reuses the existing guard rather than adding a new query — look-ahead-by-latency closed with zero new read paths"
    - "seed_history seeds through the shipped writers (upsert_bars/insert_catalyst/build_snapshot), never raw SQL, with a crc32-seeded price walk (not builtin hash) for cross-run byte-identical determinism"

key-files:
  created:
    - src/catalyst_trader/backtest/__init__.py
    - src/catalyst_trader/backtest/events.py
    - src/catalyst_trader/backtest/fill.py
    - tests/synth_history.py
    - tests/test_backtest_events.py
    - tests/test_backtest_fill.py
    - tests/test_backtest_latency.py
  modified: []

key-decisions:
  - "build_event_set's catalyst window is a tunable hold_days horizon (default 7 = the one-week hold); widening it lets the same upcoming catalyst be watched across the weeks before its event, which is what makes the 'excluded-early / included-once-verification-catches-up' verification test coherent"
  - "seed_history seeds ONE append-only universe cohort at the first week with density/liquidity criteria disabled (min_*=0) so every seeded name — including delisted — lands in the cohort; universe_as_of returns it for every later week (survivorship-free by construction)"
  - "the fill's slippage is always applied on the FAR side (against the position: lower for a long, higher for a short); held-through fills the gap OPEN, not-held fills the action-bar far-side extreme (low for long, high for short)"
  - "effective_asof lag is expressed in DAYS; a missing data class RAISES (KeyError) rather than defaulting to 0-lag, which would silently reopen look-ahead"
  - "events.py imports effective_asof lazily inside the `if latency_cfg:` branch so the BACK-01 tests (latency_cfg=None) never require fill.py and the two modules ship in either order within this plan"

patterns-established:
  - "Every backtest test seeds through tests/synth_history.py::seed_history — fully offline, zero live API, deterministic"

requirements-completed: [BACK-01, BACK-04]  # BACK-01 event-set builder + BACK-04 fill model (+ latency knob) both delivered and fully tested here

# Metrics
duration: 8min
completed: 2026-08-15
---

# Phase 7 Plan 02: Backtest Data Foundation Summary

**The offline, point-in-time backtest substrate — a synthetic-history fixture, a survivorship-free event-set builder that closes the catalyst-verification look-ahead the store does not guard, and a pessimistic gap-open fill model with a tunable data-latency knob — all built through the shipped `<= as_of` guards with zero new dependencies.**

## Performance
- **Duration:** ~8 min
- **Started:** 2026-08-15T23:24:09Z
- **Completed:** 2026-08-15T23:32:20Z
- **Tasks:** 3
- **Files created:** 7

## Accomplishments
- **`seed_history` fixture** — deterministic multi-week weekly-OHLCV history (delisted names retained), verified catalysts stamped with a realistic `last_verified_at` (per-catalyst override for look-ahead tests), and the universe cohort — all through `upsert_bars` / `insert_catalyst` / `build_snapshot` (no raw SQL). crc32-seeded walk gives byte-identical bars across runs/processes.
- **`build_event_set` (BACK-01)** — walks a weekly `as_of` cursor; universe/bars read ONLY through `universe_as_of` / `bars_asof`; catalysts read through `tradeable_catalysts` THEN the mandatory `last_verified_at <= effective_asof` post-filter. Survivorship-free (delisted cohort names appear) and look-ahead-impossible on both event date AND verification date.
- **`fill_price` (BACK-04)** — held-through binary fills at the gap-open far side worsened by slippage, provably NOT the SL (`fill != sl_level` and strictly worse); not-held fills the action-bar far-side extreme; skips only halted/delisted/zero-vol/zero-quote; volume caps ignored by design.
- **`effective_asof`** — per-class publication-lag transform (days) that makes look-ahead through delayed free-data classes impossible; missing class raises (no silent 0-lag); threads into the events verification filter (verified end-to-end: a 3-day catalyst lag excludes a catalyst that zero-lag included).

## Task Commits
Each task committed atomically on `main` (TDD RED confirmed before each GREEN):
1. **Task 1: synthetic-history fixture + backtest package** — `3d10dd9` (feat)
2. **Task 2: point-in-time survivorship-free event-set builder (BACK-01)** — `65e5f86` (feat)
3. **Task 3: pessimistic gap-open fill + data-latency effective_asof (BACK-04)** — `90a1bc5` (feat)

## Files Created
- `src/catalyst_trader/backtest/__init__.py` — package marker + module docstring
- `src/catalyst_trader/backtest/events.py` — `build_event_set` (BACK-01)
- `src/catalyst_trader/backtest/fill.py` — `fill_price` + `effective_asof` (BACK-04)
- `tests/synth_history.py` — `seed_history` offline fixture + `__main__` self-check
- `tests/test_backtest_events.py` — 5 BACK-01 tests
- `tests/test_backtest_fill.py` — 6 fill tests (incl. the gap-open-not-SL money invariant)
- `tests/test_backtest_latency.py` — 3 latency tests (incl. look-ahead-impossible)

## Decisions Made
- Catalyst window is a tunable `hold_days` horizon (default 7 = the one-week hold); widening it makes the excluded-early / included-later verification test coherent.
- `seed_history` writes one append-only cohort at the first week with criteria disabled so delisted + all names land in the cohort (survivorship-free).
- Slippage always applied on the far side; effective_asof lag in DAYS with a hard raise on a missing class.
- `effective_asof` imported lazily in events.py so BACK-01 tests never require fill.py.

## Deviations from Plan
None material. Two clarifications within the plan's stated intent:
- **[Rule 1 - correctness] crc32, not builtin `hash`, for the per-ticker RNG seed.** Python's builtin `str.__hash__` is `PYTHONHASHSEED`-salted per process, which would silently break the fixture's cross-run byte-identical determinism guarantee. Switched to `zlib.crc32`. Files: `tests/synth_history.py`. Folded into commit `3d10dd9`.
- The catalyst-window semantics were made a tunable `hold_days` knob (default 7) to reconcile the plan's "coming hold window" with its own "excluded-early / included-in-a-later-week" verification test (a tight 1-week window cannot express the latter). Documented in `build_event_set`.

## Issues Encountered
- The plan's `test_event_set_excludes_catalyst_verified_after_as_of` "appears in a later week" clause is incompatible with a strict 1-week catalyst window (disjoint weekly windows). Resolved by the tunable `hold_days` horizon (the test uses `hold_days=60`); the default remains the faithful one-week hold.

## User Setup Required
None — fully offline, zero new dependencies, zero external configuration.

## Next Phase Readiness
- The backtest data foundation is ready for the Layer-A mechanical engine (07-04) and Layer-B guarded agentic replay (07-05) to compose. Real ~1yr earnings/PDUFA calendar ingestion remains a documented carry-forward (tests run on synthetic fixtures).
- Full suite green: 885 passed (866 baseline + 19 new). 2 pre-existing statsmodels warnings (out of scope).

---
*Phase: 07-verifier-guardrails-backtest-harness*
*Completed: 2026-08-15*

## Self-Check: PASSED

All 7 created files exist on disk; all three task commits (`3d10dd9`, `65e5f86`, `90a1bc5`) are in history. Full suite: 885 passed.
