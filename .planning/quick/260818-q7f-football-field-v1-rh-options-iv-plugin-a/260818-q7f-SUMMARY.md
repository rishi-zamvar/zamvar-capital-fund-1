---
phase: quick-260818-q7f
plan: 01
subsystem: desk / football-field
tags: [FF-05, football-field, options-iv, robinhood, cross-check]
requires:
  - quant.field.expected_move_field
  - quant.options.implied_move
  - quant.valuation.rnpv / analyst_pt_move / pipeline_value
  - quant.events.catalyst_move_estimate (implied_move prior seam)
  - kb.load_params()['field']
provides:
  - desk.options_adapter.implied_move_from_provider (abstaining)
  - desk.options_adapter.write_options_snapshot / options_snapshot_provider
  - migration 012_options_snapshot (db.migrate)
  - builder.build 5-method field behind options_provider/assumptions_provider seams
  - TradeProposal.expected_move_field / retrieval_confidence
  - DiligenceDossier.dd_expected_move (abstaining)
  - md.cross_check move_discrepant flag
affects:
  - src/catalyst_trader/desk/builder.py
  - src/catalyst_trader/desk/diligence.py
  - src/catalyst_trader/desk/md.py
  - src/catalyst_trader/contracts/__init__.py
tech-stack:
  added: []
  patterns: [injected-provider-seam, abstain-not-fabricate, numbered-migration, params-not-literals]
key-files:
  created:
    - src/catalyst_trader/migrations/012_options_snapshot.sql
    - src/catalyst_trader/desk/options_adapter.py
    - tests/test_options_adapter.py
  modified:
    - src/catalyst_trader/desk/builder.py
    - src/catalyst_trader/contracts/__init__.py
    - src/catalyst_trader/desk/diligence.py
    - src/catalyst_trader/desk/md.py
    - tests/test_desk_builder.py
    - tests/test_desk_diligence.py
    - tests/test_desk_md.py
decisions:
  - "retrieval_confidence is a str label ('thin'/'ok') from analog_query_v2, not a float — contract field typed str|None to match reality (plan hint said float)"
  - "dd_expected_move stamped via model_copy AFTER enforce_dossier; computed directly from md['options'] with quant.options.implied_move (no new math)"
  - "cross_check move_discrepancy_tol defaults None (check disabled) so all existing callers/tests are byte-for-byte"
metrics:
  tasks: 3
  files: 8
  completed: 2026-08-18
---

# Phase quick-260818-q7f Plan 01: Football-field v1 — RH options-IV plugin (Tasks 1-3) Summary

Wired the trade builder to assemble a real multi-method expected-move football field (analog + implied-IV + rNPV + sum-of-parts + analyst-target) behind two injectable provider seams, added an abstaining Robinhood-sourced options-IV adapter + `options_snapshot` cache (migration 012), and closed the FF-05 loopback: DD now emits an independent `dd_expected_move` and `md.cross_check` flags a builder-field-vs-DD discrepancy. All three code tasks are offline and green; Task 4 (live RH backfill + spot-check) is left for the orchestrator.

## What shipped (Tasks 1-3)

- **Task 1** — `migration 012_options_snapshot.sql` (provisioned by `db.migrate()`, no inline DDL) + `desk/options_adapter.py`: `implied_move_from_provider` (abstains → None on no/incomplete data, never fabricates, never raises into the desk), `write_options_snapshot`, `options_snapshot_provider(conn)`. Commit `34c5fa5`.
- **Task 2** — `builder.build` now takes `options_provider=None, assumptions_provider=None` keyword-only seams; assembles the methods list (each method abstains independently), forms the field only when `>= min_methods`, and feeds the convergence into sizing via the EXISTING `catalyst_move_estimate(implied_move=field_prior)` seam. `TradeProposal` gains `expected_move_field` + `retrieval_confidence`. No-providers path is byte-for-byte. Commit `1ae659d`.
- **Task 3** — `DiligenceDossier.dd_expected_move` (abstaining straddle/iv move, reuses `implied_move`); `md.cross_check` gains `move_discrepancy_tol` (default None = disabled), flags `move_discrepant` when `|builder-dd|/dd > tol`; `reconcile` threads the tol from `load_params()['field']`. Commit `60ad24b`.

## Verification

- `pytest tests/test_options_adapter.py tests/test_desk_builder.py tests/test_field.py tests/test_desk_diligence.py tests/test_desk_md.py -q` → green.
- Full suite: **1504 passed** (2 pre-existing statsmodels ComplexWarnings in test_pairs, unrelated).
- No-provider builder path proven byte-for-byte (`test_no_provider_field_is_none_byte_for_byte`), existing builder/portfolio/weekly/DD/MD suites unregressed.

## Deviations from Plan

**1. [Rule 1 — type mismatch] `retrieval_confidence` is a label string, not a float**
- **Found during:** Task 2 (first test run — pydantic float_parsing error on input `'thin'`).
- **Issue:** the plan specified `retrieval_confidence: float | None`, but `kb.analog_query_v2` returns a `str` label (`"thin"` / `"ok"`).
- **Fix:** typed the contract field `str | None` to match the real return value.
- **Files modified:** `src/catalyst_trader/contracts/__init__.py`
- **Commit:** `1ae659d`

Otherwise executed as written.

## Known Stubs

None. The provider seams default to `None` (byte-for-byte no-field behaviour) by design; the two REAL RH provider impls (live + historical) are documented in the `options_adapter` module docstring and are authored/run in the interactive Task 4 below — this is the intended plan boundary, not a stub.

---

## LEFT FOR THE ORCHESTRATOR — Task 4 (checkpoint:human-action, RH MCP connected, main dir)

RH option MCP tools exist ONLY in an interactive/agent session, so the LIVE pulls + cache population run in the main working directory, not the headless engine or unit tests. Non-blocking — Tasks 1-3 stand alone offline.

### `options_snapshot` cache schema (migration 012, already applied by `db.migrate()`)

```
options_snapshot(
  ticker           TEXT NOT NULL,
  event_date       TEXT NOT NULL,   -- 'YYYY-MM-DD'
  underlying_price REAL NOT NULL,
  call_mid         REAL,            -- straddle leg mid (mark_price)
  put_mid          REAL,            -- straddle leg mid (mark_price)
  iv               REAL,            -- implied_volatility (IV-method fallback)
  days_to_event    INTEGER,
  source           TEXT,            -- 'rh_expired' (backfill) | 'rh_live'
  fetched_at       TEXT,            -- now_iso(), set by write_options_snapshot
  PRIMARY KEY (ticker, event_date)  -- INSERT OR REPLACE upsert
)
```

Write via `desk.options_adapter.write_options_snapshot(conn, ticker, event_date, *, underlying_price, call_mid=None, put_mid=None, iv=None, days_to_event=None, source=...)`. Read via `options_snapshot_provider(conn)(ticker, event_date)` (drops None columns; returns None on miss). Cache-first per CLAUDE.md frugality: skip any (ticker, event_date) that already has a row.

### (a) BACKFILL — historical straddles into the cache

For each in-universe past pdufa/readout `(ticker, event_date)` with NO `options_snapshot` row:
1. `get_option_instruments(symbol=ticker, state='expired')`
2. pick the expiry JUST AFTER `event_date`; take the ATM call + put (strike nearest the underlying close on `event_date`)
3. `get_option_historicals(...)` as-of **T-1** (day before event) → straddle `call_mid` / `put_mid` (+ `iv`, `days_to_event`); `underlying_price` = the T-1 close (cache / free-daily — do NOT spend a quota call)
4. `write_options_snapshot(conn, ticker, event_date, underlying_price=..., call_mid=..., put_mid=..., iv=..., days_to_event=..., source='rh_expired')`

ABSTAIN (skip, never fabricate) any name/date with no expired option data. One `get_option_instruments` call per name; degrade → skip. NO-LOOK-AHEAD: the historical row is the T-1 (pre-event) snapshot only.

### (b) SPOT-CHECK — one live field on a current in-universe name near a real upcoming catalyst

Build the LIVE `options_provider`:
1. `get_option_chains(symbol=ticker)` → nearest expiry AFTER the event date
2. ATM strike ~ underlying; `get_option_quotes(call_id, put_id)` → `mark_price` (= `call_mid`/`put_mid`) + `implied_volatility` (= `iv`)
3. underlying from `get_equity_quotes`
4. degrade to `None` when `mcp_call` is absent (abstain)

Plus a seeded live `assumptions_provider(ticker, catalyst, as_of)` (rnpv / sop / analyst_pt as available), then call:

```python
proposal = await builder.build(conn, embed, verdict, catalyst, entry=<price>,
                               options_provider=<live RH closure>,
                               assumptions_provider=<seeded live closure>)
```

Confirm `proposal.expected_move_field` carries `>= 2` methods with a sane `point_estimate` + `agreement` label, and (optionally) run `run_diligence` on the same name and eyeball `cross_check` `move_discrepant` against `dd_expected_move`.

### (c) DOCUMENT coverage in the quick FINDINGS

How many `(ticker, event_date)` rows landed vs how many abstained, and the one live spot-check field. Resume signal: **"coverage documented"** (or note abstain gaps).

## Self-Check: PASSED

- Files: `012_options_snapshot.sql`, `options_adapter.py`, `test_options_adapter.py` — all FOUND.
- Commits: `34c5fa5`, `1ae659d`, `60ad24b` — all FOUND.
