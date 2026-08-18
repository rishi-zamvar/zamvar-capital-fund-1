"""PLAY-05/06: the load-bearing NO-LOOK-AHEAD retrieval gate.

The KB is built with full hindsight (allowed at construction); the no-look-ahead rule lives at
APPLICATION. analog_query(..., as_of=D) must return ONLY catalysts whose knowable_asof <= D (and
their realized outcomes — one gate covers both, because knowable_asof is the T+2 date). Plus the
conditional type/indication filter so tightening the cohort never starves the KNN below min_analogs.
"""

from catalyst_trader import kb
from catalyst_trader.kb import EvidenceSource, KBNode, add_edge, analog_query, insert_claim


def _seed_catalyst(db, *, attrs, embed_text, outcome_attrs=None):
    """Insert a cited catalyst claim (+vector) and, if outcome given, a cited Outcome via RESULTED_IN."""
    ev = EvidenceSource(url="https://ct.gov/x", retrieved_at="2026-08-14", snippet_hash=embed_text)
    cid = insert_claim(
        db, KBNode(kind="catalyst", attrs=attrs), [ev], embed=kb.hash_embed, embed_text=embed_text
    )
    if outcome_attrs is not None:
        oid = insert_claim(db, KBNode(kind="outcome", attrs=outcome_attrs), [ev])
        add_edge(db, cid, "RESULTED_IN", oid)
    db.commit()
    return cid


def _seed_two_dated(db):
    """One early, one late catalyst — same embed text so both are KNN-close; only the date differs."""
    ctx = "pdufa decision imminent"
    _seed_catalyst(db, attrs={"type": "pdufa", "n": 1, "knowable_asof": "2024-01-15"},
                   embed_text=ctx, outcome_attrs={"move": +0.2})
    _seed_catalyst(db, attrs={"type": "pdufa", "n": 2, "knowable_asof": "2025-06-15"},
                   embed_text=ctx, outcome_attrs={"move": -0.1})
    return ctx


def test_given_as_of_between_two_dates_when_query_then_only_earlier_catalyst_and_its_outcome(db):
    ctx = _seed_two_dated(db)

    results = analog_query(db, kb.hash_embed, ctx, filters={"type": "pdufa"}, as_of="2024-06-01")

    assert len(results) == 1
    assert results[0]["catalyst"]["n"] == 1
    assert results[0]["outcome"] == {"move": +0.2}  # the realized move is gated too (one gate)


def test_given_as_of_none_when_query_then_both_catalysts_returned_backward_compatible(db):
    ctx = _seed_two_dated(db)

    results = analog_query(db, kb.hash_embed, ctx, filters={"type": "pdufa"}, as_of=None)

    assert {r["catalyst"]["n"] for r in results} == {1, 2}


def test_given_as_of_after_both_dates_when_query_then_both_returned_gate_is_lte(db):
    ctx = _seed_two_dated(db)

    results = analog_query(db, kb.hash_embed, ctx, filters={"type": "pdufa"}, as_of="2026-01-01")

    assert {r["catalyst"]["n"] for r in results} == {1, 2}


def test_given_node_missing_knowable_asof_when_as_of_set_then_excluded_fail_safe(db):
    # NULL <= date -> NULL (falsy) in SQLite: an undated node is EXCLUDED under any set as_of.
    ctx = "pdufa decision imminent"
    _seed_catalyst(db, attrs={"type": "pdufa", "n": 99}, embed_text=ctx, outcome_attrs={"move": +0.3})

    assert analog_query(db, kb.hash_embed, ctx, filters={"type": "pdufa"}, as_of="2026-01-01") == []
    # ...but with as_of=None it still surfaces (no gate applied).
    assert len(analog_query(db, kb.hash_embed, ctx, filters={"type": "pdufa"}, as_of=None)) == 1


def _seed_indication_cohort(db, n, indication="HoFH"):
    for i in range(n):
        _seed_catalyst(db, attrs={"type": "pdufa", "indication": indication, "n": i},
                       embed_text=f"case {i}", outcome_attrs={"move": 0.1})


def test_given_thin_indication_cohort_when_conditional_filters_then_indication_dropped(db):
    _seed_indication_cohort(db, n=2)  # < min_analogs=5

    filt = kb.conditional_filters(db, ctype="pdufa", indication="HoFH", min_analogs=5)

    assert filt == {"type": "pdufa"}  # indication dropped so the KNN is not starved


def test_given_ample_indication_cohort_when_conditional_filters_then_indication_kept(db):
    _seed_indication_cohort(db, n=6)  # >= min_analogs=5

    filt = kb.conditional_filters(db, ctype="pdufa", indication="HoFH", min_analogs=5)

    assert filt == {"type": "pdufa", "indication": "HoFH"}


def test_given_no_indication_when_conditional_filters_then_type_only(db):
    assert kb.conditional_filters(db, ctype="pdufa") == {"type": "pdufa"}
