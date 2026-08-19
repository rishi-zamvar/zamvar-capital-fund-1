---
phase: 07.8-live-desk-wiring-pre-paper-hardening
plan: slice4
subsystem: paper-trading-ledger
tags: [money-path, paper-trading, ledger, human-gate, no-look-ahead, no-drift]
requires:
  - "desk.live_desk.run_one_catalyst_decision (7.8-S2) -> {decision, dossier, ...}"
  - "backtest.fill.fill_price + backtest.engine._net_return + half_spread_pct (BACK-04)"
  - "serving.asof (DBOOK-03/04) point-in-time reads"
  - "kb.insert_claim + store.py idioms + db.migrate (015 on top of 014)"
provides:
  - "migration 015: paper_position / paper_mark / paper_pending"
  - "paper_ledger.py: store + inviolable gate + open/mark/close lifecycle + cited outcome feedback"
  - "scripts/paper_run.py: operator harness (run->submit->approve/reject->weekly mark)"
affects: []
tech-stack:
  added: []
  patterns: ["plain-sqlite store mirroring store.py", "structural human gate (sole opener)", "reuse-backtest-fill-for-paper (no drift)"]
key-files:
  created:
    - src/catalyst_trader/migrations/015_paper_ledger.sql
    - src/catalyst_trader/paper_ledger.py
    - scripts/paper_run.py
    - tests/test_paper_ledger_store.py
    - tests/test_paper_lifecycle.py
    - tests/test_paper_run.py
  modified: []
decisions:
  - "opened_at stores the DECISION as_of date (not approve wall-clock) so the C1 close-guard mirrors engine._fill_leg exactly"
  - "the position writer is PRIVATE (_open_paper_position); approve_pending is the sole public opener (structural gate)"
  - "slippage=0.0 on the close fill — the backtest's effective value; pessimism is the gap-open base + half-spread both sides"
  - "record_paper_outcome is separate from record_weekly_outcome (no fabricated weekly_base_rate citation for a catalyst leg)"
metrics:
  tasks_completed: 3
  new_tests: 29
  files_created: 6
  completed: 2026-08-19
---

# Phase 07.8 Slice 4: Paper Ledger + Paper Fills Summary

Turned an APPROVED MDDecision "enter" into a tracked PAPER position that opens behind an inviolable
operator gate, marks weekly against point-in-time quotes, closes at exit_by using the exact backtest
fill discipline (byte-identical realized P&L), and books a cited outcome back to the KB — the machinery
that starts the 1-month forward paper proof. Paper fills only; no live-broker order path anywhere.

## What shipped (Tasks 1-3)

**Task 1 — schema + store + gate** (`015_paper_ledger.sql`, `paper_ledger.py` store half, 10 tests):
`paper_position` / `paper_mark` / `paper_pending` tables. Store helpers mirror `store.py` idioms:
`get_open_positions`, `mark_paper_position` (upsert on `(position_id, mark_date)`), `close_paper_position`
(re-close raises — realized P&L never double-books). The **inviolable gate**: `submit_for_approval`
writes a pending record only; `approve_pending` is the **sole** opener (calls the PRIVATE
`_open_paper_position`); `reject_pending` opens nothing.

**Task 2 — lifecycle** (`paper_ledger.py` lifecycle half, 15 tests): `position_params_from_decision`
maps an `enter` dossier's own params to a position (pass/escalate/None → None); `mark_open_positions`
marks every open at the point-in-time quote and closes any past `exit_by`; `record_paper_outcome`
cites the decision's own evidence refs.

**Task 3 — operator harness** (`scripts/paper_run.py`, 4 tests + live `--dry-run` CLI): `submit_decision`
+ `dry_run` testable cores; thin `__main__` routing `<TICKER>` / `--approve` / `--reject` / `--mark`
/ `--dry-run`.

## C1–C5 resolutions (plan-check money-path concerns)

- **C1 (close-fill bar — no P&L drift):** the close reads the exit bars at
  `serving.asof(conn, exit_by).bars(ticker, exit_by)` and fills at THAT action bar, with the
  `exit_bars[-1]["week_end"] > opened_at` guard — mirroring `engine._fill_leg` (engine.py:232–234).
  A `--mark` run a full week after `exit_by` still fills at the exit-by action bar, not the mark date.
  Proven by `test_given_past_exit_when_closed_then_fills_at_exit_by_action_bar_byte_identical` (a late
  mark at 2026-08-28 closes a position whose `exit_by` was 2026-08-21).
- **C2 (slippage):** `slippage=0.0` on `fill_price` (the backtest's effective value — every real caller
  passes 0.0). Pessimism comes from the held-through gap-open base fill + `half_spread_pct` paid on
  BOTH sides via `_net_return(apply_costs=True)` on close; the unrealized mark uses `apply_costs=False`
  (a mark is not a round-trip). No slippage config imported, no invented constant.
- **C3 (empty evidence — no fabricated cite):** on close, the position ALWAYS closes and books
  `realized_ret`; the outcome write is DROPPED when `evidence_refs` is empty (`if pos["evidence_refs"]:`).
  No fabricated citation. `test_given_close_with_empty_evidence_when_closed_then_books_ret_but_no_outcome`.
- **C4 (ref shapes):** `record_paper_outcome` handles BOTH `tool:fn#hash` (snippet_hash = post-`#`) and
  `kb:<id>` (no `#` → snippet_hash = `sha256(ref)`). No blind `.split("#",1)[1]` IndexError.
  `test_given_kb_ref_without_hash_when_recording_outcome_then_no_indexerror`.
- **C5 (async):** the harness live `<TICKER>` branch wraps the async `run_one_catalyst_decision` in
  `asyncio.run(...)`; `--dry-run` uses a fake sync decision.

## Money-path proof (realized P&L byte-identical to the backtest)

The close computes `realized_ret = _net_return(entry, fill_price(exit_bars, side, held_through,
slippage=0.0), apply_costs=True)` — the SAME primitives `engine._fill_leg` uses, over the SAME
exit-by action bar read the SAME way (`serving.asof(conn, exit_by).bars(ticker, exit_by)`). The test
asserts equality against a direct call to `fill_price` + `_net_return`, so a paper fill cannot drift
from a backtest fill. `entry` is the dossier's decision-week entry (the backtest's `entry_bars[-1].close`).

## Inviolable-gate proof

The only public function that inserts a `paper_position` is `approve_pending` over a still-`pending`
record; the writer is private (`_open_paper_position`), and a test asserts
`not hasattr(paper_ledger, "open_paper_position")`. Reject → zero positions; un-approved → zero
positions; approve twice → one position (idempotent).

## Honest mark / empty-evidence handling

A mark reads `serving.asof(conn, as_of)` only (no-look-ahead). Empty bars → optional `quotes_fn`
fallback → still None → HOLD (no mark row, position stays open). A halted action bar (`fill_price`
None) or a not-yet-materialized hold-week bar → HOLD on close. No price is ever fabricated.

## Backward compatibility

Additive only: migration 015 applies cleanly on top of 014; no existing signature changed. Full suite:
**1731 passed, 1 xfail (pre-existing), 0 failures** — every prior suite byte-for-byte green plus the 3
new files (29 tests).

## Operator commands (for Task 4 hand-check)

- `.venv/bin/python scripts/paper_run.py --dry-run` — offline proof of the whole
  submit→approve→open→mark→close loop (isolated in-memory ledger, no network).
- `.venv/bin/python scripts/paper_run.py <TICKER>` — run one real catalyst (inside Claude Code, no API
  key) → review the printed dossier → the position is SUBMITTED for approval, NOT opened.
- `.venv/bin/python scripts/paper_run.py --approve <id>` / `--reject <id>` — the inviolable gate.
- `.venv/bin/python scripts/paper_run.py --mark` — the weekly mark/close pass.

## Deviations from Plan

### Auto-added (Rule 2 — critical for the money path)

**1. [Rule 2] `paper_position` carries `opened_at`, `held_through`, `direction`, `evidence_refs`
columns beyond the plan's enumerated list.**
- **Why:** `opened_at` (the decision as_of date) is REQUIRED for the C1 no-drift close guard
  (`exit_bars[-1].week_end > opened_at`); `held_through` is REQUIRED by `fill_price` (gap-open vs
  far-side); `direction` is the outcome provenance; `evidence_refs` (JSON) is needed at close time
  (the close runs from persisted state, long after the live decision) to cite the outcome.
- **Files:** `migrations/015_paper_ledger.sql`, `paper_ledger.py`.

**2. [Rule 2] The position writer is PRIVATE (`_open_paper_position`), not a public `open_paper_position`.**
- **Why:** the plan requires the human gate be "enforced structurally, not by convention" — a public
  opener would be a second insert path violating "there is NO other public function that inserts a
  paper_position". Made the writer private with `approve_pending` as the sole caller.
- **Files:** `paper_ledger.py`; asserted by `test_no_public_open_bypasses_the_gate`.

### Deferred issues

None.

## Self-Check: PASSED

All 6 created files exist; all 3 task commits present (5f0e606, 7bad660, f864a62).
