"""Happy-path KB write roundtrip (KB-01): a well-formed claim writes exactly one claim node,
one evidence_source node, one CITES edge, and (with embed_text) one kb_vec row — atomically.
Re-citing the same source reuses the evidence node; get_node round-trips attrs.
"""

from catalyst_trader import kb
from catalyst_trader.kb import EvidenceSource, KBNode, get_node, insert_claim


def test_wellformed_claim_writes_node_evidence_edge_and_vector(db):
    ev = EvidenceSource(url="https://ct.gov/x", retrieved_at="2026-08-14", snippet_hash="h1", quote="q")
    nid = insert_claim(
        db,
        KBNode(kind="outcome", attrs={"result": "pass"}, confidence=0.8),
        [ev],
        embed=kb.hash_embed,
        embed_text="phase 3 readout positive",
    )

    assert db.execute("SELECT count(*) FROM kb_node WHERE kind='outcome'").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM kb_node WHERE kind='evidence_source'").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM kb_edge WHERE rel='CITES' AND src_id=?", (nid,)).fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM kb_vec WHERE node_id=?", (nid,)).fetchone()[0] == 1


def test_reciting_same_source_reuses_evidence_node(db):
    ev = EvidenceSource(url="https://ct.gov/x", retrieved_at="2026-08-14", snippet_hash="dup")
    insert_claim(db, KBNode(kind="outcome", attrs={"r": 1}), [ev])
    insert_claim(db, KBNode(kind="playbook", attrs={"r": 2}), [ev])

    # two claims, but only ONE evidence_source node (deduped on url+snippet_hash)
    assert db.execute("SELECT count(*) FROM kb_node WHERE kind='evidence_source'").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM kb_edge WHERE rel='CITES'").fetchone()[0] == 2


def test_claim_without_embed_text_writes_no_vector(db):
    ev = EvidenceSource(url="u", retrieved_at="t", snippet_hash="h")
    nid = insert_claim(db, KBNode(kind="prediction", attrs={"p": 0.6}), [ev])
    assert db.execute("SELECT count(*) FROM kb_vec WHERE node_id=?", (nid,)).fetchone()[0] == 0


def test_get_node_roundtrips_attrs(db):
    ev = EvidenceSource(url="u", retrieved_at="t", snippet_hash="h")
    attrs = {"scenario": "pdufa", "base_rate": 0.72}
    nid = insert_claim(db, KBNode(kind="playbook", attrs=attrs, confidence=0.9), [ev])

    node = get_node(db, nid)
    assert node is not None
    assert node["kind"] == "playbook"
    assert node["confidence"] == 0.9
    assert node["attrs"] == attrs
    assert get_node(db, 999999) is None
