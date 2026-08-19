---
phase: quick-260818-oto
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - data/setup_taxonomy_v2.json
  - src/catalyst_trader/playbook/store.py
  - src/catalyst_trader/kb.py
  - src/catalyst_trader/desk/builder.py
  - scripts/retrieval_stress.py
  - tests/test_retrieval_v2_axes.py
  - tests/test_retrieval_v2.py
  - tests/test_retrieval_stress.py
autonomous: false
requirements: [OTO-RETRIEVAL-V2]

must_haves:
  truths:
    - "A catalyst node can carry setups[] (list) + disease_area (scalar) + mechanism_class (scalar) and each is retrievable via kb._structural_filter."
    - "Re-tag writes are idempotent: re-stamping the same node with the same axes leaves attrs unchanged and never duplicates the node."
    - "Retrieval v2 gathers the UNION of catalysts matching ANY of {same disease_area, same mechanism_class, any shared setup, same type} — it never hard-excludes a candidate that shares even one axis."
    - "The candidate pool is reranked by a rarity-weighted multi-axis score (IDF-style setup overlap + disease_area match + mechanism_class match + semantic distance); rarer setups outrank common ones on equal semantic distance."
    - "Each returned analog exposes which axes it matched, and the result carries a thin/ok retrieval-confidence flag when the top-k share few axes / are semantically far."
    - "The v1 analog_query signature + every existing caller is unchanged (scalar-filter path byte-for-byte); the query context still drops the ticker."
    - "The before/after stress harness emits, per held-out cid, the query's setups/disease_area/mechanism_class and each analog's matched axes under v2 retrieval."
  artifacts:
    - path: "data/setup_taxonomy_v2.json"
      provides: "Frozen LOCKED v2 vocab (18 setups incl 3-way single-asset split, 20 disease_areas, 19 mechanism_classes, tagging_rubric) — the re-tag wave's rubric source"
      contains: "mechanism_classes"
    - path: "src/catalyst_trader/playbook/store.py"
      provides: "stamp_axes idempotent UPDATE writer (mirrors backfill_outcome_fields) that stamps setups/disease_area/mechanism_class onto a catalyst node by cid"
      contains: "def stamp_axes"
    - path: "src/catalyst_trader/kb.py"
      provides: "analog_query_v2 (inclusive UNION recall + rarity-weighted multi-axis rerank + confidence) + _rarity_weights helper; analog_query untouched"
      contains: "def analog_query_v2"
    - path: "src/catalyst_trader/desk/builder.py"
      provides: "Builder wiring upgraded from setup-only analog_query to analog_query_v2 (multi-axis query + confidence captured)"
      contains: "analog_query_v2"
    - path: "scripts/retrieval_stress.py"
      provides: "v2 before/after harness path emitting per-cid axes + matched axes"
      contains: "_run_one_v2"
  key_links:
    - from: "src/catalyst_trader/playbook/store.py::stamp_axes"
      to: "kb_node.attrs_json (setups/disease_area/mechanism_class)"
      via: "idempotent UPDATE by ref_id=cid"
      pattern: "UPDATE kb_node SET attrs_json"
    - from: "src/catalyst_trader/kb.py::analog_query_v2"
      to: "kb._structural_filter"
      via: "one _structural_filter call per axis, python set UNION"
      pattern: "_structural_filter"
    - from: "src/catalyst_trader/desk/builder.py::build"
      to: "kb.analog_query_v2"
      via: "multi-axis query (type + setups + disease_area + mechanism_class)"
      pattern: "analog_query_v2"
---

<objective>
Retrieval v2. Two CEO decisions are LOCKED and non-negotiable:
1. **LLM re-tag all 470 nodes** (not the deterministic tagger) — Task 4, the live wave.
2. **Match floor is ALL-INCLUSIVE** — gather anything and everything that shares even one axis, NEVER hard-exclude, then RANK.

v1 (quick-260818-l64) filtered on setups-only and held all 5 desk grades — a foundation, not a win. v2 fixes the two failures: (a) the corpus was deterministically mis-tagged and the single-asset tag was ~half the corpus (Tier-1 refined vocab splits it 3 ways), and (b) setup-only filtering STARVED recall. v2 re-tags accurately (LLM, VOCAB rubric) and rebuilds retrieval as inclusive-recall + multi-axis rarity-weighted rerank with a confidence signal.

Purpose: flip SRRK/VERA from WEAK on the fundamental-desk stress test by retrieving the RIGHT precedents (same disease_area / mechanism_class / rare setup), rarity-weighted so common setups stop dominating.
Output: frozen v2 vocab in data/, an idempotent axis writer, kb.analog_query_v2, upgraded builder wiring, an extended before/after harness, and a documented live re-tag + stress-run operator procedure.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@CLAUDE.md
@.planning/quick/260818-oto-retrieval-v2-llm-re-tag-470-setups-disea/260818-oto-VOCAB.json

# Reuse/extend — do NOT duplicate:
@src/catalyst_trader/kb.py
@src/catalyst_trader/playbook/store.py
@src/catalyst_trader/playbook/tagger.py
@src/catalyst_trader/desk/builder.py
@scripts/retrieval_stress.py

<interfaces>
<!-- Contracts the executor uses directly. Extracted from the codebase — no exploration needed. -->

kb._structural_filter(conn, filters: dict, as_of=None) -> set[int]
  # Tier-1 (quick-260818-l64) GENERALIZED this: a LIST value = list-membership (json_each overlap),
  # a SCALAR value = exact match OR list-membership. So setups=[...] AND disease_area="x" (scalar)
  # BOTH already work through this ONE function. Empty filters -> every catalyst. REUSE, do not fork.

kb.analog_query(conn, embed, context, filters: dict, k=5, as_of=None) -> list[dict]
  # v1 — KEEP UNCHANGED (backward-compat). Structural filter -> KNN over-fetch -> intersect -> top-k.
  # When any filter value is a list it over-fetches the WHOLE vec set (reachability). Reuse that idea.

kb._with_outcome(conn, node_id, distance) -> dict
  # {node_id, distance, catalyst: <attrs>, outcome: <attrs>}  — REUSE verbatim for v2 results.

kb.hash_embed(text) / kb.serialize_float32 / kb_vec table (node_id, embedding), cosine distance.

playbook/store.py::backfill_outcome_fields(conn, classifier_fn=None) -> int
  # THE UPDATE-PATH PATTERN to mirror for stamp_axes: SELECT catalyst nodes -> json.loads(attrs_json)
  # -> mutate attrs -> UPDATE kb_node SET attrs_json=? WHERE id=? -> conn.commit(). content_sha does
  # NOT re-fire on axis writes (setups/disease_area/mechanism_class are NOT CatalystRecord fields),
  # so an UPDATE writer is REQUIRED — insert_catalyst_record will not re-write already-populated nodes.

desk/builder.py::build(...) — current wiring to UPGRADE (lines ~115-125):
  q_setups = tagger.tag_setups({...})
  filters  = kb.setup_filters(conn, ctype, q_setups)
  analogs  = kb.analog_query(conn, embed, context, filters=filters, k=5, as_of=as_of)
  # _analog_context already drops the ticker (quick-260818-l64) — KEEP that.

Test fixtures (tests/conftest.py): `db` = _db.connect(":memory:") (migrated), `embed` = kb.hash_embed.
Seed pattern (tests/test_kb_setups.py::_seed): insert_claim(cited catalyst KBNode + vector) +
insert_claim(outcome) + add_edge(cid,"RESULTED_IN",oid). USE this pattern for all v2 tests.
</interfaces>

<execution_reality_CRITICAL>
- catalyst.db is GITIGNORED / main-dir / ABSENT in a worktree. EVERY code task (1-3) verify runs
  IN-MEMORY: db.connect(":memory:") + kb.hash_embed + seeded nodes. NO code-task test may need the
  live DB. If one seems to, STOP and flag it.
- The re-tag wave + live stress run are Task 4 (main dir, operator/checkpoint) — NOT code-task tests.
- Rarity weights are computed from LIVE corpus counts by a helper, but the helper is TESTED on seeded
  in-memory data (seed N nodes with known setup frequencies, assert IDF ordering).
- Money-adjacent: tests BEFORE logic, atomic commits (test commit RED, then impl commit GREEN).
</execution_reality_CRITICAL>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Freeze v2 vocab + idempotent axis writer (setups/disease_area/mechanism_class on the node)</name>
  <files>data/setup_taxonomy_v2.json, src/catalyst_trader/playbook/store.py, tests/test_retrieval_v2_axes.py</files>
  <behavior>
    - stamp_axes(conn, cid, *, setups, disease_area, mechanism_class): stamps the three axes onto the
      catalyst node whose ref_id==cid, returns the node id, commits. Idempotent: calling twice with the
      same values leaves attrs identical and does NOT create a second node.
    - After a stamp, kb._structural_filter(conn, {"disease_area": X}) returns that node (scalar path),
      {"mechanism_class": Y} returns it (scalar path), {"setups": [S]} returns it (list-membership).
    - stamp_axes NEVER re-embeds (setups/disease_area/mechanism_class are structural axes, not vectors)
      and NEVER touches outcome/edge/citation rows.
    - Absent node (no ref_id==cid catalyst) -> raise (a re-tag can't silently no-op a missing cid).
  </behavior>
  <action>
    1. FREEZE THE VOCAB: copy the LOCKED
       `.planning/quick/260818-oto-retrieval-v2-llm-re-tag-470-setups-disea/260818-oto-VOCAB.json`
       verbatim to `data/setup_taxonomy_v2.json`. Do NOT redesign it. Do NOT overwrite the v1
       `data/setup_taxonomy.json` — the deterministic tagger + its import-time cross-check still read
       v1's `["tags"]` shape; v2 has a different shape (`setups`/`disease_areas`/`mechanism_classes`).
       This is the rubric source the Task-4 re-tag wave reads.
    2. ADD stamp_axes to `src/catalyst_trader/playbook/store.py`, MIRRORING backfill_outcome_fields'
       UPDATE discipline (SELECT -> json.loads(attrs_json) -> mutate -> UPDATE kb_node SET attrs_json=?
       WHERE id=? -> conn.commit()). Signature:
         def stamp_axes(conn, cid, *, setups, disease_area, mechanism_class) -> int
       Find the node with `SELECT id, attrs_json FROM kb_node WHERE kind='catalyst' AND ref_id=?
       ORDER BY id DESC LIMIT 1` (newest wins, same as _existing). Raise ValueError if None. Set
       attrs["setups"]=list(setups or []), attrs["disease_area"]=disease_area,
       attrs["mechanism_class"]=mechanism_class. UPDATE + commit. Idempotent by construction (overwrite,
       not append — same pattern as tagger.tag_all_catalyst_nodes). No re-embed, no edge/outcome writes.
    3. WRITE tests/test_retrieval_v2_axes.py FIRST (RED): seed catalyst nodes with the tests/test_kb_setups
       ::_seed pattern (cited claim + vector + outcome), then stamp_axes and assert:
         - _structural_filter matches disease_area (scalar), mechanism_class (scalar), setups (list) on the
           stamped node;
         - idempotency: two stamps -> one node, attrs unchanged;
         - missing cid raises.
    Commit tests RED first, then impl GREEN (atomic, money-adjacent discipline).
    Per D-1 (LLM re-tag) the WRITER is generic — the LLM values arrive in Task 4; this task only proves
    the write path + retrievability.
  </action>
  <verify>
    <automated>cd "$PWD" && python -m pytest tests/test_retrieval_v2_axes.py -x -q && test -f data/setup_taxonomy_v2.json && python -c "import json; d=json.load(open('data/setup_taxonomy_v2.json')); assert len(d['setups'])==18 and len(d['disease_areas'])==20 and len(d['mechanism_classes'])==19, d.keys()"</automated>
  </verify>
  <done>data/setup_taxonomy_v2.json frozen (18/20/19 + rubric); stamp_axes stamps + is idempotent + raises on missing cid; all three axes retrievable via _structural_filter; in-memory tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: kb.analog_query_v2 — inclusive UNION recall + rarity-weighted multi-axis rerank + confidence; wire builder</name>
  <files>src/catalyst_trader/kb.py, src/catalyst_trader/desk/builder.py, tests/test_retrieval_v2.py</files>
  <behavior>
    - _rarity_weights(conn, key="setups") -> dict[str,float]: IDF over the live corpus, idf = log(N / (1+count))
      per distinct value found via json_each over $.<key> across catalyst nodes. Rarer value -> higher weight;
      a value present in ~all nodes -> ~0. Deterministic. (Tested on seeded frequencies: assert a rare
      setup outranks a common one.)
    - analog_query_v2(conn, embed, context, *, ctype, disease_area=None, mechanism_class=None, setups=None,
      k=5, as_of=None) -> dict:
        RECALL (inclusive, never exclude): candidate set = UNION of _structural_filter results for each
        provided axis — {"type":ctype}, {"disease_area":disease_area}, {"mechanism_class":mechanism_class},
        {"setups":list(setups)}. A None/empty axis contributes nothing (no constraint), never shrinks the
        union. Empty union -> {"analogs":[], "retrieval_confidence":"thin", "n_candidates":0}.
        RERANK: over-fetch the WHOLE vec set (like analog_query's list-branch), intersect with the union,
        score each candidate:
          rw = _rarity_weights(conn, "setups")
          score = W_SETUP * sum(rw[s] for s in shared_setups)
                + W_DISEASE * (disease_area matches)
                + W_MECH    * (mechanism_class matches)
                + W_SEMANTIC * (1.0 - distance)      # cosine distance in [0,2]; closer -> higher
        Sort by score desc, take top-k. Each analog = _with_outcome(...) augmented with
        "matched_axes": the concrete axes it shares (e.g. ["disease_area","mechanism_class","setup:rare-tag"])
        and "score".
        CONFIDENCE: retrieval_confidence = "thin" when the top-k mean matched-axis count < MIN_SHARED_AXES
        OR mean distance > MAX_MEAN_DIST (few shared axes / semantically far), else "ok". Return
        {"analogs":[...], "retrieval_confidence": "...", "n_candidates": len(union)}.
    - W_* and the two thresholds are module-level named knobs (ponytail: tunable, not magic-in-loop).
    - analog_query (v1) and _with_outcome are UNCHANGED; every existing caller/test stays green.
  </behavior>
  <action>
    EXTEND kb.py, do NOT fork _structural_filter or duplicate the KNN. Add _rarity_weights and
    analog_query_v2 as NEW functions (backward-compat: analog_query signature frozen — the goal
    requires it). Reuse _with_outcome verbatim. For the KNN, reuse the "over-fetch whole vec set"
    approach analog_query already uses under a list filter (COUNT kb_vec). Rarity downweights the
    ~15-25% common setups per the VOCAB coverage_note — that is the whole point of IDF here.

    WIRE builder.py (the caller upgrade): replace the setup-only block
      q_setups = tagger.tag_setups({...}); filters = kb.setup_filters(...); analogs = kb.analog_query(...)
    with:
      q_setups = tagger.tag_setups({"thesis": verdict.thesis, "indication": _get(catalyst,"indication"),
                                    "modality": _get(catalyst,"modality")})
      q_disease = _get(catalyst, "disease_area")     # None if a fresh live catalyst isn't classified yet
      q_mech    = _get(catalyst, "mechanism_class")  # None -> that axis just doesn't constrain recall
      res = kb.analog_query_v2(conn, embed, context, ctype=ctype, disease_area=q_disease,
                               mechanism_class=q_mech, setups=q_setups, k=5, as_of=as_of)
      analogs = res["analogs"]; retrieval_confidence = res["retrieval_confidence"]
    Keep _analog_context ticker-free (unchanged). Expose retrieval_confidence downstream MINIMALLY:
    add it to the builder's estimate_inputs / narrative extra so the football field can later key
    field.weights.analog_cold vs analog_warm off it. Do NOT change the TradeProposal contract or the
    football-field aggregator in this plan — full field consumption is a documented downstream
    (# ponytail: return + surface the flag now; the analog_cold/warm mapping already exists in
    BOOTSTRAP_DEFAULT['field']['weights'] as its future consumer).
    Ponytail note: query-side disease_area/mechanism_class come off the catalyst attrs when present;
    a fresh live catalyst without them degrades to type+setups recall (still inclusive). Do NOT build
    a query-side LLM classifier now (YAGNI — the stress test in Task 3/4 reads the re-tagged node's
    OWN stored axes, so query and corpus are both v2-vocab there).

    TESTS FIRST (tests/test_retrieval_v2.py, RED then GREEN): seed with the _seed pattern —
      - UNION recall: a node sharing ONLY disease_area (different type, no shared setup) IS in the pool;
        a node sharing nothing is NOT.
      - rarity rerank: two candidates equal on semantic distance, the one sharing a RARE setup outranks
        the one sharing a COMMON setup (seed frequencies to make one setup common).
      - disease_area + mechanism_class matches lift score / appear in matched_axes.
      - confidence: an all-distant / no-shared-axis top-k -> "thin"; a tightly-matched pool -> "ok".
      - backward-compat: analog_query still returns the v1 shape (a list, not a dict) unchanged.
  </action>
  <verify>
    <automated>cd "$PWD" && python -m pytest tests/test_retrieval_v2.py tests/test_kb_analog.py tests/test_kb_setups.py tests/test_desk_builder.py tests/test_playbook_leakgate.py tests/test_playbook_store.py tests/test_desk_tools.py -x -q</automated>
  </verify>
  <done>analog_query_v2 does inclusive UNION recall + rarity-weighted multi-axis rerank + thin/ok confidence, each analog exposing matched_axes; _rarity_weights IDF-orders rare>common; analog_query + EVERY existing caller of analog_query/kb.py byte-for-byte green — the as_of no-look-ahead LEAK-GATE suite (tests/test_playbook_leakgate.py), the analog_query callers in tests/test_playbook_store.py, and the CALL-04 agent-tool ref-format guard (tests/test_desk_tools.py) are all machine-checked green in this task's verify; builder wired to v2 with ticker still dropped and confidence captured; all in-memory tests green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: extend retrieval_stress.py with the v2 before/after path (offline-tested pure helpers)</name>
  <files>scripts/retrieval_stress.py, tests/test_retrieval_stress.py</files>
  <behavior>
    - A new _run_one_v2(conn, kb, embed, cid, k) reads the held-out node's OWN stored axes
      (setups/disease_area/mechanism_class from attrs) and returns a per-cid record:
        {"cid", "query_setups", "query_disease_area", "query_mechanism_class",
         "before": [type-only analog_query results...],
         "after":  [analog_query_v2 results, each with "matched_axes"...]}
      BEFORE = v1 type-only filter (the baseline); AFTER = v2 inclusive multi-axis recall+rerank.
    - The existing pure _overlap/_aggregate helpers still work on the v2 records (query_setups vs each
      result's setups) — extend _aggregate (or add a sibling) to also report mean matched-axis count
      after, so the headline shows v2 retrieves more/rarer shared axes than v1. Keep the math PURE
      (no DB) and offline-tested.
    - All DB access stays inside main()/_run_one_v2 (lazy imports) so --help + the unit tests never open a DB.
  </behavior>
  <action>
    EXTEND scripts/retrieval_stress.py — reuse _overlap/_aggregate/_result_row; add _run_one_v2 and a
    --v2 flag (or make v2 the AFTER cohort) in main(). AFTER now calls kb.analog_query_v2(...) with the
    node's stored axes; _result_row gains disease_area/mechanism_class/matched_axes fields. The report
    JSON keeps the before/after aggregate shape + adds per-cid axes + matched axes and the
    retrieval_confidence per cid. This is HARNESS code — the LIVE run is Task 4 against the main-dir DB.
    TESTS FIRST in tests/test_retrieval_stress.py (RED then GREEN): extend the existing offline pure-helper
    tests to cover the v2 aggregation over synthetic per-cid records carrying matched_axes (NO DB).
  </action>
  <verify>
    <automated>cd "$PWD" && python -m pytest tests/test_retrieval_stress.py -x -q && python scripts/retrieval_stress.py --help >/dev/null</automated>
  </verify>
  <done>_run_one_v2 emits per-cid setups/disease_area/mechanism_class + analogs' matched_axes; the v2 aggregate reports mean setup-overlap AND mean matched-axis count before vs after; pure helpers offline-tested green; --help opens no DB.</done>
</task>

<task type="checkpoint:human-action" gate="non-blocking">
  <what-built>Code path is ready: v2 vocab frozen, stamp_axes writer, analog_query_v2, builder wired, stress harness extended (Tasks 1-3, all in-memory green). This task is the LIVE, MAIN-DIR operator run against the gitignored catalyst.db — it CANNOT run in a worktree / in pytest.</what-built>
  <how-to-verify>
    Run in the MAIN working directory (where catalyst.db lives), NOT a worktree.

    (a) LLM RE-TAG WAVE over all 470 catalyst nodes (CEO decision D-1: LLM, not deterministic).
        Mirror the Tier-1 clinical-relabel wave (~4 agents split the cids). Each agent:
          - reads data/setup_taxonomy_v2.json (the LOCKED rubric: 18 setups incl the 3-way single-asset
            split, 20 disease_areas, 19 mechanism_classes, + tagging_rubric);
          - for each assigned catalyst node, reads its FULL narrative (attrs.narrative_before +
            narrative_after: thesis, reference_class, variant_why, causal_setup, what_to_watch,
            why_narrative, lesson_rule, second_order, what_happened) + indication + modality;
          - applies the rubric to produce: setups[] (multi-label, mean ~2.5; pick AT MOST ONE of the
            3 single-asset sub-setups by stage/decisiveness per the rubric), exactly ONE disease_area,
            exactly ONE mechanism_class;
          - writes via playbook.store.stamp_axes(conn, cid, setups=..., disease_area=..., mechanism_class=...)
            (idempotent UPDATE — re-runnable). Coverage target: 470/470 disease_area + mechanism_class
            (0 unassigned; only cid 1041 BMRA -> mechanism_class 'other-na' per the VOCAB coverage_note);
            every node >=1 setup.
        AGENT PROMPT SPEC (per node): "You are tagging one biotech catalyst for case-based retrieval.
        Apply data/setup_taxonomy_v2.json's tagging_rubric EXACTLY. Output STRICT JSON
        {setups:[...], disease_area:'...', mechanism_class:'...'} using ONLY vocab names from the file.
        setups: all applicable per the v1 rubric for the 15 retained tags + AT MOST ONE single-asset
        sub-setup (pivotal-company-defining-binary | single-asset-going-concern-binary |
        early-mid-stage-single-asset-signal) chosen by stage/decisiveness; disease_area: exactly the ONE
        primary indication driving THIS catalyst (specificity order in the rubric); mechanism_class:
        exactly the ONE primary modality of the lead asset (precedence order in the rubric). Do not
        invent names. Ambiguous single-asset with no explicit stage -> pivotal-company-defining-binary."
        After the wave: re-index Graphify if code changed (it did) per CLAUDE.md.

    (b) RE-RUN the before/after stress test + fundamental-desk evaluator:
          python scripts/retrieval_stress.py --v2   # (writes the v2 before/after report JSON)
        then run the fundamental-desk stress evaluator over SRRK + VERA (the same before/after desk
        grades used in quick-260818-l64). TARGET: flip SRRK/VERA from WEAK — the pass/fail signal for
        this quick. Record mean setup-overlap + mean matched-axis count BEFORE vs AFTER and the desk
        grade deltas in the SUMMARY.
  </how-to-verify>
  <resume-signal>Type "approved" with the SRRK/VERA before/after grades + the stress mean-overlap/matched-axis numbers, or describe what regressed. Non-blocking: Tasks 1-3 stand on their own in-memory-verified merit.</resume-signal>
</task>

</tasks>

<verification>
- Tasks 1-3 are fully offline: every verify runs against db.connect(":memory:") + kb.hash_embed + seeded nodes. NO code-task test touches the live catalyst.db.
- Backward-compat guard: tests/test_kb_analog.py + tests/test_kb_setups.py + tests/test_desk_builder.py + tests/test_playbook_leakgate.py + tests/test_playbook_store.py + tests/test_desk_tools.py stay green (v1 analog_query + scalar path unchanged; the as_of leak-gate and every real analog_query caller machine-checked in Task 2's verify).
- Task 4 (live) is the only DB-touching step and is a non-blocking operator checkpoint.
</verification>

<success_criteria>
- v2 vocab frozen at data/setup_taxonomy_v2.json (18 setups / 20 disease_areas / 19 mechanism_classes + rubric), v1 vocab untouched.
- stamp_axes: idempotent UPDATE, all three axes retrievable via _structural_filter, raises on missing cid.
- analog_query_v2: inclusive UNION recall (never hard-excludes a shared-axis candidate) + rarity-weighted multi-axis rerank + thin/ok confidence + per-analog matched_axes; v1 analog_query byte-for-byte.
- builder wired to v2, ticker still dropped, confidence captured for downstream field weighting.
- stress harness emits per-cid axes + matched axes for the before/after run.
- (Live/Task 4) 470/470 nodes re-tagged; SRRK/VERA before/after desk grades recorded — target flip from WEAK.
</success_criteria>

<output>
After completion, create `.planning/quick/260818-oto-retrieval-v2-llm-re-tag-470-setups-disea/260818-oto-SUMMARY.md`
</output>
