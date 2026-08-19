---
phase: 07.8-live-desk-wiring-pre-paper-hardening
plan: slice5
type: execute
wave: 1
depends_on: []
files_modified:
  - src/catalyst_trader/migrations/016_desk_run_queue.sql
  - src/catalyst_trader/desk/desk_queue.py
  - src/catalyst_trader/calendar/refresh.py
  - scripts/weekly_cycle.py
  - launchd/com.zamvar.weekly-mark.plist
  - docs/operator-weekly-cycle.md
  - tests/test_desk_queue.py
  - tests/test_weekly_cycle.py
autonomous: true
requirements: [DATA-05, WEEK-01]
must_haves:
  truths:
    - "On a T-2 verified catalyst the daily headless refresh enqueues a desk-run request automatically — and opens NOTHING."
    - "Draining the queue inside a Claude Code session runs the live desk per queued catalyst and SUBMITS any 'enter' to the approval gate — never auto-opens."
    - "A weekly mark/close pass runs headlessly on schedule: marks every open, closes any past exit_by (byte-identical backtest fill)."
    - "weekly_cycle.py --status shows open positions, pending approvals, upcoming catalysts, and queued desk runs — offline."
    - "weekly_cycle.py --dry-run proves the whole enqueue -> drain -> submit -> mark loop offline with the human gate held."
  artifacts:
    - path: "src/catalyst_trader/migrations/016_desk_run_queue.sql"
      provides: "desk_run_request queue table (UNIQUE catalyst_id,event_date => idempotent enqueue)"
      contains: "CREATE TABLE desk_run_request"
    - path: "src/catalyst_trader/desk/desk_queue.py"
      provides: "enqueue_desk_run(conn,row) T-2 callback + register(conn) + drain/status helpers"
      min_lines: 40
    - path: "scripts/weekly_cycle.py"
      provides: "--desk (drain->gate) / --mark (headless) / --status / --dry-run runner"
      min_lines: 60
    - path: "launchd/com.zamvar.weekly-mark.plist"
      provides: "weekly headless mark/close schedule (DATA passes only; DESK is CC)"
      contains: "com.zamvar.weekly-mark"
    - path: "docs/operator-weekly-cycle.md"
      provides: "honest headless-vs-CC split + T-2 -> queue -> CC-desk -> gate handoff runbook"
  key_links:
    - from: "src/catalyst_trader/calendar/refresh.py"
      to: "triggers.register_callback -> desk_queue.enqueue_desk_run"
      via: "desk_queue.register(conn) in refresh.main() before detect_and_fire"
      pattern: "desk_queue.register"
    - from: "scripts/weekly_cycle.py (--desk)"
      to: "paper_ledger.submit_for_approval (the gate)"
      via: "run_one_catalyst_decision -> paper_run.submit_decision"
      pattern: "submit_decision|submit_for_approval"
    - from: "scripts/weekly_cycle.py (--mark)"
      to: "paper_ledger.mark_open_positions"
      via: "headless weekly pass"
      pattern: "mark_open_positions"
---

<objective>
Automate the weekly paper-trading cadence so the forward paper month runs itself: a T-2 catalyst
auto-launches a desk-run request, an operator drains the queue inside Claude Code to produce
approval-gated decisions, and a weekly mark/close pass runs on schedule. The inviolable human gate is
untouched — the scheduler SUBMITS to the gate and NEVER opens a position.

Purpose: today the operator runs `paper_run.py <TICKER>` manually per catalyst. Slice 5 wires the
existing T-2 trigger seam (`triggers.register_callback`, currently log-only, nothing registered) to a
persistent desk-run queue, adds a `weekly_cycle.py` runner + a launchd mark schedule, and documents the
honest split: DATA/MARK passes run headlessly (launchd, no LLM); the DESK/decision pass needs a Claude
Code session (Max, no API key — a headless cron cannot call the LLM desk).

Output: migration 016 (desk_run_request), `desk/desk_queue.py`, refresh wiring, `scripts/weekly_cycle.py`,
`launchd/com.zamvar.weekly-mark.plist`, `docs/operator-weekly-cycle.md`, offline test suites.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@.planning/phases/07.8-live-desk-wiring-pre-paper-hardening/PHASE-BRIEF.md
@.planning/phases/07.8-live-desk-wiring-pre-paper-hardening/slice4/SLICE4-SUMMARY.md

<interfaces>
<!-- Real contracts extracted from the codebase. Use these directly; do NOT re-explore. -->

The T-2 trigger seam (src/catalyst_trader/calendar/triggers.py):
```python
# Callback signature: takes ONLY the catalyst sqlite3.Row (NOT a conn).
_callbacks: list[Callable[[sqlite3.Row], None]] = []
def register_callback(fn: Callable[[sqlite3.Row], None]) -> None: ...   # appends; empty => _default_callback (log-only)
def detect_and_fire(conn, now=None) -> list[int]:                       # fires each verified day-precision catalyst 1-2d out
    # idempotent: INSERT OR IGNORE into trigger_event(catalyst_id,event_date) => fires EXACTLY ONCE per (catalyst,event_date)
# The fired row is a `catalyst` table row: row["id"], row["ticker"], row["catalyst_type"], row["event_date"]
```

The daily refresh (src/catalyst_trader/calendar/refresh.py) — where the callback fires, HEADLESS:
```python
def refresh(conn, tickers, now=None, ...) -> dict:      # step (7): triggers.detect_and_fire(conn, now)
def main():                                             # launchd entry (`-m catalyst_trader.calendar.refresh`)
    conn = _db.connect(); _db.migrate(conn)
    ... refresh(conn, tickers, now=..., pdufa_csv=...)
```

The live desk decision (src/catalyst_trader/desk/live_desk.py):
```python
async def run_one_catalyst_decision(conn, embed, ticker, *, as_of, live=False,
    context_hook=None, ...) -> dict   # {catalyst, verdict, dossier, dd, decision, rounds, degraded_flags, reason}
```

The operator harness cores (scripts/paper_run.py) — REUSE, do not re-implement:
```python
def submit_decision(conn, result: dict, *, as_of: str) -> int | None   # 'enter' => submit_for_approval + print gate; else None. OPENS NOTHING.
# the live per-ticker chain (paper_run.main): 
embed = kb.default_embedder(); as_of = date.today().isoformat()
hook = make_catalyst_context(embed=embed, cutoff=None, quote_override=_rh_quote_override)
result = asyncio.run(run_one_catalyst_decision(conn, embed, ticker, as_of=as_of, live=True, context_hook=hook))
submit_decision(conn, result, as_of=as_of)
```

The inviolable gate + mark pass (src/catalyst_trader/paper_ledger.py):
```python
def submit_for_approval(conn, params) -> int          # writes a 'pending' record; opens NOTHING
def approve_pending(conn, pending_id) -> int | None   # THE SOLE OPENER (do NOT call from the scheduler)
def mark_open_positions(conn, as_of, *, quotes_fn=None, embed=None) -> dict   # {marked, closed, held}; no-look-ahead, byte-identical backtest fill
def get_open_positions(conn) -> list[dict]
```

The launchd pattern (com.zamvar.catalyst-refresh.plist / launchd/com.zamvar.fund1.daemon.plist):
- `__REPO_ROOT__`-placeholder OR absolute WorkingDirectory + `.venv/bin/python` ProgramArguments.
- `StartCalendarInterval` for calendar-anchored jobs; `RunAtLoad false`; logs to `logs/`. Not auto-loaded (deliberate user install step). `plutil -lint` must pass.

Config source (no new magic numbers): the T-2 window already lives in triggers (`T2_MIN_DAYS=1, T2_MAX_DAYS=2`); the weekly anchor in `kb.load_params(conn,"weekly")["weekly"]["anchor"]`. The mark day is a launchd schedule value (plist), not a code literal.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Register the real T-2 launcher — persistent desk-run queue (headless-safe seam)</name>
  <files>src/catalyst_trader/migrations/016_desk_run_queue.sql, src/catalyst_trader/desk/desk_queue.py, src/catalyst_trader/calendar/refresh.py, tests/test_desk_queue.py</files>
  <behavior>
    - enqueue_desk_run(conn, row) writes a desk_run_request(catalyst_id, ticker, event_date, status='queued', enqueued_at); a second fire for the same (catalyst_id,event_date) is a no-op (UNIQUE + INSERT OR IGNORE) — idempotent, mirrors trigger_event.
    - The callback OPENS NOTHING: after enqueue, paper_position/paper_pending are untouched (assert zero rows).
    - register(conn) wires the seam: triggers.register_callback(lambda row: enqueue_desk_run(conn, row)); after register(conn), a seeded verified day-precision catalyst 1-2 days out, when triggers.detect_and_fire(conn) runs, leaves exactly one queued desk_run_request (proves refresh->trigger->enqueue end-to-end, offline, no LLM).
    - drain-candidate reader (list_queued(conn)) returns queued requests oldest-first; mark_request(conn, id, status, pending_id=None) flips queued->done/error and records the submitted pending_id (or None).
  </behavior>
  <action>
    Create migration `016_desk_run_queue.sql` (on top of 015): a `desk_run_request` table — id PK, catalyst_id INTEGER NOT NULL, ticker TEXT NOT NULL, event_date TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','done','error')), enqueued_at TEXT NOT NULL, resolved_at TEXT, pending_id INTEGER, UNIQUE(catalyst_id, event_date). This is the T-2 -> CC-desk handoff store; the UNIQUE key makes enqueue idempotent exactly like `trigger_event`.

    Create `src/catalyst_trader/desk/desk_queue.py` (closes DATA-05: the T-2 seam finally has a real launcher registered):
      - `enqueue_desk_run(conn, row)` — INSERT OR IGNORE a queued request from the catalyst row (row["id"]/["ticker"]/["event_date"]); commit. NEVER touches paper_position/paper_pending. This is the callback body — headless-safe, deterministic, no LLM/network.
      - `register(conn)` — `triggers.register_callback(lambda r: enqueue_desk_run(conn, r))`. This is the seam the scoping said "Phases 4+ register the real Workflow-1 launcher here." The launcher is: enqueue for a later CC-gated desk run (NOT run the LLM here — the callback fires inside the headless daily refresh which has no API key).
      - `list_queued(conn)` -> queued rows oldest-first; `mark_request(conn, id, status, pending_id=None)` -> flip status + resolved_at + pending_id.
    Reuse `dates.now_iso` for timestamps (as paper_ledger does). No new magic numbers.

    Modify `src/catalyst_trader/calendar/refresh.py`: in `main()`, call `desk_queue.register(conn)` AFTER migrate and BEFORE `refresh(...)` (so detect_and_fire, step 7, invokes the real callback instead of the log-only default). Import is local/top per file convention. Do NOT register at module import (avoids double-registration + keeps `refresh()` pure for existing tests). Backward-compat: `refresh()` signature unchanged; existing refresh tests stay green (they call refresh() directly and never register).
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_desk_queue.py -q && .venv/bin/python -c "import sqlite3,catalyst_trader.db as d; c=d.connect(':memory:'); d.migrate(c); c.execute('SELECT catalyst_id,event_date,status FROM desk_run_request'); print('016 ok')" && .venv/bin/python -m pytest tests/test_triggers.py tests/ -q -k "refresh or trigger" </automated>
  </verify>
  <done>desk_run_request exists via migrate; enqueue is idempotent and opens nothing; register(conn)+detect_and_fire enqueues exactly one request for a seeded T-2 catalyst; existing refresh/trigger suites green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: weekly_cycle.py runner + weekly mark schedule + honest handoff doc</name>
  <files>scripts/weekly_cycle.py, launchd/com.zamvar.weekly-mark.plist, docs/operator-weekly-cycle.md, tests/test_weekly_cycle.py</files>
  <behavior>
    - `--desk` drains list_queued: for each request runs the desk (injectable desk_fn, default the live run_one_catalyst_decision chain) -> submit_decision -> mark_request(done, pending_id) on an 'enter', (done, None) on a pass/no-decision, (error, None) on an exception (never crashes the drain). A submitted 'enter' produces a paper_pending row and ZERO paper_position rows — the gate holds (assert with a fake 'enter' desk_fn).
    - `--desk` NEVER calls approve_pending/_open_paper_position (grep-assert in the test: the module submits only).
    - `--mark` runs paper_ledger.mark_open_positions(conn, today) and prints {marked,closed,held} — headless, no LLM (reuses the exact Slice-4 fill discipline; no drift).
    - The launchd plist is plutil-lint clean, labels com.zamvar.weekly-mark, runs `weekly_cycle.py --mark` on a weekly StartCalendarInterval, RunAtLoad false.
  </behavior>
  <action>
    Create `scripts/weekly_cycle.py` mirroring `scripts/paper_run.py`'s structure (sys.path insert for `src`, `_db.connect`/`migrate`, argparse thin __main__, testable cores). REUSE — import, do not re-implement — `paper_run.submit_decision`, `desk.catalyst_context.make_catalyst_context`, `desk.live_desk.run_one_catalyst_decision`, `desk_queue.list_queued/mark_request`, `paper_ledger.mark_open_positions`, `kb.default_embedder`.
      - Testable core `drain_desk(conn, *, desk_fn, as_of)` — loop list_queued; for each request call `result = desk_fn(conn, request["ticker"], as_of)`; `pid = submit_decision(conn, result, as_of=as_of)`; `mark_request(conn, id, 'done', pid)`; wrap each in try/except -> mark_request(...,'error') + log, continue (one bad catalyst never sinks the batch). Return a summary {drained, submitted, errors}.
      - The default live desk_fn (thin, in __main__ only, async->asyncio.run) reproduces paper_run's live chain: make_catalyst_context(embed, cutoff=None, quote_override=paper_run._rh_quote_override) -> run_one_catalyst_decision(..., live=True, context_hook=hook). This is the ONLY network+LLM path and runs ONLY inside a CC session.
      - `--mark`: `mark_open_positions(conn, date.today().isoformat(), quotes_fn=paper_ledger._rh_quote)` (mirror paper_run --mark), print summary.
      - argparse: `--desk`, `--mark`, `--db` (default catalyst.db). (`--status`/`--dry-run` land in Task 3.)
    Create `launchd/com.zamvar.weekly-mark.plist` mirroring `launchd/com.zamvar.fund1.daemon.plist` (absolute WorkingDirectory to this checkout, `.venv/bin/python scripts/weekly_cycle.py --mark`), `StartCalendarInterval` weekly (Sunday, an after-close hour — a schedule config value, documented, not a code literal), RunAtLoad false, KeepAlive on non-zero exit only, logs to `logs/weekly-mark.{out,err}.log`. Header comment with the `cp`/`launchctl load` install steps like the sibling plists.
    Create `docs/operator-weekly-cycle.md` — the honest runtime split (RUNTIME CONSTRAINT: agents run inside Claude Code on Max, NO API key; a headless cron CANNOT call the LLM desk):
      - HEADLESS (launchd): the daily `com.zamvar.catalyst-refresh` job already fires detect_and_fire, which now enqueues desk-run requests (Task 1); the new `com.zamvar.weekly-mark` job runs the mark/close pass. Neither calls the LLM.
      - CC SESSION (operator): `weekly_cycle.py --desk` drains the queue -> gated decisions. Document the handoff options plainly: (a) operator checks `weekly_cycle.py --status` when a T-2 fires and runs `--desk`; (b) OPTIONAL future wake-touch (the dispatch pattern) — the enqueue could write a `~/.dispatch/wake-touches/` signal so a CC session auto-wakes; note it as an upgrade path, do NOT build it here. Do NOT claim headless LLM works.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_weekly_cycle.py -q && plutil -lint launchd/com.zamvar.weekly-mark.plist && grep -L "approve_pending\|_open_paper_position\|place_equity_order" scripts/weekly_cycle.py</automated>
  </verify>
  <done>--desk drains via an injected fake desk_fn, submits 'enter's to the gate (paper_pending written, ZERO paper_position — gate held), routes pass/error without crashing; --mark marks/closes via mark_open_positions; plist is lint-clean; weekly_cycle.py contains no opener/broker call.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Observability — --status, --dry-run offline proof, per-catalyst cost logging</name>
  <files>scripts/weekly_cycle.py, tests/test_weekly_cycle.py</files>
  <behavior>
    - `--status` prints (offline, no LLM): open positions (get_open_positions), pending approvals (paper_pending status='pending'), upcoming catalysts (verified, event_date in the next window), and queued desk runs (list_queued). Returns a summary dict the test asserts on.
    - `--dry-run` drives the WHOLE Slice-5 loop offline with ZERO network/LLM: seed a T-2 verified catalyst -> register+detect_and_fire enqueues -> drain_desk with a fake 'enter' desk_fn -> submit_decision -> assert a paper_pending row and ZERO paper_position (gate held) -> then approve + mark to show the tail closes. Mirrors paper_run.dry_run's in-memory-db pattern.
    - Cost/observability: drain_desk logs per-catalyst elapsed wall-time + a running submitted/error count, and echoes the Slice-0 ~10-11s/call reference so the operator can sanity-check spend. Elapsed seconds is the HONEST measured metric; if desk.runtime already exposes a call tally, include it, else do not fabricate a call count.
  </behavior>
  <action>
    Extend `scripts/weekly_cycle.py` (no new file): add testable cores `status(conn, *, as_of)` and `dry_run(conn)`, and wire `--status`/`--dry-run` into argparse (dry-run uses an in-memory `:memory:` db exactly like paper_run.dry_run — never touches catalyst.db).
      - `status(conn, as_of)`: assemble + print the four sections above; return {open, pending, upcoming, queued} counts/rows.
      - `dry_run(conn)`: reuse a fake 'enter' result (import/adapt paper_run._fake_enter_result) as the desk_fn; seed one verified day-precision catalyst 1-2d out + its action bars (upsert_bars, as paper_run.dry_run does); call desk_queue.register(conn) + triggers.detect_and_fire(conn) to enqueue; run drain_desk(desk_fn=fake); assert gate held (pending>0, positions==0); then approve_pending + mark_open_positions to show close. Print each step; return a summary.
      - In `drain_desk` add `t0=time.monotonic()` around each desk_fn call and log `logger.info("desk-run %s elapsed=%.1fs (~10-11s/LLM call, Slice-0) submitted=%d errors=%d", ticker, dt, submitted, errors)`. No new magic numbers — 10-11s is a cited Slice-0 measurement in a log string, not a code constant.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_weekly_cycle.py -q && .venv/bin/python scripts/weekly_cycle.py --dry-run && .venv/bin/python -m pytest tests/ -q</automated>
  </verify>
  <done>--status returns the four-section summary offline; --dry-run runs the full enqueue->drain->submit->approve->mark loop offline and asserts the gate held (pending written, no auto-open); drain_desk logs per-catalyst elapsed + counts; full suite green.</done>
</task>

</tasks>

<verification>
- Migration 016 applies cleanly on top of 015; `desk_run_request` present after `db.migrate`.
- The T-2 seam is wired: `desk_queue.register(conn)` + `triggers.detect_and_fire(conn)` on a seeded verified day-precision catalyst 1-2d out enqueues exactly one request; a re-run enqueues nothing (idempotent).
- Gate inviolable: `--desk` and `--dry-run` on a fake 'enter' write a `paper_pending` row and ZERO `paper_position` rows; no `approve_pending`/`_open_paper_position`/`place_equity_order` reference anywhere in `scripts/weekly_cycle.py`.
- Headless passes work with no LLM/network: `--mark`, `--status`, `--dry-run`, and the T-2 enqueue callback are fully offline.
- `plutil -lint launchd/com.zamvar.weekly-mark.plist` passes.
- All code-task tests are offline (fake trigger row / fake desk_fn / in-memory db); existing suites (refresh, triggers, paper_ledger, paper_run) stay green.
- No new magic numbers: T-2 window reuses triggers constants, weekly anchor reuses params, mark schedule is a plist config value.
</verification>

<success_criteria>
- A T-2 verified catalyst, during the already-scheduled daily headless refresh, auto-enqueues a desk-run request and opens nothing.
- `weekly_cycle.py --desk` (inside CC) drains the queue, runs the live desk per catalyst, and submits any 'enter' to the approval gate — never auto-opens.
- `weekly_cycle.py --mark` (headless, launchd-schedulable) marks opens + closes past exit_by with the byte-identical backtest fill.
- `weekly_cycle.py --status` and `--dry-run` give the operator an offline view + a full-loop offline proof with the gate held.
- The headless-vs-CC runtime split and the T-2 -> queue -> CC-desk -> gate handoff are documented honestly (no pretend headless LLM).
</success_criteria>

<output>
After completion, create `.planning/phases/07.8-live-desk-wiring-pre-paper-hardening/slice5/SLICE5-SUMMARY.md`.
</output>
