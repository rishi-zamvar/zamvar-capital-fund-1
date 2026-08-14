---
phase: 02-contracts-knowledge-base-skeleton
plan: 03
subsystem: knowledge-base
tags: [sqlite, provenance, atomic-write, kb, anti-hallucination, tdd]
requires:
  - phase: 01-data-integrity-catalyst-feed
    provides: "store.insert_catalyst atomic reject-before-write + try/commit/except-rollback pattern"
  - phase: 02-contracts-knowledge-base-skeleton
    plan: 01
    provides: "kb.hash_embed/EMBED_DIM + migration 003 (kb_node/kb_edge/kb_vec) + db fixture loads sqlite-vec"
provides:
  - "catalyst_trader.kb.insert_claim: atomic, provenance-enforced claim write-path (rejects uncited claim, full rollback, no orphans)"
  - "KBNode / EvidenceSource pydantic models (kind validated against migration-003 enum; attrs_json property)"
  - "_upsert_evidence (dedup evidence_source on url+snippet_hash), add_edge (no-commit edge helper), get_node (attrs roundtrip)"
affects:
  - "Plan 02-04 (hedge HEDGE_PEER edges, playbook nodes) — routes all its writes through insert_claim + add_edge"
  - "Plan 02-05+ analog query (reads kb_node/kb_edge/kb_vec written here)"
tech-stack:
  added: []
  patterns:
    - "atomic reject-before-write + try/commit/except-rollback (lifted verbatim from store.insert_catalyst)"
    - "application-level transaction invariant for provenance (NOT a DB trigger — CONTEXT.md's explicit choice)"
    - "single enforced write-path: all claims route through kb.insert_claim, like Phase-1 routes through store.py"
    - "evidence dedup via json_extract(attrs_json,'$.snippet_hash'/'$.url')"
    - "pydantic v2 field_validator for kind enum (DB CHECK is the backstop)"
key-files:
  created:
    - tests/test_kb_provenance.py
    - tests/test_kb_store.py
  modified:
    - src/catalyst_trader/kb.py
key-decisions:
  - "CITES edge routed through the same add_edge helper Plan 02-04 will use — one edge-insert path, no fork"
  - "add_edge does NOT commit — it runs inside insert_claim's transaction and inside Plan 02-04's future writes"
  - "kind validated at the pydantic boundary AND by the SQLite CHECK (two layers, same as Phase 1)"
  - "evidence dedup keyed on (url, snippet_hash) so re-citing one source reuses its node instead of duplicating"
patterns-established:
  - "insert_claim(conn, node, evidence, embed=None, embed_text=None): reject empty evidence -> node -> per-evidence upsert+CITES -> optional kb_vec -> commit; rollback on any failure"
requirements-completed: [KB-01, KB-02]
duration: ~2min
completed: 2026-08-14
---

# Phase 2 Plan 03: Provenance-Enforced KB Claim Write-Path Summary

**`kb.insert_claim` is the KB's anti-hallucination spine at the DB boundary — a claim node without at least one `:CITES → EvidenceSource` edge is rejected before any write, and any mid-transaction failure rolls back completely so no orphan node/edge/vector survives. The shape is lifted verbatim from Phase-1's `store.insert_catalyst`; evidence is deduped on url+snippet_hash and one optional kb_vec row is written when an embedder is supplied.**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-08-14T22:11:36Z
- **Completed:** 2026-08-14T22:13:29Z
- **Tasks:** 2 (TDD)
- **Files modified:** 3 (2 created, 1 extended)

## Accomplishments

- **KB-02 (the phase's most important behavior):** `insert_claim` rejects an uncited claim (`evidence=[]`) with `ValueError` *before* any INSERT, and rolls back the whole transaction on any mid-insert failure — verified there is zero orphan node/edge/vec left behind in both the empty-evidence and forced-mid-transaction-failure cases.
- **KB-01:** a well-formed claim writes exactly one claim `kb_node` + one `evidence_source` `kb_node` + one `CITES` `kb_edge` + (with `embed_text`) one `kb_vec` row, all in one transaction.
- **Evidence dedup:** re-citing the same source (same url+snippet_hash) reuses the existing `evidence_source` node — two claims citing one source → one evidence node, two CITES edges.
- **Single write-path:** the CITES edge routes through the same `add_edge` helper Plan 02-04 will use for HEDGE_PEER, so there is one edge-insert path and no forked store; `get_node` round-trips `attrs` for downstream readers.

## Task Commits

1. **Task 1: RED — provenance rejection + atomic-rollback suite** — `6ebbcdb` (test)
2. **Task 2: GREEN — KBNode/EvidenceSource models + atomic insert_claim** — `292685f` (feat)

_TDD: RED (import fails — insert_claim/models absent, collection error) → GREEN (implemented; 10 KB tests + full 218 pass). No refactor needed — minimal on first pass._

## Files Created/Modified

- `src/catalyst_trader/kb.py` — added `_now`, `KBNode`, `EvidenceSource`, `_upsert_evidence`, `add_edge`, `insert_claim`, `get_node` (the deterministic embedder from Plan 02-01 is unchanged).
- `tests/test_kb_provenance.py` — reject-uncited (no orphan), mid-transaction failure (full rollback via monkeypatched `_upsert_evidence`), parametrized no-uncited-claim-ever-persists invariant.
- `tests/test_kb_store.py` — node+evidence+CITES+vector roundtrip, evidence dedup on re-cite, no-vector-without-embed_text, `get_node` attrs roundtrip.

## Decisions Made

- **CITES routed through `add_edge`** (not an inline INSERT in `insert_claim`) — Plan 02-04 needs `add_edge` for HEDGE_PEER anyway; one edge-insert path, no duplication.
- **`add_edge` does not commit** — it executes inside the caller's transaction, so it composes cleanly inside `insert_claim` and inside Plan 02-04's future multi-edge writes.
- **`kind` validated at two layers** — pydantic `field_validator` against the migration-003 enum, with the SQLite CHECK as the backstop (mirrors Phase-1's pydantic + DB double-check).

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — the KB is offline (deterministic hash embedder, no network/ML deps).

## Next Phase Readiness

- Plan 02-04 (hedge relationships + playbooks) can now route every claim through `kb.insert_claim` + `kb.add_edge` — the provenance invariant is enforced for it for free.
- Full suite green: `.venv/bin/pytest -q` → **218 passed**. No regression.
- Plan 02-04 is the last plan in this phase; analog query (Plan 02-05+ / KB-03) reads the tables written here.

## Self-Check: PASSED

Both created test files present; kb.py extended; both task commits (6ebbcdb, 292685f) in history.

---
*Phase: 02-contracts-knowledge-base-skeleton*
*Completed: 2026-08-14*
