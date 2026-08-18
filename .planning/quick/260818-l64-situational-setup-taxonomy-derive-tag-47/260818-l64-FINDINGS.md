# Quick 260818-l64 — Findings: setup taxonomy + setup-aware retrieval

**Date:** 2026-08-18 · **Branch:** feat/backtest-readiness

## What shipped
- `data/setup_taxonomy.json` — frozen 16-tag vocabulary (12 ex-ante + 4 outcome) + tagging rubric.
- `src/catalyst_trader/playbook/tagger.py` — deterministic (LLM-free) rubric tagger; multi-label, idempotent.
- `kb.py` — generic list-membership in `_structural_filter`; `analog_query` full-vec over-fetch under a list filter; new `setup_filters` thinness gate (sibling of `conditional_filters`, different axis).
- `desk/builder.py` — tags the query event, filters analogs on setups, **drops the ticker** from `_analog_context`.
- `scripts/retrieval_stress.py` — committed before/after harness. 82 tests green.

## Live tagging (Task 4)
- **Coverage: 97.4%** (458/470 with ≥1 ex-ante tag). Avg 3.03 tags/node, max 8, 7 zero-tag nodes.
- Distribution (top): single-asset-microcap-binary **237**, financing-overhang 187, priced-in-derisked 165, first-in-class 140, trial-graveyard 132.

## Retrieval stress test — BEFORE vs AFTER (fundamental-desk POV, same 5 held-out cids)

| Query | Before | After | Δ |
|---|---|---|---|
| DNLI (earnings) | STRONG | STRONG | held |
| INSM (pdufa, first-in-class) | OK | OK | held |
| GOSS (earnings) | OK | OK | held |
| SRRK (readout, SMA/myostatin) | WEAK | WEAK | held |
| VERA (readout, IgAN) | WEAK | WEAK | held |

Harness proxy metric (23 cids): mean setup-overlap 1.835 → 2.035 (+11%).

**Verdict: v1 setup-aware retrieval held every grade and rescued neither WEAK case.** No harm to the good cases; no help to the bad ones. The idea is sound; the tag vocabulary + query-tagging aren't yet strong enough to cash it in.

## Why v1 didn't move the needle (root causes, from the data)
1. **Query under-tagging.** Query setups come from ex-ante fields only (thesis/indication/modality). 2/5 queries (both earnings) got `[]` → filter fell back to type-only (feature never engaged). The other 3 got exactly ONE tag → no cohort-tightening, and one (VERA) was a *wrong* tag.
2. **Tag precision.** `single-asset-microcap-binary` sits on ~237/470 (≈50%) → filtering on it ≈ type-only. VERA→`trial-graveyard` is an outright mis-tag that routed retrieval into Alzheimer's/ALS. `first-in-class` is precise but co-varies with CRL (INSM: 5/8 analogs CRL vs an actual approve), skewing the football-field magnitude.
3. **Mechanism/indication — the highest-signal analogy axes — are still ignored.** A shared broad setup was allowed to substitute for domain proximity; it shouldn't.

## Highest-leverage next improvements (ranked)
1. **Add mechanism + indication/disease-area as a co-filter or rerank FLOOR** — setup refines *within* a domain-proximate pool; never substitutes for it. Directly fixes both WEAK cases (would surface neuromuscular for SRRK, nephrology/TVTX for VERA).
2. **Rarity-weight tags (IDF) + split the mega-tag** — downweight single-asset-binary (~50% prevalence); let rare discriminating tags (priced-for-perfection, cmc-risk, contested-adcom) dominate. Convert binary intersection → graded signal.
3. **Richer ex-ante query tagging, esp. earnings** — 40% of queries currently bypass the feature. Derive priced-in / commercial-quality / financing-overhang at print time.
4. **Tag-quality audit** — validate high-frequency tags vs indication to catch mis-tags (VERA); flag setups that co-vary with the outcome label so the field can debias.

## Keep
- Dropping the ticker from the query string caused **no self-history loss** (DNLI still retrieved its own prior earnings semantically). Removes leakage risk at no cost.

## Status
The setup axis is BUILT, tagged, wired, and measured. It is a foundation, not yet a win — the measurement tells us the next build (domain-floor + rarity-weighting) is what converts it into real precedent-quality gains. Validation remains the desk workflow in the forward paper month, not a systematic backtest.
