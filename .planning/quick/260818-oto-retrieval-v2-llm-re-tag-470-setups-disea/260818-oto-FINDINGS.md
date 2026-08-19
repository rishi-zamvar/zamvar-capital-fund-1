# Quick 260818-oto — Retrieval v2: Live Results

**Date:** 2026-08-19 · **Branch:** feat/backtest-readiness · DB backed up pre-run.

## What shipped (code, Tasks 1-3)
- `data/setup_taxonomy_v2.json` — 18 setups (single-asset split 3 ways) + 20 disease_areas + 19 mechanism_classes + rubric (v1 file untouched).
- `playbook.store.stamp_axes` — idempotent UPDATE writer for the 3 axes on the catalyst node (mirrors backfill_outcome_fields; content_sha won't re-fire).
- `kb.analog_query_v2` + `kb._rarity_weights` — all-inclusive UNION recall (never hard-excludes a shared-axis candidate) + rarity-weighted (IDF) multi-axis rerank + `matched_axes` per analog + `retrieval_confidence` (ok/thin). v1 `analog_query` byte-for-byte unchanged.
- `desk/builder.py` rewired to v2 (uses the catalyst's own disease_area/mechanism_class/setups, ticker dropped, confidence surfaced into the narrative).
- `scripts/retrieval_stress.py --v2`. Full suite **1484 passed** incl. the no-look-ahead leak-gate.

## Live re-tag (Task 4)
- 5-agent LLM wave re-tagged all 470 nodes → setups[] + disease_area + mechanism_class. **0 None on all three axes.** Avg 1.89 setups/node.
- The over-broad `single-asset-microcap-binary` (was 237/470) is **gone**, split into pivotal-company-defining-binary (93) / early-mid-stage-single-asset-signal (70) / single-asset-going-concern-binary (23) — all <25%.
- 20 disease_areas, 19 mechanism_classes populated.

## Stress test — v1 → v2 (fundamental-desk POV, same 5 held-out cids)

| Query | v1 | v2 | Δ |
|---|---|---|---|
| DNLI (earnings, rare-genetic/recomb-protein) | STRONG | STRONG | held (deepened — SYRE now a true same-biology comp) |
| INSM (pdufa, respiratory/sm-enzyme, first-in-class) | OK | **STRONG** | ↑ |
| GOSS (earnings, cardiovascular) | OK | **STRONG** | ↑ (gold triple: BBIO CV+sm-other+no-new-info) |
| SRRK (readout, neuromuscular/mAb) | WEAK | **OK** | ↑ (mechanism+setup cohort; correctly telegraphs hit→surge) |
| VERA (readout, nephrology/APRIL-BAFF) | WEAK | **OK (thin)** | ↑ (6 real nephrology peers vs COPD/ovarian before) |

Harness metric (6 cids): mean matched-axes/analog **3.5** (v2) — multi-axis, vs v1 setup-only.

**Verdict: v2 clearly improved precedent quality. 0 regressions, 2 OK→STRONG, both WEAK cases lifted; both flips are real analyst-usable precedent, not cosmetic.** The normalized disease_area + mechanism_class axes surface true peer classes where the corpus has them; the `thin` flag honestly fires where it doesn't (VERA has no APRIL/BAFF twin in the corpus).

## Remaining weakness + next refinement
- **Corpus-density gap (not a logic gap):** VERA has 0 mechanism peers, SRRK has 1 mechanism + 0 disease peers. UNION recall + rarity rerank behaved correctly given what exists.
- **Highest-leverage cheap next refinement (from the evaluator):** make `retrieval_confidence` AXIS-AWARE, not count-based. Emit per-axis coverage (disease-matched / mechanism-matched / setup-only) and downgrade to `thin`/`setup-only` whenever NO analog matches on disease_area OR mechanism_class — so a setup-only cohort (SRRK: 7-of-8 setup-only) is flagged as low-biology-confidence just like VERA. Stops the analyst over-trusting a setup-only slate. No re-tagging needed.
- Bigger (expensive) fix: expand corpus density in thin cells (neuromuscular pivotal readouts, BAFF/APRIL assets).

## Status
Retrieval v2 is BUILT, re-tagged, measured, and verified — a real improvement on accurate (Tier-1) labels. Next in Tier 2: the axis-aware confidence tweak (cheap) then the football-field wiring (analyst estimates assumptions live). Ultimate validation = the forward paper month.
