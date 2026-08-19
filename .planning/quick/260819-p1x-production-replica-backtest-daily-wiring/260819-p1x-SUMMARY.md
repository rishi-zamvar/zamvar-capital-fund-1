---
phase: quick-260819-p1x
plan: 01
subsystem: backtest
tags: [backtest, daily-bars, cache, latency-sweep, frugality, no-look-ahead]
requires: [get_daily_bars, run_layer_a, latency_sweep, reflex_exit, baseline_distribution, build_event_set, upsert_bars, bars_asof]
provides: [daily_bar-table, upsert_daily_bars, daily_bars_asof, make_daily_bars_provider, cache_daily_bars.py, run_daily_backtest.py]
affects: [store.py, backtest]
requirements: [BACK-02, BACK-04]
metrics:
  tasks: 3
  files_created: 5
  files_modified: 1
  tests_added: 13
  duration: ~50m
---

# Quick 260819-p1x: Production-Replica Backtest (Daily-Bars Wiring) Summary

Wired the honest daily+latency backtest to a REAL cached price feed: a separate `daily_bar` cache
table + trade-date-keyed store mirrors, a cache-first as-of-scoped production provider satisfying the
existing `(ticker, as_of, exit_by)` seam, a vetted `--dry-run`-safe one-wide-call-per-ticker populate
script, and a runner that emits the 6-section FINDINGS payoff report. The weekly money-path is
byte-for-byte untouched; the live data pull is left un-run pending operator vet.

## What shipped, per task

### Task 1 — daily_bar cache mirror + cache-first provider (TDD) — commit `7c2b7dd`
- **`migrations/014_daily_bar.sql`** — new `daily_bar` table, `UNIQUE(ticker, trade_date)`, index
  `idx_daily_bar_ticker_date`. SEPARATE from weekly `price_bar` (which is `UNIQUE(ticker, week_end)`
  on a Friday) so a daily Friday row can never overwrite/corrupt the weekly substrate.
- **`store.upsert_daily_bars` / `store.daily_bars_asof`** — close mirrors of `upsert_bars`/`bars_asof`
  but keyed + windowed on `trade_date`. Bars arrive in the `get_daily_bars` shape (`week_end` == raw
  trade date); mapped to `trade_date` on write, emitted as `week_end` on read so the reflex reads the
  same key it always has. `_agreeing` helper comma-joins the cross-check set.
- **`backtest/daily_provider.make_daily_bars_provider(conn, *, allow_fetch=False, max_delay_bars=2)`**
  — a closure over `conn` returning `provider(ticker, as_of, exit_by) -> list[dict]`. Cache-first
  (`daily_bars_asof` read → trimmed window); gap fetch via free-unlimited `get_daily_bars` ONLY when
  `allow_fetch=True`; abstains ([]) on any miss/degrade, never raises.
- **`tests/test_backtest_daily_provider.py`** — 13 offline tests (see below).

**Window semantics (the plan-check fixes, honored exactly):**
- **STRICT lower bound** `as_of < week_end` (CONCERN-2): entry fills at the NEXT bar after the
  as_of-close signal, never a same-as_of-dated bar.
- **BUFFERED upper bound** `<= exit_by + max_delay_bars trading bars` (BLOCKER-1): the post-`exit_by`
  bars are the DELAYED-FILL supply for the T+1/T+2 latency sweep. The decision stays fixed at
  `time_barrier=exit_by`; the buffer is a modelled delayed fill, NOT look-ahead. Stepped over
  available cache bars (a real trading-bar count regardless of weekends/holidays), so `max_delay_bars`
  derives from the sweep's `delays` (default 2) — no fresh magic literal. The buffer also resolves the
  holiday-`exit_by` abstain (CONCERN-3): the next trading bar past a holiday `exit_by` is now in window.

### Task 2 — vetted, dry-runnable wide populate — commit `d6112e4` (+ migrate fix in `089def8`)
- **`scripts/cache_daily_bars.py`** — `distinct_ticker_windows` dedupes catalyst events to ONE wide
  window per DISTINCT ticker (`min(event_date)-21d .. max(event_date)+21d`, buffer covers entry
  lookback + one-week hold + delayed-fill supply). `--dry-run` (DEFAULT-safe) prints the vetted plan
  (distinct tickers, call count, free source, budget) and EXITS with ZERO network. Live pull only with
  `--no-dry-run`: one free-unlimited `get_daily_bars` per ticker → `upsert_daily_bars`, idempotent,
  skip-on-miss (never spends paid quota). `--self-check` asserts dedupe + one-wide-call-per-ticker
  offline. Live path routed through `db.connect + migrate` so `daily_bar` exists before upsert
  (dry-run stays read-only).

### Task 3 — runner + FINDINGS generator — commit `089def8`
- **`scripts/run_daily_backtest.py`** — thin composition over `run_layer_a` (weekly + daily) +
  `latency_sweep(delays=(0,1,2))` on a cache-only provider (`allow_fetch=False`), `embed=lambda`.
  Every metric is read off the shipped `BaselineDistribution` (no new money math). `build_findings`
  emits all six sections; `coverage`/`off_map_stats` compute the Task-B go/no-go inputs with explicit
  numerator/denominator. `--smoke` proves the generator over `tests/` synthetic fixtures + a fake
  in-memory provider (all six sections, no cache, no network).

## Reuse map (no duplication)
| New code | Reuses / mirrors |
| -------- | ---------------- |
| `upsert_daily_bars` / `daily_bars_asof` | mirror `store.upsert_bars` / `store.bars_asof` (trade_date key) |
| `014_daily_bar.sql` | mirrors `005_price_bars.sql` structure + provenance columns |
| `make_daily_bars_provider` | satisfies the existing engine seam `daily_bars_provider(ticker, as_of, exit_by)`; reads `daily_bars_asof`, gap-fetches `providers.prices.get_daily_bars` (free-unlimited `DAILY_PROVIDERS`) |
| `cache_daily_bars.py` | mirrors `scripts/price_backfill_free.py` skeleton; `store.upsert_daily_bars`; adds no new provider |
| `run_daily_backtest.py` | `run_layer_a` / `latency_sweep` / `build_event_set`; metrics off `BaselineDistribution` |
| migration wiring | auto-applied by `db.migrate` numbered runner (014 > current) |

## price_bar isolation proof
`daily_bar` is a physically separate table (migration 014); `upsert_daily_bars` writes ONLY
`daily_bar`. Test `test_writing_daily_bar_leaves_price_bar_untouched` seeds a weekly Friday bar
(`price_bar`, close 50.0) then upserts a same-date (`2025-01-10`) daily bar (close 999.0), and asserts
the `price_bar` Friday close is byte-for-byte 50.0, `price_bar` still has exactly 1 row, and the daily
bar lives in `daily_bar` at 999.0. The full weekly-path regression suites (`test_store.py`,
`test_backtest_engine.py`, `test_backtest_reflex.py`, `test_backtest_latency_sweep.py`) stay green.

## Verification
- Task 1: `pytest tests/test_backtest_daily_provider.py` → **13 passed**; regression
  `tests/test_store.py tests/test_backtest_engine.py` green.
- Full block: `tests/test_backtest_daily_provider.py tests/test_backtest_reflex.py
  tests/test_backtest_latency_sweep.py tests/test_store.py tests/test_backtest_engine.py` →
  **59 passed, 1 xfailed** (the pre-existing deferred Task-B off-map reasoning-agent xfail).
- Task 2: `scripts/cache_daily_bars.py --dry-run` → prints plan, zero network, grep OK; `--self-check` OK.
- Task 3: `scripts/run_daily_backtest.py --smoke` → all six sections, `SMOKE_OK`.

## Dry-run vet (operator sanity check)
The `--dry-run` plan enumerates **76 distinct tickers → 76 `get_daily_bars` calls**, all on
free-unlimited `DAILY_PROVIDERS` (yfinance daily + Nasdaq daily cross-check). This is SANE vs the free
budget: yfinance is effectively unlimited and Nasdaq is a free cross-check — **0 paid quota** spent.
(Plan estimated ~60; the DB has grown to 76 distinct tickers / 195 events in the warm-playbook window
since planning — still one wide call per ticker, still all free.)

## Live pull left UN-RUN (operator step)
Per CLAUDE.md frugality + the task constraint, the live network pull was **NOT** executed. The backtest
provider defaults `allow_fetch=False` (cache-only), so nothing sprays live calls mid-run. To produce
`260819-p1x-FINDINGS.md`, the operator runs, after reviewing the dry-run plan:
1. `.venv/bin/python scripts/cache_daily_bars.py --no-dry-run`   (the one vetted live pull)
2. `.venv/bin/python scripts/run_daily_backtest.py`              (emits FINDINGS.md from the cache)

`260819-p1x-FINDINGS.md` is therefore intentionally not yet created — it is generated by step 2.

## Deviations from Plan
- **[Rule 3 — Blocking]** `cache_daily_bars.py` (and `run_daily_backtest.py`) route through
  `db.connect + migrate` instead of raw `sqlite3.connect`, so migration 014 (`daily_bar`) is applied
  before the first `upsert_daily_bars`; without it the live pull would crash on a missing table.
  Dry-run stays read-only (migrate runs only on the live/`--no-dry-run` path). Folded into commit
  `089def8`. No other deviations — the plan-check fixes (BLOCKER-1, CONCERN-1/2/3) were implemented as
  specified.

## Known Stubs
None. No hardcoded empty data flows to any output; abstained legs are an honest documented behavior
(dropped, never fabricated). FINDINGS.md is not a stub — it is generated on the operator's live run.

## Self-Check: PASSED
All 5 shipped files + SUMMARY present; all 3 task commits (`7c2b7dd`, `d6112e4`, `089def8`) exist.
Verified the real `catalyst.db` has NO `daily_bar` table — confirming the dry-run stayed read-only and
the live pull is genuinely un-run pending operator vet.
