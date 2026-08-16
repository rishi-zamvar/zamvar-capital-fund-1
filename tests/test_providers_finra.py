"""FINRA Query API short-interest provider (finra.py) — offline.

FINRA content-negotiates: a */* request gets CSV (text/plain), which broke both 6.9 (one
json.loads -> "Extra data") and 6.10-05 (parsed as NDJSON -> every line failed -> silent no data).
The 06.10-07 fix sends `Accept: application/json`, so FINRA returns a proper JSON ARRAY, parsed
directly. Money-path guards preserved: the query MUST carry an EQUAL compareFilter on the partition
key settlementDate (Pitfall 5), si_settlement_date is the ACTUAL bi-monthly settlement date, and a
missing row / empty array / 403 degrades to None (never fabricate). ZERO live API in this suite.
"""

import json

import pytest

from catalyst_trader.providers import _http, finra

# The real FINRA JSON-array shape (Accept: application/json), one row per ticker.
_ROW = {
    "symbolCode": "KURA",
    "issueName": "Kura Oncology, Inc.",
    "settlementDate": "2026-07-31",
    "currentShortPositionQuantity": 13160945,
    "daysToCoverQuantity": 6.27,
}


@pytest.fixture(autouse=True)
def _isolate():
    _http._clear_cache()
    yield
    _http._clear_cache()


def test_finra_parses_json_array(httpx_mock):
    httpx_mock.add_response(json=[_ROW])
    out = finra.fetch("KURA", settlement_date="2026-07-31")
    assert out["short_interest"] == 13160945
    assert out["days_to_cover"] == 6.27
    assert out["si_settlement_date"] == "2026-07-31"  # honest bi-monthly staleness
    assert out["provenance"]["grade"] == "green"
    assert out["provenance"]["source_url"].startswith("https://api.finra.org")
    assert out["provenance"]["fetch_ts"]


def test_finra_requests_json_and_settlementdate_equal_filter(httpx_mock):
    httpx_mock.add_response(json=[_ROW])
    finra.fetch("KURA", settlement_date="2026-07-31")
    req = httpx_mock.get_requests()[0]
    # the fix: without Accept: application/json FINRA silently returns CSV and we get zero data
    assert req.headers.get("Accept") == "application/json"
    body = json.loads(req.read())
    equals = [
        f
        for f in body.get("compareFilters", [])
        if f.get("fieldName") == "settlementDate" and f.get("compareType") == "EQUAL"
    ]
    assert equals, "Pitfall 5: the query MUST carry an EQUAL compareFilter on settlementDate"
    assert equals[0]["fieldValue"] == "2026-07-31"


def test_finra_no_matching_row_returns_none(httpx_mock):
    httpx_mock.add_response(json=[_ROW])
    assert finra.fetch("NOSUCH", settlement_date="2026-07-31") is None  # degrade, no fabrication


def test_finra_empty_array_returns_none(httpx_mock):
    httpx_mock.add_response(json=[])
    assert finra.fetch("KURA", settlement_date="2026-07-31") is None


def test_finra_403_degrades_not_raises(httpx_mock):
    httpx_mock.add_response(status_code=403)
    assert finra.fetch("KURA", settlement_date="2026-07-31") is None
