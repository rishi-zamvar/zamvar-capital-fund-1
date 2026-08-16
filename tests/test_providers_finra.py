"""FINRA Query API short-interest provider (finra.py) — offline.

Money-path guards: the query MUST carry an EQUAL compareFilter on the partition key
settlementDate (Pitfall 5 — without it the query fails/returns unsorted), si_settlement_date is
the ACTUAL bi-monthly settlement date so downstream freshness sees the real age, and a missing
row / 403 degrades to None (never fabricate). ZERO live API in this suite.
"""

import json

import pytest

from catalyst_trader.providers import _http, finra


@pytest.fixture(autouse=True)
def _isolate():
    _http._clear_cache()
    yield
    _http._clear_cache()


def test_finra_parses_si_with_provenance(httpx_mock, load_fixture):
    httpx_mock.add_response(json=load_fixture("finra_si"))
    out = finra.fetch("KURA", settlement_date="2026-07-31")
    assert out["short_interest"] == 13160945
    assert out["days_to_cover"] == 6.27
    assert out["si_settlement_date"] == "2026-07-31"  # honest bi-monthly staleness
    assert out["provenance"]["grade"]
    assert out["provenance"]["source_url"].startswith("https://api.finra.org")
    assert out["provenance"]["fetch_ts"]


def test_finra_uses_settlement_date_equal_filter(httpx_mock, load_fixture):
    httpx_mock.add_response(json=load_fixture("finra_si"))
    finra.fetch("KURA", settlement_date="2026-07-31")
    body = json.loads(httpx_mock.get_requests()[0].read())
    equals = [
        f for f in body.get("compareFilters", [])
        if f.get("fieldName") == "settlementDate" and f.get("compareType") == "EQUAL"
    ]
    assert equals, "Pitfall 5: the query MUST carry an EQUAL compareFilter on settlementDate"
    assert equals[0]["fieldValue"] == "2026-07-31"


def test_finra_no_row_returns_none(httpx_mock, load_fixture):
    httpx_mock.add_response(json=load_fixture("finra_si"))
    assert finra.fetch("NOSUCH", settlement_date="2026-07-31") is None  # degrade, no fabrication


def test_finra_403_degrades_not_raises(httpx_mock):
    httpx_mock.add_response(status_code=403)
    assert finra.fetch("KURA", settlement_date="2026-07-31") is None
