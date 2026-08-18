"""Offline TDD for the ATTRIBUTION back-half (playbook.store, Plan 07.5-04).

Every test is offline + free: records are built inline from the Plan-01 contract and embedded
with hash_embed (no fastembed, no network, no LLM). Asserts on kb_node/kb_edge/kb_vec rows
directly AND via the kb.analog_query round-trip, so the write shape and the read shape are both
proven. No live model is ever invoked (the extractor's complete_fn seam is not exercised here).
"""

from catalyst_trader import kb
from catalyst_trader.kb import hash_embed
from catalyst_trader.playbook.schema import (
    CatalystRecord,
    Citation,
    DriverClaim,
    NarrativeAfter,
    NarrativeBefore,
    compose_card,
)
from catalyst_trader.playbook.store import (
    assert_embedder_consistency,
    insert_catalyst_record,
)


def _record(cid=271, *, ctype="pdufa", move=0.052, thesis="clean pivotal, first-cycle approval"):
    """A minimal VALID CatalystRecord (Plan 01 contract) for the writer under test."""
    cite = Citation(url="https://ct.gov/x", quote="q", snippet_hash=f"h{cid}")
    return CatalystRecord(
        catalyst_id=cid,
        ticker="KRYS",
        catalyst_type=ctype,
        indication="DEB",
        modality="gene therapy",
        event_date="2023-02-17",
        knowable_asof="2023-02-22",
        outcome_label="approve" if move > 0 else "crl",
        signed_move=move,
        move_window="(-1,2)",
        confidence=0.7,
        drivers=[DriverClaim(factor="designations", value="BTD+PR",
                             evidence_quote="granted priority review", source_url="https://ct.gov/x")],
        narrative_before=NarrativeBefore(
            thesis=thesis, causal_setup="expedited stack", reference_class="orphan gene tx",
            variant_why="market underweighted designations",
            what_to_watch=["cmc 483"], what_would_change_our_mind=["surprise adcom"]),
        narrative_after=NarrativeAfter(
            what_happened="approved", why_narrative="clean pivotal held",
            surprise_vs_prior="low", which_disconfirmer_fired="none",
            lesson_rule="anchor to approval", process_grade="A"),
        citations=[cite],
    )


# ── node / edge / vec shapes ─────────────────────────────────────────────────

def test_given_record_when_insert_then_catalyst_and_outcome_nodes_written(db):
    cat_id = insert_catalyst_record(db, _record(), embed=hash_embed)
    cat = kb.get_node(db, cat_id)
    assert cat["kind"] == "catalyst"
    assert cat["ref_id"] == 271
    # structural-filter keys are TOP-LEVEL (json_extract-accessible)
    for key, val in [("knowable_asof", "2023-02-22"), ("type", "pdufa"), ("ticker", "KRYS"),
                     ("indication", "DEB"), ("modality", "gene therapy")]:
        got = db.execute(
            f"SELECT json_extract(attrs_json,'$.{key}') AS v FROM kb_node WHERE id=?", (cat_id,)
        ).fetchone()["v"]
        assert got == val, f"{key}: {got!r} != {val!r}"
    # exactly one outcome node, reached via RESULTED_IN
    out_row = db.execute(
        "SELECT dst_id FROM kb_edge WHERE src_id=? AND rel='RESULTED_IN'", (cat_id,)
    ).fetchone()
    assert out_row is not None
    assert kb.get_node(db, out_row["dst_id"])["kind"] == "outcome"


def test_given_record_when_insert_then_resulted_in_and_cites_on_both_nodes(db):
    cat_id = insert_catalyst_record(db, _record(), embed=hash_embed)
    out_id = db.execute(
        "SELECT dst_id FROM kb_edge WHERE src_id=? AND rel='RESULTED_IN'", (cat_id,)
    ).fetchone()["dst_id"]
    # CITES on BOTH the catalyst and the outcome node
    for nid in (cat_id, out_id):
        n = db.execute(
            "SELECT COUNT(*) AS c FROM kb_edge WHERE src_id=? AND rel='CITES'", (nid,)
        ).fetchone()["c"]
        assert n >= 1, f"node {nid} has no CITES edge"


def test_given_record_when_insert_then_single_vec_on_catalyst_only(db):
    cat_id = insert_catalyst_record(db, _record(), embed=hash_embed)
    out_id = db.execute(
        "SELECT dst_id FROM kb_edge WHERE src_id=? AND rel='RESULTED_IN'", (cat_id,)
    ).fetchone()["dst_id"]
    assert db.execute("SELECT COUNT(*) AS c FROM kb_vec WHERE node_id=?", (cat_id,)).fetchone()["c"] == 1
    assert db.execute("SELECT COUNT(*) AS c FROM kb_vec WHERE node_id=?", (out_id,)).fetchone()["c"] == 0


def test_given_record_when_insert_then_card_is_the_embedded_text(db):
    rec = _record()
    cat_id = insert_catalyst_record(db, rec, embed=hash_embed)
    # the catalyst vector equals hash_embed(compose_card(rec)) — the card is what got embedded
    from sqlite_vec import serialize_float32
    stored = db.execute("SELECT embedding FROM kb_vec WHERE node_id=?", (cat_id,)).fetchone()["embedding"]
    assert stored == serialize_float32(hash_embed(compose_card(rec)))


# ── signed move key (money path) via analog_query round-trip ──────────────────

def test_given_populated_when_analog_query_then_outcome_move_present_and_signed(db):
    insert_catalyst_record(db, _record(cid=1, move=+0.20), embed=hash_embed)
    insert_catalyst_record(db, _record(cid=2, move=-0.30), embed=hash_embed)
    results = kb.analog_query(db, hash_embed, compose_card(_record(cid=1)),
                              filters={"type": "pdufa"})
    assert results
    moves = [r["outcome"]["move"] for r in results]
    assert any(m > 0 for m in moves) and any(m < 0 for m in moves)  # SIGNED, not abs


# ── idempotency + content-hash re-write ──────────────────────────────────────

def test_given_same_record_twice_when_insert_then_idempotent_single_node(db):
    first = insert_catalyst_record(db, _record(), embed=hash_embed)
    second = insert_catalyst_record(db, _record(), embed=hash_embed)  # identical content
    assert first == second  # second call is a no-op, returns the existing id
    n = db.execute(
        "SELECT COUNT(*) AS c FROM kb_node WHERE kind='catalyst' AND ref_id=271"
    ).fetchone()["c"]
    assert n == 1


def test_given_changed_content_when_insert_then_rewritten_new_node(db):
    first = insert_catalyst_record(db, _record(thesis="v1 thesis"), embed=hash_embed)
    second = insert_catalyst_record(db, _record(thesis="v2 CHANGED thesis"), embed=hash_embed)
    assert second != first  # content-hash changed -> a new node
    n = db.execute(
        "SELECT COUNT(*) AS c FROM kb_node WHERE kind='catalyst' AND ref_id=271"
    ).fetchone()["c"]
    assert n == 2


# ── cite-or-drop (contract-level: a record cannot exist without a citation) ───

def test_given_no_citations_when_build_record_then_rejected_before_any_write(db):
    import pytest
    with pytest.raises(ValueError):
        rec = _record()
        rec.citations = []
        rec.model_validate(rec.model_dump())  # re-validate -> cite-or-drop rejects


# ── warm cohort: cold_start flips False once a cohort is populated ────────────

def test_given_min_analogs_populated_when_estimate_then_cold_start_false(db):
    from catalyst_trader.quant.events import catalyst_move_estimate
    moves = [+0.10, +0.15, -0.08, -0.12, +0.05, -0.20]  # 6 >= min_analogs (5)
    for i, m in enumerate(moves):
        insert_catalyst_record(db, _record(cid=100 + i, ctype="trial_readout", move=m,
                                           thesis=f"readout thesis {i}"), embed=hash_embed)
    results = kb.analog_query(db, hash_embed, "readout thesis 0",
                              filters={"type": "trial_readout"}, k=10)
    assert len(results) >= 5  # the cohort is warm
    got = [r["outcome"]["move"] for r in results]
    up = [m for m in got if m > 0]
    down = [abs(m) for m in got if m < 0]
    params = kb.load_params(db, "trial_readout")
    est = catalyst_move_estimate(0.5, up, down, params)
    assert est.detail["cold_start"] is False


# ── CRITICAL NIT 2: embedder-identity guard (populate vs query drift) ─────────

def test_given_matching_embedder_when_assert_then_ok(db):
    insert_catalyst_record(db, _record(), embed=hash_embed)
    assert_embedder_consistency(db, hash_embed)  # same embedder -> no raise


def test_given_mismatched_embedder_when_assert_then_raises(db):
    import pytest

    def fake_local(text):  # a DIFFERENT embedder identity than the populate-time hash_embed
        return hash_embed(text)

    insert_catalyst_record(db, _record(), embed=hash_embed)
    with pytest.raises(ValueError, match="embedder"):
        assert_embedder_consistency(db, fake_local)


def test_given_mismatched_embedder_when_insert_then_refuses_to_corrupt_corpus(db):
    import pytest

    def fake_local(text):
        return hash_embed(text)

    insert_catalyst_record(db, _record(cid=1), embed=hash_embed)
    with pytest.raises(ValueError, match="embedder"):
        insert_catalyst_record(db, _record(cid=2), embed=fake_local)  # would poison the KNN


# ── build_playbooks driver: offline --run loop (injected complete_fn, no LLM/network) ──

def _seed_candidate(conn, cid, ctype="pdufa"):
    conn.execute(
        "INSERT INTO catalyst (id, ticker, company_name, catalyst_type, event_date, date_precision, "
        "uncertainty_type, status, source_origin, created_at, updated_at) "
        "VALUES (?, 'KRYS','Krystal',?, '2023-02-17','day','firm','resolved','curated_pdufa',"
        "'2026-01-01','2026-01-01')",
        (cid, ctype),
    )
    conn.execute(
        "INSERT INTO catalyst_move (catalyst_id, realized_move, move_window, knowable_asof, computed_at) "
        "VALUES (?, 0.052, '(-1,2)', '2023-02-22', '2026-01-01')", (cid,))
    conn.execute(
        "INSERT INTO catalyst_source (catalyst_id, source_name, source_url, source_type, reported_date, "
        "retrieved_at) VALUES (?, 'edgar','https://sec.gov/x','primary','2023-02-17','2026-01-01')", (cid,))
    conn.commit()


def test_given_dry_run_when_main_then_counts_corpus_offline(db):
    import scripts.build_playbooks as bp
    _seed_candidate(db, 501, "pdufa")
    _seed_candidate(db, 502, "trial_readout")
    _seed_candidate(db, 503, "earnings")
    out = bp.main([], conn=db)  # default dry-run
    assert out["total"] == 3
    assert out["core"] == 2 and out["earnings"] == 1


def test_given_run_with_injected_fn_when_main_then_populates_without_llm(db, monkeypatch):
    """--run wiring: build_bundle -> extract_record(injected complete_fn) -> insert_catalyst_record.
    build_bundle is monkeypatched to a canned bundle so the loop stays offline (no CIK network)."""
    import scripts.build_playbooks as bp

    _seed_candidate(db, 601, "pdufa")

    def fake_bundle(conn, cid, **kw):
        return dict(catalyst_id=cid, ticker="KRYS", catalyst_type="pdufa", indication="DEB",
                    modality="gene therapy", event_date="2023-02-17",
                    exhibit_text="FDA accepts ... priority review granted.", ctgov=None,
                    signed_move=0.052, move_window="(-1,2)", knowable_asof="2023-02-22",
                    date_precision="day")

    def fake_complete(prompt):  # the injected, offline completion (no live Sonnet)
        import json
        return json.dumps({
            "outcome_label": "approve", "confidence": 0.7,
            "drivers": [{"factor": "designations", "value": "BTD",
                         "evidence_quote": "priority review granted", "source_url": "https://sec.gov/x"}],
            "narrative_before": {"thesis": "clean pivotal", "causal_setup": "expedited",
                                 "reference_class": "orphan", "variant_why": "underweighted",
                                 "what_to_watch": ["cmc"], "what_would_change_our_mind": ["adcom"]},
            "narrative_after": {"what_happened": "approved", "why_narrative": "held",
                                "surprise_vs_prior": "low", "which_disconfirmer_fired": "none",
                                "lesson_rule": "anchor approve", "process_grade": "A"},
            "citations": [{"url": "https://sec.gov/x", "quote": "priority review", "snippet_hash": "h601"}],
        })

    monkeypatch.setattr(bp, "build_bundle", fake_bundle)
    monkeypatch.setenv("CT_EMBEDDER", "hash")  # keep the driver's default_embedder offline
    out = bp.main(["--run"], complete_fn=fake_complete, conn=db)
    assert out["processed"] == 1
    assert db.execute("SELECT COUNT(*) AS c FROM kb_node WHERE kind='catalyst' AND ref_id=601"
                      ).fetchone()["c"] == 1
