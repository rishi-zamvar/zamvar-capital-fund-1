---
phase: 07.8-live-desk-wiring-pre-paper-hardening
plan: slice1
subsystem: desk
tags: [catalyst_context, live-desk-wiring, walking-skeleton, honest-degrade, no-look-ahead]
requires:
  - desk.orchestrator.run_desk / run_portfolio (Phase 4-6)
  - desk.weekly._catalyst_dict (WEEK-01)
  - backtest.engine.resolve_direction_proxy / _NO_ANALOG_GAPS
  - kb.analog_query / serving.asof / desk.builder._split_moves
provides:
  - desk.catalyst_context.make_catalyst_context (the live {entry, risk_inputs} feed hook)
  - scripts.run_one_catalyst.run_one (one-catalyst live-run harness + --dry-run offline seam)
affects:
  - desk/weekly.py:115 (the previously-skipped catalyst leg now has a real feed to pass)
tech-stack:
  added: []
  patterns: [injectable-provider-factory, honest-degrade, TDD-tests-first, cache-first-frugal]
key-files:
  created:
    - src/catalyst_trader/desk/catalyst_context.py
    - scripts/run_one_catalyst.py
    - tests/test_desk_catalyst_context.py
    - tests/test_run_one_catalyst.py
  modified: []
decisions:
  - "single-leg by honest degrade is the shipped Slice-1 path (KB stores no peer conditional co-moves)"
  - "reused params['weekly']['beta_window_weeks'] as the price-series lookback (no new magic number)"
  - "C1: run_portfolio_fn injected so --dry-run is genuinely offline (run_portfolio fires LLM via risk.assess)"
metrics:
  duration: ~35m
  completed: 2026-08-19
  tasks: 2
  tests_added: 11
  files: 4
---

# Phase 07.8 Slice 1: Live catalyst_context Binding + One-Catalyst Harness Summary

The one missing wire is built: a live `catalyst_context` hook that honestly satisfies the
`run_portfolio` work-item price/analog contract from existing point-in-time data, plus a
one-catalyst harness that runs ONE real biotech catalyst through the live desk end-to-end. The
walking skeleton is offline-tested and green; the real `--live` LLM run is the operator hand-check
gated behind the blocking checkpoint (below).

## What shipped

- **`desk/catalyst_context.py`** — `make_catalyst_context(...)` injectable-provider factory returning
  the async closure `catalyst_context(conn, ticker, catalyst, as_of) -> {"entry", "risk_inputs"}`,
  matching `weekly.py:84` exactly. Every `risk_input` is a point-in-time tool output or the shipped
  honest degrade — zero fabricated numbers. Single-leg by honest degrade (no fabricated peer/hedge).
- **`scripts/run_one_catalyst.py`** — `run_one(...)` testable core (`run_desk -> catalyst_context ->
  run_portfolio -> print StrategyDossier`) + a thin `__main__` with `--dry-run` (offline wiring proof)
  and `--live` (operator-gated real run). Reuses `weekly._catalyst_dict` for the knowability-gated pick.
- **11 offline tests** (8 hook + 3 harness), all green; existing desk suites byte-for-byte green.

## risk_inputs sourcing map (which field from where)

| field                 | source (point-in-time, cache-first)                                                   | honest degrade |
|-----------------------|----------------------------------------------------------------------------------------|----------------|
| `entry`               | last cached close via `serving.asof(conn, cutoff).bars(ticker, as_of)` (== `weekly._last_close`); optional `--live` RH `quotes_rt` override | None/`<=0` -> `entry=None`, caller skips the leg |
| `p_loss`              | `1 - P(positive)` from `resolve_direction_proxy("base_rate")` over `as_of_view` (the INDEPENDENT risk prior, engine.py:303 — NOT the analyst verdict) | proxy `None` / `ValueError` / `KeyError` -> `entry=None` honest skip (never `1 - None`) |
| `gap`                 | `median` of the catalyst analogs' DOWN moves (split like `builder._split_moves`)        | no analogs -> `abs(params["weekly"]["hard_veto_drop"])` (the SAME stat_gap the sleeve + backtest use) |
| `analog_gaps.target_up/down` | `median` of analog up / `-median` down moves                                    | no analogs -> `0.0` (the `engine._NO_ANALOG_GAPS` default) |
| `analog_gaps.peer_*` + `w_*` | a COPY of `engine._NO_ANALOG_GAPS` (`peer_up/down/w_peer=0.0`, `w_target=1.0`)   | always the single-leg default (KB has no peer co-moves) |
| `prices.target`       | close series from cached bars (`lookback = params["weekly"]["beta_window_weeks"]`)      | `[]` when uncached (entry already None-guards) |
| `prices.peer`         | `[]`                                                                                    | always `[]` (single-leg) |

## Single-leg by honest degrade (confirmed)

The KB's `hedge_peers` carries only `peer` / `payoff_direction` / `weight` — **no peer conditional
co-moves**. Fabricating `peer_up`/`peer_down` would be inventing hedge math. So the hook always emits
the `_NO_ANALOG_GAPS` peer default (`peer_*=0.0`, `w_peer=0.0`, `prices.peer=[]`), which drives
`risk.validate_hedge` to return `None` = the honest single-leg fallback (identical to
`backtest.engine._honest_hedge`). This is asserted directly:
`test_givenNoInversePeer_...` feeds the produced dict to `validate_hedge` and asserts `None`. A real
paired-comove source is out of scope for the skeleton (a documented Slice-2+ carry-forward).

## Plan-check C1/C2/C3 resolutions

- **C1 (offline `--dry-run` seam):** `run_portfolio` fires REAL `run_structured` LLM calls inside
  `builder.build` + `risk.assess`, so injecting only `run_desk_fn` + `context_hook` would still hit
  the live model. Fixed by adding `run_portfolio_fn=run_portfolio` to `run_one`'s injectable surface
  (mirrors the `run_desk_fn` pattern). `--dry-run` passes a fake `run_portfolio_fn` returning a canned
  `StrategyDossier`, so it prints an offline dossier with zero LLM/network. The harness tests inject
  all three fakes.
- **C2 (None-guard + honest skip):** `resolve_direction_proxy("base_rate")` RETURNS `(None,None,None)`
  on a no-measured-cell case (it does not raise). The hook guards BOTH `except (ValueError, KeyError)`
  AND `if side is None or p_positive is None:` -> `entry=None` degrade (the harness skips the leg,
  mirroring `engine.py:306-307`). A neutral `p_loss` is never fabricated (`1.0 - None` would
  TypeError). Covered by `test_givenProxyYieldsNone_...` and `test_givenProxyRaises_...`.
- **C3 (embed binding):** the hook signature `(conn, ticker, catalyst, as_of)` carries no `embed`, but
  `kb.analog_query` requires it. The default `analog_source` captures `embed` at factory construction
  (`_default_analog_source(embed)` closure) — `run_one` passes `embed` into `make_catalyst_context`.
  No embed-less `analog_query` is ever wired.

## No-look-ahead + frugality

`catalyst_context` reads only through `serving.asof(conn, cutoff)` at the catalyst's knowable point
(`cutoff = as_of` backtest / `None = now` live) and the injected sources are read at the passed
`as_of` (asserted in `test_givenAsOf_...`). Entry is cache-first (the same frugal read as the sleeve);
the `--live` RH quote is the only optional network and degrades to the cached close. The operator
`--live` run is the only real network + LLM, and it is checkpoint-gated (not run here).

## Deviations from Plan

None beyond the mandated C1/C2/C3 fixes (all applied as specified). Plan executed as written.

## Live one-catalyst hand-check command (operator step — run AFTER this verifies)

Inside a Claude Code session (Max auth, `ANTHROPIC_API_KEY` unset — the Slice-0 runtime):

```
.venv/bin/python -m scripts.run_one_catalyst CAPR --live
```

**Suggested ticker: `CAPR`** — a real upcoming PDUFA (event_date 2026-08-22, inside the (today, +7d]
hold window), with a cached entry price (last close ≈ $6.65) and 29 `pdufa` KB analogs for the
base-rate + analog gaps. It is the canonical single-name binary event the fund targets.

Deep-analog-coverage alternatives (`trial_readout`, 239 analogs): `AZN` / `PFE` — BUT both currently
have **no cached price bars**, so their entry would honestly degrade to None (leg skipped). Cache
their bars first if you want to hand-check a trial_readout instead.

Hand-check at the checkpoint: entry price looks right? p_loss/gap plausible for that catalyst?
hedge = None (honest single-leg — expected for Slice 1)? Then approve to proceed to Slice 2 (DD + MD).

## Self-Check: PASSED

- All 4 code/test files present + SUMMARY.md written.
- Both task commits present (a4e0d42 hook, ec3ac95 harness).
- 11 new tests green; regression suites (weekly/risk/orchestrator/builder) byte-for-byte green.
