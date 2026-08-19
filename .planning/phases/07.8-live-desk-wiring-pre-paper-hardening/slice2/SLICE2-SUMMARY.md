---
phase: 07.8-live-desk-wiring-pre-paper-hardening
plan: slice2
subsystem: desk
tags: [diligence-inputs, live-desk-wiring, md-reconciliation, honest-degrade, no-look-ahead, orphan-wire]
requires:
  - desk.diligence.run_diligence (Workflow-3, DILIG-01/02/03)
  - desk.md.reconcile (RECON-01..08)
  - desk.catalyst_context.make_catalyst_context (7.8-S1)
  - desk.orchestrator.run_desk / run_portfolio (Phase 4-6)
  - desk.weekly._catalyst_dict / serving.asof
  - providers.options_cboe.fetch (CBOE delayed quotes)
provides:
  - desk.diligence_inputs.make_diligence_inputs (the (DiligenceInput, market_data, degraded) live binding)
  - desk.live_desk.run_one_catalyst_decision (catalyst -> reconciled MDDecision chain)
  - scripts.run_one_catalyst --with-dd (DiligenceDossier + MDDecision + round log print path)
affects:
  - the previously-orphaned run_diligence + md.reconcile now have a live caller outside tests
tech-stack:
  added: []
  patterns: [injectable-provider-factory, honest-degrade, TDD-tests-first, cache-first-frugal, omit-and-flag]
key-files:
  created:
    - src/catalyst_trader/desk/diligence_inputs.py
    - src/catalyst_trader/desk/live_desk.py
    - tests/test_desk_diligence_inputs.py
    - tests/test_live_desk_decision.py
  modified:
    - scripts/run_one_catalyst.py
decisions:
  - "B1: financials OMITTED this slice (edgar.fundamentals exposes shares_outstanding+cash_runway_months, NOT cash_usd/monthly_burn_usd/months_to_catalyst) -> ungrounded -> forced NO-GO. Sourcing = Slice 2.5."
  - "C4: ownership OMITTED unconditionally (no free insider_net; EDGAR Form-4 deferred) -> ungrounded -> forced NO-GO. finra call skipped (frugal). Sourcing = Slice 2.5."
  - "B2: CBOE options seam is nested (cboe['options_quote']) + nullable; catalyst_date injected by us; illiquid -> call_bid=0 sentinel -> grounded historical-gap fallback."
  - "C1: underlying_quote['bid'] can be None -> coerced to 0 (zero_liquidity's .get default only fires on a MISSING key)."
  - "C5: run_one left byte-green; run_one_catalyst_decision is a fresh no-print chain (small head overlap accepted over refactoring money-path Slice-1 code)."
metrics:
  duration: ~40m
  completed: 2026-08-19
  tasks: 3
  tests_added: 20
  files: 5
---

# Phase 07.8 Slice 2: Independent DD + MD Reconciliation Wire Summary

The orphaned independent diligence + MD reconciliation loop is now attached to the Slice-1 dossier. `run_diligence`
+ `md.reconcile` were built and unit-tested but called from nowhere outside tests; Slice 2 builds the two missing
live bindings (`make_diligence_inputs`, `run_one_catalyst_decision`) and an extended `--with-dd` harness so ONE
real catalyst produces an approvable go/no-go **decision** (an `MDDecision`: enter/pass/escalate + reconciliation
round log), not just a `StrategyDossier`. The whole offline path is TDD-tested and green; the real `--live` LLM run
is the operator hand-check gated behind the blocking checkpoint (below).

## What shipped

- **`desk/diligence_inputs.py`** — `make_diligence_inputs(*, options_source, trial_source)` injectable-provider
  factory returning `diligence_inputs(conn, ticker, catalyst, *, entry, risk_inputs, exit_by_date, pair, as_of)
  -> (DiligenceInput, market_data, degraded)`. Mirrors Slice-1's `make_catalyst_context`. Every money dim is
  honestly sourced or honestly degraded — zero fabricated numbers.
- **`desk/live_desk.py`** — `run_one_catalyst_decision(...)`: the end-to-end chain
  `_catalyst_dict -> run_desk -> catalyst_context -> run_portfolio -> (promoted?) make_diligence_inputs ->
  run_diligence -> md.reconcile -> MDDecision`, with an honest zero-trade short-circuit. Every LLM seam is an
  injectable function param, so the whole path runs offline.
- **`scripts/run_one_catalyst.py`** — a `--with-dd` flag routing through `run_one_catalyst_decision` + a
  `_print_decision` helper (DiligenceDossier verdict + per-dimension + red/degrade flags, MDDecision +
  round count/dispositions, or the honest no-trade reason). `--dry-run --with-dd` is pure-offline; `--live
  --with-dd` is operator-gated. Slice-1 dossier-only path is byte-for-byte unchanged.
- **20 offline tests** (10 inputs + 8 chain + 2 harness-print), all green; full suite 1688 passed, 1 pre-existing xfail.

## market_data sourcing map (honest-degrade column)

| market_data key    | source (Slice 2)                                        | honest degrade                                              |
|--------------------|---------------------------------------------------------|------------------------------------------------------------|
| `options`          | **SOURCED** — `options_cboe.fetch` nested `options_quote` (B2); we inject `catalyst_date=event_date`, `underlying_price=entry`, `days_to_event` | `options_quote` None / cboe None -> `call_bid=0` sentinel -> `options_liquid` False -> **grounded** in-house historical-gap fallback (never a fabricated IV) |
| `liquidity_quote`  | **SOURCED** — CBOE `underlying_quote` {bid,volume,oi}; None-bid coerced to 0 (C1) | cboe None -> all-zero (conservative zero-liquidity -> honest NO-GO) |
| `hedge`            | **SOURCED (reuse)** — Slice-1 `catalyst_context` risk_inputs {entry, exit_by_date, analog_gaps, prices}, no recompute | single-leg (pair=None) -> `validate_hedge` None -> HEDGE-04 fallback (grounded; hedge dim does NOT force NO-GO) |
| `trial`            | **SOURCED (optional)** — `trial_source(ticker)`; default None | None (non-money; no NO-GO) |
| `financials`       | **DEGRADED -> OMITTED (B1)** — edgar.fundamentals lacks cash_usd/monthly_burn_usd/months_to_catalyst | key absent -> `financials_context(None)` None -> **ungrounded -> forced NO-GO** + degrade flag |
| `ownership`        | **DEGRADED -> OMITTED (C4)** — no free insider_net (Form-4 deferred); finra call skipped (frugal) | whole key absent (a partial dict KeyErrors) -> **ungrounded -> forced NO-GO** + degrade flag |

**Sourced honestly:** options, liquidity, hedge (+ optional trial). **Degraded (omit + flag -> NO-GO):**
financials + ownership.

## Plan-check resolutions (corrected contracts, verified against code)

- **B1 (financials fictional):** the plan's `edgar.fetch(ticker) -> cash/burn/runway` is false — `edgar.fetch`
  returns the offering card; `edgar.fundamentals` returns `{shares_outstanding, cash_runway_months}`, NOT the
  `cash_usd`/`monthly_burn_usd`/`months_to_catalyst` keys `financials_context` direct-subscripts. Resolution:
  OMIT the `financials` key entirely -> ungrounded -> forced NO-GO (honest, no fabrication).
- **B2 (CBOE seam nested + nullable):** read `cboe["options_quote"]` (None on a non-None fetch when no live
  ATM pair qualifies); inject `catalyst_date=event_date`; source liquidity from `cboe["underlying_quote"]`;
  every options structure (liquid OR sentinel) carries `days_to_event` (diligence.py:526 subscripts it).
- **C1 (None-bid TypeError guard):** `_num(None) -> 0.0` when building `liquidity_quote` — `zero_liquidity`'s
  `quote.get("bid", 0) <= 0` default only fires on a MISSING key, so a present-but-None bid would raise.
- **C4 (frugality):** ownership always omitted -> no `finra.fetch` + shares calls spent this slice.
- **C5 (backward-compat):** `run_one` untouched (byte-green); `run_one_catalyst_decision` is a fresh no-print
  chain. `test_run_one_catalyst.py` unchanged and green.

## Ownership + financials data-gap decision (carry-forward)

Both `ownership` (insider_net) and `financials` (cash/burn/runway) are UNSOURCEABLE from free data this slice, so
both are honestly omitted -> the diligence verdict on the current wire will be **NO-GO by data gap**, not by an
adversarial thesis. This is a wiring success (the loop runs end-to-end and the honest degrade forces the
asymmetric-safe NO-GO) but NOT a thesis verdict.

**Slice 2.5 (extend `edgar.fundamentals` for cash_usd/monthly_burn_usd/months_to_catalyst + a Form-4 net-insider
source for ownership) MUST precede Slice 4 (paper) or paper trades nothing** — every candidate NO-GOs on the two
data gaps regardless of merit.

## No-look-ahead + frugality

Per C3, point-in-time (`serving.asof`) is genuine only for the price bars + finra path. `options_cboe.fetch` and
`edgar.fundamentals` are now-snapshots (no as_of arg) — acceptable for a T-2 operator-gated live run. `days_to_event`
is still scoped to `as_of` (money-data shaping). Frugal: options is one cache-first CBOE call; ownership skips
finra entirely (omitted); the `--live` run is the only network + LLM and is checkpoint-gated.

## Deviations from Plan

The plan's `<interfaces>` block was materially wrong on financials (B1) and the options seam shape (B2); the
corrected contracts (supplied at execution, verified against code) OVERRODE the plan and were applied as the
canonical spec. Tests were written to the corrected reality (financials + ownership UNCONDITIONALLY omitted;
options seam nested/nullable) rather than the plan's fictional shapes. `--dry-run` added as an explicit
backward-compat alias so the documented operator command works (default was already offline). No architectural
(Rule 4) changes.

## Live hand-check command (operator step — the blocking checkpoint)

Inside a Claude Code session (Max auth, `ANTHROPIC_API_KEY` UNSET — the Slice-0 runtime), pick a POSITIVE-leaning
upcoming catalyst that will actually PROMOTE a trade (so DD/MD have something to reconcile). Confirm a dossier
promotes FIRST, then run the full decision:

```
.venv/bin/python -m scripts.run_one_catalyst <TICKER> --live            # 1. confirm a dossier promotes
.venv/bin/python -m scripts.run_one_catalyst <TICKER> --live --with-dd  # 2. the full DD + MD decision
```

Note: `CAPR` was correctly no-trade in Slice 1 (negative), so it will short-circuit before DD — choose a name with
a bullish base-rate prior + cached price bars (confirm step 1 promotes before step 2). Hand-check: is the
DiligenceDossier go/no-go plausible? Is a NO-GO resting ONLY on the ownership/financials DATA GAP (a degraded
flag will say so) vs a genuine adversarial NO-GO? Does the MDDecision (enter/pass/escalate) follow from
verdict + dossier + DD? How many reconciliation rounds, what dispositions? On escalate, confirm
`.monitor/blocker.json` was written. Note cost/latency (several opus in reconcile + narrative).

## Self-Check: PASSED

- All 5 code/test files present + SUMMARY.md written.
- 3 task commits present (84ff38a inputs, 42c3501 chain, 6158b6d harness).
- 20 new tests green; regression (test_desk_md / test_desk_diligence / test_desk_catalyst_context) byte-for-byte
  green; full suite 1688 passed / 1 pre-existing xfail.
- `--dry-run --with-dd CAPR` prints DiligenceDossier + MDDecision + round log fully offline.
