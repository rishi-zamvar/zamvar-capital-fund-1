"""Retrieval v2 Task 2: inclusive UNION recall + rarity-weighted multi-axis rerank + confidence.

Two CEO-locked invariants under test:
  1. ALL-INCLUSIVE recall: the candidate pool is the UNION of catalysts sharing ANY axis
     (type / disease_area / mechanism_class / any setup) — a candidate sharing even ONE axis is
     NEVER hard-excluded; a candidate sharing NOTHING is not in the pool.
  2. Rarity-weighted rerank: on equal semantic distance, a candidate sharing a RARE setup outranks
     one sharing a COMMON setup (IDF). disease_area / mechanism_class matches lift score + surface in
     matched_axes. A far / axis-poor top-k is flagged "thin"; a tight, axis-rich top-k is "ok".

Backward-compat: v1 analog_query still returns the v1 shape (a list, not a dict), unchanged.
All offline: db.connect(":memory:") + kb.hash_embed + seeded nodes.
"""

from catalyst_trader import kb
from catalyst_trader.kb import EvidenceSource, KBNode, add_edge, insert_claim


def _seed(db, *, attrs, embed_text, move=0.0):
    ev = EvidenceSource(url="https://ct.gov/x", retrieved_at="2026-08-14", snippet_hash=embed_text)
    cid = insert_claim(db, KBNode(kind="catalyst", attrs=attrs), [ev],
                       embed=kb.hash_embed, embed_text=embed_text)
    oid = insert_claim(db, KBNode(kind="outcome", attrs={"move": move}), [ev])
    add_edge(db, cid, "RESULTED_IN", oid)
    db.commit()
    return cid


# ── UNION recall ──────────────────────────────────────────────────────────────

def test_union_recall_includes_disease_only_match_excludes_shared_nothing(db):
    # target query: type=pdufa, disease_area=nephrology, mechanism_class=x, setups=[rare]
    disease_only = _seed(db, attrs={"type": "earnings", "disease_area": "nephrology"},
                         embed_text="a nephrology name with a totally different setup")
    shares_nothing = _seed(db, attrs={"type": "earnings", "disease_area": "dermatology"},
                           embed_text="unrelated dermatology name")
    type_match = _seed(db, attrs={"type": "pdufa", "disease_area": "dermatology"},
                       embed_text="a pdufa name")

    res = kb.analog_query_v2(db, kb.hash_embed, "nephrology pdufa query",
                             ctype="pdufa", disease_area="nephrology",
                             mechanism_class=None, setups=None, k=10)
    ids = {a["node_id"] for a in res["analogs"]}
    assert disease_only in ids   # shares ONLY disease_area but is included (never hard-excluded)
    assert type_match in ids     # shares type
    assert shares_nothing not in ids  # shares no queried axis -> not in the union


def test_empty_union_returns_thin_zero(db):
    _seed(db, attrs={"type": "earnings", "disease_area": "dermatology"}, embed_text="x")
    res = kb.analog_query_v2(db, kb.hash_embed, "q",
                             ctype="pdufa", disease_area="nephrology",
                             mechanism_class="sirna-rnai", setups=["a-tag-nobody-has"], k=5)
    assert res["analogs"] == []
    assert res["retrieval_confidence"] == "thin"
    assert res["n_candidates"] == 0


# ── rarity-weighted rerank ────────────────────────────────────────────────────

def test_rarity_weights_idf_orders_rare_above_common(db):
    # COMMON setup present in many nodes; RARE setup in one -> rare weight > common weight.
    for i in range(8):
        _seed(db, attrs={"type": "pdufa", "setups": ["common-tag"]}, embed_text=f"c{i}")
    _seed(db, attrs={"type": "pdufa", "setups": ["rare-tag", "common-tag"]}, embed_text="r")

    rw = kb._rarity_weights(db, "setups")
    assert rw["rare-tag"] > rw["common-tag"]
    assert rw["common-tag"] >= 0.0  # a near-ubiquitous setup contributes ~0, never a penalty


def test_rare_setup_outranks_common_on_equal_distance(db):
    # make "common-tag" common so its IDF is low; "rare-tag" rare so its IDF is high.
    for i in range(8):
        _seed(db, attrs={"type": "pdufa", "setups": ["common-tag"]}, embed_text=f"filler {i}")
    # two candidates SAME embed_text (equal distance to the query), differing only in which
    # setup they share with the query {rare-tag, common-tag}.
    same = "identical embedding text for both candidates"
    rare_cand = _seed(db, attrs={"type": "pdufa", "setups": ["rare-tag"]}, embed_text=same)
    common_cand = _seed(db, attrs={"type": "pdufa", "setups": ["common-tag"]}, embed_text=same)

    res = kb.analog_query_v2(db, kb.hash_embed, same, ctype="pdufa", disease_area=None,
                             mechanism_class=None, setups=["rare-tag", "common-tag"], k=10)
    order = [a["node_id"] for a in res["analogs"]]
    assert order.index(rare_cand) < order.index(common_cand)  # rarer shared setup ranks higher


def test_disease_and_mechanism_matches_appear_in_matched_axes(db):
    ctx = "same text so distance is small"
    node = _seed(db, attrs={"type": "pdufa", "disease_area": "nephrology",
                            "mechanism_class": "april-blys-baff-fusion",
                            "setups": ["pivotal-company-defining-binary"]}, embed_text=ctx)
    res = kb.analog_query_v2(db, kb.hash_embed, ctx, ctype="pdufa", disease_area="nephrology",
                             mechanism_class="april-blys-baff-fusion",
                             setups=["pivotal-company-defining-binary"], k=5)
    matched = next(a for a in res["analogs"] if a["node_id"] == node)["matched_axes"]
    assert "disease_area" in matched
    assert "mechanism_class" in matched
    assert "setup:pivotal-company-defining-binary" in matched


# ── confidence ────────────────────────────────────────────────────────────────

def test_confidence_ok_when_tight_and_axis_rich(db):
    ctx = "a tightly matched pool query"
    for i in range(3):
        _seed(db, attrs={"type": "pdufa", "disease_area": "nephrology",
                         "mechanism_class": "april-blys-baff-fusion"}, embed_text=ctx)
    res = kb.analog_query_v2(db, kb.hash_embed, ctx, ctype="pdufa", disease_area="nephrology",
                             mechanism_class="april-blys-baff-fusion", setups=None, k=5)
    assert res["retrieval_confidence"] == "ok"


def test_confidence_thin_when_no_shared_axes(db):
    # candidates share only TYPE (recall axis, not a scored/matched axis) and are semantically far.
    for i in range(3):
        _seed(db, attrs={"type": "pdufa"}, embed_text=f"utterly unrelated distant text {i}")
    res = kb.analog_query_v2(db, kb.hash_embed, "a query with nothing in common at all",
                             ctype="pdufa", disease_area="nephrology",
                             mechanism_class="sirna-rnai", setups=None, k=5)
    # nodes recalled by type only -> matched_axes empty + far -> thin
    assert res["retrieval_confidence"] == "thin"


# ── backward-compat ───────────────────────────────────────────────────────────

def test_v1_analog_query_returns_list_shape_unchanged(db):
    _seed(db, attrs={"type": "pdufa"}, embed_text="pdufa readout")
    out = kb.analog_query(db, kb.hash_embed, "pdufa readout", filters={"type": "pdufa"}, k=5)
    assert isinstance(out, list)          # v1 still returns a list, not the v2 dict
    assert "matched_axes" not in out[0]   # v1 result shape untouched


# ── builder wiring ────────────────────────────────────────────────────────────

def test_builder_uses_analog_query_v2_and_captures_confidence(db, monkeypatch):
    from catalyst_trader.desk import builder, verifier
    from catalyst_trader.contracts import DebateVerdict

    # seed a pdufa cohort so the v2 union is non-empty
    for i in range(3):
        _seed(db, attrs={"type": "pdufa", "disease_area": "nephrology"},
              embed_text=f"pdufa nephrology {i}", move=(0.2 if i % 2 else -0.5))

    captured = {}
    real_v2 = kb.analog_query_v2

    def _spy(conn, embed, context, **kw):
        captured.update(kw)
        return real_v2(conn, embed, context, **kw)

    monkeypatch.setattr(builder.kb, "analog_query_v2", _spy)

    async def _narr(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"):
        return builder.BuilderNarrative(pair_rationale="ok")

    async def _cmp(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"):
        return verifier.AnalogComparability(comparable=True, reasons=["same-type"])

    monkeypatch.setattr(builder, "run_structured", _narr)
    monkeypatch.setattr(verifier, "run_structured", _cmp)

    v = DebateVerdict(
        thesis="pivotal pdufa likely approves", direction="positive", confidence=0.62,
        bull_strongest_point="x", bear_strongest_point="y",
        kill_criteria=["a CRL is issued"], evidence_refs=["tool:base_rate#abc"])
    cat = {"ticker": "ACME", "catalyst_type": "pdufa", "event_date": "2026-11-15",
           "event_date_end": "2026-11-22", "catalyst_id": "cat-1",
           "disease_area": "nephrology", "mechanism_class": "april-blys-baff-fusion"}

    import asyncio
    asyncio.get_event_loop().run_until_complete(
        builder.build(db, kb.hash_embed, v, cat, entry=100.0))

    # the builder threaded the catalyst's OWN axes into v2 recall (multi-axis, not setup-only)
    assert captured["ctype"] == "pdufa"
    assert captured["disease_area"] == "nephrology"
    assert captured["mechanism_class"] == "april-blys-baff-fusion"
