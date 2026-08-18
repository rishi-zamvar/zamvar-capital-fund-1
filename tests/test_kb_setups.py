"""Setup-aware retrieval (quick-260818-l64 Task 2): a catalyst's `setups` LIST is a retrievable
filter axis. Money-adjacent invariants under test:
  - _structural_filter matches list-membership generically, ACROSS indications (the whole point),
  - a multi-tag list filter is ANY-overlap,
  - scalar filters are byte-for-byte unchanged (test_kb_analog.py must stay green),
  - analog_query surfaces a DISEASE-DISTANT setup-sibling under a list filter (reachability: not
    truncated out of the global k*4),
  - setup_filters is a thinness gate (never starve the KNN below min_analogs),
  - _analog_context carries no ticker.
"""

from catalyst_trader import kb
from catalyst_trader.desk import builder
from catalyst_trader.kb import EvidenceSource, KBNode, add_edge, analog_query, insert_claim


def _seed(db, *, attrs, embed_text, move=0.0):
    """A cited catalyst claim (+vector) with a realized outcome, filterable by its top-level attrs."""
    ev = EvidenceSource(url="https://ct.gov/x", retrieved_at="2026-08-14", snippet_hash=embed_text)
    cid = insert_claim(db, KBNode(kind="catalyst", attrs=attrs), [ev],
                       embed=kb.hash_embed, embed_text=embed_text)
    oid = insert_claim(db, KBNode(kind="outcome", attrs={"move": move}), [ev])
    add_edge(db, cid, "RESULTED_IN", oid)
    db.commit()
    return cid


def test_list_filter_matches_membership_across_indications(db):
    _seed(db, attrs={"type": "pdufa", "indication": "ALS", "setups": ["single-asset-microcap-binary"]},
          embed_text="als microcap binary")
    _seed(db, attrs={"type": "pdufa", "indication": "psoriasis", "setups": ["single-asset-microcap-binary"]},
          embed_text="psoriasis microcap binary")
    _seed(db, attrs={"type": "pdufa", "indication": "ALS", "setups": ["priced-in-derisked-readout"]},
          embed_text="als priced in")

    got = kb._structural_filter(db, {"setups": ["single-asset-microcap-binary"]})
    assert len(got) == 2  # both indications with the tag, NOT the priced-in node


def test_list_filter_is_any_overlap(db):
    _seed(db, attrs={"type": "pdufa", "setups": ["single-asset-microcap-binary"]}, embed_text="a")
    _seed(db, attrs={"type": "pdufa", "setups": ["financing-overhang-going-concern"]}, embed_text="b")
    _seed(db, attrs={"type": "pdufa", "setups": ["priced-in-derisked-readout"]}, embed_text="c")

    got = kb._structural_filter(
        db, {"setups": ["single-asset-microcap-binary", "financing-overhang-going-concern"]})
    assert len(got) == 2  # any-overlap: the two whose setups intersect the query list


def test_scalar_filter_unchanged_and_matches_list_attr(db):
    # a plain scalar filter behaves exactly as before (test_kb_analog covers the non-setups path)...
    _seed(db, attrs={"type": "pdufa", "setups": ["single-asset-microcap-binary"]}, embed_text="x")
    _seed(db, attrs={"type": "earnings", "setups": ["commercial-single-product-quality"]}, embed_text="y")
    assert len(kb._structural_filter(db, {"type": "pdufa"})) == 1
    # ...and a scalar setups query can still match a node whose setups is a LIST (json_each overlap).
    assert len(kb._structural_filter(db, {"setups": "single-asset-microcap-binary"})) == 1


def test_analog_query_surfaces_disease_distant_setup_sibling(db):
    # one setup-matched node with a DISEASE-DISTANT embed_text, buried behind many same-disease
    # non-setup nodes; a plain global KNN would truncate it — the list filter must surface it.
    for i in range(12):
        _seed(db, attrs={"type": "pdufa", "indication": "psoriasis", "setups": ["priced-in-derisked-readout"]},
              embed_text=f"psoriasis crowded benchmark readout {i}")
    _seed(db, attrs={"type": "pdufa", "indication": "ALS", "setups": ["single-asset-microcap-binary"]},
          embed_text="completely unrelated als nanocap survival binary", move=-0.8)

    results = analog_query(db, kb.hash_embed, "psoriasis crowded benchmark readout query",
                           filters={"type": "pdufa", "setups": ["single-asset-microcap-binary"]})
    assert len(results) == 1
    assert results[0]["catalyst"]["indication"] == "ALS"  # the cross-disease sibling is reachable


def test_setup_filters_thinness_gate(db):
    for i in range(3):  # only 3 microcap nodes — below the default min_analogs=5
        _seed(db, attrs={"type": "pdufa", "setups": ["single-asset-microcap-binary"]}, embed_text=f"m{i}")

    thin = kb.setup_filters(db, "pdufa", ["single-asset-microcap-binary"])
    assert thin == {"type": "pdufa"}  # thin cohort -> type-only, never starve the KNN

    for i in range(5):  # now a healthy cohort
        _seed(db, attrs={"type": "pdufa", "setups": ["single-asset-microcap-binary"]}, embed_text=f"n{i}")
    healthy = kb.setup_filters(db, "pdufa", ["single-asset-microcap-binary"])
    assert healthy == {"type": "pdufa", "setups": ["single-asset-microcap-binary"]}


def test_setup_filters_empty_setups_is_type_only(db):
    assert kb.setup_filters(db, "pdufa", None) == {"type": "pdufa"}
    assert kb.setup_filters(db, "pdufa", []) == {"type": "pdufa"}


def test_analog_context_has_no_ticker():
    from catalyst_trader.contracts import DebateVerdict

    # the builder passes only (verdict, ctype) now — the target/ticker is never threaded into context.
    v = DebateVerdict(
        thesis="pivotal likely approves on a met endpoint", direction="positive", confidence=0.6,
        bull_strongest_point="x", bear_strongest_point="y",
        kill_criteria=["a CRL is issued"], evidence_refs=["tool:base_rate#abc"])
    ctx = builder._analog_context(v, "pdufa")
    assert "ACME" not in ctx  # the caller's ticker never appears — identity-clustering removed
    assert "pdufa catalyst" in ctx and v.thesis in ctx
