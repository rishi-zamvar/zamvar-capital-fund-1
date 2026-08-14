"""Provenance invariant (KB-02): a claim node may not be committed without at least
one :CITES -> EvidenceSource edge, enforced atomically. This is the KB's analog of
Phase-1's no-LLM-date write-path (store.insert_catalyst) — reject before write, and
roll back completely on any mid-transaction failure so no orphan row survives.

RED-first: written before insert_claim exists.
"""

import pytest

from catalyst_trader import kb
from catalyst_trader.kb import EvidenceSource, KBNode, insert_claim


def _counts(conn):
    return (
        conn.execute("SELECT count(*) FROM kb_node").fetchone()[0],
        conn.execute("SELECT count(*) FROM kb_edge").fetchone()[0],
        conn.execute("SELECT count(*) FROM kb_vec").fetchone()[0],
    )


def test_uncited_claim_rejected_leaves_no_orphan(db):
    """evidence=[] -> ValueError AND zero rows written (reject before any INSERT)."""
    with pytest.raises(ValueError):
        insert_claim(db, KBNode(kind="outcome", attrs={"x": 1}), [])
    assert _counts(db) == (0, 0, 0)


def test_mid_transaction_failure_rolls_back_fully(db, monkeypatch):
    """A valid node but an evidence upsert that fails on the 2nd source -> full rollback:
    no partial claim (node written, first CITES edge written) survives."""
    ev1 = EvidenceSource(url="u1", retrieved_at="t", snippet_hash="h1")
    ev2 = EvidenceSource(url="u2", retrieved_at="t", snippet_hash="h2")

    real = kb._upsert_evidence
    calls = {"n": 0}

    def flaky(conn, ev):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("boom on 2nd source")
        return real(conn, ev)

    monkeypatch.setattr("catalyst_trader.kb._upsert_evidence", flaky)

    with pytest.raises(RuntimeError):
        insert_claim(
            db,
            KBNode(kind="outcome", attrs={"r": "pass"}),
            [ev1, ev2],
            embed=kb.hash_embed,
            embed_text="ctx",
        )
    assert _counts(db) == (0, 0, 0), "partial claim survived a mid-insert failure"


@pytest.mark.parametrize("kind", ["outcome", "playbook", "hedge_peer", "prediction"])
def test_no_uncited_claim_ever_persists(db, kind):
    """INVARIANT: after any rejected insert_claim, no non-evidence node lacks a CITES edge."""
    with pytest.raises(ValueError):
        insert_claim(db, KBNode(kind=kind, attrs={}), [])
    orphans = db.execute(
        "SELECT n.id FROM kb_node n WHERE n.kind != 'evidence_source' "
        "AND NOT EXISTS (SELECT 1 FROM kb_edge e WHERE e.src_id = n.id AND e.rel = 'CITES')"
    ).fetchall()
    assert orphans == [], f"uncited {kind} claim persisted"
