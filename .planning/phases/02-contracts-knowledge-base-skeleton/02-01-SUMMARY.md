---
phase: 02-contracts-knowledge-base-skeleton
plan: 01
subsystem: knowledge-base
tags: [sqlite-vec, migration, embedder, kb-schema]
requires: []
provides:
  - "db.connect() loads sqlite-vec on every connection (vec0 available before migrate)"
  - "kb_node / kb_edge / kb_vec (vec0 float[384] cosine) tables in the single DB file"
  - "kb.hash_embed + EMBED_DIM — deterministic offline 384-dim embedder"
  - "shared embed pytest fixture"
affects:
  - src/catalyst_trader/db.py
  - tests/conftest.py
tech-stack:
  added: ["sqlite-vec>=0.1.9"]
  patterns: ["numbered-migration runner (unchanged)", "per-connection extension load", "deterministic offline embedder behind an injectable callable"]
key-files:
  created:
    - src/catalyst_trader/migrations/003_kb.sql
    - src/catalyst_trader/kb.py
    - tests/test_kb_schema.py
    - tests/test_kb_embed.py
  modified:
    - pyproject.toml
    - src/catalyst_trader/db.py
    - tests/conftest.py
decisions:
  - "Extension loaded in connect() (not migrate) so both prod + the shared db fixture get vec0 before migrate() runs"
  - "384-dim baked into vec0 DDL to align with the intended real embedder (MiniLM) — no re-migration on model swap"
  - "Deterministic sha256 hash embedder as the offline default; real model is a later one-line swap behind the callable"
metrics:
  duration: ~2min
  tasks: 3
  files: 7
  completed: 2026-08-14
---

# Phase 2 Plan 01: KB Skeleton Foundation Summary

Wave-0 substrate for the knowledge base: `sqlite-vec` pinned + loaded on every connection, migration `003_kb.sql` adding generic graph tables (`kb_node`/`kb_edge`) plus a `vec0 float[384] cosine` KNN table (`kb_vec`), and a deterministic offline `hash_embed` (384-dim, L2-normalized) with a shared `embed` fixture — zero network, zero ML deps.

## What Was Built

- **Task 1** — Added `sqlite-vec>=0.1.9` to `pyproject.toml` + venv; `db.connect()` now does `enable_load_extension(True); sqlite_vec.load(conn); enable_load_extension(False)` after `row_factory`, before `PRAGMA foreign_keys`. `migrate()`/`_pending()` untouched. Smoke test asserts `vec_version()` on the shared fixture. (commit 6685e49)
- **Task 2** — `migrations/003_kb.sql`: `kb_node` (CHECK-enum kind, ref_id, confidence), `kb_edge` (FK src/dst → kb_node, CHECK-enum rel, weight, attrs_json), `kb_vec` vec0 `float[384] distance_metric=cosine`, three indexes. Tests: tables exist + coexist with Phase-1 `catalyst`, CHECK enums reject bad values, 384-dim vector round-trips at distance ~0. (commit 19ce4c0)
- **Task 3** — `kb.py`: `EMBED_DIM=384` + `hash_embed()` (sha256 chunks → [-0.5,0.5] → L2-normalize). `embed` fixture in conftest returns it. Tests: dimension, determinism, distinctness, normalization. (commit 8767ad3)

## Verification

- `.venv/bin/pytest -q` → **188 passed** (179 Phase-1 + 9 new). The `db` fixture now loads sqlite-vec with no regression.
- Migration 003 applies on top of Phase-1 schema; kb_node/kb_edge/kb_vec coexist with `catalyst`.
- `vec_version()` returns `v0.1.9` on the shared fixture; 384-dim vector round-trips through `kb_vec`.

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. `hash_embed` is a deliberate, documented offline default (not a stub) — the injectable embedder swap point is called out with a `ponytail:` comment for a later phase when analog *quality* matters. KB write/query paths (insert_claim, analog_query, hedge/playbook) are intentionally deferred to later Phase-2 plans (02-02..02-04), as scoped.

## Self-Check: PASSED

All 4 created files present; all 3 task commits (6685e49, 19ce4c0, 8767ad3) in history.
