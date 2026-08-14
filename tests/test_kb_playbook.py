"""Playbook store (KB-05): playbooks are queryable by scenario type, ordered by and surfacing
their first-class confidence, and stored under the mandatory-citation invariant (via insert_claim).
"""

import pytest

from catalyst_trader.kb import EvidenceSource, insert_playbook, query_playbooks

EV = [EvidenceSource(url="https://ct.gov/outcome", retrieved_at="2026-08-14", snippet_hash="h")]


def test_query_returns_confidence_desc_and_surfaces_confidence(db):
    insert_playbook(db, "pdufa_prior_crl", "resubmission after CRL", "size tiny", 0.7, EV)
    insert_playbook(db, "pdufa_prior_crl", "clean label", "hold through", 0.9, EV)
    insert_playbook(db, "phase3_readout", "primary endpoint", "exit before", 0.5, EV)

    r = query_playbooks(db, "pdufa_prior_crl")
    assert [x["confidence"] for x in r] == [0.9, 0.7]  # confidence-desc, surfaced first-class
    assert all("confidence" in x for x in r)
    assert all(x["scenario_type"] == "pdufa_prior_crl" for x in r)


def test_uncited_playbook_rejected(db):
    with pytest.raises(ValueError):
        insert_playbook(db, "pdufa_prior_crl", "s", "strat", 0.7, [])
    assert db.execute("SELECT count(*) FROM kb_node WHERE kind='playbook'").fetchone()[0] == 0


def test_confidence_out_of_range_rejected(db):
    with pytest.raises(ValueError):
        insert_playbook(db, "t", "s", "strat", 1.5, EV)
    with pytest.raises(ValueError):
        insert_playbook(db, "t", "s", "strat", -0.1, EV)
    assert db.execute("SELECT count(*) FROM kb_node WHERE kind='playbook'").fetchone()[0] == 0
