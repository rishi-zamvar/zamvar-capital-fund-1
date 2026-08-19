# Football-field options-IV backfill — coverage (Task 4 live pull)

**Date:** 2026-08-19 · cache: `options_snapshot` (source=`rh_hist`)

## Result
- **85 clean historical straddles cached** (of 152 candidate universe pdufa/readout events).
- Implied-move (straddle/underlying) median **18.5%**, range **3.6%–120%** — a sane pre-catalyst distribution.
- Remaining ~67 events **abstain honestly**: no listed options (~20+ tickers), no real T-1 bar (interpolated-only), or a sentinel leg (one side never traded). The football field runs on its other methods for those; the `retrieval_confidence`/agreement flag covers the gap.

## Data-quality discipline
- All 4 backfill agents converged on a key finding: the worklist `approx_underlying` was often the POST-event (or split-adjusted) price → wrong ATM strike. Fixed by anchoring every straddle on the **free (non-RH) T-1 daily close**, then picking the strike — zero extra RH cost.
- A final deterministic audit purged 10 rows with a sentinel (0.01) leg or a leg exceeding the underlying. Nothing fabricated; only genuine two-legged straddles remain.

## API usage (one-time, read-only)
- ~403 RH calls across the 4 chunks — higher than the ~200 floor, due to (a) an accidental fork double-running chunk 0 (~80 extra, remediated) and (b) strike-guessing re-pulls before the "free-T-1-first, no-strike-discovery-first" protocol was adopted mid-run. Cache-first + resumable: a re-run skips all 85 with 0 calls.
- LESSON for any future pull: free T-1 underlying FIRST → one no-strike instruments call/group → one batched historicals/event. That is the ~1+1/event floor.

## Salvageable later (optional)
The events abstained purely for wrong-strike/approx-underlying in early passes are already re-pulled/clean; the remaining abstains are genuine (no options or no liquidity). No further pull is high-value.
