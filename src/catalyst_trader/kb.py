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


def _structural_filter(conn, filters: dict) -> set[int]:
    """Candidate catalyst node ids whose attrs match every key in `filters` (deterministic SQL).

    A scenario failing the structural filter never reaches the semantic rank, even if
    embedding-close. Empty filters -> every catalyst is a candidate.
    """
    sql = "SELECT id FROM kb_node WHERE kind='catalyst'"
    params: list = []
    for key, val in filters.items():
        sql += f" AND json_extract(attrs_json,'$.{key}')=?"
        params.append(val)
    return {r["id"] for r in conn.execute(sql, params).fetchall()}


def _with_outcome(conn, node_id: int, distance: float) -> dict:
    """Attach the catalyst's realized Outcome (via RESULTED_IN edge) so callers cite base rates."""
    cat = get_node(conn, node_id)
    row = conn.execute(
        "SELECT dst_id FROM kb_edge WHERE src_id=? AND rel='RESULTED_IN' ORDER BY id LIMIT 1",
        (node_id,),
    ).fetchone()
    outcome = get_node(conn, row["dst_id"]) if row is not None else None
    return {
        "node_id": node_id,
        "distance": distance,
        "catalyst": cat["attrs"] if cat else None,
        "outcome": outcome["attrs"] if outcome else None,
    }


def analog_query(conn, embed, context: str, filters: dict, k: int = 5) -> list[dict]:
    """Nearest past scenarios matching `filters`, ranked by semantic similarity to `context`,
    each with its realized Outcome. Structural SQL filter first, then KNN rank (KB-03).

    # ponytail: SQL-filter + python-set intersect avoids sqlite-vec's alpha metadata-filter API;
    #           brute-force KNN over hundreds of vecs is sub-ms. Over-fetch k*4 then intersect.
    """
    cand = _structural_filter(conn, filters)
    if not cand:
        return []
    q = serialize_float32(embed(context))
    rows = conn.execute(
        "SELECT node_id, distance FROM kb_vec WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
        (q, k * 4),
    ).fetchall()
    ranked = [r for r in rows if r["node_id"] in cand][:k]
    return [_with_outcome(conn, r["node_id"], r["distance"]) for r in ranked]


def _get_or_create_company(conn, ticker: str) -> int:
    """Company nodes are reference nodes (not claims) so they need no citation. Get-or-create by ticker."""
    row = conn.execute(
        "SELECT id FROM kb_node WHERE kind='company' AND json_extract(attrs_json,'$.ticker')=?",
        (ticker,),
    ).fetchone()
    if row is not None:
        return row["id"]
    return conn.execute(
        "INSERT INTO kb_node (kind, ref_id, attrs_json, confidence, created_at) "
        "VALUES ('company', NULL, ?, NULL, ?)",
        (json.dumps({"ticker": ticker}), _now()),
    ).lastrowid


def insert_hedge_peer(conn, name, peer, mechanism, payoff_direction, weight, evidence) -> int:
    """Store a hedge relationship for `name` as a CITED hedge_peer claim (KB-04).

    A hedge relationship is a claim, so it MUST carry a citation — routed through insert_claim so
    the provenance invariant is enforced atomically. Also writes a HEDGE_PEER edge between the two
    company nodes for graph traversal. `payoff_direction` sign is explicit: +1 correlated co-move,
    -1 inverse-payoff (PROJECT.md vs ARCHITECTURE.md readings) — store the sign, don't hard-code polarity.
    """
    if payoff_direction not in (-1, 1):
        raise ValueError(f"payoff_direction must be +1 or -1, got {payoff_direction!r}")
    if not evidence:
        raise ValueError("cannot store a hedge peer without a CITES->EvidenceSource edge")
    name_id = _get_or_create_company(conn, name)
    peer_id = _get_or_create_company(conn, peer)
    attrs = {"name": name, "peer": peer, "mechanism": mechanism,
             "payoff_direction": payoff_direction, "weight": weight}
    # insert_claim commits (companies included); then add the traversal edge and commit it.
    hp_id = insert_claim(conn, KBNode(kind="hedge_peer", attrs=attrs), evidence)
    add_edge(conn, name_id, "HEDGE_PEER", peer_id, weight=weight,
             attrs={"mechanism": mechanism, "payoff_direction": payoff_direction})
    conn.commit()
    return hp_id


def hedge_peers(conn, name: str) -> list[dict]:
    """Every hedge_peer claim for `name` with its mechanism, payoff_direction, weight, and citations."""
    rows = conn.execute(
        "SELECT id, attrs_json FROM kb_node WHERE kind='hedge_peer' "
        "AND json_extract(attrs_json,'$.name')=?",
        (name,),
    ).fetchall()
    out = []
    for r in rows:
        a = json.loads(r["attrs_json"])
        cites = conn.execute(
            "SELECT dst_id FROM kb_edge WHERE src_id=? AND rel='CITES'", (r["id"],)
        ).fetchall()
        evidence = [get_node(conn, c["dst_id"])["attrs"] for c in cites]
        out.append({
            "peer": a["peer"], "mechanism": a["mechanism"],
            "payoff_direction": a["payoff_direction"], "weight": a["weight"],
            "evidence": evidence,
        })
    return out


def insert_playbook(conn, scenario_type, scenario, strategy, confidence, evidence) -> int:
    """Store a playbook as a derived, cited claim (KB-05).

    Routed through insert_claim so the citation invariant holds — playbooks cite the outcomes they
    generalize from. `confidence` is a first-class kb_node column (surfaced by every query).
    """
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence must be in [0,1], got {confidence!r}")
    node = KBNode(
        kind="playbook",
        confidence=confidence,
        attrs={"scenario_type": scenario_type, "scenario": scenario, "strategy": strategy},
    )
    return insert_claim(conn, node, evidence)


def query_playbooks(conn, scenario_type: str) -> list[dict]:
    """Playbooks for `scenario_type`, confidence-desc, each surfacing its first-class confidence."""
    rows = conn.execute(
        "SELECT id, confidence, attrs_json FROM kb_node "
        "WHERE kind='playbook' AND json_extract(attrs_json,'$.scenario_type')=? "
        "ORDER BY confidence DESC",
        (scenario_type,),
    ).fetchall()
    out = []
    for r in rows:
        a = json.loads(r["attrs_json"])
        out.append({
            "id": r["id"], "confidence": r["confidence"],
            "scenario_type": a["scenario_type"], "scenario": a["scenario"], "strategy": a["strategy"],
        })
    return out


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
