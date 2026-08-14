"""Analog query (KB-03): structural SQL filter THEN semantic KNN rank, returning each nearest
past scenario WITH its realized Outcome. A scenario failing the structural filter must never
surface, even when embedding-close; results are distance-ordered and carry outcome attrs.
"""

from catalyst_trader import kb
from catalyst_trader.kb import EvidenceSource, KBNode, add_edge, analog_query, insert_claim


def _seed_catalyst(db, *, attrs, embed_text, outcome_attrs):
    """Insert a cited catalyst claim (+vector) and a cited Outcome linked via RESULTED_IN."""
    ev = EvidenceSource(url="https://ct.gov/x", retrieved_at="2026-08-14", snippet_hash=embed_text)
    cid = insert_claim(
        db,
        KBNode(kind="catalyst", attrs=attrs),
        [ev],
        embed=kb.hash_embed,
        embed_text=embed_text,
    )
    oid = insert_claim(db, KBNode(kind="outcome", attrs=outcome_attrs), [ev])
    add_edge(db, cid, "RESULTED_IN", oid)
    db.commit()
    return cid


def test_structural_filter_excludes_nonmatching_even_if_semantically_close(db):
    # Two PDUFA catalysts and one non-PDUFA, all embedded on the SAME text so the non-PDUFA
    # one is a KNN tie — the structural filter must still drop it.
    ctx = "pdufa decision imminent"
    _seed_catalyst(db, attrs={"type": "pdufa", "n": 1}, embed_text=ctx, outcome_attrs={"move": +0.2})
    _seed_catalyst(db, attrs={"type": "pdufa", "n": 2}, embed_text=ctx, outcome_attrs={"move": -0.1})
    _seed_catalyst(db, attrs={"type": "earnings", "n": 3}, embed_text=ctx, outcome_attrs={"move": +0.5})

    results = analog_query(db, kb.hash_embed, ctx, filters={"type": "pdufa"})

    assert len(results) == 2
    assert all(r["catalyst"]["type"] == "pdufa" for r in results)
    assert all(r["catalyst"]["n"] != 3 for r in results)


def test_results_are_distance_ordered(db):
    _seed_catalyst(db, attrs={"type": "pdufa"}, embed_text="alpha readout", outcome_attrs={"move": +0.1})
    _seed_catalyst(db, attrs={"type": "pdufa"}, embed_text="beta unrelated topic", outcome_attrs={"move": -0.1})

    results = analog_query(db, kb.hash_embed, "alpha readout", filters={"type": "pdufa"})

    dists = [r["distance"] for r in results]
    assert dists == sorted(dists)
    assert results[0]["distance"] == 0.0  # exact context match ranks first


def test_each_result_carries_its_outcome(db):
    _seed_catalyst(db, attrs={"type": "pdufa"}, embed_text="crl prior cycle", outcome_attrs={"move": -0.3, "label": "crl"})

    results = analog_query(db, kb.hash_embed, "crl prior cycle", filters={"type": "pdufa"})

    assert len(results) == 1
    assert results[0]["outcome"] == {"move": -0.3, "label": "crl"}


def test_no_structural_candidates_returns_empty(db):
    _seed_catalyst(db, attrs={"type": "pdufa"}, embed_text="x", outcome_attrs={"move": 0.0})
    assert analog_query(db, kb.hash_embed, "x", filters={"type": "does_not_exist"}) == []
