---
phase: quick-260818-r3y
plan: 01
subsystem: desk / football-field valuation methods (FF-05)
tags: [assumptions, valuation, no-look-ahead, cache, backtest-readiness]
requires:
  - desk/builder.py assumptions_provider seam (lines 183-195, already consumed)
  - quant.valuation rnpv / pipeline_value / analyst_pt_move (reused, not duplicated)
  - kb._structural_filter / kb._with_outcome (as_of-gated prior-readout reuse)
  - serving.asof (as_of-gated price/card reads)
provides:
  - migration 013 assumptions_snapshot cache table
  - desk.assumptions_adapter.assumptions_snapshot_provider (headless-readable, {} abstain)
  - desk.assumptions_adapter.write_assumptions_snapshot (reject-not-fabricate validating write)
  - desk.assumptions_adapter.assumptions_context (as_of-gated pre-event pack for the Task-4 agent)
affects:
  - desk/builder.py now DEFAULTS assumptions_provider to the cache reader (byte-for-byte on no row)
tech-stack:
  added: []
  patterns: [thin-cache-adapter-mirror-of-options_snapshot, provider-abstains-empty-dict, no-look-ahead-gate]
key-files:
  created:
    - src/catalyst_trader/migrations/013_assumptions_snapshot.sql
    - src/catalyst_trader/desk/assumptions_adapter.py
    - tests/test_assumptions_adapter.py
  modified:
    - src/catalyst_trader/desk/builder.py
    - tests/test_desk_builder.py
decisions:
  - "ABSTAIN is {} (never None) so the builder can membership-test `\"rnpv\" in a` unchanged."
  - "No-look-ahead is a two-sided provider/packer discipline: provider gates stored as_of > requested as_of; packer gates prior readouts via kb._structural_filter(as_of) + event_date < as_of and price/card via serving.asof(cutoff=as_of)."
  - "Validation is SHAPE-only (PoS/prob_reach ∈ [0,1], shares_out > 0, non-empty cashflows/segments/price_targets, ≥1 method) — rnpv math stays in quant.valuation."
metrics:
  duration: ~15min
  completed: 2026-08-18
---

# Phase quick-260818-r3y Plan 01: Live Assumption Estimation (pre-event-constrained) Summary

Mirrored the `options_snapshot` pattern for VALUATION ASSUMPTIONS: an additive migration-013 cache,
a thin abstaining provider + reject-not-fabricate validating write helper, a deterministic
as_of-gated pre-event context packer, and a one-line builder default — so the football field gets
its rnpv / sum-of-parts / analyst-PT methods from an agent-fillable cache that is readable HEADLESS
(agent estimation is unavailable in the backtest, same constraint as options_snapshot). The desk
seam was already built; this plan only PROVIDES the cache/provider/packer that populate it.

## What shipped (Tasks 1-3)

- **Migration 013 `assumptions_snapshot`** — additive `CREATE TABLE` only (PK `ticker,event_date`),
  provisioned by `db.migrate()`. `assumptions_json` holds the rnpv/sop/analyst_pt dict; `as_of` is
  the knowable-as-of stamp.
- **`assumptions_snapshot_provider(conn)`** — `(ticker, catalyst, as_of) -> dict`. Abstains `{}` on
  an absent row AND on a stored `as_of` AFTER the requested as_of (no-look-ahead). Live (`None`) as_of
  is ungated.
- **`write_assumptions_snapshot(...)`** — validates FIRST (raises `ValueError` on bad shapes; nothing
  lands), then `INSERT OR REPLACE` + commit.
- **`assumptions_context(conn, ticker, catalyst, as_of)`** — deterministic pre-event pack: identity
  (drug/indication/modality/stage/disease_area/mechanism_class/catalyst_type; kb-node fallback),
  `prior_readouts` (this ticker's PAST outcomes, knowable ≤ as_of, event_date < as_of, this
  catalyst's own outcome excluded), `cash_runway_months`/`float`/`shares_outstanding` and
  `current_price` via `serving.asof(as_of)` (None-safe).
- **Builder default** — `assumptions_provider=None -> assumptions_snapshot_provider(conn)`; the `{}`
  abstain keeps no-row builds byte-for-byte.

**Tests:** 28 in `test_assumptions_adapter.py` (Tasks 1+2) + 3 e2e in `test_desk_builder.py` (Task 3).
Verify suites green: builder / desk_portfolio / portfolio / weekly_runner (78) and a broader
adapter/field/serving/estimate-gate sweep (106).

## Commits

- `c1e1682` feat(quick-260818-r3y): assumptions_snapshot cache + provider + pre-event context packer (FF-05)
- `fc7b220` feat(quick-260818-r3y): default builder assumptions_provider to assumptions_snapshot_provider

## Deviations from Plan

None — plan executed as written. (Task-3 e2e tests needed analogs stamped with `knowable_asof` so
they survive the builder's as_of-gated analog recall when a decision `as_of` is threaded; added a
local `_seed_knowable_analog` helper. This is a test-fixture detail, not a code change.)

## Self-Check: PASSED

- Files: `migrations/013_assumptions_snapshot.sql`, `desk/assumptions_adapter.py`,
  `tests/test_assumptions_adapter.py`, `desk/builder.py`, `tests/test_desk_builder.py` — all present.
- Commits `c1e1682` and `fc7b220` present on `feat/backtest-readiness`.

---

## Task 4 — LIVE AGENT ESTIMATION PASS (checkpoint:human-action, non-blocking) — LEFT FOR THE ORCHESTRATOR

The cache + provider + packer are shipped and the builder reads them. What remains is POPULATING the
cache with live, pre-event-constrained agent estimates. This pass is main-dir + orchestrator-run +
agent-driven (agent estimation is NOT available in the headless backtest — same as the
`options_snapshot` backfill). **Do NOT run it inside the executor; it touches the live `catalyst.db`.**

### Procedure (per tradeable pdufa / trial_readout event, main dir vs `catalyst.db`)

1. **Assemble the pre-event pack** (T-1 = one trading day before `event_date` — the decision as_of):
   ```python
   from catalyst_trader.desk.assumptions_adapter import assumptions_context, write_assumptions_snapshot
   pack = assumptions_context(conn, ticker, catalyst, as_of=T_minus_1)
   ```

2. **Hand the pack to a Claude agent with THIS exact prompt spec:**

   ```
   SYSTEM / CONSTRAINT (hard): You are valuing {ticker} AS OF {as_of}. You may use ONLY the
   pre-event facts in the pack below plus your general domain knowledge. You do NOT know the
   catalyst outcome — reason as-of {as_of} and IGNORE any hindsight of what happened. If the pack
   lacks enough pre-event basis to estimate a method, OMIT that method (abstain) — never invent
   cashflows, PoS, shares, or price targets.

   PRE-EVENT PACK: {assumptions_context(...) json}

   TASK: Estimate the valuation methods you can defensibly support and return EXACTLY this schema
   (omit any method you cannot ground):
   {
     "rnpv":       {"cashflows": [[year:int, cashflow_usd:float, cumulative_pos:0..1], ...],
                    "discount_rate": float, "costs": [[year,cost,prob_reach:0..1],...] | null,
                    "shares_out": >0},
     "sop":        {"segments": [{"cashflows":[...], "discount_rate":float, "costs":[...]|null}, ...],
                    "shares_out": >0},
     "analyst_pt": {"price_targets": [float, ...]}
   }
   cumulative_pos and prob_reach MUST be in [0,1]; shares_out MUST be > 0; cashflows non-empty.
   ```

3. **Validate + persist** (the write REJECTS a bad shape — Task-1 validation — so a malformed
   estimate never lands):
   ```python
   write_assumptions_snapshot(conn, ticker, event_date, estimate, as_of=T_minus_1, source="agent")
   ```
   Events without enough pre-event info ABSTAIN (no row written) — **DOCUMENT the abstain count**.

### Guardrails / notes for the pass

- **Pre-event constraint is HARD.** The agent reasons as-of `as_of`; the packer already fed it only
  as_of-gated facts. Persist with `as_of=T_minus_1` so the provider's no-look-ahead gate holds when a
  backtest later reads the row at any decision as_of ≥ T-1 (and abstains for any as_of < T-1).
- **Schema must match the validating write** exactly: `cumulative_pos` is the 3rd rnpv-cashflow
  element (PoS ∈ [0,1]); `costs` tuples are `(year, cost, prob_reach)` with `prob_reach ∈ [0,1]`;
  `shares_out > 0`; every list non-empty; at least one of `{rnpv, sop, analyst_pt}` present.
- **API frugality (CLAUDE.md):** cache-first — make no external call the pack didn't already carry.
- **Spot-check afterwards:** a seeded event should make the live football field converge on more
  methods (analog + rnpv/sop/analyst_pt) in a real build.

### Resume signal

Type **"estimation pass complete"** with the counts (events estimated / abstained), or describe issues.
