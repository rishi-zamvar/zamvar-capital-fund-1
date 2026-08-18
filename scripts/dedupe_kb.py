"""Dedupe duplicate catalyst nodes in the KB (one per ref_id), safely and reversibly.

Duplicates arise ONLY from concurrent writers: insert_catalyst_record is idempotent on
(ref_id, content_sha), so two agents that extract the SAME cid into slightly different JSON produce
two nodes with different shas -> two catalyst nodes for one catalyst. analog_query / _structural_filter
do NOT dedup, so every duplicate is a separate KNN candidate and inflates cohort counts. This collapses
each ref_id to ONE node.

Keeper rule: KEEP max(id) per ref_id — the pipeline's OWN canonical choice (store._existing and
generalize both resolve "newest node per ref_id wins"). For the deliberate PDUFA move-anchor
re-inserts, the newer node is the corrected record, so newest-wins is also semantically right.

Two-phase, so a human/agent can audit BEFORE anything is destroyed:
  --archive <out.json>   scan dups, write FULL content of every would-be-dropped node (catalyst +
                         outcome + cited evidence + all edges) alongside the keeper snapshot. NO writes.
  --apply <out.json>     re-read the archive, re-verify keeper+drops still present, then delete in
                         FK-safe order (edges -> outcome+catalyst nodes -> orphaned evidence -> vec),
                         all in ONE transaction. Refuses if the live dup-set drifted from the archive.

FK note: foreign_keys=ON and kb_edge.src/dst REFERENCE kb_node(id) NO ACTION -> edges MUST be deleted
before the nodes they point at. Evidence nodes are SHARED (upsert by snippet_hash+url) so they are
deleted only when no CITES edge points at them any more.
"""
import argparse
import json
import sys

from catalyst_trader import db

DB = "catalyst.db"


def _dup_groups(conn):
    """{ref_id: [node_ids sorted asc]} for every catalyst ref_id with >1 node."""
    groups = {}
    for r in conn.execute(
        "SELECT ref_id, id FROM kb_node WHERE kind='catalyst' AND ref_id IS NOT NULL ORDER BY ref_id, id"
    ):
        groups.setdefault(r["ref_id"], []).append(r["id"])
    return {k: v for k, v in groups.items() if len(v) > 1}


def _node(conn, nid):
    r = conn.execute("SELECT id, kind, ref_id, attrs_json, confidence, created_at FROM kb_node WHERE id=?", (nid,)).fetchone()
    return dict(r) if r else None


def _edges(conn, nid):
    return [dict(r) for r in conn.execute(
        "SELECT id, src_id, rel, dst_id, weight, attrs_json, created_at FROM kb_edge WHERE src_id=? OR dst_id=?",
        (nid, nid),
    )]


def _outcome_id(conn, cat_id):
    r = conn.execute("SELECT dst_id FROM kb_edge WHERE src_id=? AND rel='RESULTED_IN' ORDER BY id LIMIT 1", (cat_id,)).fetchone()
    return r["dst_id"] if r else None


def _cited_evidence(conn, nid):
    return [r["dst_id"] for r in conn.execute("SELECT dst_id FROM kb_edge WHERE src_id=? AND rel='CITES'", (nid,))]


def _has_vec(conn, nid):
    return conn.execute("SELECT COUNT(*) c FROM kb_vec WHERE node_id=?", (nid,)).fetchone()["c"] > 0


def _snapshot(conn, cat_id):
    """Full recoverable snapshot of one catalyst record (catalyst + outcome + evidence + edges)."""
    out_id = _outcome_id(conn, cat_id)
    ev_ids = sorted(set(_cited_evidence(conn, cat_id) + (_cited_evidence(conn, out_id) if out_id else [])))
    return {
        "catalyst_node": _node(conn, cat_id),
        "catalyst_has_vec": _has_vec(conn, cat_id),
        "outcome_node": _node(conn, out_id) if out_id else None,
        "evidence_nodes": [_node(conn, e) for e in ev_ids],
        "edges": _edges(conn, cat_id) + (_edges(conn, out_id) if out_id else []),
    }


def archive(path):
    conn = db.connect(DB)
    groups = _dup_groups(conn)
    payload = {"db": DB, "keeper_rule": "max(id) per ref_id", "groups": []}
    for ref_id, ids in sorted(groups.items()):
        keeper = max(ids)
        drops = [i for i in ids if i != keeper]
        payload["groups"].append({
            "ref_id": ref_id,
            "keeper_id": keeper,
            "keeper_snapshot": _snapshot(conn, keeper),
            "drop_ids": drops,
            "drop_snapshots": {str(d): _snapshot(conn, d) for d in drops},
        })
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    n_drop = sum(len(g["drop_ids"]) for g in payload["groups"])
    print(f"ARCHIVED {len(payload['groups'])} dup cids, {n_drop} nodes to drop -> {path}")
    return payload


def apply(path):
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    conn = db.connect(DB)
    live = _dup_groups(conn)
    # Refuse if the live dup-set drifted from what we archived (a writer touched these since archive).
    archived = {g["ref_id"]: sorted(g["drop_ids"] + [g["keeper_id"]]) for g in payload["groups"]}
    for ref_id, ids in archived.items():
        if sorted(live.get(ref_id, [])) != ids:
            sys.exit(f"ABORT: cid {ref_id} dup-set drifted since archive (live={live.get(ref_id)}, archived={ids}). Re-archive.")
    conn.execute("BEGIN")
    dropped_cat = dropped_out = dropped_edge = dropped_vec = dropped_ev = 0
    try:
        for g in payload["groups"]:
            for cat_id in g["drop_ids"]:
                out_id = _outcome_id(conn, cat_id)
                ev_ids = set(_cited_evidence(conn, cat_id) + (_cited_evidence(conn, out_id) if out_id else []))
                node_ids = [cat_id] + ([out_id] if out_id else [])
                # 1) edges first (FK NO ACTION)
                for nid in node_ids:
                    dropped_edge += conn.execute("DELETE FROM kb_edge WHERE src_id=? OR dst_id=?", (nid, nid)).rowcount
                # 2) vec (catalyst only carries a vector)
                dropped_vec += conn.execute("DELETE FROM kb_vec WHERE node_id=?", (cat_id,)).rowcount
                # 3) the catalyst + outcome nodes
                dropped_out += conn.execute("DELETE FROM kb_node WHERE id=?", (out_id,)).rowcount if out_id else 0
                dropped_cat += conn.execute("DELETE FROM kb_node WHERE id=?", (cat_id,)).rowcount
                # 4) orphaned evidence (shared: delete only if no CITES points at it any more)
                for eid in ev_ids:
                    still = conn.execute("SELECT COUNT(*) c FROM kb_edge WHERE dst_id=? AND rel='CITES'", (eid,)).fetchone()["c"]
                    if still == 0:
                        dropped_ev += conn.execute("DELETE FROM kb_node WHERE id=? AND kind='evidence_source'", (eid,)).rowcount
        dang = conn.execute(
            "SELECT COUNT(*) c FROM kb_edge e WHERE NOT EXISTS(SELECT 1 FROM kb_node n WHERE n.id=e.src_id) "
            "OR NOT EXISTS(SELECT 1 FROM kb_node n WHERE n.id=e.dst_id)"
        ).fetchone()["c"]
        if dang:
            raise RuntimeError(f"post-delete dangling edges={dang} — rolling back")
        remaining = _dup_groups(conn)
        if remaining:
            raise RuntimeError(f"dups still present after delete: {list(remaining)} — rolling back")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    print(f"APPLIED: dropped {dropped_cat} catalyst, {dropped_out} outcome, {dropped_edge} edges, "
          f"{dropped_vec} vec, {dropped_ev} orphaned-evidence. 0 dangling, 0 dups remain.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive")
    ap.add_argument("--apply")
    a = ap.parse_args()
    if a.archive:
        archive(a.archive)
    elif a.apply:
        apply(a.apply)
    else:
        sys.exit("use --archive <out.json> or --apply <archive.json>")
