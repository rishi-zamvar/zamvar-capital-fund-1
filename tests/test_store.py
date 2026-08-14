"""Atomic persistence write-path: a date cannot reach the DB without a source row
in the same transaction (no-LLM-date enforcement at the write layer)."""

import pytest

from catalyst_trader import store
from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    CatalystType,
    DatePrecision,
    DateType,
    SourceOrigin,
    SourceType,
    Status,
    Uncertainty,
)


def _source(**over):
    base = dict(
        source_name="ClinicalTrials.gov",
        source_url="https://clinicaltrials.gov/study/NCT1",
        source_type=SourceType.primary,
        reported_date="2026-11-30",
        date_type=DateType.estimated,
        retrieved_at="2026-08-14T00:00:00Z",
    )
    base.update(over)
    return CatalystSource(**base)


def _catalyst(sources=None, **over):
    base = dict(
        ticker="VRTX",
        company_name="Vertex Pharmaceuticals Incorporated",
        catalyst_type=CatalystType.pdufa,
        event_date="2026-11-30",
        date_precision=DatePrecision.day,
        uncertainty_type=Uncertainty.window,
        source_origin=SourceOrigin.curated_pdufa,
        sources=sources if sources is not None else [_source()],
    )
    base.update(over)
    return Catalyst(**base)


def test_insert_catalyst_writes_catalyst_and_source_rows(db):
    cid = store.insert_catalyst(db, _catalyst(sources=[_source(), _source(source_type=SourceType.secondary)]))
    assert isinstance(cid, int)
    n_cat = db.execute("SELECT count(*) c FROM catalyst").fetchone()["c"]
    n_src = db.execute("SELECT count(*) c FROM catalyst_source WHERE catalyst_id=?", (cid,)).fetchone()["c"]
    assert n_cat == 1
    assert n_src == 2


def test_get_catalyst_roundtrips_with_sources(db):
    cid = store.insert_catalyst(db, _catalyst())
    got = store.get_catalyst(db, cid)
    assert got is not None
    assert got.ticker == "VRTX"
    assert len(got.sources) == 1
    assert got.sources[0].source_name == "ClinicalTrials.gov"


def test_get_catalyst_missing_returns_none(db):
    assert store.get_catalyst(db, 9999) is None


def test_insert_empty_sources_raises_and_writes_no_orphan(db):
    # bypass the pydantic guard to prove the write path ALSO refuses a sourceless date
    orphan = Catalyst.model_construct(**{**_catalyst().model_dump(), "sources": []})
    with pytest.raises(ValueError):
        store.insert_catalyst(db, orphan)
    assert db.execute("SELECT count(*) c FROM catalyst").fetchone()["c"] == 0


def test_atomicity_source_failure_rolls_back_catalyst(db):
    # second source violates the NOT NULL / CHECK on catalyst_source -> whole tx rolls back
    bad = CatalystSource.model_construct(**{**_source().model_dump(), "reported_date": None})
    with pytest.raises(Exception):
        store.insert_catalyst(db, _catalyst(sources=[_source(), bad]))
    assert db.execute("SELECT count(*) c FROM catalyst").fetchone()["c"] == 0
    assert db.execute("SELECT count(*) c FROM catalyst_source").fetchone()["c"] == 0


def test_dedup_by_external_ref_updates_not_duplicates(db):
    first = _catalyst(external_ref="NCT05915442", event_date="2026-11-30")
    cid1 = store.insert_catalyst(db, first)
    # re-fetch of the same study with a slipped date -> same row, updated
    again = _catalyst(external_ref="NCT05915442", event_date="2026-12-15")
    cid2 = store.insert_catalyst(db, again)
    assert cid1 == cid2
    assert db.execute("SELECT count(*) c FROM catalyst").fetchone()["c"] == 1
    got = store.get_catalyst(db, cid1)
    assert got.event_date == "2026-12-15"


def test_tradeable_catalysts_returns_only_verified(db):
    store.insert_catalyst(db, _catalyst(ticker="AAA", status=Status.unverified))
    store.insert_catalyst(db, _catalyst(ticker="BBB", status=Status.verified))
    store.insert_catalyst(db, _catalyst(ticker="CCC", status=Status.excluded))
    tradeable = store.tradeable_catalysts(db)
    assert [c.ticker for c in tradeable] == ["BBB"]
    assert all(c.status == Status.verified for c in tradeable)
