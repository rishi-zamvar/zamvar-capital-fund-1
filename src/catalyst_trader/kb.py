"""Knowledge-base write-path + default deterministic embedder.

The KB stores an L2-normalized vector per node in kb_vec (vec0 float[384] cosine). The default
embedder here is offline and dependency-free so the whole KB tests with zero network / zero ML deps.

Provenance invariant (KB-02): a claim node may not be committed without at least one
:CITES -> EvidenceSource edge. Enforced in ONE transaction, exactly like store.insert_catalyst
rejects a source-less catalyst — reject before write, roll back completely on any failure.

# ponytail: one write-path; all KB writes route through insert_claim, like Phase-1 routes through
#           store.py. No agent writes a claim via raw SQL — that would sidestep the invariant.
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

from pydantic import BaseModel, field_validator
from sqlite_vec import serialize_float32

EMBED_DIM = 384

# The kind/rel enums are the DB CHECK constraints (migration 003) — kept here so a bad value is
# rejected at the pydantic boundary too, not only at the SQLite backstop.
_NODE_KINDS = frozenset(
    {
        "company", "drug", "indication", "trial", "catalyst", "outcome",
        "trade", "playbook", "evidence_source", "prediction", "hedge_peer",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvidenceSource(BaseModel):
    """A citation: where a claim's fact came from. Deduped on (url, snippet_hash)."""

    url: str
    retrieved_at: str
    snippet_hash: str
    quote: str | None = None


class KBNode(BaseModel):
    """A graph node. `attrs` is the kind-specific payload, serialized to attrs_json on write."""

    kind: str
    ref_id: int | None = None  # optional link to a Phase-1 row (e.g. catalyst.id) — don't copy data
    attrs: dict = {}
    confidence: float | None = None

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, v: str) -> str:
        if v not in _NODE_KINDS:
            raise ValueError(f"unknown kb_node kind {v!r} (not in migration-003 enum)")
        return v

    @property
    def attrs_json(self) -> str:
        return json.dumps(self.attrs)


def _upsert_evidence(conn: sqlite3.Connection, ev: EvidenceSource) -> int:
    """Return the id of the evidence_source node for `ev`, inserting it if absent.

    Dedup on (snippet_hash, url) via json_extract so re-citing the same source reuses one node.
    """
    row = conn.execute(
        "SELECT id FROM kb_node WHERE kind='evidence_source' "
        "AND json_extract(attrs_json,'$.snippet_hash')=? "
        "AND json_extract(attrs_json,'$.url')=?",
        (ev.snippet_hash, ev.url),
    ).fetchone()
    if row is not None:
        return row["id"]
    attrs = json.dumps(
        {"url": ev.url, "retrieved_at": ev.retrieved_at, "snippet_hash": ev.snippet_hash, "quote": ev.quote}
    )
    return conn.execute(
        "INSERT INTO kb_node (kind, ref_id, attrs_json, confidence, created_at) "
        "VALUES ('evidence_source', NULL, ?, NULL, ?)",
        (attrs, _now()),
    ).lastrowid


def add_edge(conn, src_id, rel, dst_id, weight=None, attrs=None) -> int:
    """Insert one kb_edge (no commit — runs inside the caller's transaction). Used by insert_claim
    for CITES and by Plan 02-04 for HEDGE_PEER etc."""
    return conn.execute(
        "INSERT INTO kb_edge (src_id, rel, dst_id, weight, attrs_json, created_at) VALUES (?,?,?,?,?,?)",
        (src_id, rel, dst_id, weight, json.dumps(attrs) if attrs is not None else None, _now()),
    ).lastrowid


def insert_claim(conn, node: KBNode, evidence: list[EvidenceSource], embed=None, embed_text=None) -> int:
    """Persist a claim node + its CITES->EvidenceSource edges (+ optional vector) atomically.

    Shape lifted verbatim from store.insert_catalyst: reject before any write if there is no
    evidence, then node insert -> per-evidence upsert + CITES edge -> optional kb_vec row, all in
    one transaction that rolls back completely on any failure (no orphan node/edge/vec survives).
    """
    if not evidence:
        raise ValueError("cannot store a claim without a CITES->EvidenceSource edge")
    try:
        nid = conn.execute(
            "INSERT INTO kb_node (kind, ref_id, attrs_json, confidence, created_at) VALUES (?,?,?,?,?)",
            (node.kind, node.ref_id, node.attrs_json, node.confidence, _now()),
        ).lastrowid
        for ev in evidence:
            eid = _upsert_evidence(conn, ev)
            add_edge(conn, nid, "CITES", eid)
        if embed is not None and embed_text is not None:
            conn.execute(
                "INSERT INTO kb_vec (node_id, embedding) VALUES (?, ?)",
                (nid, serialize_float32(embed(embed_text))),
            )
        conn.commit()
        return nid
    except Exception:
        conn.rollback()
        raise


def get_node(conn, node_id: int) -> dict | None:
    """Return a node as a dict with `attrs` parsed from attrs_json, or None if absent."""
    row = conn.execute("SELECT * FROM kb_node WHERE id=?", (node_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["attrs"] = json.loads(d["attrs_json"]) if d["attrs_json"] else {}
    return d


def hash_embed(text: str, dim: int = EMBED_DIM) -> list[float]:
    """Deterministic, offline, L2-normalized embedding of `text` (default 384-dim).

    Same text -> same vector, no network, no ML dep. Not semantically meaningful — plumbing only.
    """
    out: list[float] = []
    i = 0
    while len(out) < dim:
        h = hashlib.sha256(f"{text}#{i}".encode()).digest()
        out += [b / 255.0 - 0.5 for b in h]
        i += 1
    v = out[:dim]
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]  # L2-normalized for cosine


# ponytail: hash embedder = plumbing only, not semantic quality; swap to model2vec/MiniLM behind
#           this callable when analog quality matters (later phase).
