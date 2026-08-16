"""SEC EDGAR submissions provider (edgar.py) — offline.

Scope guard: edgar.fetch returns ONLY what desk/company_scan.build_card consumes —
seen_accessions (list of {accession, form, filing_date}) + live_shelf (bool) + provenance.
Form-4/13F are DEFERRED (no consumer yet — YAGNI, RESEARCH Open Q3).

Money-path guards: the request MUST carry the declared SEC UA (Pitfall 3 — SEC blocks a
missing UA); an unset SEC_USER_AGENT surfaces the config error (never send an empty UA to
SEC); a 403/timeout degrades to None (never raise, never fabricate). ZERO live API here.
"""

import pytest

from catalyst_trader.config import settings
from catalyst_trader.providers import _http, edgar


@pytest.fixture(autouse=True)
def _isolate():
    _http._clear_cache()
    yield
    _http._clear_cache()


@pytest.fixture
def _sec_ua(monkeypatch):
    monkeypatch.setattr(settings, "sec_user_agent", "Zamvar Capital research@zamvar.example")
    return settings.sec_user_agent


def test_edgar_extracts_accessions_and_shelf(httpx_mock, load_fixture, _sec_ua):
    httpx_mock.add_response(json=load_fixture("edgar_submissions"))
    out = edgar.fetch("KURA", cik="1770787")

    accessions = {a["accession"] for a in out["seen_accessions"]}
    assert "0001193125-26-000123" in accessions
    forms = {a["form"] for a in out["seen_accessions"]}
    assert {"424B5", "8-K", "S-3ASR"} <= forms
    # each row carries the two keys build_card's F9 offering flag reads + the filing date
    row = out["seen_accessions"][0]
    assert {"accession", "form", "filing_date"} <= set(row)

    assert out["live_shelf"] is True  # S-3ASR present -> effective shelf

    assert out["provenance"]["grade"]
    assert out["provenance"]["source_url"].startswith("https://data.sec.gov")
    assert out["provenance"]["fetch_ts"]


def test_edgar_no_shelf_when_absent(httpx_mock, _sec_ua):
    httpx_mock.add_response(
        json={
            "filings": {
                "recent": {
                    "accessionNumber": ["0001193125-26-000999"],
                    "form": ["8-K"],
                    "filingDate": ["2026-08-11"],
                }
            }
        }
    )
    out = edgar.fetch("KURA", cik="1770787")
    assert out["live_shelf"] is False
    assert len(out["seen_accessions"]) == 1


def test_edgar_sends_sec_ua(httpx_mock, load_fixture, _sec_ua):
    httpx_mock.add_response(json=load_fixture("edgar_submissions"))
    edgar.fetch("KURA", cik="1770787")
    req = httpx_mock.get_requests()[0]
    assert req.headers["User-Agent"] == _sec_ua  # declared contact-email UA (Pitfall 3)
    # 10-digit zero-padded CIK in the submissions URL
    assert "CIK0001770787.json" in str(req.url)


def test_edgar_no_ua_config_error(monkeypatch):
    monkeypatch.setattr(settings, "sec_user_agent", None)
    with pytest.raises(RuntimeError):  # never send an empty UA to SEC
        edgar.fetch("KURA", cik="1770787")


def test_edgar_403_degrades_not_raises(httpx_mock, _sec_ua):
    httpx_mock.add_response(status_code=403)
    assert edgar.fetch("KURA", cik="1770787") is None  # degrade, no exception


def test_edgar_no_cik_returns_none():
    # no CIK -> cannot query SEC -> degrade to None (Plan 07 wires the curated ticker->CIK map)
    assert edgar.fetch("KURA", cik=None) is None
