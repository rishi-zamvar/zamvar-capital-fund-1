---
phase: 05-trade-builder-honest-hedge-ruin-avoidant-sizing-workflow-1b-2
plan: 04
subsystem: risk-desk / survival-sizing + honest-hedge + committee
tags: [sizing, risk-of-ruin, hedge, cointegration, conditional-payoff, committee, blocker-1]
requires:
  - quant.risk_of_ruin (no-return-target survival DP, Phase 3)
  - quant.conditional_payoff + quant.cointegration (Phase 3 pairs)
  - kb.hedge_peers + store.tradeable_catalysts (Phase 1/2 — candidate peers + catalyst-clean)
  - contracts.Hedge / RiskAssessment (Plan 05-01 — Hedge object carried on assessment)
  - desk.runtime.run_structured (the one SDK seam) + desk.debate fan-out pattern
provides:
  - desk.risk.size_for_survival(p_loss, gap, ruin_cap, per_event_cap, n_trades) -> ToolResult
  - desk.risk.validate_hedge(conn, embed, target, catalyst, entry, exit_by_date, analog_gaps, prices) -> Hedge | None
  - desk.risk.assess(...) -> RiskAssessment  # 3-way committee, deterministic money numbers
  - desk.risk.CommitteeView  # argued-inputs schema (p_loss/gap/hedge opinion, never the size)
affects:
  - 05-05 trade builder (calls assess; supplies analog_gaps + prices)
  - 05-07 portfolio reconciliation (reads RiskAssessment.hedge OBJECT onto the promoted proposal — BLOCKER-1)
tech-stack:
  added: []
  patterns:
    - "sizing has NO return-target param (structural anti-1%-coupling, mirrors risk_of_ruin)"
    - "agents interpret, deterministic tools own every money number (overwrite the LLM synthesis)"
    - "honest hedge = -1 inverse peer that passes conditional_payoff + cointegration + catalyst-clean, else None"
    - "flat async fan-out over run_structured, mirrors debate.py (no base classes/config objects)"
key-files:
  created:
    - src/catalyst_trader/desk/risk.py
    - tests/test_desk_risk.py
    - tests/fixtures/agent_responses/risk_aggressive.json
    - tests/fixtures/agent_responses/risk_conservative.json
    - tests/fixtures/agent_responses/risk_neutral.json
    - tests/fixtures/agent_responses/risk_synthesis.json
  modified: []
decisions:
  - "size_for_survival sweeps size DOWNWARD from per_event_cap; risk_of_ruin is monotonic in size so the first size clearing the cap from the top is the largest survivable one — no optimizer needed."
  - "The tiny-FLOOR fallback is defensive: with a realistic 52-trade horizon a ruinous streak cannot fit at small sizes (ruin -> 0), so the floor branch is unreachable via normal params and is unit-tested by stubbing risk_of_ruin (a real long-horizon DP test cost 90s — rejected)."
  - "assess takes analog_gaps + prices as keyword args (the caller supplies them) rather than pulling inside — keeps the function pure/testable; 05-05 threads them from analog_query + price history."
  - "Deterministic size/matrix/worst/hedge OVERWRITE the opus synthesis via model_copy(update=...) so the LLM can never inject a size OR a hedge (Pitfall B)."
  - "validate_hedge is called EXACTLY ONCE in assess and its single result threads onto BOTH hedge (object) AND hedge_valid (bool) — the BLOCKER-1 fix, proven by a spy/counter test."
metrics:
  duration: 18min
  tasks: 3
  files: 6
  tests_added: 21
  completed: 2026-08-15
---

# Phase 5 Plan 04: Survival Sizing + Honest Hedge + Risk Committee Summary

`desk/risk.py`: the deterministic survival-sizing engine (`size_for_survival`, no return-target param),
the honest per-catalyst inverse-hedge validator (`validate_hedge` — a peer counts only if it is a `-1`
inverse peer that passes conditional_payoff + cointegration + catalyst-clean THIS catalyst, else `None`),
and the 3-way (aggressive/conservative/neutral) Risk Committee (`assess`) that mirrors `debate.py`'s flat
fan-out over the one `run_structured` seam — the committee interprets while the quant tools own every
money number, and the validated Hedge OBJECT is carried on the `RiskAssessment` for 05-07 (BLOCKER-1).

## What Was Built

- **`size_for_survival`** — largest `size_pct` whose `risk_of_ruin(p_loss, size, gap).value <= ruin_cap`,
  clamped to `per_event_cap`. Sweeps downward in 5bp `STEP`s from the cap (monotonicity → first clear is
  the largest). Returns a `ToolResult` carrying the `risk_of_ruin` snapshot as its audit citation. NO
  target/return/weekly parameter — enforced by a signature-introspection test. Tiny `FLOOR` fallback when
  nothing clears (size-tiny / exit downstream).
- **`validate_hedge`** — the crux. Filters `hedge_peers` to `payoff_direction == -1` (a `+1` co-move peer
  is never an idiosyncratic hedge). For the top candidate, three gates ALL must pass: (1) payoff — the
  un-netted worst cell of `conditional_payoff` from the analog gaps is materially better than holding the
  target alone AND the peer has real downside (`peer_down < 0`); (2) `cointegration.detail["cointegrated"]`
  True (necessary-not-sufficient); (3) catalyst-clean — the peer has no own tradeable catalyst in the
  `[entry, exit]` hold window. All pass → a validated `equity_peer` idiosyncratic `Hedge`; anything else →
  `None`. Pure/deterministic (no LLM).
- **`assess` + `CommitteeView`** — three isolated `run_structured` sonnet calls (each argues p_loss / gap /
  hedge validity with citations, never the size) then one opus synthesis for the narrative. The money +
  hedge fields (`recommended_size_pct`, `conditional_payoff_matrix`, `conditional_worst`, `hedge`,
  `hedge_valid`, `ruin_at_size`) are computed deterministically and OVERWRITE the synthesis via
  `model_copy(update=...)`. `validate_hedge` is called once; its result threads onto both `hedge` and
  `hedge_valid`.

## Reuse (no rebuild)

Mirrors `debate.py`'s fan-out shape verbatim (flat async over `run_structured`, monkeypatch seam, dispatch
on schema/role in tests). Reuses `risk_of_ruin`, `conditional_payoff`, `cointegration` (real, deterministic
in tests), `kb.hedge_peers`, `store.tradeable_catalysts`, and the `contracts.Hedge` / `RiskAssessment`
boundary from 05-01. No new base classes, no config objects, no new schema/migration.

## Deviations from Plan

**1. [Rule 3 - Blocking/correctness] `assess` takes `analog_gaps` + `prices` as keyword args.**
- **Found during:** Task 3.
- **Issue:** The plan's `assess(...)` signature omitted where the analog gaps + price series come from,
  but `validate_hedge` and `conditional_payoff` both need them. Pulling them inside `assess` would couple it
  to `analog_query` + a price provider that don't belong at this layer.
- **Fix:** Added `analog_gaps` and `prices` as required keyword args (plus optional `entry`/`exit_by_date`,
  defaulted from the catalyst/proposal) — the caller (05-05) supplies them, keeping `assess` pure and
  offline-testable. Acceptance grep (`async def assess(`) still passes.
- **Files:** src/catalyst_trader/desk/risk.py · **Commit:** bbb30fe

**2. [Rule 1 - Test correctness] Floor-fallback test stubs `risk_of_ruin` instead of a long-horizon DP.**
- **Found during:** Task 1.
- **Issue:** The plan assumed a small size could breach the ruin cap; with the real 52-trade DP a ruinous
  streak cannot fit at small sizes, so ruin → 0 and the floor is unreachable. The only real-quant path that
  reaches it (n_trades=100k) made a single test take 90s.
- **Fix:** Unit-test the fallback branch by monkeypatching `risk.risk_of_ruin` to always breach — fast and
  precise. Documented that the FLOOR is defensive/unreachable with realistic params.
- **Files:** tests/test_desk_risk.py · **Commit:** 5be912d

## Verification

- `.venv/bin/python -m pytest tests/test_desk_risk.py -q` → 21 passed
- `.venv/bin/python -m pytest -q` → 597 passed (576 baseline + 21 new), no regression, zero live API calls
- All acceptance greps pass: `size_for_survival` present + no return-target param; `validate_hedge` +
  `conditional_payoff` + `cointegration` present; `async def assess` + `run_structured` present;
  `risk_synthesis.json` fixture exists.
- Structural invariants enforced: #1 no return-target (introspection test), #2 fake idiosyncratic hedge
  unrepresentable (contract test), BLOCKER-1 single-validate_hedge-call + Hedge object carried (spy test).
- The 2 warnings are pre-existing statsmodels ComplexWarnings in test_pairs.py (out of scope).

## Requirements progressed

PORT-03 (survival sizing), HEDGE-01 (inverse-only), HEDGE-02 (per-catalyst conditional payoff),
HEDGE-03 (catalyst-clean), HEDGE-04 (honest None fallback).

## Known Stubs

None. The committee/synthesis fixtures are test doubles for the LLM seam (offline testing), not production
stubs. Every money number is a real deterministic quant output.

## Self-Check: PASSED
- FOUND: src/catalyst_trader/desk/risk.py (size_for_survival, validate_hedge, assess, CommitteeView)
- FOUND: tests/test_desk_risk.py (21 tests) + 4 risk_*.json fixtures
- FOUND commits: fd15fb2, 5be912d, 5154f6f, 118c7b6, 11a896d, bbb30fe
