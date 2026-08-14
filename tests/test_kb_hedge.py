"""Hedge sub-store (KB-04): a hedge relationship is a CITED hedge_peer claim carrying
mechanism + payoff_direction sign (+1/-1) + weight, routed through insert_claim so it is
rejected without a citation and leaves no orphan on rejection. hedge_peers() returns each
peer with its mechanism, sign, weight, and cited EvidenceSource.
"""

import pytest

from catalyst_trader.kb import EvidenceSource, hedge_peers, insert_hedge_peer

EV = [EvidenceSource(url="https://sec.gov/10k", retrieved_at="2026-08-14", snippet_hash="h")]


def test_insert_and_query_roundtrips_mechanism_sign_weight_and_citation(db):
    insert_hedge_peer(db, "ABC", "XYZ", "same-indication competitor", -1, 0.82, EV)

    peers = hedge_peers(db, "ABC")
    assert len(peers) == 1
    p = peers[0]
    assert p["peer"] == "XYZ"
    assert p["mechanism"] == "same-indication competitor"
    assert p["payoff_direction"] == -1
    assert p["weight"] == 0.82
    assert p["evidence"][0]["url"] == "https://sec.gov/10k"

    # traversal edge exists between company nodes
    assert db.execute("SELECT count(*) FROM kb_edge WHERE rel='HEDGE_PEER'").fetchone()[0] == 1


def test_missing_citation_rejected_and_leaves_no_hedge_node(db):
    with pytest.raises(ValueError):
        insert_hedge_peer(db, "ABC", "XYZ", "same sector", 1, 0.8, [])
    assert db.execute("SELECT count(*) FROM kb_node WHERE kind='hedge_peer'").fetchone()[0] == 0


def test_both_signs_roundtrip_and_zero_rejected(db):
    insert_hedge_peer(db, "AAA", "BBB", "correlated long", +1, 0.5, EV)
    insert_hedge_peer(db, "CCC", "DDD", "inverse payoff", -1, 0.7, EV)
    assert hedge_peers(db, "AAA")[0]["payoff_direction"] == +1
    assert hedge_peers(db, "CCC")[0]["payoff_direction"] == -1

    with pytest.raises(ValueError):
        insert_hedge_peer(db, "EEE", "FFF", "neither", 0, 0.5, EV)
    assert db.execute("SELECT count(*) FROM kb_node WHERE kind='hedge_peer'").fetchone()[0] == 2
