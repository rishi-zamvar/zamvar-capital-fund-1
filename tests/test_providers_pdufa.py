"""AdCom catalyst provider (pdufa.py) — Federal Register only, offline.

The RTTNews scraper was dropped (operator decision 2026-08-16): the dead scrape half is gone;
the Federal Register (GREEN, primary) AdCom half stays. FR is authoritative-sufficient, so an
attributed FR notice emits ONE single-source primary Catalyst that verifies on the single-source
path (DATA-03 amendment). The FR source carries its document publication_date for point-in-time
last_verified_at stamping. The provider NEVER sets last_verified_at and NEVER verifies (Pitfall 4).
Undated / unattributable / uncitable notices are dropped (date-or-drop, cite-or-drop). ZERO live API.
"""

import re

import pytest

from catalyst_trader.models import CatalystType, SourceType
from catalyst_trader.providers import _http, pdufa

_FR = re.compile(r"https://www\.federalregister\.gov.*")

_TICKERS = ["KURA", "CDEX"]
_MAP = {"KURA": ["Ziftomenib", "Kura Oncology"], "CDEX": ["Cardiodex"]}


@pytest.fixture(autouse=True)
def _isolate():
    _http._clear_cache()
    yield
    _http._clear_cache()


def _by_ticker(catalysts, ticker):
    return next((c for c in catalysts if c.ticker == ticker), None)


def test_pdufa_emits_single_source_primary(httpx_mock, load_fixture):
    httpx_mock.add_response(url=_FR, json=load_fixture("fedregister"))
    out = pdufa.fetch(_TICKERS, "2026-08-01", "2026-12-31", company_map=_MAP)

    kura = _by_ticker(out, "KURA")
    assert kura is not None
    # ONE FR primary source — authoritative-sufficient, verifies single-source downstream.
    assert len(kura.sources) == 1
    assert kura.sources[0].source_type == SourceType.primary
    assert kura.sources[0].source_name == "Federal Register"
    assert kura.external_ref and "KURA" in kura.external_ref


def test_pdufa_fr_source_carries_publication_date(httpx_mock, load_fixture):
    httpx_mock.add_response(url=_FR, json=load_fixture("fedregister"))
    out = pdufa.fetch(_TICKERS, "2026-08-01", "2026-12-31", company_map=_MAP)

    kura = _by_ticker(out, "KURA")
    fr = kura.sources[0]
    # publication_date = the FR document publication_date, DISTINCT from the event date
    assert fr.published_date == "2026-08-10"
    assert fr.reported_date == "2026-11-14"
    assert fr.published_date != fr.reported_date
    assert kura.event_date == "2026-11-14"


def test_pdufa_does_not_set_last_verified_at(httpx_mock, load_fixture):
    httpx_mock.add_response(url=_FR, json=load_fixture("fedregister"))
    out = pdufa.fetch(_TICKERS, "2026-08-01", "2026-12-31", company_map=_MAP)
    assert out  # non-empty
    assert all(c.last_verified_at is None for c in out)  # verify/ingest owns it (Pitfall 4)


def test_pdufa_attributes_multiple_universe_tickers(httpx_mock, load_fixture):
    httpx_mock.add_response(url=_FR, json=load_fixture("fedregister"))
    out = pdufa.fetch(_TICKERS, "2026-08-01", "2026-12-31", company_map=_MAP)
    # KURA (Ziftomenib) and CDEX (Cardiodex) both attribute from FR titles.
    assert _by_ticker(out, "KURA") is not None
    assert _by_ticker(out, "CDEX") is not None
    assert all(c.catalyst_type in (CatalystType.adcom, CatalystType.pdufa) for c in out)


def test_pdufa_degrades_to_empty_when_fr_down(httpx_mock):
    httpx_mock.add_response(url=_FR, status_code=403)  # FR down -> no raise, empty result
    out = pdufa.fetch(_TICKERS, "2026-08-01", "2026-12-31", company_map=_MAP)
    assert out == []
