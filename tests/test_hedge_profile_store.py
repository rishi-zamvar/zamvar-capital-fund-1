"""hedge_profile storage + reader (HEDGE-CORR-1b): stamp_hedge_profile / hedge_profile on company
nodes, mirroring playbook/store.stamp_axes' UPDATE discipline (NOT the catalyst-record path).

Invariants under test (offline, :memory:):
  - round-trip: stamp then read returns the exact dict, byte-identical.
  - idempotent OVERWRITE: re-stamping a new profile replaces (never appends) and keeps exactly ONE
    company node; re-stamping the SAME profile leaves attrs unchanged.
  - the pre-existing {"ticker"} key is preserved across stamps.
  - no company node yet -> reader returns None; stamp then creates it.
  - content_sha-safe: company nodes are written via the UPDATE writer, never the catalyst-record path.
"""

import json

from catalyst_trader import kb

_PROFILE = {
    "as_of": "2026-08-19",
    "xbi": {"full": {"corr": 0.31, "beta": 0.4, "r2": 0.0961, "verdict": "weak",
                     "direction": "co-move", "window": "full"}},
    "peers": [{"peer": "PEER", "disease_or_mech": "disease:oncology", "corr_full": -0.62,
               "corr_ex_event": -0.55, "verdict": "strong", "direction": "inverse"}],
    "systematic_frac": 0.0961, "idiosyncratic_frac": 0.9039,
    "suggested_hedge": "sizing_only", "note": "n",
}


def _company_count(db, ticker):
    return db.execute(
        "SELECT count(*) FROM kb_node WHERE kind='company' "
        "AND json_extract(attrs_json,'$.ticker')=?",
        (ticker,),
    ).fetchone()[0]


def test_givenTickerAndProfile_whenStamp_thenReadRoundTripsExactDict(db):
    kb.stamp_hedge_profile(db, "NAME", _PROFILE)
    assert kb.hedge_profile(db, "NAME") == _PROFILE


def test_givenNoCompanyNode_whenReadHedgeProfile_thenNone(db):
    assert kb.hedge_profile(db, "GHOST") is None


def test_givenStampedProfile_whenReStampNewProfile_thenOverwriteNotAppendAndSingleNode(db):
    kb.stamp_hedge_profile(db, "NAME", _PROFILE)
    new = {**_PROFILE, "suggested_hedge": "xbi_overlay@beta 0.40"}
    kb.stamp_hedge_profile(db, "NAME", new)

    assert kb.hedge_profile(db, "NAME") == new  # only the new one
    assert kb.hedge_profile(db, "NAME") != _PROFILE
    assert _company_count(db, "NAME") == 1  # never a second node


def test_givenSameProfile_whenReStamp_thenIdempotentAndNodeCountUnchanged(db):
    nid = kb.stamp_hedge_profile(db, "NAME", _PROFILE)
    before = db.execute("SELECT attrs_json FROM kb_node WHERE id=?", (nid,)).fetchone()[0]
    nid2 = kb.stamp_hedge_profile(db, "NAME", _PROFILE)
    after = db.execute("SELECT attrs_json FROM kb_node WHERE id=?", (nid,)).fetchone()[0]
    assert nid2 == nid
    assert json.loads(before) == json.loads(after)
    assert _company_count(db, "NAME") == 1


def test_givenExistingTickerKey_whenStamp_thenTickerKeyPreserved(db):
    kb._get_or_create_company(db, "NAME")  # pre-existing {"ticker": "NAME"} node
    kb.stamp_hedge_profile(db, "NAME", _PROFILE)
    node = db.execute(
        "SELECT attrs_json FROM kb_node WHERE kind='company' "
        "AND json_extract(attrs_json,'$.ticker')=?",
        ("NAME",),
    ).fetchone()
    attrs = json.loads(node[0])
    assert attrs["ticker"] == "NAME"  # original key kept alongside hedge_profile
    assert attrs["hedge_profile"] == _PROFILE
    assert _company_count(db, "NAME") == 1


def test_givenStamp_whenReading_thenNoCatalystRecordPathUsed(db):
    # content_sha-safe: a company node is not sha-gated; no catalyst/outcome node is created.
    kb.stamp_hedge_profile(db, "NAME", _PROFILE)
    assert db.execute("SELECT count(*) FROM kb_node WHERE kind='catalyst'").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM kb_node WHERE kind='outcome'").fetchone()[0] == 0
