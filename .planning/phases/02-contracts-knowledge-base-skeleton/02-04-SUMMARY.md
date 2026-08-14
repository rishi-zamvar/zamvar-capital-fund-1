---
phase: 02-contracts-knowledge-base-skeleton
plan: 04
subsystem: knowledge-base
tags: [sqlite, sqlite-vec, knn, analog, hedge, playbook, provenance, kb, tdd]
requires:
  - phase: 02-contracts-knowledge-base-skeleton
    plan: 03
    provides: "kb.insert_claim (atomic, provenance-enforced) + add_edge + get_node + KBNode/EvidenceSource"
  - phase: 02-contracts-knowledge-base-skeleton
    plan: 01
    provides: "kb.hash_embed/EMBED_DIM + migration 003 (kb_node/kb_edge/kb_vec float[384] cosine)"
provides:
  - "catalyst_trader.kb.analog_query: structural SQL filter -> KNN rank over kb_vec -> RESULTED_IN outcome (KB-03)"
  - "_structural_filter + _with_outcome analog helpers"
  - "insert_hedge_peer / hedge_peers: cited hedge_peer claim + HEDGE_PEER traversal edge, mechanism + payoff_direction sign + weight (KB-04)"
  - "insert_playbook / query_playbooks: cited playbook claim, first-class confidence, ordered by confidence desc (KB-05)"
affects:
  - "Phase 5 (Portfolio Construction) — Trade Builder pulls hedge peers via hedge_peers(); Risk agent re-analyzes them"
  - "Analyst layer — pulls base rates via analog_query; researchers pull playbooks via query_playbooks"
tech-stack:
  added: []
  patterns:
    - "two-tier analog: SQL structural filter (candidate set) THEN KNN over-fetch (k*4) THEN python-set intersect — version-robust vs sqlite-vec alpha metadata-filter API"
    - "hedge relationship stored as a CITED hedge_peer kb_node (citation enforceable) PLUS a HEDGE_PEER edge between company nodes (traversable)"
    - "reference nodes (company) get-or-created without citation; only claims route through insert_claim"
    - "confidence as a first-class kb_node column surfaced by every playbook query"
key-files:
  created:
    - tests/test_kb_analog.py
    - tests/test_kb_hedge.py
    - tests/test_kb_playbook.py
  modified:
    - src/catalyst_trader/kb.py
key-decisions:
  - "analog KNN uses ORDER BY distance LIMIT ? (SQLite 3.53 confirmed) not the AND k=? workaround"
  - "hedge relationship = hedge_peer node via insert_claim (so citation is atomic) + HEDGE_PEER edge for graph traversal — per plan-checker, node-based shape (edges cannot carry :CITES directly)"
  - "payoff_direction stored as explicit sign (+1/-1), validated to (-1,1); polarity not hard-coded (PROJECT.md correlated-long vs ARCHITECTURE.md inverse both representable)"
  - "structural filter narrows before the vector rank; a filter-excluded scenario never surfaces even if embedding-tied"
patterns-established:
  - "analog_query(conn, embed, context, filters, k=5): structural set -> KNN k*4 -> intersect -> top-k -> attach RESULTED_IN outcome"
  - "insert_hedge_peer validates sign+evidence up front (before creating company nodes), routes citation through insert_claim, then adds traversal edge"
requirements-completed: [KB-03, KB-04, KB-05]
duration: ~4min
completed: 2026-08-14
---

# Phase 2 Plan 04: Analog / Hedge / Playbook Query Capabilities Summary

**The KB's three read/query capabilities on top of the provenance write-path: `analog_query` two-tiers a structural SQL filter then a KNN rank over `kb_vec` and traverses `RESULTED_IN` so callers cite realized base rates not vibes; the hedge sub-store persists each inverse/peer relationship as a CITED `hedge_peer` node (mechanism + explicit payoff-direction sign + weight) plus a `HEDGE_PEER` traversal edge; the playbook store surfaces first-class confidence, ordered desc. Hedge peers and playbooks route through `insert_claim`, inheriting the mandatory-citation invariant for free.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-08-14T22:14:22Z
- **Completed:** 2026-08-14T22:18:00Z
- **Tasks:** 3
- **Files modified:** 4 (3 created, 1 extended)

## Accomplishments

- **KB-03 analog_query:** structural SQL filter builds the candidate catalyst set first; KNN over-fetches `k*4` from `kb_vec`, intersects against the candidate set, takes top-k, then traverses `RESULTED_IN` to attach each scenario's realized `Outcome`. A scenario failing the structural filter never surfaces even when embedding-tied — verified by seeding three catalysts on the *same* embed text where the non-matching one is a KNN tie yet is dropped.
- **KB-04 hedge sub-store:** `insert_hedge_peer` stores a hedge relationship as a cited `hedge_peer` node (via `insert_claim`, so citation is atomic) carrying `{name, peer, mechanism, payoff_direction, weight}`, plus a `HEDGE_PEER` edge between the two company nodes for traversal. Sign is explicit (+1/-1), validated; `0` rejected; empty evidence rejected leaving no `hedge_peer` node. `hedge_peers(name)` returns each peer with mechanism, sign, weight, and its cited EvidenceSource.
- **KB-05 playbook store:** `insert_playbook` routes through `insert_claim` with `confidence` as a first-class column; `query_playbooks(scenario_type)` returns confidence-desc, each row surfacing `confidence`. Out-of-range confidence and uncited playbooks rejected.
- Full suite green: **228 passed** (up from 218), no regression.

## Task Commits

Each task committed atomically:

1. **Task 1: two-tier analog query with outcomes** — `e3e839e` (feat)
2. **Task 2: cited hedge-peer sub-store** — `908886b` (feat)
3. **Task 3: cited playbook store with confidence** — `1da71d4` (feat)

## Files Created/Modified

- `src/catalyst_trader/kb.py` — added `_structural_filter`, `_with_outcome`, `analog_query`, `_get_or_create_company`, `insert_hedge_peer`, `hedge_peers`, `insert_playbook`, `query_playbooks`.
- `tests/test_kb_analog.py` — structural-filter-excludes-tie, distance-ordering, outcome-attached, empty-candidate-set.
- `tests/test_kb_hedge.py` — mechanism/sign/weight/citation roundtrip + traversal edge, uncited-rejected-no-orphan, both signs roundtrip + zero rejected.
- `tests/test_kb_playbook.py` — confidence-desc ordering + surfaced, uncited-rejected, out-of-range-rejected.

## Decisions Made

- **KNN syntax:** confirmed `ORDER BY distance LIMIT ?` works on the in-env SQLite 3.53 (smoke test) — used it, no `AND k=?` fallback needed.
- **Hedge shape (per plan-checker):** the hedge relationship is a `hedge_peer` node created via `insert_claim` (nodes can be cited; a `:CITES` cannot hang off an edge), PLUS a `HEDGE_PEER` edge between company nodes for graph traversal. Acceptance tests assert the node-based shape.
- **Validation before side effects:** `insert_hedge_peer` validates sign and evidence *before* get-or-creating company nodes, so a rejected call leaves nothing pending.
- **payoff_direction sign is stored, not polarity hard-coded** — both PROJECT.md's correlated-long (+1) and ARCHITECTURE.md's inverse (-1) readings are representable and cited.

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — the KB is offline (deterministic hash embedder, no network/ML deps).

## Next Phase Readiness

- Phase 2 code complete: all of KB-01..05 + the six contracts shipped and green (228 tests).
- **Phase-close carry-forward (orchestrator/verify step):** generate `docs/phase-reports/phase-02-report.html`, update `.planning/TOKEN-NOTES.md` retrospective, and re-index Graphify (`/graphify`) after this code-producing phase — flagged in the plan verification block, not done per-plan.
- Downstream: Phase 5 Trade Builder / Risk agent consume `hedge_peers()`; analyst layer consumes `analog_query`; researchers consume `query_playbooks`.

## Self-Check: PASSED

All three test files present; kb.py extended; all three task commits (e3e839e, 908886b, 1da71d4) in history.

---
*Phase: 02-contracts-knowledge-base-skeleton*
*Completed: 2026-08-14*
