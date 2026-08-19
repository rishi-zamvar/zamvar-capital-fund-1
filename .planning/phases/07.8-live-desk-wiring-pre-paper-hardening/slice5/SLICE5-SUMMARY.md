---
phase: 07.8-live-desk-wiring-pre-paper-hardening
plan: slice5
subsystem: auto-cadence-scheduler
tags: [scheduler, t-2-trigger, paper-trading, launchd, money-gate]
requires: [desk.live_desk, paper_run.submit_decision, paper_ledger.mark_open_positions, calendar.triggers, calendar.refresh]
provides: [desk_run_request-queue, desk_queue.enqueue/register/list_queued/mark_request, weekly_cycle.py, com.zamvar.weekly-mark.plist]
affects: [calendar.refresh.main]
tech-stack:
  added: []
  patterns: [closure-supplied-conn-callback, INSERT-OR-IGNORE-idempotent-queue, injectable-desk_fn, headless-vs-CC-split]
key-files:
  created:
    - src/catalyst_trader/migrations/016_desk_run_queue.sql
    - src/catalyst_trader/desk/desk_queue.py
    - scripts/weekly_cycle.py
    - launchd/com.zamvar.weekly-mark.plist
    - docs/operator-weekly-cycle.md
    - tests/test_desk_queue.py
    - tests/test_weekly_cycle.py
  modified:
    - src/catalyst_trader/calendar/refresh.py
decisions:
  - "dry_run stops at GATE HELD (no approve/open tail) to preserve the whole-file no-opener invariant (B1)"
  - "--status upcoming window reuses triggers.T2_MAX_DAYS, no new literal (C2)"
  - "register(conn) uses a closure to supply conn since the callback contract is Callable[[Row],None]"
metrics:
  duration: ~35m
  completed: 2026-08-19
---

# Phase 07.8 Slice 5: Weekly Scheduler + T-2 Trigger (Auto-Cadence) Summary

Wired the long-dormant T-2 trigger seam to a real, headless-safe launcher and built the
`weekly_cycle.py` auto-cadence runner + a weekly headless mark schedule, so the forward paper month
runs itself — while the inviolable human gate stays untouched (the scheduler SUBMITS, never opens).

## What shipped

- **Migration 016 — `desk_run_request` queue.** `UNIQUE(catalyst_id, event_date)` makes enqueue
  idempotent exactly like `trigger_event`. It is a work-log; it never opens a position.
- **`desk/desk_queue.py`.** `enqueue_desk_run(conn, row)` (the T-2 callback body — headless-safe, no
  LLM/network, opens nothing), `register(conn)` (registers `lambda r: enqueue_desk_run(conn, r)` via
  `triggers.register_callback` — the closure supplies conn), `list_queued` (oldest-first drain order),
  `mark_request` (queued -> done/error + pending_id).
- **`refresh.main()` wiring.** Calls `desk_queue.register(conn)` ONCE after migrate, before the
  refresh (so `detect_and_fire` step 7 invokes the real launcher). `refresh()` itself stays pure — no
  registration — so every existing refresh/trigger suite is unaffected.
- **`scripts/weekly_cycle.py`.** `--desk` (drain queue -> `run_one_catalyst_decision` per request ->
  `submit_decision` to the PENDING gate; one bad catalyst is marked `error` and skipped, never sinks
  the batch), `--mark` (headless `mark_open_positions`), `--status` (offline four-section snapshot),
  `--dry-run` (offline full-loop proof to GATE HELD). Per-catalyst elapsed wall-time logged with the
  Slice-0 ~10-11s/call reference.
- **`launchd/com.zamvar.weekly-mark.plist`.** Weekly (Sun 18:00 local) headless `--mark` pass;
  `RunAtLoad false`; `plutil -lint` clean. Mirrors the sibling fund1 daemon plist.
- **`docs/operator-weekly-cycle.md`.** The honest headless-vs-CC runbook.

## B1 / C1 / C2 resolutions

- **B1 (money-gate integrity).** `dry_run` proves the real Slice-5 path only: enqueue -> drain ->
  submit -> **GATE HELD (assert pending > 0 AND open positions == 0)**, then STOPS. It does not add an
  approve -> open -> close tail (that is already proven by `paper_run.dry_run` in Slice 4, and adding
  it would require calling the opener, breaking the invariant). The whole-file grep of
  `scripts/weekly_cycle.py` for `approve_pending` / `_open_paper_position` / `place_equity_order` is
  empty — enforced by `test_module_contains_no_opener_or_broker_call`. (Docstrings were reworded so
  even prose never contains the forbidden tokens.)
- **C1 (test isolation).** Both new suites reuse the `tests/test_triggers.py` autouse
  `_clear_callbacks` fixture, and `dry_run` clears `triggers._callbacks` before/after registering — so
  no callback bound to a stale conn can leak into the next `detect_and_fire` (no double-enqueue /
  wrong-conn writes).
- **C2 (--status window).** The "upcoming catalysts" window uses the existing `triggers.T2_MAX_DAYS`
  constant (`_STATUS_WINDOW_DAYS = triggers.T2_MAX_DAYS`), not a new literal.

## The honest headless / CC handoff

```
HEADLESS (launchd, no API key):  daily refresh -> detect_and_fire -> enqueue_desk_run -> desk_run_request(queued)
CC SESSION (operator, LLM on Max):  weekly_cycle.py --desk -> run desk per catalyst -> submit_decision -> paper_pending (GATE)
operator:                           paper_run.py --approve <id>  (the SOLE opener)
HEADLESS (launchd, weekly):         weekly_cycle.py --mark -> mark opens + close past exit_by
```

A headless cron cannot call the LLM desk (no API key) — so the T-2 callback enqueues instead of
deciding, and the decision pass runs inside Claude Code. The doc states this plainly and marks the
`~/.dispatch/wake-touches/` auto-wake as a future upgrade path, NOT built here.

## No-auto-open proof

`test_desk_drain_enter_submits_to_gate_and_opens_nothing` and `test_dry_run_full_loop_gate_held`:
a fake 'enter' drained through `weekly_cycle.py` writes exactly one `paper_pending` row and **zero**
`paper_position` rows. `test_enqueue_is_idempotent_and_opens_nothing`: the T-2 callback leaves
`paper_position` / `paper_pending` empty. No double-enqueue: `register` once + `UNIQUE` idempotency,
proven by `test_register_then_detect_and_fire_enqueues_exactly_one`.

## Backward compatibility

Additive only. `refresh()` signature and purity unchanged; registration lives solely in `main()`.
Migration 016 stacks cleanly on 015. Full suite: **1753 passed, 1 pre-existing xfail** (unchanged).

## Operator + launchd install

```sh
# weekly headless mark/close schedule
cp launchd/com.zamvar.weekly-mark.plist ~/Library/LaunchAgents/
launchctl load  ~/Library/LaunchAgents/com.zamvar.weekly-mark.plist   # start (Sun 18:00 local)
launchctl start com.zamvar.weekly-mark                                 # run one now
launchctl unload ~/Library/LaunchAgents/com.zamvar.weekly-mark.plist  # stop

# operator commands
.venv/bin/python scripts/weekly_cycle.py --status     # offline snapshot (anywhere)
.venv/bin/python scripts/weekly_cycle.py --desk       # drain queue -> gate (INSIDE Claude Code)
.venv/bin/python scripts/weekly_cycle.py --mark       # headless mark/close (or via launchd)
.venv/bin/python scripts/weekly_cycle.py --dry-run    # offline full-loop proof, gate held
```

## Tests / commands

- `tests/test_desk_queue.py` — 5 tests (migration, idempotent enqueue opens-nothing, register+fire
  enqueues one, oldest-first + mark_request).
- `tests/test_weekly_cycle.py` — 8 tests (drain enter->gate opens-nothing, pass, error-doesn't-sink,
  mark closes, no-opener grep, status four-section, dry-run gate-held, drain logs elapsed).
- Slice suites: `.venv/bin/python -m pytest tests/test_desk_queue.py tests/test_weekly_cycle.py -q` -> **12 passed**.
- Full suite: `.venv/bin/python -m pytest tests/ -q` -> **1753 passed, 1 xfailed**.
- `plutil -lint launchd/com.zamvar.weekly-mark.plist` -> OK.

## Deviations from Plan

None beyond the plan-check fixes (B1/C1/C2, all folded into the build). One incidental fix:
`weekly_cycle.py` imports `scripts.paper_run`, which resolves under `python -m pytest` (repo-root on
path) but not when run as `python scripts/weekly_cycle.py` (scripts/ on path). Added a
`try: import scripts.paper_run / except ModuleNotFoundError: import paper_run` fallback so the plan's
`scripts/weekly_cycle.py --dry-run` verify command runs directly. [Rule 3 - blocking].

## Self-Check: PASSED

All 8 created files present on disk; all 3 task commits (653a8b4, 9824c36, 92328e4) present in history.
