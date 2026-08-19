"""Retrieval v2 Task 1: the idempotent axis writer + the three retrieval axes.

stamp_axes stamps setups[] (list) + disease_area (scalar) + mechanism_class (scalar) onto the
catalyst node by ref_id (the Phase-1 catalyst_id), mirroring backfill_outcome_fields' UPDATE
discipline. Money-adjacent invariants under test:
  - all three axes become retrievable via kb._structural_filter (list-membership + scalar paths),
  - idempotency: re-stamping the same values leaves attrs identical and never duplicates the node,
  - a missing cid RAISES (a re-tag can't silently no-op a node that isn't there).
"""

import json

import pytest

from catalyst_trader import kb
from catalyst_trader.kb import EvidenceSource, KBNode, add_edge, insert_claim
from catalyst_trader.playbook.store import stamp_axes


def _seed(db, *, cid, attrs=None, embed_text="x", move=0.0):
    """A cited catalyst claim (+vector +outcome) carrying ref_id=cid (the Phase-1 catalyst_id),
    the key stamp_axes finds a node by."""
    ev = EvidenceSource(url="https://ct.gov/x", retrieved_at="2026-08-14", snippet_hash=embed_text)
    node_id = insert_claim(db, KBNode(kind="catalyst", ref_id=cid, attrs=attrs or {"type": "pdufa"}),
                           [ev], embed=kb.hash_embed, embed_text=embed_text)
    oid = insert_claim(db, KBNode(kind="outcome", attrs={"move": move}), [ev])
    add_edge(db, node_id, "RESULTED_IN", oid)
    db.commit()
    return node_id


def test_stamp_axes_makes_all_three_axes_retrievable(db):
    node_id = _seed(db, cid=201)
    got = stamp_axes(db, 201, setups=["pivotal-company-defining-binary"],
                     disease_area="nephrology", mechanism_class="april-blys-baff-fusion")
    assert got == node_id

    # scalar paths
    assert kb._structural_filter(db, {"disease_area": "nephrology"}) == {node_id}
    assert kb._structural_filter(db, {"mechanism_class": "april-blys-baff-fusion"}) == {node_id}
    # list-membership path
    assert kb._structural_filter(db, {"setups": ["pivotal-company-defining-binary"]}) == {node_id}


def test_stamp_axes_is_idempotent_no_duplicate_node(db):
    _seed(db, cid=262)
    first = stamp_axes(db, 262, setups=["early-mid-stage-single-asset-signal"],
                       disease_area="oncology-solid", mechanism_class="small-molecule-kinase-targeted-onc")
    before = db.execute("SELECT attrs_json FROM kb_node WHERE id=?", (first,)).fetchone()["attrs_json"]
    n_before = db.execute("SELECT COUNT(*) AS c FROM kb_node WHERE kind='catalyst' AND ref_id=?",
                          (262,)).fetchone()["c"]

    second = stamp_axes(db, 262, setups=["early-mid-stage-single-asset-signal"],
                        disease_area="oncology-solid", mechanism_class="small-molecule-kinase-targeted-onc")
    after = db.execute("SELECT attrs_json FROM kb_node WHERE id=?", (second,)).fetchone()["attrs_json"]
    n_after = db.execute("SELECT COUNT(*) AS c FROM kb_node WHERE kind='catalyst' AND ref_id=?",
                         (262,)).fetchone()["c"]

    assert second == first          # same node id
    assert n_before == n_after == 1  # never duplicated
    assert json.loads(before) == json.loads(after)  # attrs unchanged


def test_stamp_axes_overwrites_not_appends(db):
    _seed(db, cid=273)
    stamp_axes(db, 273, setups=["priced-in-derisked-readout"],
               disease_area="respiratory", mechanism_class="monoclonal-antibody")
    node_id = stamp_axes(db, 273, setups=["financing-overhang-going-concern"],
                         disease_area="cardiovascular", mechanism_class="sirna-rnai")
    attrs = json.loads(db.execute("SELECT attrs_json FROM kb_node WHERE id=?", (node_id,)).fetchone()["attrs_json"])
    assert attrs["setups"] == ["financing-overhang-going-concern"]  # overwritten, not appended
    assert attrs["disease_area"] == "cardiovascular"
    assert attrs["mechanism_class"] == "sirna-rnai"


def test_stamp_axes_missing_cid_raises(db):
    with pytest.raises(ValueError):
        stamp_axes(db, 999999, setups=["x"], disease_area="nephrology", mechanism_class="other-na")


def test_stamp_axes_does_not_touch_outcome_or_edges(db):
    node_id = _seed(db, cid=318, move=-0.4)
    edges_before = db.execute("SELECT COUNT(*) AS c FROM kb_edge").fetchone()["c"]
    outcomes_before = db.execute("SELECT COUNT(*) AS c FROM kb_node WHERE kind='outcome'").fetchone()["c"]
    vecs_before = db.execute("SELECT COUNT(*) AS c FROM kb_vec").fetchone()["c"]

    stamp_axes(db, 318, setups=["contested-efficacy-adcom-risk"],
               disease_area="immunology-inflammation", mechanism_class="fusion-protein-fc")

    assert db.execute("SELECT COUNT(*) AS c FROM kb_edge").fetchone()["c"] == edges_before
    assert db.execute("SELECT COUNT(*) AS c FROM kb_node WHERE kind='outcome'").fetchone()["c"] == outcomes_before
    assert db.execute("SELECT COUNT(*) AS c FROM kb_vec").fetchone()["c"] == vecs_before  # no re-embed
    # the realized outcome is still reachable
    result = kb._with_outcome(db, node_id, 0.0)
    assert result["outcome"] == {"move": -0.4}


def test_v2_vocab_frozen_shape(db):
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "data" / "setup_taxonomy_v2.json"
    d = json.loads(path.read_text())
    assert len(d["setups"]) == 18
    assert len(d["disease_areas"]) == 20
    assert len(d["mechanism_classes"]) == 19
    assert d.get("tagging_rubric")  # the re-tag wave's rubric source
