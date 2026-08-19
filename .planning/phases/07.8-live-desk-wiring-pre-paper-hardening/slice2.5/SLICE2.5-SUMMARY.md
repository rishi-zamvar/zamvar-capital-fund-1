---
phase: 07.8-live-desk-wiring-pre-paper-hardening
plan: slice2.5
subsystem: desk / providers (DD money-dim sourcing)
tags: [diligence, edgar, finra, form4, financials, ownership, source-or-omit]
requires:
  - edgar.fetch / edgar.fundamentals (6.10)
  - finra.fetch + registry.recent_si_settlement (6.10)
  - make_diligence_inputs (7.8-S2)
  - run_diligence money-dim contracts (Phase 6)
provides:
  - edgar.fundamentals cash_usd + monthly_burn_usd (additive)
  - edgar.insider_net (free EDGAR Form-4 net-insider fetcher)
  - grounded financials + ownership dims in make_diligence_inputs (source-or-omit)
affects:
  - src/catalyst_trader/providers/edgar.py
  - src/catalyst_trader/desk/diligence_inputs.py
tech-stack:
  added: []          # edgartools Form-4 surface already a dep; no new packages
  patterns: [source-or-omit, whole-dict-or-omit, single-fetch-reuse, degrade-never-fabricate]
key-files:
  created: []
  modified:
    - src/catalyst_trader/providers/edgar.py
    - src/catalyst_trader/desk/diligence_inputs.py
    - tests/test_providers_edgar.py
    - tests/test_desk_diligence_inputs.py
decisions:
  - "insider signal = Form-4 net_change (shares), not net_value (net_value can be None with no price)"
  - "insider_net 0.0 (quiet tape) is a REAL grounding datum, not a miss; None only on genuine failure"
  - "ownership is whole-dict-or-omit (a partial dict KeyErrors at diligence.py:269)"
  - "short_interest_pct = short_interest / shares_outstanding (shares-out ratio, not float — documented)"
metrics:
  duration: ~1 session (Tasks 1-2; Task 3 = blocking human checkpoint, deferred to operator)
  completed: 2026-08-19
  tasks: 2 of 3 (Task 3 = human-verify checkpoint, operator-owned)
  tests-added: edgar +9, diligence_inputs +7 (2 replaced)
---

# Phase 7.8 Slice 2.5: Live Money-Dim Sourcing (financials + Form-4 ownership) Summary

Grounded the two structurally-ungrounded DD money dimensions — **financials** (cash / burn /
months-to-catalyst) and **ownership** (short-interest % / days-to-cover / net insider) — from FREE
point-in-time data (SEC EDGAR XBRL + EDGAR Form-4 + FINRA), so `run_diligence` now reaches a REAL
thesis-based GO/NO-GO instead of the Slice-2 forced data-gap NO-GO. This un-gates Slice 4 (paper).

## What Shipped

### Task 1 — Provider layer (edgar.py) · commit `f4b8516`
- **`_monthly_burn(ocf_meta) -> float | None`** extracted as the SINGLE burn derivation (`-ocf/months`
  when `ocf < 0` and the cumulative period is known), now called by BOTH `_runway_months` and
  `fundamentals` — no duplicated arithmetic.
- **`fundamentals`** additively returns `cash_usd` (the cash value) + `monthly_burn_usd` (via
  `_monthly_burn`). All existing keys (`shares_outstanding`, `cash_runway_months`, `provenance`)
  unchanged byte-for-byte. Each new key is `None` when its underlying fact is absent / not burning
  (never fabricated).
- **`insider_net(ticker, *, since, until) -> float | None`** — free EDGAR Form-4 net-insider fetcher:
  `edgar.Company(ticker).get_filings(form="4", filing_date="since:until")` → per filing
  `.obj().get_ownership_summary().net_change` (purchases − sales, shares), summed. Semantics:
  - genuinely quiet tape (no Form-4 in window) → **0.0** (a REAL datum, grounds ownership)
  - edgartools error (unknown ticker / API failure) → **None** (degrade, never raises)
  - a single unparseable filing is **skipped**, the good ones still sum; all-fail → **None**
  - SEC-UA gated via the existing `_set_identity()` (RuntimeError if unset), matching `fetch`/`fundamentals`
- Signal = `net_change` (shares), NOT `net_value` (net_value can be None when a txn carries no price).
- Window is the caller's concern (`since`/`until` args) — no magic literal inside the provider.

### Task 2 — Wire into make_diligence_inputs (diligence_inputs.py) · commit `80112fe`
- **`_INPUTS_PARAMS = {"form4_lookback_days": 90, "days_per_month": 30.4375}`** — missing-key-raises,
  no magic literals (Form-4 trailing window + months conversion).
- Three injectable sources added (production defaults are free + cache-first):
  `financials_source` → `edgar.fundamentals`; `insider_source` → `edgar.insider_net`;
  `finra_source` → resolved INSIDE the closure (see C1).
- **ONE `fundamentals` fetch reused for BOTH dims** (financials cash/burn AND ownership shares) — no
  double EDGAR hit (frugality: cache-first).
- **financials** grounds only when BOTH `cash_usd` + `monthly_burn_usd` exist →
  `{cash_usd, monthly_burn_usd, months_to_catalyst}` (months_to_catalyst from the already-computed
  `days_to_event`, not the provider); else OMIT the key + append a per-genuine-miss `degraded` flag.
- **ownership** is whole-dict-or-omit: `{short_interest_pct, days_to_cover, insider_net}` assembled ONLY
  when `si and shares and net is not None` (net==0.0 GROUNDS); a single miss OMITS the whole key +
  flags. NEVER a partial dict (which would KeyError at diligence.py:269).

## C1 / C2 Resolutions (mandatory plan-check concerns)

- **C1 — FINRA default-binding trap:** the FINRA production default references `as_of`, which is NOT in
  scope at factory level. Resolved by defaulting it INSIDE the `diligence_inputs` closure where `as_of`
  is bound:
  `finra_fetch = finra_source or (lambda tk: finra.fetch(tk, registry.recent_si_settlement(as_of)))`.
  `financials_source` + `insider_source` have no `as_of` dependency, so they default at factory level.
  A dedicated test (`test_ownershipInsiderWindow_scopedToParams`) confirms the window is
  `[as_of - form4_lookback_days, as_of]`.
- **C2 — short_interest_pct denominator:** computed as `short_interest / shares_outstanding` — a
  shares-out ratio that slightly UNDERSTATES true short-%-of-float (free float isn't free). A one-line
  `# ponytail:` note at the computation flags it as a shares-out ratio with the float-denominator
  upgrade path.

## Money-Dim Sourcing Map (now GROUNDED)

| Dim         | Source(s)                                              | Grounding rule                                           |
| ----------- | ----------------------------------------------------- | ------------------------------------------------------- |
| financials  | SEC EDGAR XBRL (`edgar.fundamentals`)                 | both cash_usd + monthly_burn_usd present → grounded      |
| ownership   | FINRA SI + EDGAR shares + EDGAR Form-4 (`insider_net`)| all three present (net==0.0 counts) → whole dict grounded|
| options     | CBOE (`options_cboe.fetch`) — Slice 2                 | live ATM pair → grounded; else honest sentinel           |
| liquidity   | CBOE underlying — Slice 2                              | grounded; None-bid → 0 (honest NO-GO), never fabricated  |
| hedge       | Slice-1 catalyst_context risk_inputs — Slice 2        | reused verbatim (no recompute)                           |

All five money dims are now honestly sourced-or-degraded. The two that Slice 2 unconditionally omitted
(financials, ownership) are the deliverable of this slice.

## Slice-2 Omit Removal (confirmed)

The Slice-2 unconditional omit is GONE: `_FINANCIALS_DEGRADE` + `_OWNERSHIP_DEGRADE` constants deleted,
and the unconditional `degraded = [_FINANCIALS_DEGRADE, _OWNERSHIP_DEGRADE]` replaced with a
`degraded: list[str] = []` built up ONLY from genuine misses (empty when both dims ground). The
Slice-2 tests `test_financialsAlwaysOmitted_B1` / `test_ownershipAlwaysOmitted_C4` were replaced with
source-or-omit coverage.

## Backward-Compat Proof

- `edgar.fundamentals` additions are purely additive; existing callers use `.get()`
  (registry.py:97, discover.py:806/883) so new keys are safe.
- Full offline suite: **1682 passed, 1 pre-existing xfail** (`test_off_map_escalates_to_reasoning_agent`,
  unrelated deferred wiring). No regressions.
- Task-1 verify: `tests/test_providers_edgar.py` → 20 passed.
- Task-2 verify: `tests/test_desk_diligence_inputs.py tests/test_desk_diligence.py
  tests/test_live_desk_decision.py tests/test_providers_finra.py` → 65 passed.
- All code-task tests are fully OFFLINE (fake edgartools Form-4/facts + fake FINRA + fake fundamentals
  injected; zero live network, zero LLM).

## Task 3 — Combined live checkpoint (OPERATOR STEP — NOT run by executor)

This is the blocking `checkpoint:human-verify` (the deferred Slice-2 live check + the Slice-2.5 proof
in one run). Run it yourself:

```
.venv/bin/python -m scripts.run_one_catalyst CAPR --live --with-dd
```
(equivalently: `.venv/bin/python scripts/run_one_catalyst.py CAPR --live --with-dd --db catalyst.db`)

**Suggested ticker — CAPR (Capricor):** a positive-leaning near-term catalyst — PDUFA on **2026-08-22**
(T-3 from the 2026-08-19 as_of, matching the desk's 1–2-day-out window), **204 cached daily bars** in
`catalyst.db`, and confirmed SEC/Form-4 coverage (CAPR was in the 6.11 tradeable-PDUFA list
IMNM/CAPR/BBIO×2/DYN/PRAX, so it has real 8-K + XBRL + insider filings — not a shell).

**Alternative (more liquid, if CAPR's insider tape is quiet):** **ARWR (Arrowhead)** — trial_readout
2026-09-30, 249 cached bars, large mid-cap with dense Form-4 + robust XBRL.

**What to confirm in the printed block:**
1. A `DiligenceDossier` prints a MEANINGFUL go/no_go resting on the DIMENSION THESIS (financials +
   ownership per-dimension findings populated + cited), NOT on an ungrounded-money data gap.
2. The `degraded` lines do NOT include the old financials/ownership "ungrounded, forces NO-GO" flags
   for a name whose facts genuinely exist (a legitimately-missing source may still flag — that is honest).
3. An `MDDecision` (enter/pass/escalate) + reconciliation round log print.
4. A quiet insider tape → `insider_net ≈ 0` (a real datum) and ownership STILL grounds — verdict turns
   on thesis, not "no data".

Resume signal: type "approved" (DD reached a thesis-based GO/NO-GO on grounded money dims) or describe
what degraded/failed.

## Test Counts

- edgar: +9 tests (cash/burn exposure ×3, insider_net ×6). Suite: 20 passed.
- diligence_inputs: +7 net (financials sourced/omit ×3, ownership sourced/quiet/omit/window ×4; the 2
  Slice-2 "always omitted" tests replaced). Task-2 suite: 65 passed.
- Full offline suite: 1682 passed, 1 pre-existing xfail.

## Deviations from Plan

None of substance. One minor structural simplification in `insider_net`: the plan sketched
`if not filings: return 0.0` AFTER the parse loop; implemented as an early return BEFORE the loop
(functionally identical for the empty-window case, slightly clearer). All plan semantics preserved.

## Self-Check: PASSED

- FOUND: src/catalyst_trader/providers/edgar.py (def insider_net)
- FOUND: src/catalyst_trader/desk/diligence_inputs.py (def make_diligence_inputs)
- FOUND: commits f4b8516 (Task 1), 80112fe (Task 2)
