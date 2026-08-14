"""Ad-hoc catalyst injection: a user lead enters the SAME verify pipeline, starts
unverified, and cannot bypass the two-source rule."""

import pytest

from catalyst_trader import cli, store
from catalyst_trader.calendar import verify
from catalyst_trader.models import (
    DatePrecision,
    DateType,
    SourceOrigin,
    SourceType,
    Status,
    Uncertainty,
)


def test_inject_starts_unverified_and_ad_hoc(db):
    cid = cli.inject(db, ticker="XYZ", catalyst_type="pdufa", date="2026-11-30",
                     source_url="https://ir.example.com/pr")
    c = store.get_catalyst(db, cid)
    assert c.status == Status.unverified
    assert c.source_origin == SourceOrigin.ad_hoc_user
    assert len(c.sources) == 1
    assert c.sources[0].source_type == SourceType.secondary
    assert c.sources[0].date_type == DateType.estimated
    assert c.sources[0].source_url == "https://ir.example.com/pr"


def test_injected_catalyst_is_not_tradeable(db):
    cid = cli.inject(db, ticker="XYZ", catalyst_type="trial_readout", date="2026-11-30",
                     source_url="https://ir.example.com/pr")
    assert verify.is_tradeable(store.get_catalyst(db, cid)) is False
    # even after a verify pass it stays untradeable — only one source
    verify.verify_catalyst(db, cid)
    assert verify.is_tradeable(store.get_catalyst(db, cid)) is False


def test_partial_date_stored_as_window_not_coerced(db):
    cid = cli.inject(db, ticker="XYZ", catalyst_type="pdufa", date="2027-04",
                     source_url="https://ir.example.com/pr")
    c = store.get_catalyst(db, cid)
    assert c.event_date == "2027-04"  # never coerced to a day
    assert c.date_precision == DatePrecision.month
    assert c.uncertainty_type == Uncertainty.window


def test_invalid_date_raises_rather_than_fabricating(db):
    with pytest.raises(ValueError):
        cli.inject(db, ticker="XYZ", catalyst_type="pdufa", date="not-a-date",
                   source_url="https://ir.example.com/pr")
    assert db.execute("SELECT count(*) c FROM catalyst").fetchone()["c"] == 0


def test_window_end_persisted(db):
    cid = cli.inject(db, ticker="XYZ", catalyst_type="conference", date="2027-04",
                     window_end="2027-06", source_url="https://ir.example.com/pr")
    assert store.get_catalyst(db, cid).event_date_end == "2027-06"
