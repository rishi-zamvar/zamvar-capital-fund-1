"""Domain-model tests — the no-LLM-date invariant lives at the type boundary."""

import pytest
from pydantic import ValidationError

from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    DatePrecision,
    DateType,
    SourceOrigin,
    SourceType,
    Status,
    Uncertainty,
    UniverseSnapshot,
)


def _source(**over):
    base = dict(
        source_name="ClinicalTrials.gov",
        source_url="https://clinicaltrials.gov/study/NCT05915442",
        source_type=SourceType.primary,
        reported_date="2026-11-30",
        retrieved_at="2026-08-14T00:00:00Z",
    )
    base.update(over)
    return CatalystSource(**base)


def _catalyst(**over):
    base = dict(
        ticker="VRTX",
        catalyst_type="trial_readout",
        event_date="2026-11-30",
        date_precision="day",
        uncertainty_type="firm",
        source_origin="clinicaltrials_gov",
        sources=[_source()],
    )
    base.update(over)
    return Catalyst(**base)


def test_catalyst_with_sources_validates():
    c = _catalyst()
    assert c.status is Status.unverified  # default
    assert len(c.sources) == 1


def test_catalyst_rejects_empty_sources():
    with pytest.raises(ValidationError):
        _catalyst(sources=[])


def test_source_default_date_type_is_estimated():
    assert _source().date_type is DateType.estimated


def test_source_rejects_invalid_date_type():
    with pytest.raises(ValidationError):
        _source(date_type="bogus")


@pytest.mark.parametrize(
    "enum, bad",
    [
        (Uncertainty, "maybe"),
        (DatePrecision, "week"),
        (Status, "traded"),
        (SourceOrigin, "twitter"),
        (DateType, "guessed"),
    ],
)
def test_enum_rejects_out_of_set(enum, bad):
    with pytest.raises(ValueError):
        enum(bad)


def test_universe_snapshot_model():
    snap = UniverseSnapshot(
        as_of_date="2026-08-14",
        ticker="VRTX",
        included=True,
        delisted=False,
        reason="high catalyst density",
    )
    assert snap.ticker == "VRTX"
    assert snap.included is True
