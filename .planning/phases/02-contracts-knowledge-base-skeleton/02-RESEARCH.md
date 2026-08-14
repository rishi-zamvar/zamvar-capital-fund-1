# Phase 2: Contracts + Knowledge-Base Skeleton - Research

**Researched:** 2026-08-14
**Domain:** Provenance-enforced graph-shaped SQLite KB + sqlite-vec analog search + pydantic v2 inter-layer contracts
**Confidence:** HIGH (Phase 1 patterns, pydantic v2, env verified) / MEDIUM (sqlite-vec metadata-filter API — alpha, verify against installed version)

## Summary

Phase 2 extends Phase 1's single SQLite file with a graph-shaped knowledge layer and a pydantic-validated contract module. Nothing here needs new architecture — it is a mechanical extension of three Phase 1 patterns that already exist and are tested:

1. **Provenance write-path** (`store.py::insert_catalyst`): atomic transaction, rejects a row that lacks provenance *before* writing, rolls back on any mid-insert failure. The KB claim write-path is the same shape — reject a claim node with no `:CITES → EvidenceSource` edge, in one transaction. CONTEXT.md explicitly asks for this to be a **transaction-level invariant**, not a DB trigger — mirror `insert_catalyst`, do not invent a trigger.
2. **Numbered-migration runner** (`db.py::migrate`): drop `003_kb.sql` into `migrations/`, it applies automatically on next `connect()+migrate()`. The vec0 virtual table lives in the same file alongside the relational tables.
3. **Two-layer validation** (`models.py` field_validator + `store.py` re-check): pydantic rejects at the type boundary, the write function re-checks at the DB boundary. The KB and the contracts reuse this exactly.

The graph is tiny (~20 tickers, hundreds of nodes) so the lazy-and-correct choices win: **generic `kb_node` + `kb_edge` tables** (not per-type tables — one migration, migrates mechanically to Neo4j later), **brute-force KNN** over a `vec0` table (milliseconds at this scale, no ANN index needed), and an **injectable embedder callable defaulting to a deterministic stdlib hash embedder** so the whole KB tests with zero network and zero ML deps. Real local embeddings (model2vec, no torch) are a documented one-line swap, not a Phase 2 requirement.

**Primary recommendation:** Add `sqlite-vec` (only new dep), load it in `db.connect()`, add migration `003_kb.sql` (generic node/edge tables + one `vec0` table), write `kb.py` mirroring `store.py`'s atomic provenance-enforcing pattern, and a `contracts/` module of pydantic v2 models with `ConfigDict(extra="forbid")`. Structural-SQL-filter-then-KNN-rank for analog query. Hedge peers and playbooks are just edge/node kinds under the same provenance invariant.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Stack settled: **SQLite + sqlite-vec + pydantic v2**. Do not re-research the stack.
- **Extend the same DB file / migration chain** — build on `store.py`, `db.py`, `models.py`; add migration 003+. Do NOT create a parallel store.
- Borrow contract shapes from `research/ARCHITECTURE.md`'s JSON contracts section.
- **Provenance enforced at the KB write path**: a claim node without a `:CITES → EvidenceSource` edge is rejected (schema violation), as a **transaction-level invariant**, mirroring Phase 1's no-LLM-date write-path.
- Contracts are pydantic-validated; **malformed payloads rejected at the boundary**.
- **Full test coverage / TDD** — tests before logic.
- **Simplicity + readability; minimal deps** — sqlite-vec is the only new one.

### Claude's Discretion
Discuss skipped. Follow ROADMAP success criteria, PROJECT.md, CLAUDE.md STACK decisions. All KB design detail (table shape, embedder choice, dimension, analog-query mechanics) is discretionary within the locked constraints above.

### Deferred Ideas (OUT OF SCOPE)
None — discuss phase skipped.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| KB-01 | SQLite graph-shaped store + sqlite-vec for playbooks, memory, base rates, analogs | Generic `kb_node`/`kb_edge` tables + one `vec0` table in migration 003; loaded via `db.connect()`. See Standard Stack + Architecture Patterns. |
| KB-02 | Every stored claim carries a citation edge; writes without provenance are rejected | `kb.insert_claim()` mirrors `store.insert_catalyst()` — atomic txn, reject if no `EvidenceSource`, rollback on failure. See Pattern 1. |
| KB-03 | Analog query returns nearest past scenarios with outcomes | Two-tier: structural SQL filter on `kb_node` → KNN rank on `vec0` → JOIN to `Outcome` nodes. See Pattern 3. |
| KB-04 | Hedge-relationship sub-store: per name, inverse/peer + mechanism + payoff-direction + citation | Not a separate store — `kb_edge` rel=`HEDGE_PEER` with `attrs` {mechanism, payoff_direction ±1} + mandatory `:CITES`. See Pattern 4. |
| KB-05 | Playbook entries queryable + surface confidence | `kb_node` kind=`playbook`, confidence a first-class column; plain SELECT. Under the same provenance invariant. See Pattern 5. |
| (契约) | Pydantic contracts: AnalystSignal, DebateVerdict, TradeProposal, RiskAssessment, StrategyDossier, DiligenceDossier; malformed rejected | `contracts/` module, pydantic v2 `model_validate` + `extra="forbid"`. See Code Examples. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Minimal dependencies, boring over clever.** `sqlite-vec` is the only permitted new dep this phase. No torch/sentence-transformers in the required path — use the deterministic embedder default.
- **TDD, exhaustive edge cases, especially money-critical deterministic tools.** Every KB module and contract ships with tests before logic.
- **Env-first secrets** (N/A this phase — no external API keys needed; embeddings are local/deterministic).
- **Graphify: query the graph, don't re-read `src/`.** Re-index after this phase (it produces code).
- **Phase-completion HTML report** (`docs/phase-reports/phase-02-report.html`) and **TOKEN-NOTES.md** update are mandatory at phase close (planner/executor concern, flagged here so it isn't forgotten).

---

## Standard Stack

### Core (verified in this repo's environment)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `sqlite-vec` | 0.1.9 (PyPI, 2026-03-31) | `vec0` virtual table for KNN analog search in the same DB file | Zero-ops embedded vector search; brute-force is fine at this scale (~hundreds of vecs). The STACK.md decision. |
| `pydantic` | 2.13.4 (already pinned) | Inter-layer contract validation + KB domain models | Already the money-path validation layer (`models.py`). |
| SQLite | 3.53.3 (Homebrew python) | Relational + graph tables + vec0 host | Already the store. `>= 3.41` so `LIMIT` works in KNN (no `k=` workaround needed). |
| Python | 3.14.6 (`/opt/homebrew/bin/python3`) | Runtime | **`enable_load_extension` is AVAILABLE** (verified) — the macOS "system python disables it" gotcha does NOT apply here. |

### Supporting (optional, NOT required for Phase 2)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `model2vec` | latest | Real local static embeddings (~256-dim, no torch, CPU-fast, deterministic) | ONLY when analog *quality* matters (a later phase). Swap behind the embedder callable. Do not add in Phase 2. |
| `sentence-transformers` | latest | `all-MiniLM-L6-v2` (384-dim) local embeddings | Heavier (pulls torch). Avoid unless model2vec proves insufficient. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Generic `kb_node`/`kb_edge` tables | Per-type node tables (company, drug, trial…) | Per-type = more CHECK safety but N migrations + N write functions + rigid. Generic = one migration, one write-path, graph-shaped → mechanical Neo4j migration later. **Pick generic.** |
| Deterministic hash embedder (default) | model2vec / MiniLM in Phase 2 | Real embeddings give meaningful similarity but add a dep + break the "no-network test" property. Phase 2 is a *skeleton* — plumbing correctness, not analog quality. **Deterministic default, real model is a later swap.** |
| Brute-force KNN | ANN index | sqlite-vec has **no ANN index** (alpha). Irrelevant — brute-force over hundreds of vecs is sub-millisecond. |
| vec0 metadata-column pre-filter | SQL-filter-then-JOIN | vec0 metadata filtering is an alpha API (verify per version). The JOIN approach (filter relational tables → KNN → INNER JOIN on node_id) is version-robust and trivially fast here. **Prefer JOIN; treat metadata columns as an optional optimization.** |

**Installation:**
```bash
pip install sqlite-vec
```
Add to `pyproject.toml` `[project].dependencies`: `"sqlite-vec>=0.1.9"`.

**Version verification (already done):**
```
python3 -m pip show sqlite-vec   # NOT INSTALLED — must be added
python3 -c "import sqlite3; print(hasattr(sqlite3.connect(':memory:'),'enable_load_extension'))"  # True
python3 -c "import sqlite3; print(sqlite3.sqlite_version)"  # 3.53.3
```
`sqlite-vec` ships a vendored precompiled loadable extension (not a CPython C-extension), so it has no CPython ABI dependency — Python 3.14 compatibility is expected. Confirm import + `vec_version()` in a Wave-0 smoke test.

---

## Architecture Patterns

### Recommended module layout (extends existing `src/catalyst_trader/`)
```
src/catalyst_trader/
├── db.py                # MODIFY: connect() loads sqlite-vec extension
├── store.py             # unchanged (Phase 1)
├── models.py            # unchanged; add KB models OR put them in kb.py
├── kb.py                # NEW: node/edge/claim write-path + analog/hedge/playbook queries
├── contracts/           # NEW: pydantic v2 inter-layer models
│   └── __init__.py      #      AnalystSignal, DebateVerdict, TradeProposal,
│                        #      RiskAssessment, StrategyDossier, DiligenceDossier
└── migrations/
    └── 003_kb.sql       # NEW: kb_node, kb_edge, kb_vec (vec0)
```
`ponytail: one kb.py, one migration, one contracts module. No package explosion for a skeleton.`

### Pattern 1: Provenance-enforced claim write-path (KB-02) — mirror `insert_catalyst`
**What:** A "claim" node (any factual assertion — an Outcome, a hedge relationship, a playbook base rate) may not be committed without at least one `:CITES → EvidenceSource` edge. Enforce in ONE transaction, exactly like `store.insert_catalyst` rejects a source-less catalyst.
**When:** every write of a claim-bearing node/edge.
**Two enforcement layers (same as Phase 1):**
1. Pydantic: the KB claim model has `cites: list[EvidenceRef]` with a `field_validator` that raises if empty (copy `_at_least_one_source`).
2. Write function: re-check `if not cites: raise ValueError(...)` *before* any INSERT; wrap node+edge inserts in try/commit/except-rollback.
```python
# kb.py — shape lifted verbatim from store.insert_catalyst
def insert_claim(conn, node: KBNode, evidence: list[EvidenceSource]) -> int:
    if not evidence:
        raise ValueError("cannot store a claim without a CITES→EvidenceSource edge")
    try:
        nid = conn.execute(
            "INSERT INTO kb_node (kind, ref_id, attrs_json, confidence, created_at) "
            "VALUES (?,?,?,?,?)",
            (node.kind, node.ref_id, node.attrs_json, node.confidence, _now()),
        ).lastrowid
        for ev in evidence:
            eid = _upsert_evidence(conn, ev)          # EvidenceSource node
            conn.execute(
                "INSERT INTO kb_edge (src_id, rel, dst_id, attrs_json) VALUES (?,?,?,?)",
                (nid, "CITES", eid, None),
            )
        conn.commit()
        return nid
    except Exception:
        conn.rollback()
        raise
```
**Trade-off:** application-level invariant (CONTEXT.md's explicit choice) not a DB trigger — a `model_construct` bypass or raw SQL could sidestep it, same limitation Phase 1 accepts. Keep ALL KB writes routed through `kb.py` (no agent writes raw SQL), exactly as Phase 1 routes everything through `store.py`.

### Pattern 2: Graph-shaped generic tables (KB-01)
**What:** two tables model the whole graph.
```sql
-- 003_kb.sql
CREATE TABLE kb_node (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN
    ('company','drug','indication','trial','catalyst','outcome',
     'trade','playbook','evidence_source','prediction','hedge_peer')),
  ref_id INTEGER,                    -- optional link to Phase-1 rows (e.g. catalyst.id) — DON'T copy data in
  attrs_json TEXT,                   -- kind-specific payload
  confidence REAL,                   -- KB-05: playbooks/predictions surface confidence here
  created_at TEXT NOT NULL
);
CREATE TABLE kb_edge (
  id INTEGER PRIMARY KEY,
  src_id INTEGER NOT NULL REFERENCES kb_node(id),
  rel TEXT NOT NULL CHECK (rel IN
    ('DEVELOPS','TARGETS','TESTED_IN','ABOUT','RESULTED_IN','PLACED_ON',
     'USED_PLAYBOOK','REALIZED','MADE_BY','CITES','ANALOG_OF','HEDGE_PEER')),
  dst_id INTEGER NOT NULL REFERENCES kb_node(id),
  weight REAL,                       -- ANALOG_OF similarity, HEDGE_PEER strength
  attrs_json TEXT,                   -- HEDGE_PEER: {mechanism, payoff_direction:+1/-1}
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_edge_src ON kb_edge(src_id, rel);
CREATE INDEX idx_edge_dst ON kb_edge(dst_id, rel);
CREATE INDEX idx_node_kind ON kb_node(kind);
```
**Why generic over per-type:** the graph is tiny and mostly append; typed CHECK enums give the safety that matters; one write-path enforces provenance uniformly; migrating to Neo4j later is `MATCH`-able node/edge dumps. Per-type tables would be premature structure.
`ponytail: kb_node.ref_id points at Phase-1 catalyst rows, we do NOT migrate catalyst data into the graph. Two layers, loosely joined by id.`

### Pattern 3: Analog query — structural filter THEN semantic rank (KB-03)
**What:** two-tier, cheapest-first (ARCHITECTURE.md Q4).
1. **Structural (SQL):** filter `kb_node` where kind='catalyst' AND attrs match {type, phase, indication_class, market_cap_bucket} → candidate node ids. Deterministic, explainable, covers most cases.
2. **Semantic (KNN):** KNN over `kb_vec` restricted to / re-ranked against the candidate set, then traverse `RESULTED_IN` edges to the `Outcome` nodes so callers cite realized base rates, not vibes.
```python
def analog_query(conn, embed, context: str, filters: dict, k: int = 5):
    cand = _structural_filter(conn, filters)           # set[int] of kb_node.id
    q = serialize_float32(embed(context))
    rows = conn.execute(
        "SELECT v.node_id, v.distance FROM kb_vec v "
        "WHERE v.embedding MATCH ? AND k = ? ORDER BY distance", (q, k * 4)
    ).fetchall()
    ranked = [r for r in rows if r["node_id"] in cand][:k]  # JOIN in python — set is tiny
    return [_with_outcome(conn, r["node_id"], r["distance"]) for r in ranked]
```
**Trade-off:** over-fetch `k*4` from KNN then filter in python — trivial at this scale and immune to sqlite-vec's alpha metadata-filter API churn. Upgrade to vec0 metadata/partition columns only if a profile ever shows it matters.

### Pattern 4: Hedge sub-store is just edges (KB-04)
Per universe name, candidate peers are `HEDGE_PEER` edges from the name's node, `attrs_json = {"mechanism": "...", "payoff_direction": +1}` (sign: +1 co-move correlated-long hedge, −1 inverse), `weight` = correlation strength. Because it is a **claim**, it goes through `insert_claim` → mandatory `:CITES → EvidenceSource`. Query = `SELECT ... FROM kb_edge WHERE src_id=? AND rel='HEDGE_PEER'`.
> Note: PROJECT.md's hedge is a *correlated long* (positive co-move offsetting sector/market risk), while ARCHITECTURE.md says "inverse-payoff." Store the sign explicitly in `payoff_direction` so both readings are representable and cited — don't hard-code one polarity.

### Pattern 5: Playbook store (KB-05)
`kb_node` kind='playbook', `confidence` is a first-class column (surfaced by every query), `attrs_json = {"scenario": ..., "strategy": ...}`. Queryable via plain SELECT ordered by confidence. Playbooks are derived claims → also under `insert_claim` (cite the outcomes they generalize from).
```sql
SELECT id, confidence, attrs_json FROM kb_node
WHERE kind='playbook' AND json_extract(attrs_json,'$.scenario_type')=?
ORDER BY confidence DESC;
```

### Anti-Patterns to Avoid
- **DB trigger for provenance.** CONTEXT.md wants a transaction-level app invariant mirroring Phase 1. A trigger fires before the CITES edge is inserted in the same txn → false rejects. Enforce in `kb.py`.
- **Per-type node tables.** Premature structure for a hundreds-of-nodes graph; N migrations for zero benefit.
- **Copying Phase 1's `catalyst` rows into `kb_node`.** Reference by `ref_id`; don't duplicate/desync data.
- **Adding torch/sentence-transformers this phase.** Violates minimal-deps; breaks no-network tests. Deterministic embedder default.
- **Uncited claims via raw SQL.** All KB writes route through `kb.py`, like Phase 1 routes through `store.py`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Vector KNN search | A python cosine loop over a JSON blob column | `sqlite-vec` `vec0` + `MATCH ... ORDER BY distance` | Correct distance math, binary storage, `distance_metric=cosine`, milliseconds. |
| Float→blob serialization | `struct.pack` by hand | `sqlite_vec.serialize_float32(list)` | Exact binary format vec0 expects. |
| Migration/versioning | New bootstrap code | Existing `db.migrate` — drop `003_kb.sql` | Already numbered, idempotent, tested. |
| Provenance atomicity | New transaction wrapper | Copy `store.insert_catalyst`'s try/commit/except-rollback | Proven Phase-1 money-path pattern. |
| Contract boundary rejection | Manual key/type checks | pydantic `model_validate` + `ConfigDict(extra="forbid")` | Rejects missing/extra/mistyped fields in one call. |

**Key insight:** every piece of this phase is a re-application of an existing Phase-1 pattern or a one-liner from sqlite-vec/pydantic. The only genuinely new code is the ~2 KB tables, the analog-query filter, and the six contract models.

---

## Common Pitfalls

### Pitfall 1: Extension not loaded before migration 003 runs
**What goes wrong:** `CREATE VIRTUAL TABLE ... USING vec0` fails with "no such module: vec0" when `migrate()` runs, because the extension is per-connection and must be loaded first.
**Why:** sqlite-vec is a loadable extension, not compiled-in.
**How to avoid:** load it inside `db.connect()` so EVERY connection (prod + the `db` test fixture) has it before `migrate()`:
```python
# db.py connect()
import sqlite_vec
conn = sqlite3.connect(path if path is not None else settings.db_path)
conn.row_factory = sqlite3.Row
conn.enable_load_extension(True)
sqlite_vec.load(conn)
conn.enable_load_extension(False)
conn.execute("PRAGMA foreign_keys = ON")
```
**Warning sign:** tests using the `db` fixture fail only on the vec table.

### Pitfall 2: vec0 dimension is baked into DDL
**What goes wrong:** changing embedder dimension later requires a new migration + re-embed; you can't ALTER it.
**How to avoid:** pick a dimension now aligned to the intended real embedder and keep it a named constant. Recommend **384** (MiniLM standard) and have the deterministic default embedder emit 384-dim L2-normalized vectors, so swapping to a real 384-dim model needs no migration.

### Pitfall 3: cosine vs L2
**What goes wrong:** default distance is L2; semantic similarity wants cosine, and unnormalized vectors make L2 misleading.
**How to avoid:** declare `contents_embedding float[384] distance_metric=cosine` in the vec0 DDL AND L2-normalize embeddings (the deterministic embedder normalizes too).

### Pitfall 4: sqlite-vec is pre-v1 (alpha) — API churn
**What goes wrong:** metadata-column / partition-key filtering syntax has moved between alpha releases.
**How to avoid:** pin `sqlite-vec` in pyproject; keep the analog query on the version-robust **SQL-filter + python-set JOIN** (Pattern 3), not on vec0 metadata WHERE clauses. Add one smoke test asserting `vec_version()`.

### Pitfall 5: Contract silently accepts LLM garbage
**What goes wrong:** pydantic by default ignores unknown fields — an LLM hallucinating extra keys or the wrong shape passes validation.
**How to avoid:** `model_config = ConfigDict(extra="forbid")` on every contract, `Field(ge=-1, le=1)` on `score`, `Field(ge=0, le=1)` on `confidence`, and a `field_validator` requiring non-empty `evidence_ref` on each `key_finding` (the anti-hallucination boundary — mirror `_at_least_one_source`).

---

## Code Examples

### Load sqlite-vec + serialize a vector (verified against official python docs)
```python
# Source: https://alexgarcia.xyz/sqlite-vec/python.html
import sqlite3, sqlite_vec
from sqlite_vec import serialize_float32

db = sqlite3.connect(":memory:")
db.enable_load_extension(True)
sqlite_vec.load(db)
db.enable_load_extension(False)
db.execute("CREATE VIRTUAL TABLE kb_vec USING vec0(node_id integer primary key, embedding float[384] distance_metric=cosine)")
db.execute("INSERT INTO kb_vec(node_id, embedding) VALUES (?, ?)", (1, serialize_float32([0.1]*384)))
rows = db.execute(
    "SELECT node_id, distance FROM kb_vec WHERE embedding MATCH ? ORDER BY distance LIMIT 5",
    (serialize_float32([0.1]*384),),
).fetchall()
```

### Deterministic, dependency-free embedder (default; test fallback)
```python
# kb.py — no network, no ML dep; stable vectors for TDD.
import hashlib, struct
def hash_embed(text: str, dim: int = 384) -> list[float]:
    out, i = [], 0
    while len(out) < dim:
        h = hashlib.sha256(f"{text}#{i}".encode()).digest()
        out += [b / 255.0 - 0.5 for b in h]; i += 1
    v = out[:dim]
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]   # L2-normalized for cosine
# ponytail: hash embedder = plumbing only, not semantic quality.
#           swap `embed=model2vec_encode` when analog quality matters (later phase).
```
> `demo()` self-check: assert `len(hash_embed("x"))==384`, `hash_embed("x")==hash_embed("x")` (deterministic), and `abs(sum(c*c for c in hash_embed("x"))-1.0) < 1e-6` (normalized).

### Contract with strict boundary rejection (pydantic v2)
```python
# contracts/__init__.py
from pydantic import BaseModel, ConfigDict, Field, field_validator

class KeyFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim: str
    evidence_ref: str = Field(min_length=1)   # anti-hallucination: no source → reject
    source_url: str | None = None

class AnalystSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dimension: str
    ticker: str
    catalyst_id: str
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    key_findings: list[KeyFinding]
    kb_analogs_queried: list[str] = []
    unknowns: list[str] = []

    @field_validator("key_findings")
    @classmethod
    def _needs_evidence(cls, v):
        if not v:
            raise ValueError("an AnalystSignal must carry at least one sourced key_finding")
        return v

# boundary use: raises pydantic.ValidationError on malformed LLM payload
signal = AnalystSignal.model_validate(payload_dict)
```
Remaining contracts (`DebateVerdict`, `TradeProposal`, `RiskAssessment`, `StrategyDossier`, `DiligenceDossier`) follow the exact field lists in ARCHITECTURE.md §"Pipeline 1 structured contracts" and §"Pipeline 2" — same `extra="forbid"` + evidence-ref discipline. `StrategyDossier`/`DiligenceDossier` embed the sub-contracts as typed fields.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Kùzu embedded graph (PROJECT.md original) | SQLite graph-shaped + sqlite-vec | Kùzu archived Oct 2025 (Apple acquihire) | Confirmed by STACK.md; do NOT use Kùzu. |
| pydantic v1 validators (`@validator`) | pydantic v2 `@field_validator` + `model_config=ConfigDict` | pydantic 2.x | Repo already on 2.13.4; use v2 idioms only. |
| KNN with `k=` in WHERE | `ORDER BY distance LIMIT n` | SQLite ≥ 3.41 | Env has 3.53.3 → use `LIMIT`. |

**Deprecated/outdated:** Kùzu upstream (archived); pydantic v1 `@validator` / `class Config`.

---

## Open Questions

1. **Exact vec0 metadata-filter syntax in 0.1.9**
   - What we know: metadata/partition columns exist in sqlite-vec; the KNN doc page is a WIP stub, README doesn't show the current syntax.
   - What's unclear: precise WHERE-clause behavior in the installed alpha.
   - Recommendation: **avoid it** — use the SQL-filter + python-set JOIN (Pattern 3). Add one smoke test if the executor wants to try metadata columns; otherwise no dependency on the churny API.

2. **Real embedder choice (deferred)**
   - What we know: model2vec (no torch, ~256-dim, deterministic) or MiniLM (384-dim) are the local, no-paid-API options.
   - What's unclear: which the analyst layer will want — not a Phase 2 decision.
   - Recommendation: ship the injectable `embed` callable + deterministic default at 384-dim; pick the real model in the phase that needs analog *quality*.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python `enable_load_extension` | Loading sqlite-vec | ✓ | 3.14.6 Homebrew | (system python lacks it — Homebrew is in use, fine) |
| SQLite ≥ 3.41 | `LIMIT` in KNN | ✓ | 3.53.3 | — |
| `sqlite-vec` | KB-01/03 vector search | ✗ | — (0.1.9 on PyPI) | `pip install sqlite-vec`; no fallback needed |
| `pydantic` v2 | contracts + models | ✓ | 2.13.4 | — |
| `pytest` + `freezegun` | tests | ✓ | 9.1.1 / 1.5.5 | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies to install:** `sqlite-vec` (add to `pyproject.toml`, `pip install`). Verified installable path; ships vendored extension binary.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (+ pytest-cov, freezegun 1.5.5) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths=["tests"]`, `addopts="-ra"`) |
| Quick run command | `python3 -m pytest tests/test_kb_*.py tests/test_contracts.py -x -q` |
| Full suite command | `python3 -m pytest` |
| Shared fixture | `tests/conftest.py::db` (in-memory, migrated) — **must now load sqlite-vec via `db.connect()`** |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| KB-01 | vec0 table created + coexists with relational tables; node+embedding roundtrips | integration | `pytest tests/test_kb_store.py -x` | ❌ Wave 0 |
| KB-02 | claim without EvidenceSource is rejected AND leaves no orphan row (rollback) | unit | `pytest tests/test_kb_provenance.py -x` | ❌ Wave 0 |
| KB-03 | analog query = structural filter → KNN rank → returns nearest scenarios with their Outcome | integration | `pytest tests/test_kb_analog.py -x` | ❌ Wave 0 |
| KB-04 | HEDGE_PEER edge stores mechanism + payoff_direction sign + citation; rejected without citation | unit | `pytest tests/test_kb_hedge.py -x` | ❌ Wave 0 |
| KB-05 | playbook queryable, ordered by + surfacing confidence | unit | `pytest tests/test_kb_playbook.py -x` | ❌ Wave 0 |
| Contracts | each of 6 models validates a good payload; rejects extra field / missing evidence_ref / out-of-range score | unit | `pytest tests/test_contracts.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** the single relevant `pytest tests/test_kb_<x>.py -x` (< 5s each).
- **Per wave merge:** `python3 -m pytest tests/test_kb_*.py tests/test_contracts.py -q`.
- **Phase gate:** full `python3 -m pytest` green before `/gsd:verify-work`.

### Wave 0 Gaps
- [ ] Add `sqlite-vec>=0.1.9` to `pyproject.toml` + `pip install`.
- [ ] `db.py::connect()` — load sqlite-vec extension (so migrate + `db` fixture work).
- [ ] `migrations/003_kb.sql` — `kb_node`, `kb_edge`, `kb_vec` (vec0, float[384] cosine).
- [ ] `tests/test_kb_store.py`, `test_kb_provenance.py`, `test_kb_analog.py`, `test_kb_hedge.py`, `test_kb_playbook.py`, `test_contracts.py`.
- [ ] Optional conftest fixture: `embed` (the deterministic `hash_embed`) so KB tests share it.
- [ ] Smoke test asserting `SELECT vec_version()` returns a value (extension actually loaded).

---

## Sources

### Primary (HIGH confidence)
- Repo Phase-1 code (Graphify + direct read): `store.py::insert_catalyst` (atomic provenance pattern), `db.py::migrate/connect` (numbered-migration runner), `models.py` (pydantic v2 field_validator, `_at_least_one_source`), `migrations/001_init.sql`, `tests/conftest.py::db` fixture.
- `research/ARCHITECTURE.md` — JSON contract shapes (§Pipeline 1/2), graph node/edge schema (§Q4), provenance requirement, two-tier analog design.
- Local environment probe: Python 3.14.6, SQLite 3.53.3, `enable_load_extension` available, `sqlite-vec` NOT installed.
- sqlite-vec Python docs (load + `serialize_float32`): https://alexgarcia.xyz/sqlite-vec/python.html

### Secondary (MEDIUM confidence)
- sqlite-vec PyPI (0.1.9, 2026-03-31) + releases (0.1.10-alpha.4): https://pypi.org/project/sqlite-vec/ · https://github.com/asg017/sqlite-vec/releases
- sqlite-vec KNN docs (stub — LIMIT vs k=, distance_metric=cosine): https://alexgarcia.xyz/sqlite-vec/features/knn.html
- STACK.md (in CLAUDE.md): sqlite-vec no-ANN caveat, Kùzu archived, `enable_load_extension` gotcha.

### Tertiary (LOW confidence — flagged)
- vec0 metadata-column / partition-key filtering syntax: referenced in README but exact current-version syntax not confirmed → **design avoids depending on it** (Pattern 3 uses SQL-JOIN instead).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified in-env; sqlite-vec install path confirmed.
- Architecture / write-path: HIGH — mechanical extension of tested Phase-1 patterns.
- Analog query mechanics: MEDIUM-HIGH — two-tier is sound; deliberately routes around the alpha metadata-filter API.
- Contracts: HIGH — pydantic v2 already in use; shapes come straight from ARCHITECTURE.md.
- vec0 advanced filtering: LOW — alpha API, avoided by design.

**Research date:** 2026-08-14
**Valid until:** ~2026-09-14 (sqlite-vec is pre-v1; re-check version + KNN/metadata syntax before any future phase leans harder on it).
