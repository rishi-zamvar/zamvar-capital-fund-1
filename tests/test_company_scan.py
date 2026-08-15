"""Phase 6.8 Plan 01 — company-card store (migration 006 + store fns) + scan contracts.

Mirrors the price-bar store discipline (tests/test_price_store.py): write-once per
(ticker, week_end), point-in-time reads with the week_end <= as_of no-look-ahead guard.
"""

import pytest
from pydantic import ValidationError

from catalyst_trader import store
from catalyst_trader.contracts import KeyFinding, OpportunityFlag, ScanInput


# --- Task 1: company_card + scan_flag store ------------------------------------------------


def test_card_written_once_per_ticker_week(db):
    """A second write for the same (ticker, week_end) UPDATES in place — one row, latest wins."""
    store.write_card(db, "ABCD", "2026-01-02", {"price": 10.0, "note": "v1"})
    store.write_card(db, "ABCD", "2026-01-02", {"price": 11.0, "note": "v2"})

    rows = db.execute(
        "SELECT COUNT(*) AS n FROM company_card WHERE ticker=? AND week_end=?",
        ("ABCD", "2026-01-02"),
    ).fetchone()
    assert rows["n"] == 1  # UNIQUE(ticker, week_end) — no duplicate row

    card = store.card_asof(db, "ABCD", "2026-01-02")
    assert card == {"price": 11.0, "note": "v2"}  # second content is what we read back


def test_card_asof_never_returns_future(db):
    """card_asof returns the latest card with week_end <= as_of, NEVER a future card."""
    store.write_card(db, "ABCD", "2026-01-02", {"wk": "W1"})
    store.write_card(db, "ABCD", "2026-01-16", {"wk": "W3"})

    # as_of between W1 and W3 -> W1, never the future W3 (no look-ahead, the money invariant)
    assert store.card_asof(db, "ABCD", "2026-01-09") == {"wk": "W1"}
    # as_of before the earliest card -> None
    assert store.card_asof(db, "ABCD", "2025-12-01") is None
    # as_of at/after W3 -> W3
    assert store.card_asof(db, "ABCD", "2026-01-16") == {"wk": "W3"}


def test_scan_flag_round_trips_and_is_pointintime(db):
    """write_scan_flag persists a JSON payload once per (ticker, week_end); scan_flags_asof
    reads payloads with week_end <= as_of (audit ledger), never a future one."""
    store.write_scan_flag(db, "ABCD", "2026-01-02", {"opportunity_type": "no_opportunity"})
    store.write_scan_flag(db, "ABCD", "2026-01-02", {"opportunity_type": "squeeze_setup"}, routed=True)
    store.write_scan_flag(db, "ABCD", "2026-01-16", {"opportunity_type": "dilution_risk"})

    n = db.execute(
        "SELECT COUNT(*) AS n FROM scan_flag WHERE ticker=? AND week_end=?",
        ("ABCD", "2026-01-02"),
    ).fetchone()["n"]
    assert n == 1  # idempotent per (ticker, week_end)

    asof = store.scan_flags_asof(db, "ABCD", "2026-01-09")
    assert asof == [{"opportunity_type": "squeeze_setup"}]  # future W3 flag excluded


# --- Task 2: ScanInput firewall + OpportunityFlag contract ---------------------------------


def test_scan_input_firewall_forbids_desk_artifacts():
    """ScanInput carries ONLY {ticker, week_end, card_prev, card_cur, tripped} — any desk
    artifact (verdict/thesis/position/direction) is a ValidationError, not a policy check."""
    # clean construction succeeds
    ok = ScanInput(ticker="ABCD", week_end="2026-01-02", card_cur={"price": 10.0})
    assert ok.card_prev is None and ok.tripped == []

    for leak in ("verdict", "thesis", "position", "direction"):
        with pytest.raises(ValidationError):
            ScanInput(ticker="ABCD", week_end="2026-01-02", card_cur={}, **{leak: "x"})


def _flag(**over):
    base = dict(
        ticker="ABCD",
        week_end="2026-01-02",
        opportunity_type="catalyst_vol",
        thesis_to_verify="PDUFA within 2 weeks could drive a >20% move",
        verification_needed="catalyst_call",
        key_findings=[KeyFinding(claim="PDUFA 2026-01-20", evidence_ref="kb:1")],
        confidence=0.4,
    )
    base.update(over)
    return OpportunityFlag(**base)


def test_flag_vocabulary_fixed():
    """opportunity_type + verification_needed accept ONLY their fixed vocabularies."""
    for ot in ("catalyst_vol", "squeeze_setup", "dilution_risk", "technical_reversal",
               "continuation", "competitor_event", "unknown_vol", "no_opportunity"):
        _flag(opportunity_type=ot)
    for vn in ("catalyst_call", "measured_edge", "mini_backtest", "diligence"):
        _flag(verification_needed=vn)
    with pytest.raises(ValidationError):
        _flag(opportunity_type="buy")
    with pytest.raises(ValidationError):
        _flag(verification_needed="yolo")


def test_flag_carries_gap_not_answer():
    """OpportunityFlag exposes the gap-not-answer payload and NO answer-shaped field."""
    fields = set(OpportunityFlag.model_fields.keys())
    assert {"thesis_to_verify", "verification_needed"} <= fields
    assert fields.isdisjoint({"direction", "size", "size_pct", "target", "route"})
    # no_opportunity is a first-class outcome; confidence bounded [0,1]
    _flag(opportunity_type="no_opportunity")
    with pytest.raises(ValidationError):
        _flag(confidence=1.5)
