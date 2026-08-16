"""FINRA Query API short-interest provider (finra.py) — offline.

FINRA answers the consolidatedShortInterest POST with NDJSON (one JSON object per line), not a
single JSON array — the 6.9 shakedown's "Extra data: line 1 column 28" (degraded all 21 names)
was one json.loads() over NDJSON. finra.fetch now pulls via get_text(json_body=) and parses
line-by-line. Money-path guards preserved: the query MUST carry an EQUAL compareFilter on the
partition key settlementDate (Pitfall 5), si_settlement_date is the ACTUAL bi-monthly settlement
date, and a missing row / 403 degrades to None (never fabricate). ZERO live API in this suite.
"""

import json

import pytest

from catalyst_trader.providers import _http, finra


@pytest.fixture(autouse=True)
def _isolate():
    _http._clear_cache()
    yield
    _http._clear_cache()


def test_finra_parses_ndjson_lines(httpx_mock, load_text_fixture):
    # Real shape: NDJSON text, NOT a JSON array (the shape that broke get_json/"Extra data").
    httpx_mock.add_response(text=load_text_fixture("finra_si.ndjson"))
    out = finra.fetch("KURA", settlement_date="2026-07-31")
    assert out["short_interest"] == 13160945
    assert out["days_to_cover"] == 6.27
    assert out["si_settlement_date"] == "2026-07-31"  # honest bi-monthly staleness
    assert out["provenance"]["grade"] == "green"
    assert out["provenance"]["source_url"].startswith("https://api.finra.org")
    assert out["provenance"]["fetch_ts"]


def test_finra_still_sends_settlementdate_equal_filter(httpx_mock, load_text_fixture):
    httpx_mock.add_response(text=load_text_fixture("finra_si.ndjson"))
    finra.fetch("KURA", settlement_date="2026-07-31")
    body = json.loads(httpx_mock.get_requests()[0].read())
    equals = [
        f
        for f in body.get("compareFilters", [])
        if f.get("fieldName") == "settlementDate" and f.get("compareType") == "EQUAL"
    ]
    assert equals, "Pitfall 5: the query MUST carry an EQUAL compareFilter on settlementDate"
    assert equals[0]["fieldValue"] == "2026-07-31"


def test_finra_skips_blank_and_bad_lines(httpx_mock):
    # A blank line + a malformed line degrade the LINE, not the fetch — good rows still parse.
    ndjson = (
        "\n"
        '   \n'
        "{not valid json at all}\n"
        '{"symbolCode": "KURA", "settlementDate": "2026-07-31", '
        '"currentShortPositionQuantity": 13160945, "daysToCoverQuantity": 6.27}\n'
    )
    httpx_mock.add_response(text=ndjson)
    out = finra.fetch("KURA", settlement_date="2026-07-31")
    assert out["short_interest"] == 13160945
    assert out["days_to_cover"] == 6.27


def test_finra_no_row_returns_none(httpx_mock, load_text_fixture):
    httpx_mock.add_response(text=load_text_fixture("finra_si.ndjson"))
    assert finra.fetch("NOSUCH", settlement_date="2026-07-31") is None  # degrade, no fabrication


def test_finra_403_degrades_not_raises(httpx_mock):
    httpx_mock.add_response(status_code=403)
    assert finra.fetch("KURA", settlement_date="2026-07-31") is None
