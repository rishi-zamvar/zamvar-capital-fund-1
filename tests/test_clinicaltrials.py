"""ClinicalTrials.gov v2 provider — parsed entirely offline against the Wave-0 fixtures.

Covers the two verified gotchas: partial dates survive as month/window (never coerced
to a day) and collaborator/university studies are not attributed to the wrong ticker.
"""

import pytest

from catalyst_trader.models import (
    CatalystType,
    DatePrecision,
    DateType,
    SourceOrigin,
    SourceType,
    Uncertainty,
)
from catalyst_trader.providers import clinicaltrials as ct

SPONSOR_MAP = {"VRTX": ["Vertex Pharmaceuticals Incorporated"]}


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(ct.settings, "ctgov_request_spacing_s", 0)


def _wrap(*studies, next_token=None):
    r = {"studies": list(studies), "totalCount": len(studies)}
    if next_token:
        r["nextPageToken"] = next_token
    return r


def test_partial_date_is_month_window_not_coerced(httpx_mock, load_fixture):
    httpx_mock.add_response(json=_wrap(load_fixture("ctgov_partial_date")))
    out = ct.fetch_trial_readouts(
        ["VRTX"], "2010-01-01", "2010-12-31", sponsor_map=SPONSOR_MAP
    )
    assert len(out) == 1
    c = out[0]
    assert c.event_date == "2010-03"  # NOT coerced to a day
    assert c.date_precision is DatePrecision.month
    assert c.uncertainty_type is Uncertainty.window
    assert c.catalyst_type is CatalystType.trial_readout
    assert c.source_origin is SourceOrigin.clinicaltrials_gov
    assert c.external_ref == "NCT00923728"


def test_source_provenance_attached(httpx_mock, load_fixture):
    httpx_mock.add_response(json=_wrap(load_fixture("ctgov_partial_date")))
    c = ct.fetch_trial_readouts(
        ["VRTX"], "2010-01-01", "2010-12-31", sponsor_map=SPONSOR_MAP
    )[0]
    s = c.sources[0]
    assert s.source_name == "ClinicalTrials.gov"
    assert s.source_type is SourceType.primary
    assert "NCT00923728" in s.source_url
    assert s.reported_date == "2010-03"
    assert s.retrieved_at
    assert s.date_type is DateType.estimated  # ESTIMATED -> estimated


def test_full_date_actual_maps_date_type_actual(httpx_mock, load_fixture):
    httpx_mock.add_response(json=_wrap(load_fixture("ctgov_full_date")))
    c = ct.fetch_trial_readouts(
        ["VRTX"], "2024-01-01", "2024-12-31", sponsor_map=SPONSOR_MAP
    )[0]
    assert c.date_precision is DatePrecision.day
    assert c.event_date == "2024-06-12"
    assert c.sources[0].date_type is DateType.actual  # ACTUAL -> actual
    # single-source ACTUAL, uncorroborated at provider stage -> soft (verify promotes later)
    assert c.uncertainty_type is Uncertainty.soft


def test_collaborator_study_not_attributed_to_ticker(httpx_mock, load_fixture):
    httpx_mock.add_response(json=_wrap(load_fixture("ctgov_collaborator")))
    out = ct.fetch_trial_readouts(
        ["VRTX"], "2032-01-01", "2032-12-31", sponsor_map=SPONSOR_MAP
    )
    assert out == []  # lead sponsor is a university, not VRTX's legal name


def test_pagination_follows_next_page_token(httpx_mock, load_fixture):
    httpx_mock.add_response(json=_wrap(load_fixture("ctgov_partial_date"), next_token="TOK"))
    httpx_mock.add_response(json=_wrap(load_fixture("ctgov_full_date")))
    out = ct.fetch_trial_readouts(
        ["VRTX"], "2010-01-01", "2024-12-31", sponsor_map=SPONSOR_MAP
    )
    assert len(out) == 2
    # second request carried the page token
    assert dict(httpx_mock.get_requests()[1].url.params)["pageToken"] == "TOK"


def test_builds_date_range_and_sponsor_query(httpx_mock, load_fixture):
    httpx_mock.add_response(json=_wrap(load_fixture("ctgov_partial_date")))
    ct.fetch_trial_readouts(
        ["VRTX"], "2010-01-01", "2010-12-31", sponsor_map=SPONSOR_MAP
    )
    params = dict(httpx_mock.get_requests()[0].url.params)
    assert (
        params["filter.advanced"]
        == "AREA[PrimaryCompletionDate]RANGE[2010-01-01,2010-12-31]"
    )
    assert params["query.spons"] == "Vertex Pharmaceuticals Incorporated"


def test_default_sponsor_map_loads_from_csv():
    m = ct.load_sponsor_map()
    assert "VRTX" in m
    assert "Vertex Pharmaceuticals Incorporated" in m["VRTX"]
