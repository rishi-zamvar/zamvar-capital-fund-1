---
phase: 07.8-live-desk-wiring-pre-paper-hardening
plan: slice4
type: tdd
wave: 1
depends_on: []          # builds on slice2/2.5 (already shipped) — run_one_catalyst_decision exists on disk
files_modified:
  - src/catalyst_trader/migrations/015_paper_ledger.sql
  - src/catalyst_trader/paper_ledger.py
  - scripts/paper_run.py
  - tests/test_paper_ledger_store.py
  - tests/test_paper_lifecycle.py
  - tests/test_paper_run.py
autonomous: false
requirements:
  - "7.8-S4"   # paper ledger + open/mark/close lifecycle + minimal operator-approval gate (forward paper trading begins)

user_setup: []

must_haves:
  truths:
    - "No paper position ever opens without an explicit operator approval: the ONLY code path to open is approve_pending(conn, id) over a pending record; a rejected or un-approved decision produces ZERO positions (tested, inviolable)."
    - "An approved MDDecision 'enter' opens exactly one paper_position carrying the dossier's own params — entry, size_pct, direction->side, exit_by, ticker, and a decision_ref back to the catalyst/decision that authored it. A 'pass'/'escalate' decision opens nothing."
    - "mark_open_positions(conn, as_of) marks every OPEN position at the point-in-time quote (serving.asof cache-first, RH quotes_rt degrade-to-None) and CLOSES any position whose exit_by <= as_of, booking realized_ret via the SAME pessimistic fill discipline the backtest uses (fill.fill_price + engine._net_return half-spread-both-sides) — no live-vs-backtest drift."
    - "No-look-ahead: a mark at date D reads only serving.asof(conn, D); a missing mark quote (bars empty / halted action bar / quotes_rt None) HOLDS the position (skips the mark) and NEVER fabricates a price."
    - "The realized outcome of a closed paper position is fed back to the KB as a CITED claim that references the decision's OWN evidence refs (not a fabricated weekly_base_rate citation) — cite-or-drop holds by construction."
    - "NO live broker order anywhere: paper fills only; providers.robinhood.place_equity_order is never imported or called (Phase 11 is strictly last, behind the paper proof)."
    - "Additive only: db.migrate() applies 015 cleanly on top of 014; every existing suite stays green; no existing signature changes."
  artifacts:
    - path: "src/catalyst_trader/migrations/015_paper_ledger.sql"
      provides: "paper_position + paper_mark + paper_pending tables (the ledger substrate)"
      contains: "CREATE TABLE paper_position"
    - path: "src/catalyst_trader/paper_ledger.py"
      provides: "store helpers (open/mark/close/get_open) + pending gate (submit/approve/reject) + position_params_from_decision + mark_open_positions lifecycle + record_paper_outcome"
      min_lines: 120
    - path: "scripts/paper_run.py"
      provides: "operator harness: run one catalyst -> (if enter) submit_for_approval; --approve/--reject; --mark weekly pass; --dry-run offline"
      min_lines: 50
    - path: "tests/test_paper_ledger_store.py"
      provides: "deterministic :memory: store + inviolable-gate tests (no open without approval; reject->no position)"
    - path: "tests/test_paper_lifecycle.py"
      provides: "money-critical mark/close edge cases (gap-open, halt->hold, direction sign, exit_by past/future) with injected bars/quotes; NO live network/LLM"
    - path: "tests/test_paper_run.py"
      provides: "offline --dry-run harness wiring proof (fake decision + injected quotes)"
  key_links:
    - from: "src/catalyst_trader/paper_ledger.py"
      to: "run_one_catalyst_decision result['dossier'].trade"
      via: "position_params_from_decision maps dossier.trade -> {ticker, entry, size_pct, side, exit_by, decision_ref}"
      pattern: "\\.trade\\."
    - from: "src/catalyst_trader/paper_ledger.py"
      to: "backtest.fill.fill_price + backtest.engine._net_return"
      via: "pessimistic close fill + realized_ret (half-spread both sides) — reuse, do not reinvent P&L"
      pattern: "fill_price|_net_return"
    - from: "src/catalyst_trader/paper_ledger.py"
      to: "serving.asof(conn, as_of).bars(ticker, as_of)"
      via: "point-in-time mark-to-market read (cache-first, no-look-ahead)"
      pattern: "serving\\.asof"
    - from: "src/catalyst_trader/paper_ledger.py"
      to: "providers.robinhood.quotes_rt"
      via: "live mark fallback, degrade-to-None (frugality: cache/bars first)"
      pattern: "quotes_rt"
    - from: "src/catalyst_trader/paper_ledger.py"
      to: "kb.insert_claim"
      via: "record_paper_outcome cites the decision's own evidence refs (cite-or-drop)"
      pattern: "insert_claim"
    - from: "scripts/paper_run.py"
      to: "desk.live_desk.run_one_catalyst_decision + paper_ledger.submit_for_approval/mark_open_positions"
      via: "operator harness: decision -> approval -> open -> weekly mark/close"
      pattern: "run_one_catalyst_decision|mark_open_positions"
---

<objective>
Turn an APPROVED MDDecision "enter" into a tracked PAPER position that opens, marks weekly against
live/point-in-time quotes, closes at exit_by, and books realized P&L back into the KB — behind an
INVIOLABLE minimal operator-approval gate. This is the machinery that makes forward paper trading
real (the true out-of-sample test). The desk already reaches a decision
(`live_desk.run_one_catalyst_decision` -> MDDecision + the surfaced dossier); what is missing is the
ledger + open/mark/close lifecycle + the human gate.

Purpose: begin the 1-month forward paper proof (the leak-free edge proof the whole strategy rests on).
Output: a paper ledger (SQLite, migration 015), `paper_ledger.py` (store + gate + lifecycle), and a
`paper_run.py` operator harness. Paper fills ONLY — no live broker order (Phase 11 is strictly last).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/07.8-live-desk-wiring-pre-paper-hardening/slice2.5/SLICE2.5-SUMMARY.md

<interfaces>
<!-- Confirmed from the codebase. Executor should use these directly — no exploration needed. -->

# desk/live_desk.py — the decision the ledger consumes (dossier IS surfaced alongside the decision):
run_one_catalyst_decision(conn, embed, ticker, *, as_of, live=False, ...) -> dict
  # returns {catalyst, verdict, dossier, dd, decision, rounds, degraded_flags, reason}
  # decision: MDDecision | None ; dossier: StrategyDossier | None

# contracts — MDDecision.decision in {"enter","pass","escalate"}. Only "enter" opens.
# StrategyDossier.trade: TradeProposal with:
#   target_long: str ; entry: float ; exit_by_date: str ; size_pct: float
#   direction: Literal["positive","negative"]  # positive -> side "long" ; the desk is long-only
#   holds_through_catalyst: bool ; catalyst_id: str ; hedge: Hedge | None
# StrategyDossier.all_evidence_refs: list[str]  # kb:<id> / tool:<fn>#<hash> — cite source for the outcome

# backtest/fill.py — REUSE the pessimistic fill (no backtest drift):
fill_price(bars, *, side, held_through, slippage, sl_level=None) -> float | None
  # bars[-1] = the exit/action bar; held_through -> gap-open; None iff halted/delisted/zero-vol/zero-quote
half_spread_pct(price) -> float

# backtest/engine.py — REUSE the realized-return math (half-spread paid BOTH sides):
_net_return(entry, fill, apply_costs) -> float   # apply_costs=True for RH ($0 commission, spread only)

# serving.py — point-in-time mark read (no-look-ahead):
serving.asof(conn, cutoff).bars(ticker, as_of) -> list[dict]  # [-1] is the latest knowable weekly bar

# providers/robinhood.py — live mark fallback, degrade-to-None:
quotes_rt(tickers, *, mcp_call=None) -> dict | None   # {SYM: {last, bid, ask, prev_close, ...}}

# kb — cited outcome write (as record_weekly_outcome uses it):
kb.insert_claim(conn, KBNode(kind="outcome", attrs={...}), [EvidenceSource(url, retrieved_at, snippet_hash, quote)], embed=None, embed_text=None)

# db.py — migrations auto-apply NNN_*.sql > schema_version; NEXT NUMBER = 015 (last was 014_daily_bar).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Ledger schema (migration 015) + deterministic store + inviolable pending gate</name>
  <files>src/catalyst_trader/migrations/015_paper_ledger.sql, src/catalyst_trader/paper_ledger.py, tests/test_paper_ledger_store.py</files>
  <behavior>
    - open_paper_position writes one row (ticker, side, entry_price, size_pct, opened_at, exit_by, status='open', decision_ref); get_open_positions returns only status='open'.
    - mark_paper_position appends a paper_mark row (position_id, mark_date, mark_price, unrealized_ret); a second mark at the same date is idempotent (UNIQUE(position_id, mark_date) -> update in place, mirrors upsert_bars).
    - close_paper_position sets status='closed', close_price, realized_ret, closed_at; a re-close is a no-op / raises (never double-books).
    - GATE (inviolable): submit_for_approval writes paper_pending(status='pending', params json); approve_pending(id) -> opens the position AND flips status='approved' (returns the new position id); reject_pending(id) -> status='rejected', NO position. There is NO other public function that inserts a paper_position.
    - Test: submit then reject -> get_open_positions == []. Submit then approve -> exactly one open position with the submitted params. Approve twice -> the second is a no-op (no duplicate position).
  </behavior>
  <action>
    Write migrations/015_paper_ledger.sql with three tables (header comment in the 014 style explaining
    why they are separate from price_bar): paper_position (id, ticker, side, entry_price, size_pct,
    opened_at, exit_by, status TEXT CHECK(status IN ('open','closed')), close_price, realized_ret,
    closed_at, decision_ref, catalyst_id), paper_mark (id, position_id FK, mark_date, mark_price,
    unrealized_ret, source, UNIQUE(position_id, mark_date)), paper_pending (id, status CHECK IN
    ('pending','approved','rejected'), params TEXT json, submitted_at, resolved_at, position_id).
    Add indexes on paper_position(status) and paper_mark(position_id).

    Write paper_ledger.py store helpers using now_iso() + the store.py insert/upsert idiom (no ORM):
    open_paper_position, get_open_positions, mark_paper_position (upsert on the natural key),
    close_paper_position (guard against re-close), submit_for_approval, approve_pending, reject_pending.
    approve_pending is the SOLE opener — it reads the pending params and calls open_paper_position, so
    the human gate is enforced structurally, not by convention (per D: human gate INVIOLABLE).
    # ponytail: plain sqlite helpers mirroring store.py; no repository class, no ORM.
    Do NOT put P&L/fill math here — this file is pure persistence + the gate; the mark/close math is Task 2.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_paper_ledger_store.py -x -q</automated>
  </verify>
  <done>Migration 015 applies via db.migrate() on top of 014; store + gate helpers pass; no paper_position can be inserted except through approve_pending; reject/re-approve produce zero/one position as specified.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Lifecycle — dossier->params mapping + mark_open_positions (reuse fill discipline) + cited outcome feedback</name>
  <files>src/catalyst_trader/paper_ledger.py, tests/test_paper_lifecycle.py</files>
  <behavior>
    - position_params_from_decision(result): only when result['decision'].decision == 'enter' returns
      {ticker: dossier.trade.target_long, entry: .entry, size_pct: .size_pct, side: 'long'
      (desk is long-only; direction carried for provenance), exit_by: .exit_by_date,
      held_through: .holds_through_catalyst, catalyst_id: .catalyst_id,
      decision_ref, evidence_refs: dossier.all_evidence_refs}. 'pass'/'escalate'/None -> None.
    - mark_open_positions(conn, as_of, *, quotes_fn=None): for each open position:
        * mark price: serving.asof(conn, as_of).bars(ticker, as_of)[-1]['close'] (cache-first). If empty,
          fall back to quotes_fn(ticker) (default a robinhood.quotes_rt wrapper) 'last'; still None -> HOLD
          (skip this mark, do NOT close, do NOT fabricate).
        * if exit_by <= as_of: CLOSE via fill.fill_price(bars, side, held_through, slippage=EXIT slippage
          knob) then engine._net_return(entry, fill, apply_costs=True) -> realized_ret; call
          close_paper_position + record_paper_outcome. A halted/unfillable action bar (fill_price None)
          -> HOLD (unmeasurable, never a fabricated close), mirroring engine._fill_leg.
        * else: mark_paper_position with unrealized_ret = _net_return(entry, mark_price, apply_costs=False)
          (a mark is not a round-trip; no exit spread booked until close).
      Returns a summary {marked, closed, held}.
    - record_paper_outcome(conn, position, realized_ret, *, embed=None): insert_claim a KBNode(kind='outcome',
      attrs={kind:'paper_leg', ticker, direction, size, realized_ret, win: realized_ret>0}) citing the
      position's FIRST evidence_ref (from the decision) as the EvidenceSource url — cite-or-drop holds by
      construction. Do NOT reuse record_weekly_outcome (it forces a weekly_base_rate citation a catalyst
      leg does not have — that would fabricate a mismatched ref). See RISK note in the return.
  </behavior>
  <action>
    Add position_params_from_decision, mark_open_positions, record_paper_outcome to paper_ledger.py.
    REUSE backtest.fill.fill_price + backtest.engine._net_return + half_spread_pct verbatim so paper
    fills are byte-identical to backtest fills (no live-vs-backtest drift, per D). Read marks ONLY
    through serving.asof(conn, as_of) (no-look-ahead). The live quote fallback wraps
    providers.robinhood.quotes_rt (degrade-to-None); default quotes_fn=None means bars-only (offline).
    Use the SAME slippage knob the backtest reads (import it from the backtest config, do not invent a
    new magic number). NEVER import providers.robinhood.place_equity_order.
    Money-critical: exhaustive edge tests — gap-open close, halted action bar -> hold, exit_by in the
    past -> close vs future -> mark, missing mark quote -> hold, direction/side sign, size_pct scaling.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_paper_lifecycle.py -x -q</automated>
  </verify>
  <done>An 'enter' result maps cleanly to position params (pass/escalate -> None); mark_open_positions marks open + closes past-exit_by at the pessimistic fill with correct realized_ret; a missing/halted quote holds (never fabricates); closed positions write a cited paper outcome; place_equity_order is never referenced.</done>
</task>

<task type="auto">
  <name>Task 3: Operator harness scripts/paper_run.py (run -> submit -> approve/reject -> weekly mark)</name>
  <files>scripts/paper_run.py, tests/test_paper_run.py</files>
  <action>
    Build a thin harness mirroring scripts/run_one_catalyst.py: a testable core + a thin __main__.
    Default mode: run_one_catalyst_decision(conn, embed, ticker, as_of=today) -> if decision=='enter',
    submit_for_approval and PRINT the dossier summary + the pending id + the exact approve/reject command
    (the operator gate surface — minimal this slice; full iOS/FastAPI gate is Phase 9). Non-enter -> print
    the honest reason, submit nothing.
    Flags: --approve <id> / --reject <id> (call the gate), --mark (run mark_open_positions(conn, today)
    and print marked/closed/held), --dry-run (offline: a fake 'enter' decision + injected bars/quotes,
    proving the full submit->approve->open->mark->close wiring with NO network/LLM).
    # ponytail: argparse + a handful of branches; reuse run_one_catalyst.py's structure, no new framework.
    Write tests/test_paper_run.py: the --dry-run core opens exactly one position after approve and closes
    it on --mark past exit_by, all offline.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_paper_run.py -x -q && .venv/bin/python scripts/paper_run.py --dry-run</automated>
  </verify>
  <done>paper_run.py --dry-run drives the whole loop offline (decision -> submit -> approve -> open -> mark -> close); --approve/--reject/--mark work against the ledger; no live order path.</done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 4: Operator hand-check — approve one real catalyst, confirm the gate held</name>
  <action>Operator verification only (no code). Confirm the offline proof + full suite, then optionally run one real catalyst live and exercise the inviolable approval gate.</action>
  <what-built>The paper ledger + open/mark/close lifecycle + the operator-approval gate + paper_run.py harness. Forward paper trading can now begin: one real catalyst can run to a decision, be approved by you, open a paper position, and be marked/closed weekly.</what-built>
  <how-to-verify>
    1. Confirm the offline proof: `.venv/bin/python scripts/paper_run.py --dry-run` drives submit->approve->open->mark->close with no network.
    2. Full suite green: `.venv/bin/python -m pytest -q` (existing suites unchanged + the three new files).
    3. (Optional, live) Run one real catalyst inside Claude Code (Max subscription runtime, no API key): `.venv/bin/python scripts/paper_run.py <TICKER>` — review the printed dossier, then explicitly approve or reject. Confirm NOTHING opened before your approval (the inviolable gate) and that a rejected decision leaves the ledger empty.
  </how-to-verify>
  <verify>Operator confirms: nothing opened before approval; reject leaves the ledger empty; --dry-run loop passes.</verify>
  <done>Operator has approved (or rejected) one decision and confirmed the gate held; paper trading is live.</done>
  <resume-signal>Type "approved" (paper trading is live and the gate held) or describe issues.</resume-signal>
</task>

</tasks>

<verification>
- `.venv/bin/python -m pytest -q` — all suites green (existing byte-for-byte + 3 new files).
- `.venv/bin/python -c "from catalyst_trader import db; c=db.connect(':memory:'); db.migrate(c); print(c.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'paper_%'\").fetchall())"` — the three paper_ tables exist.
- `grep -rn "place_equity_order" src/catalyst_trader/paper_ledger.py scripts/paper_run.py` — returns NOTHING (paper only).
- No-look-ahead + no-fabrication + inviolable-gate cases pass in tests/test_paper_lifecycle.py + tests/test_paper_ledger_store.py.
</verification>

<success_criteria>
- Migration 015 applies cleanly; the ledger tracks open/mark/close with realized_ret computed by the reused backtest fill discipline (no drift).
- No paper position opens without explicit approval; reject leaves the ledger empty; approve opens exactly one from the dossier's own params.
- Weekly mark/close reads point-in-time only, holds on a missing/halted quote, and feeds a cited outcome back to the KB.
- Zero live-broker order path anywhere. Existing suites unchanged.
</success_criteria>

<output>
After completion, create `.planning/phases/07.8-live-desk-wiring-pre-paper-hardening/slice4/SLICE4-SUMMARY.md`
</output>
