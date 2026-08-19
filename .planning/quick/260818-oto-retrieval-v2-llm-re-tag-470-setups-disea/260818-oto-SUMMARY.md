---
phase: quick-260818-oto
plan: 01
subsystem: knowledge-base / retrieval
tags: [retrieval, kb, analog-query, taxonomy, rerank]
requires:
  - kb._structural_filter (Tier-1 generalized list/scalar path)
  - playbook.store.backfill_outcome_fields (UPDATE-path pattern)
  - kb._with_outcome / kb.analog_query (v1, unchanged)
provides:
  - data/setup_taxonomy_v2.json (frozen LOCKED v2 rubric)
  - playbook.store.stamp_axes (idempotent axis writer)
  - kb.analog_query_v2 + kb._rarity_weights
  - desk/builder.py multi-axis v2 wiring + captured retrieval_confidence
  - scripts/retrieval_stress.py --v2 before/after path
affects:
  - desk/builder.py analog retrieval (v1 setup-only -> v2 multi-axis)
tech-stack:
  added: []
  patterns: [idf-rarity-rerank, inclusive-union-recall, idempotent-update-writer]
key-files:
  created:
    - data/setup_taxonomy_v2.json
    - tests/test_retrieval_v2_axes.py
    - tests/test_retrieval_v2.py
  modified:
    - src/catalyst_trader/playbook/store.py
    - src/catalyst_trader/kb.py
    - src/catalyst_trader/desk/builder.py
    - scripts/retrieval_stress.py
    - tests/test_retrieval_stress.py
decisions:
  - "Recall is ALL-INCLUSIVE UNION over {type,disease_area,mechanism_class,setups} — a candidate sharing even one axis is never hard-excluded, then rarity-weighted rerank ranks it (CEO D-2)."
  - "IDF rarity weight clamped at >=0 so a near-ubiquitous shared setup contributes ~0, never a penalty."
  - "Rerank knobs (W_SETUP/W_DISEASE/W_MECH/W_SEMANTIC + MIN_SHARED_AXES/MAX_MEAN_DIST) are named module-level constants, tunable in Phase-9 refit."
  - "Builder degrades gracefully: a live catalyst without disease_area/mechanism_class just doesn't constrain those axes (still inclusive type+setups recall); no query-side LLM classifier built (YAGNI)."
metrics:
  tasks: 3
  files: 9
  completed: 2026-08-18
---

# Phase quick-260818-oto Plan 01: Retrieval v2 (LLM re-tag prep + inclusive multi-axis recall) Summary

Retrieval v2 code path: a frozen 18/20/19 v2 vocab, an idempotent three-axis node writer
(`stamp_axes`), `kb.analog_query_v2` doing all-inclusive UNION recall + IDF-rarity-weighted
multi-axis rerank + a thin/ok confidence flag, the builder rewired from setup-only to multi-axis
retrieval, and a `--v2` before/after stress-harness path. Tasks 1-3 only (all in-memory green);
Task 4 (the live 470-node LLM re-tag wave + live stress/desk run) is the operator checkpoint below.

## What was built

### Task 1 — v2 vocab frozen + `stamp_axes` (commits `43a4ca0` RED, `1ce5420` GREEN)
- `data/setup_taxonomy_v2.json`: LOCKED VOCAB copied verbatim — 18 setups (incl. the 3-way
  single-asset split), 20 disease_areas, 19 mechanism_classes, + `tagging_rubric`. v1
  `data/setup_taxonomy.json` untouched (the deterministic tagger + its import-time cross-check still
  read v1's `["tags"]` shape).
- `playbook.store.stamp_axes(conn, cid, *, setups, disease_area, mechanism_class) -> int`: mirrors
  `backfill_outcome_fields`' UPDATE discipline (SELECT by `ref_id` newest-wins -> overwrite the three
  axis keys -> `UPDATE kb_node SET attrs_json` -> commit). Idempotent by construction (overwrite,
  not append), no re-embed, no edge/outcome writes, raises `ValueError` on a missing cid. All three
  axes retrievable via `kb._structural_filter` (scalar + list-membership).

### Task 2 — `analog_query_v2` + `_rarity_weights` + builder wiring (commits `2de55a5` RED, `bfdb7b9` GREEN)
- `kb._rarity_weights(conn, key="setups")`: IDF `log(N/(1+count))` over the live corpus, clamped
  `>=0`. Rare > common ordering; near-ubiquitous setups ~0.
- `kb.analog_query_v2(...) -> {"analogs", "retrieval_confidence", "n_candidates"}`: candidate pool =
  UNION of `_structural_filter` per provided axis (None/empty axis contributes nothing, never
  shrinks the union); whole-vec-set over-fetch -> intersect -> score
  `W_SETUP*Σrarity(shared) + W_DISEASE*disease_match + W_MECH*mech_match + W_SEMANTIC*(1-distance)` ->
  top-k. Each analog carries `matched_axes` + `score`. Confidence `thin` when top-k mean matched-axis
  count `< MIN_SHARED_AXES` OR mean distance `> MAX_MEAN_DIST`, else `ok`.
- `desk/builder.py`: replaced the setup-only `setup_filters`+`analog_query` block with
  `analog_query_v2` on the catalyst's OWN axes (`type`+`setups`+`disease_area`+`mechanism_class`);
  `_analog_context` still ticker-free; `retrieval_confidence` captured + surfaced into the narrative
  extra (`RETRIEVAL analog confidence: …`) for downstream `field.weights.analog_cold/analog_warm`.
  Analog `tool:` ref re-minted as `tool:analog_query_v2#…` (CALL-04-clean, still resolved-by-construction).
- v1 `kb.analog_query` + `_with_outcome` byte-for-byte. Machine-checked green: `test_retrieval_v2`,
  `test_kb_analog`, `test_kb_setups`, `test_desk_builder`, **`test_playbook_leakgate`** (as_of
  no-look-ahead), `test_playbook_store`, `test_desk_tools` (CALL-04 ref guard) — 74 passed.

### Task 3 — stress harness v2 path (commits `4cf4e04` RED, `728cdb4` GREEN)
- `scripts/retrieval_stress.py`: `_run_one_v2` reads the held-out node's stored axes, runs BEFORE
  (v1 type-only `analog_query`) + AFTER (v2 `analog_query_v2`), emits per-cid
  `query_setups/query_disease_area/query_mechanism_class` + `retrieval_confidence` + `n_candidates`
  + each analog's `matched_axes`. `_aggregate` now also reports `mean_matched_axes_after`. `--v2`
  flag selects the v2 AFTER cohort + v2 example_cids + v2 report path. Pure helpers offline-tested;
  `--help` opens no DB.

## Deviations from Plan

None functional. Two mechanical adjustments:
- **[Rule 3 - blocking] async test harness:** the builder-wiring test was written `async def` (the
  repo's pytest-asyncio auto pattern) after a manual `get_event_loop()` raised on Python 3.14. No
  production impact.
- Builder analog `tool:` ref name changed `analog_query` -> `analog_query_v2` to match the new call
  (the verifier's `_is_analog` still classifies it via `input=="analogs"`; leak-gate + CALL-04 green).

## Known Stubs

None. `stamp_axes` is a generic writer proven end-to-end (write -> retrieve) in-memory; the actual
per-node axis VALUES are produced by the Task-4 LLM re-tag wave (by design — D-1). `analog_query_v2`
and the `--v2` harness are fully live-ready and only await the re-tagged corpus.

## Verification

- Task 1: `tests/test_retrieval_v2_axes.py` — 6 passed; vocab 18/20/19 asserted.
- Task 2: 7-file backward-compat suite incl. leak-gate — 74 passed.
- Task 3: `tests/test_retrieval_stress.py` — 5 passed; `--help` opens no DB.
- Full suite: **1484 passed** (2 unrelated statsmodels ComplexWarnings).

---

## Task 4 — LIVE OPERATOR CHECKPOINT (main dir, run by the orchestrator, NOT in a worktree)

`catalyst.db` is gitignored / main-dir only. Task 4 is the sole DB-touching step. Non-blocking:
Tasks 1-3 stand on their own in-memory-verified merit.

### (a) LLM RE-TAG WAVE over all 470 catalyst nodes (CEO D-1: LLM, not the deterministic tagger)

Mirror the Tier-1 clinical-relabel wave — ~4 agents split the cids. Each agent, per assigned node:
1. reads `data/setup_taxonomy_v2.json` (the LOCKED rubric);
2. reads the node's FULL narrative — `attrs.narrative_before` + `attrs.narrative_after`
   (thesis, reference_class, variant_why, causal_setup, what_to_watch, why_narrative, lesson_rule,
   second_order, what_happened) + `attrs.indication` + `attrs.modality`;
3. applies the rubric to produce `setups[]` (multi-label, mean ~2.5; AT MOST ONE of the 3
   single-asset sub-setups by stage/decisiveness), exactly ONE `disease_area`, exactly ONE
   `mechanism_class`;
4. writes via `playbook.store.stamp_axes` (idempotent UPDATE — re-runnable).

Get the full cid list from the live DB:
```bash
# in the main working dir (catalyst.db present):
.venv/bin/python -c "from catalyst_trader import db; c=db.connect(None); print(len(c.execute(\"SELECT DISTINCT ref_id FROM kb_node WHERE kind='catalyst' AND ref_id IS NOT NULL\").fetchall()))"
```

Per-node write (what each agent calls once it has decided the axes):
```python
from catalyst_trader import db
from catalyst_trader.playbook.store import stamp_axes
conn = db.connect(None)  # live catalyst.db (settings.db_path)
stamp_axes(conn, cid, setups=[...], disease_area="...", mechanism_class="...")
```

**Coverage target:** 470/470 `disease_area` + `mechanism_class` (0 unassigned; only cid 1041 BMRA ->
`mechanism_class="other-na"` per the VOCAB coverage_note); every node `>=1` setup.

**AGENT PROMPT SPEC (per node), verbatim:**
> You are tagging one biotech catalyst for case-based retrieval. Apply
> `data/setup_taxonomy_v2.json`'s `tagging_rubric` EXACTLY. Output STRICT JSON
> `{setups:[...], disease_area:'...', mechanism_class:'...'}` using ONLY vocab names from the file.
> `setups`: all applicable per the v1 rubric for the 15 retained tags + AT MOST ONE single-asset
> sub-setup (`pivotal-company-defining-binary` | `single-asset-going-concern-binary` |
> `early-mid-stage-single-asset-signal`) chosen by stage/decisiveness; `disease_area`: exactly the
> ONE primary indication driving THIS catalyst (specificity order in the rubric); `mechanism_class`:
> exactly the ONE primary modality of the lead asset (precedence order in the rubric). Do not invent
> names. Ambiguous single-asset with no explicit stage -> `pivotal-company-defining-binary`.

After the wave: re-index Graphify (code changed) per CLAUDE.md.

**Post-wave coverage check:**
```bash
.venv/bin/python -c "
from catalyst_trader import db; import json
c=db.connect(None)
rows=c.execute(\"SELECT attrs_json FROM kb_node WHERE kind='catalyst'\").fetchall()
n=len(rows); da=mc=st=0
for r in rows:
    a=json.loads(r['attrs_json']) if r['attrs_json'] else {}
    da+=bool(a.get('disease_area')); mc+=bool(a.get('mechanism_class')); st+=bool(a.get('setups'))
print(f'nodes={n} disease_area={da} mechanism_class={mc} >=1_setup={st}')
"
```

### (b) RE-RUN the before/after stress test + fundamental-desk evaluator

```bash
.venv/bin/python scripts/retrieval_stress.py --v2
# writes .planning/quick/260818-oto-retrieval-v2-llm-re-tag-470-setups-disea/retrieval_stress_v2.json
# prints: mean setup-overlap BEFORE/AFTER + mean matched-axes AFTER
```
Then run the fundamental-desk stress evaluator over **SRRK + VERA** (the same before/after desk
grades used in quick-260818-l64). **TARGET: flip SRRK/VERA from WEAK** — the pass/fail signal.

Record in this SUMMARY (fill on resume): mean setup-overlap BEFORE vs AFTER, mean matched-axis count
AFTER, and the SRRK/VERA desk-grade deltas.

**Resume signal:** Type "approved" with the SRRK/VERA before/after grades + the stress
mean-overlap/matched-axis numbers, or describe what regressed.

## Self-Check: PASSED
- Created files present: `data/setup_taxonomy_v2.json`, `tests/test_retrieval_v2_axes.py`,
  `tests/test_retrieval_v2.py` (all exist).
- Commits present: `1ce5420`, `bfdb7b9`, `728cdb4`, `43a4ca0`, `2de55a5`, `4cf4e04` (git log verified).
- Full suite 1484 passed; Task-1/2/3 verify commands green.
