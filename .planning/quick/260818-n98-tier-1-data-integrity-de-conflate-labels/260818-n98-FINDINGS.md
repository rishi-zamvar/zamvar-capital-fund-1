# Quick 260818-n98 — Tier-1 Data-Integrity: Live Results

**Date:** 2026-08-19 · **Branch:** feat/backtest-readiness · DB backed up pre-run.

## FIX A — de-conflate the outcome label ✅
Split every outcome node into two honest fields (legacy `label` retained, additive/non-breaking).
- **`market_reaction`** (deterministic from signed move): 100% coverage. Dist — surged 61, popped 94, flat 123, faded 112, crashed 78, unknown 2.
- **`clinical_regulatory_outcome`** (real result): pass-1 deterministic filled 181; pass-2 LLM classifier (4 agents over 318 nodes = all blanks + all 29 PDUFAs re-verified) filled the rest. 100% coverage. Dist — hit 120, miss 121, mixed 68, inline 70, beat 62, approved 19, crl 8, delayed 2.
- **De-circularization worked:** CRLs 16→**8**, approvals 13→**19**. ~10 real approvals that had sold off were rescued from a false "crl": **CRSP=CASGEVY, MCRB=VOWST, CTXR=LYMPHIR, LPCN=TLANDO, AUTL=AUCATZYL, ABEO=ZEVASKYN, AGIO=Pyrukynd, ETON=Khindivi, BCRX-ORLADEYO-peds, VNDA-tradipitant**; + 2 crl→delayed (BCRX ext, ALDX Dec-2025 extension). ALDX reproxalap correctly KEPT as a real rejection despite +6.7%.
- **New first-class signal: 40 "good outcome / negative reaction" cases** (approved|hit|beat + faded|crashed) — the sell-the-news population, now directly queryable instead of hidden inside a move-anchored label.

## FIX B — verify move data ✅ (hypothesis falsified, corpus clean)
Recomputed the signed T-1→T+2 move from daily bars (same source the moves were built from; zero paid API).
- **All 4 flagged suspects reproduce EXACTLY** (VERA -71%, ZBIO -52%, LYRA -32%, QURE -42%). Sample sweep of 91 (incl. all 62 big movers): **0 divergences.**
- Conclusion: the moves are correct — the "positive event, stock down" cases are **real market reactions**, not windowing artifacts. Nothing to correct. This is why FIX A (the label split) was the right fix, not a move rewrite. Artifact: `move-divergences.json`.

## FIX C — clean catalyst_source + delisted rescue ✅
- Pulled SEC `company_tickers.json` (one free call) → ticker→CIK for 957 catalysts; **pruned 324 cross-filer (wrong-CIK) contaminated source rows.** 35 delisted tickers left untouched (no CIK to verify against — the naked ones). Artifact: `source-prune.json`.
- `scripts/pb_agent.py` gained `--own_cik` to extract delisted/CIK-unresolvable tickers.

## Verification
- Code: 1467 tests pass (executor), all code-task verifies in-memory. Live DB (gitignored) updated in place; backups retained.
- Spot-check: CRSP clinical=approved / market_reaction=crashed / legacy label=crl — correct.

## What this hardened
The corpus everything reasons off is now honest: outcomes reflect what actually happened, reactions reflect the tape, the moves are verified sound, and provenance is de-contaminated. This is the floor Tier 2 (retrieval v2 + football-field wiring) will build on.
