---
phase: quick-260819-pf2
plan: 01
subsystem: desk/portfolio
tags: [PORT-01, portfolio-risk, weekly-assembly, backward-compat]
requires: [desk.portfolio_builder.build_portfolio, kb.hedge_profile]
provides: [book_to_portfolio_inputs, PortfolioContext.portfolio_outcome, run_portfolio.attach_book_risk]
affects: [desk.orchestrator.run_portfolio, desk.weekly.run_weekly]
key-files:
  created: [tests/test_desk_book_risk.py]
  modified:
    - src/catalyst_trader/desk/portfolio.py
    - src/catalyst_trader/desk/orchestrator.py
    - src/catalyst_trader/contracts/__init__.py
decisions:
  - "The attached PortfolioOutcome is TARGET-LEG scope, not whole-book gross (peer notional not fabricated)."
  - "conn=None binds corr_source=None (engine idiosyncratic fallback) so null-conn offline callers never crash."
  - "Duplicate ticker across two promoted legs aggregates size_pct into one position."
metrics:
  duration: ~40min
  completed: 2026-08-19
  tasks: 3
  tests-added: 18
  files: 4
---

# Phase 7.8 Followup 2 Plan 01: Wire build_portfolio into Weekly Assembly Summary

Wired the stateless `build_portfolio` what-if engine into the weekly desk assembly so the whole-book
risk read runs AUTOMATICALLY: a pure adapter maps the assembled promoted book's `TradeProposal`s into
the engine's `(positions, assumptions)` contract, `run_portfolio` calls the engine ONCE after
`select_book`, and the resulting `PortfolioOutcome` rides on each promoted dossier's
`portfolio_context.portfolio_outcome`. Previously `build_portfolio` only ran when an analyst invoked
the MCP tool — it never ran on the committed weekly book.

## What shipped

**Task 1 — pure adapter + additive contract field** (`e69d4bc`)
- `desk/portfolio.py::book_to_portfolio_inputs(book, *, corr_source=None, sector_shock=None)` — maps a
  `list[StrategyDossier]` OR `list[TradeProposal]` into `(positions, assumptions)`. PURE: no conn, no
  network, no LLM. Per-name moves come from what the desk ALREADY computed — a catalyst leg reads
  `exit_plan.ev_flip` (upside/downside/p); a statistical/defensive leg (`exit_plan=None`) contributes
  only `expected_return_pct`, letting the engine default `down_move`/`p_positive`.
- `BOOK_RISK_PARAMS = {"default_sector_shock": -0.10}` — direct-subscript, missing-key-raises (no magic
  literal on the code path).
- `contracts/__init__.py::PortfolioContext.portfolio_outcome: dict | None = None` — one additive
  optional field (mirrors `TradeProposal.hedge_profile`), defaults `None` until attached.

**Task 2 — guarded attach pass in `run_portfolio`** (`6268558`)
- New kwarg `attach_book_risk: bool = True` (automatic by default, explicit off-switch).
- After `select_book` + every `pm_decide`/`build_weekly_leg_dossier` call and immediately before
  `return dossiers`: run `build_portfolio` once over the promoted subset and `model_copy` the outcome
  onto each promoted dossier's `portfolio_context`. `run_weekly` needs NO change — it returns
  `run_portfolio`'s dossier list, so the outcome rides along (proven by an end-to-end `run_weekly` test).

**Task 3 — backward-compat + no-magic guard sweep** (`0c0fa6c`)
- Tests only: PARAMS-driven sector-shock default (patchable), missing-key raises `KeyError`, additive
  field breaks no existing `PortfolioContext` construction.

## The conn-guard fix (plan-check blocker)

The plan's naive binding `corr_source = lambda t: kb.hedge_profile(conn, t)` with `attach_book_risk=True`
would crash EVERY existing offline `run_portfolio` test — they pass `conn=None`, and
`kb.hedge_profile(None, t)` does `None.execute(...)` → `AttributeError`. Fixed by guarding the binding:

```python
corr_source = (lambda t: kb.hedge_profile(conn, t)) if conn is not None else None
```

A null-conn book falls back to the engine's documented `corr_source=None` idiosyncratic-correlation
behavior (no off-diagonal correlation, no crash); the real-conn production path stays byte-for-byte
identical to the MCP tool (`tools.py`). Covered by `test_conn_none_book_still_attaches_no_crash`, which
also asserts `kb.hedge_profile` is NEVER called when `conn is None`.

## Plan-check concerns folded in

- **C1 (labeling honesty):** the outcome is a TARGET-LEG exposure read, NOT whole-book gross. The
  long/long hedge peer is real deployed capital but carries no `size_pct`/move this phase, so it is
  correctly excluded (fabricating peer notional would violate no-fabrication). Labeled on the field
  comment, the adapter docstring, and the attach-pass comment. Upgrade path documented: needs BOTH a
  peer move estimate AND a peer `size_pct`, then `pos["hedge"]` + `assumptions[peer]` add ADDITIVELY.
- **C2 (duplicate ticker):** if the same ticker appears in two promoted legs (catalyst + statistical
  sleeve on the same name), the adapter AGGREGATES their `size_pct` (sum) into one position — otherwise
  `build_portfolio`'s `weights_by_ticker` dict silently keeps only the last leg and under-counts
  exposure. The richer `exit_plan`-derived moves win when a duplicate carries them. Covered by
  `test_adapter_aggregates_duplicate_ticker`.
- **C3 (money-path guard):** the outcome is a READ — the attach mutates only `portfolio_context`, never
  `trade`. `test_attach_never_resizes_promoted_legs` runs `run_portfolio` with attach OFF vs ON and
  asserts promoted `size_pct` are byte-for-byte identical.

## Backward-compat proof

Additive-only. The two existing money-path suites stay GREEN with ZERO edits (the conn-guard is what
makes that true):
- `tests/test_desk_portfolio.py` (18 tests) — `select_book` selection/sizing byte-for-byte unchanged.
- `tests/test_weekly_runner.py` (16 tests) — weekly cadence + null-conn `run_portfolio` calls unchanged.

Full suite: **1658 passed, 1 pre-existing xfail** (unrelated deferred latency-sweep wiring).
Targeted: `test_desk_book_risk + test_desk_portfolio + test_weekly_runner + test_desk_orchestrator` =
57 passed. `-k "desk or portfolio or weekly or contract"` = 410 passed.

## Worked example (a promoted 2-leg book -> attached PortfolioOutcome)

Book: one catalyst leg `ACME` (exit_plan ev_flip up 0.30 / down 0.20 / p 0.6, size 0.03) + one
statistical leg `BOUNCE` (expected_return_pct 0.03, size 0.02).

Adapter output:
```
positions:   [{ticker: ACME, side: long, size_pct: 0.03}, {ticker: BOUNCE, side: long, size_pct: 0.02}]
assumptions: {ACME: {expected_move: 0.30, down_move: 0.20, p_positive: 0.6},
              BOUNCE: {expected_move: 0.03},           # engine defaults down_move/p
              sector_shock: -0.10}                     # BOOK_RISK_PARAMS default
```

`build_portfolio(...)` -> attached `portfolio_outcome`:
```
gross_exposure: 0.05    net_exposure: 0.05     concentration: 0.0013
expected_return: 0.0096  portfolio_vol: 0.00902
scenarios worst/expected/best: -0.0066 / 0.0030 / 0.0096
risk[risk_of_ruin]: 0.0   # modest book, tiny worst-case -> ~0 portfolio ruin over 52 weeks
```

A high-loss book (big `down_move`, low `p_positive`) instead surfaces a non-None `risk_of_ruin > 0`
(`test_high_ruin_book_surfaces_risk_of_ruin`).

## Deviations from plan

- The shared test builders were inlined into `tests/test_desk_book_risk.py` rather than a separate
  `_book_risk_fixtures` module: `tests/` has no `__init__.py`, so relative imports don't resolve. No
  behavior impact. (Rule 3 — blocking-issue fix.)
- No other deviations. The conn-guard, C1/C2/C3 folds were mandated by the prompt and implemented as
  specified.

## Known Stubs

None. The TARGET-LEG scope is a documented, intentional phase boundary (not a stub) with a stated
upgrade path; peer notional is deliberately excluded to avoid fabrication.

## Self-Check: PASSED
- `src/catalyst_trader/desk/portfolio.py::book_to_portfolio_inputs` — FOUND
- `src/catalyst_trader/desk/orchestrator.py::attach_book_risk` pass — FOUND
- `src/catalyst_trader/contracts/__init__.py::portfolio_outcome` — FOUND
- `tests/test_desk_book_risk.py` — FOUND (18 tests)
- Commits e69d4bc, 6268558, 0c0fa6c — FOUND
