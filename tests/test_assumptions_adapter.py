"""Valuation-assumptions adapter (FF-05): the cache read/write helpers + pre-event context packer
that feed the football-field rnpv / sum-of-parts / analyst-PT valuation methods.

Money-critical invariants under test (Task 1):
  - migration 013 provisions assumptions_snapshot under db.migrate() (no inline DDL);
  - write_assumptions_snapshot round-trips a valid dict AND REJECTS a bad shape (reject-not-fabricate):
    PoS/prob_reach outside [0,1], shares_out <= 0, empty cashflows/segments/price_targets, and a
    dict carrying none of {rnpv, sop, analyst_pt};
  - the provider ABSTAINS with {} (never None — the builder membership-tests `"rnpv" in a`) on an
    absent row AND on a stored as_of that is AFTER the requested as_of (NO-LOOK-AHEAD gate); a live
    (None) as_of is ungated;
  - a present, knowable row round-trips the exact dict.

Task 2 (pre-event context packer):
  - assumptions_context assembles ONLY as_of-gated pre-event facts (identity + prior readouts +
    card + current price); a post-as_of readout and THIS catalyst's own outcome are provably absent;
  - deterministic on seeded rows.

Everything offline: the cache uses the migrated in-memory db fixture; no live DB, no agent calls.
"""

import pytest

from catalyst_trader import store
from catalyst_trader.desk.assumptions_adapter import (
    assumptions_context,
    assumptions_snapshot_provider,
    write_assumptions_snapshot,
)
from catalyst_trader.kb import EvidenceSource, KBNode, add_edge, hash_embed, insert_claim

CAT = {
    "ticker": "ACME", "catalyst_type": "pdufa", "event_date": "2026-11-15",
    "catalyst_id": "cat-1", "indication": "NSCLC", "modality": "small_molecule",
}

_VALID_RNPV = {"rnpv": {"cashflows": [[1, 5.0e8, 0.6], [2, 8.0e8, 0.6]],
                        "discount_rate": 0.12, "costs": None, "shares_out": 1.0e8}}
_VALID_SOP = {"sop": {"segments": [{"cashflows": [[1, 3.0e8, 0.5]], "discount_rate": 0.12, "costs": None},
                                   {"cashflows": [[1, 2.0e8, 0.4]], "discount_rate": 0.10, "costs": None}],
                      "shares_out": 1.0e8}}
_VALID_PT = {"analyst_pt": {"price_targets": [120.0, 140.0, 160.0]}}


# --- migration 013 via db.migrate ------------------------------------------


def test_migration_013_creates_assumptions_snapshot(db):
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='assumptions_snapshot'"
    ).fetchone()
    assert row is not None


# --- write + provider round-trip -------------------------------------------


def test_round_trip_rnpv(db):
    write_assumptions_snapshot(db, "ACME", "2026-11-15", _VALID_RNPV, as_of="2026-11-14", source="agent")
    got = assumptions_snapshot_provider(db)("ACME", CAT, "2026-11-14")
    assert got == _VALID_RNPV


def test_round_trip_all_methods(db):
    a = {**_VALID_RNPV, **_VALID_SOP, **_VALID_PT}
    write_assumptions_snapshot(db, "ACME", "2026-11-15", a, as_of="2026-11-14", source="agent")
    got = assumptions_snapshot_provider(db)("ACME", CAT, "2026-11-14")
    assert got == a
    assert {"rnpv", "sop", "analyst_pt"} <= got.keys()


def test_upsert_replaces_on_pk(db):
    write_assumptions_snapshot(db, "ACME", "2026-11-15", _VALID_RNPV, as_of="2026-11-14", source="agent")
    write_assumptions_snapshot(db, "ACME", "2026-11-15", _VALID_PT, as_of="2026-11-14", source="agent")
    got = assumptions_snapshot_provider(db)("ACME", CAT, "2026-11-14")
    assert got == _VALID_PT  # REPLACE on (ticker, event_date)


# --- provider abstain: {} not None -----------------------------------------


def test_absent_row_abstains_empty_dict(db):
    got = assumptions_snapshot_provider(db)("NOPE", CAT, "2026-11-14")
    assert got == {}
    assert got is not None  # abstain is {} so the builder can do `"rnpv" in a`


def test_no_look_ahead_row_after_requested_abstains(db):
    # stored as_of is AFTER the requested as_of -> the estimate was not knowable yet -> abstain.
    write_assumptions_snapshot(db, "ACME", "2026-11-15", _VALID_RNPV, as_of="2026-11-14", source="agent")
    got = assumptions_snapshot_provider(db)("ACME", CAT, "2026-11-01")
    assert got == {}


def test_no_look_ahead_row_on_or_before_requested_returns(db):
    write_assumptions_snapshot(db, "ACME", "2026-11-15", _VALID_RNPV, as_of="2026-11-14", source="agent")
    assert assumptions_snapshot_provider(db)("ACME", CAT, "2026-11-14") == _VALID_RNPV
    assert assumptions_snapshot_provider(db)("ACME", CAT, "2026-11-20") == _VALID_RNPV


def test_live_none_as_of_is_ungated(db):
    write_assumptions_snapshot(db, "ACME", "2026-11-15", _VALID_RNPV, as_of="2026-11-14", source="agent")
    assert assumptions_snapshot_provider(db)("ACME", CAT, None) == _VALID_RNPV


# --- reject-not-fabricate: bad shapes raise ValueError, never land ---------


def test_reject_dict_with_no_method(db):
    with pytest.raises(ValueError):
        write_assumptions_snapshot(db, "ACME", "2026-11-15", {"foo": 1}, as_of="2026-11-14", source="agent")


def test_reject_pos_out_of_range(db):
    bad = {"rnpv": {"cashflows": [[1, 5.0e8, 1.4]], "discount_rate": 0.12, "costs": None, "shares_out": 1e8}}
    with pytest.raises(ValueError):
        write_assumptions_snapshot(db, "ACME", "2026-11-15", bad, as_of="2026-11-14", source="agent")


def test_reject_cost_prob_reach_out_of_range(db):
    bad = {"rnpv": {"cashflows": [[1, 5.0e8, 0.6]], "discount_rate": 0.12,
                    "costs": [[0, 1e8, 1.5]], "shares_out": 1e8}}
    with pytest.raises(ValueError):
        write_assumptions_snapshot(db, "ACME", "2026-11-15", bad, as_of="2026-11-14", source="agent")


def test_reject_rnpv_shares_out_non_positive(db):
    bad = {"rnpv": {"cashflows": [[1, 5.0e8, 0.6]], "discount_rate": 0.12, "costs": None, "shares_out": 0}}
    with pytest.raises(ValueError):
        write_assumptions_snapshot(db, "ACME", "2026-11-15", bad, as_of="2026-11-14", source="agent")


def test_reject_rnpv_empty_cashflows(db):
    bad = {"rnpv": {"cashflows": [], "discount_rate": 0.12, "costs": None, "shares_out": 1e8}}
    with pytest.raises(ValueError):
        write_assumptions_snapshot(db, "ACME", "2026-11-15", bad, as_of="2026-11-14", source="agent")


def test_reject_sop_empty_segments(db):
    bad = {"sop": {"segments": [], "shares_out": 1e8}}
    with pytest.raises(ValueError):
        write_assumptions_snapshot(db, "ACME", "2026-11-15", bad, as_of="2026-11-14", source="agent")


def test_reject_sop_segment_empty_cashflows(db):
    bad = {"sop": {"segments": [{"cashflows": [], "discount_rate": 0.12, "costs": None}], "shares_out": 1e8}}
    with pytest.raises(ValueError):
        write_assumptions_snapshot(db, "ACME", "2026-11-15", bad, as_of="2026-11-14", source="agent")


def test_reject_sop_shares_out_non_positive(db):
    bad = {"sop": {"segments": [{"cashflows": [[1, 3e8, 0.5]], "discount_rate": 0.12, "costs": None}],
                   "shares_out": -1e8}}
    with pytest.raises(ValueError):
        write_assumptions_snapshot(db, "ACME", "2026-11-15", bad, as_of="2026-11-14", source="agent")


def test_reject_analyst_pt_empty_targets(db):
    with pytest.raises(ValueError):
        write_assumptions_snapshot(db, "ACME", "2026-11-15", {"analyst_pt": {"price_targets": []}},
                                   as_of="2026-11-14", source="agent")


def test_reject_analyst_pt_non_finite_target(db):
    bad = {"analyst_pt": {"price_targets": [120.0, float("inf")]}}
    with pytest.raises(ValueError):
        write_assumptions_snapshot(db, "ACME", "2026-11-15", bad, as_of="2026-11-14", source="agent")


def test_bad_write_leaves_no_row(db):
    with pytest.raises(ValueError):
        write_assumptions_snapshot(db, "ACME", "2026-11-15", {"foo": 1}, as_of="2026-11-14", source="agent")
    # validation runs BEFORE the INSERT, so nothing landed
    assert assumptions_snapshot_provider(db)("ACME", CAT, "2026-11-14") == {}


# ---------------------------------------------------------------------------
# Task 2 — pre-event context packer (assumptions_context)
# ---------------------------------------------------------------------------

_EV = [EvidenceSource(url="https://ct.gov/x", retrieved_at="2026-08-14", snippet_hash="h")]


def _seed_readout(db, *, ticker, event_date, knowable_asof, move, ctype="pdufa", indication="NSCLC"):
    """A past catalyst KB node (ticker + event_date + knowable_asof attrs) with a realized outcome."""
    cid = insert_claim(db, KBNode(kind="catalyst", attrs={
        "type": ctype, "ticker": ticker, "indication": indication,
        "event_date": event_date, "knowable_asof": knowable_asof}), _EV,
        embed=hash_embed, embed_text=f"{ticker} {ctype} {event_date}")
    oid = insert_claim(db, KBNode(kind="outcome", attrs={"move": move}), _EV)
    add_edge(db, cid, "RESULTED_IN", oid)
    db.commit()


def test_context_carries_identity_fields(db):
    ctx = assumptions_context(db, "ACME", CAT, "2026-11-14")
    assert ctx["ticker"] == "ACME"
    assert ctx["catalyst_type"] == "pdufa"
    assert ctx["indication"] == "NSCLC"
    assert ctx["modality"] == "small_molecule"


def test_context_identity_falls_back_to_kb_node_attrs(db):
    # catalyst object lacks disease_area/mechanism_class; the kb catalyst node (ref_id) carries them.
    cid = insert_claim(db, KBNode(kind="catalyst", ref_id=42, attrs={
        "type": "pdufa", "ticker": "ZETA", "disease_area": "oncology",
        "mechanism_class": "kinase_inhibitor"}), _EV, embed=hash_embed, embed_text="zeta")
    cat = {"ticker": "ZETA", "catalyst_type": "pdufa", "event_date": "2026-12-01", "catalyst_id": 42}
    ctx = assumptions_context(db, "ZETA", cat, "2026-11-30")
    assert ctx["disease_area"] == "oncology"
    assert ctx["mechanism_class"] == "kinase_inhibitor"


def test_prior_readouts_only_before_as_of_and_knowable(db):
    # a knowable past readout is IN; a post-as_of readout (event_date >= as_of) is OUT.
    _seed_readout(db, ticker="ACME", event_date="2025-06-01", knowable_asof="2025-06-03", move=-0.40)
    _seed_readout(db, ticker="ACME", event_date="2027-01-01", knowable_asof="2027-01-03", move=0.30)
    ctx = assumptions_context(db, "ACME", CAT, "2026-11-14")
    moves = [r["move"] for r in ctx["prior_readouts"]]
    assert -0.40 in moves
    assert 0.30 not in moves  # a future readout never leaks


def test_prior_readouts_excludes_not_yet_knowable(db):
    # event_date is past, but the outcome was not KNOWABLE until after as_of -> excluded (no-look-ahead).
    _seed_readout(db, ticker="ACME", event_date="2026-11-10", knowable_asof="2026-11-20", move=0.55)
    ctx = assumptions_context(db, "ACME", CAT, "2026-11-14")
    assert all(r["move"] != 0.55 for r in ctx["prior_readouts"])


def test_prior_readouts_are_ticker_scoped(db):
    _seed_readout(db, ticker="OTHER", event_date="2025-06-01", knowable_asof="2025-06-03", move=0.99)
    ctx = assumptions_context(db, "ACME", CAT, "2026-11-14")
    assert all(r["move"] != 0.99 for r in ctx["prior_readouts"])


def test_context_carries_card_and_price(db):
    store.write_card(db, "ACME", "2026-11-07",
                     {"cash_runway_months": 18.0, "float": 5.0e7, "shares_outstanding": 1.0e8})
    store.upsert_bars(db, "ACME", [
        {"week_end": "2026-11-07", "open": 90, "high": 100, "low": 88, "close": 95.0, "volume": 1000}])
    ctx = assumptions_context(db, "ACME", CAT, "2026-11-14")
    assert ctx["cash_runway_months"] == 18.0
    assert ctx["float"] == 5.0e7
    assert ctx["current_price"] == 95.0


def test_context_price_gated_no_look_ahead(db):
    # a bar dated AFTER as_of must never appear as the current price.
    store.upsert_bars(db, "ACME", [
        {"week_end": "2026-11-07", "open": 90, "high": 100, "low": 88, "close": 95.0, "volume": 1000},
        {"week_end": "2026-11-21", "open": 95, "high": 130, "low": 90, "close": 125.0, "volume": 1000}])
    ctx = assumptions_context(db, "ACME", CAT, "2026-11-14")
    assert ctx["current_price"] == 95.0  # the post-as_of 125.0 bar is excluded


def test_context_none_safe_when_no_card_or_bars(db):
    ctx = assumptions_context(db, "ACME", CAT, "2026-11-14")
    assert "current_price" not in ctx  # no bars -> key simply absent, never a raise
    assert ctx["prior_readouts"] == []


def test_context_is_deterministic(db):
    _seed_readout(db, ticker="ACME", event_date="2025-06-01", knowable_asof="2025-06-03", move=-0.40)
    assert assumptions_context(db, "ACME", CAT, "2026-11-14") == assumptions_context(db, "ACME", CAT, "2026-11-14")
