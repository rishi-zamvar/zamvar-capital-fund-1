# Operator runbook — the weekly paper-trading cadence (7.8-S5)

This is how the forward paper month runs itself. It is split HONESTLY into two halves:

- **HEADLESS (launchd, no LLM, no API key):** data refresh, T-2 enqueue, weekly mark/close.
- **CLAUDE CODE SESSION (the operator, LLM on Max):** draining the desk queue into gated decisions.

> **RUNTIME CONSTRAINT (why the split exists).** The analyst desk runs as Claude Code subagents on a
> Max plan — there is **no API key** on this host. A headless cron therefore **cannot** call the LLM
> desk. Anything that needs the desk (a decision) must run inside a Claude Code session. Everything
> deterministic (fetching data, firing the T-2 trigger, marking/closing positions) runs headlessly.
> We do **not** pretend headless LLM works.

---

## The loop

```
  [HEADLESS launchd]                          [CLAUDE CODE session]
  com.zamvar.fund1.daemon / catalyst-refresh
     └─ refresh() step 7: detect_and_fire
          └─ T-2 catalyst -> enqueue_desk_run  ──►  desk_run_request (queued)
                                                        │
                                          weekly_cycle.py --desk  (operator, in CC)
                                                        └─ run the live desk per queued catalyst
                                                             └─ submit_decision -> paper_pending
                                                                  (the INVIOLABLE gate — opens nothing)
                                                                        │
                                        operator reviews & approves ────┘
                                          paper_run.py --approve <id>  -> position opens

  com.zamvar.weekly-mark  (HEADLESS, weekly)
     └─ weekly_cycle.py --mark  -> mark opens + close any past exit_by (byte-identical backtest fill)
```

The daily refresh already runs headlessly (see `com.zamvar.fund1.daemon`). Slice 5 gave its T-2
trigger a real launcher: a fired T-2 catalyst now writes a **`desk_run_request`** row instead of just
logging. Enqueue is idempotent (`UNIQUE(catalyst_id, event_date)`) and **opens nothing**.

---

## Commands

| Command | Where | LLM? | What it does |
|---|---|---|---|
| `weekly_cycle.py --status` | anywhere | no | offline snapshot: open positions, pending approvals, upcoming catalysts, queued desk runs |
| `weekly_cycle.py --desk` | **Claude Code session** | **yes** | drain the queue -> run the desk per catalyst -> **submit** any 'enter' to the gate (never opens) |
| `weekly_cycle.py --mark` | headless (launchd) | no | mark every open + close any past `exit_by` |
| `weekly_cycle.py --dry-run` | anywhere | no | offline proof of the whole enqueue -> drain -> submit loop, with the gate held |
| `paper_run.py --approve <id>` | operator | no | the SOLE opener — over a pending record, open the paper position |

**The human gate is inviolable.** `--desk` and the whole `weekly_cycle.py` module only ever *submit*
to the gate; `approve_pending` (the sole opener) is never called by the scheduler. A drain of a fake
'enter' writes a `paper_pending` row and **zero** `paper_position` rows.

---

## The weekly operator flow

1. **When a T-2 fires** (check any time): `weekly_cycle.py --status` shows queued desk runs.
2. **In a Claude Code session:** `weekly_cycle.py --desk` drains the queue into gated decisions.
3. **Review each pending** and approve the ones you want: `paper_run.py --approve <id>`.
4. **The weekly mark** runs itself via `com.zamvar.weekly-mark` (or run `weekly_cycle.py --mark` by hand).

## Install the headless mark schedule

```sh
cp launchd/com.zamvar.weekly-mark.plist ~/Library/LaunchAgents/
launchctl load  ~/Library/LaunchAgents/com.zamvar.weekly-mark.plist   # start (Sunday 18:00 local)
launchctl start com.zamvar.weekly-mark                                 # run one now
launchctl unload ~/Library/LaunchAgents/com.zamvar.weekly-mark.plist  # stop
```

(The daily refresh / enqueue job — `com.zamvar.fund1.daemon` — is installed separately; see its plist.)

---

## Upgrade path (NOT built here)

The `--desk` step still needs a human to open a Claude Code session. A future upgrade could make the
headless enqueue also write a `~/.dispatch/wake-touches/` signal (the existing Dispatch wake-touch
pattern), so a Claude Code session **auto-wakes** when a T-2 fires and runs `--desk` on its own. That
is an upgrade path only — Slice 5 does **not** build it, and does not claim headless LLM.
