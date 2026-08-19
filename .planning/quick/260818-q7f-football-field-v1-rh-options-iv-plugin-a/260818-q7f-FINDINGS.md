# Quick 260818-q7f — Football Field v1: Live Results

**Date:** 2026-08-19 · **Branch:** feat/backtest-readiness · Closes FF-05.

## What shipped (code, Tasks 1-3; 1504 tests pass)
- `migrations/012_options_snapshot.sql` — cache table (ticker,event_date,underlying_price,call_mid,put_mid,iv,days_to_event,source,fetched_at), provisioned via db.migrate().
- `desk/options_adapter.py` — `implied_move_from_provider` (wraps the existing quant.options.implied_move; straddle or IV), `options_snapshot_provider` (headless cache reader), `write_options_snapshot`. **Abstains (None) when no data — never fabricates.**
- `desk/builder.py` — assembles the 5-method football field (analog + rNPV + analyst-target + sum-of-parts + options-IV) via the existing `expected_move_field`, behind injectable `options_provider` + `assumptions_provider` seams; convergence feeds the existing `catalyst_move_estimate` implied_move prior. **Backward-compat by construction:** no providers → 1 method (<min_methods=2) → no field → implied_move=None → sizing/hold/SL-TP byte-for-byte unchanged.
- `desk/diligence.py` + `desk/md.py` — DD now emits an independent `dd_expected_move`; `cross_check` compares Builder-field vs DD (threaded `move_discrepancy_tol` from load_params()['field']); the existing `reconcile` loop routes the discrepancy. (DD had no structured number before — genuinely new.)
- Reuses expected_move_field/implied_move/rnpv/analyst_pt_move/pipeline_value/cross_check/reconcile verbatim; all weights/thresholds from load_params()['field'] — no new magic numbers.

## Options-IV sourcing = Robinhood (no Polygon, no Kaggle)
Verified RH `get_option_quotes` returns `implied_volatility` + greeks + bid/ask/mark directly (IONS $60 call IV=0.475). So implied move is computed from RH two ways — IV (`iv×√(days/365)`) or ATM straddle (`(call+put mark)/underlying`). `get_option_historicals` accepts `state='expired'` → historical straddle reconstruction for past events. Polygon key in .env is UNUSED; free Kaggle options sets are SPY/index-only (useless for per-biotech).

## Live end-to-end validation (Task 4, partial)
- **Live path:** IONS 2026-08-21 ATM straddle from RH (call mark 0.80 + put mark 1.35, underlying 59.59) → adapter → **implied move 3.6%** (straddle method). Written to `options_snapshot`, read back via provider. ✓
- **Abstain:** missing ticker → None (field runs on survivors). ✓
- **Field convergence:** 4 real methods (analog 28% / implied 3.6% / rNPV 22% / analyst 18%) → `expected_move_field` → **convergence 0.22, range 0.036–0.28, dispersion 0.50, agreement "wide", n_methods 4.** The "wide" flag correctly surfaces that implied (3.6%) and analog (28%) disagree — the desk sees the divergence, not a false point estimate. ✓

## Remaining (deferred, graceful)
- **Full historical options backfill:** ~70 pdufa/readout events × RH expired-contract ATM straddle as-of T-1 → `options_snapshot`. A pure data-population batch (~hundreds of RH calls); options-IV **abstains** per-event until populated, so the field already runs on the other 4 methods. Live/paper path is fully wired now.
- **Live-agent assumption estimation** (rNPV PoS/peak-sales, analyst PTs, SOP) per opportunity, pre-event-constrained in backtest — the injectable `assumptions_provider` seam is in place; the agent fills it during the desk run / paper month.

## Status
The football field is LIVE: the desk now anchors magnitude on the convergence of up to 5 independent methods with an explicit agreement/dispersion signal + a Builder-vs-DD discrepancy loopback — replacing the analog-only estimate. Options-IV is free (RH). Full historical backfill + live-assumption wiring are the remaining population steps; validation is the forward paper month.
