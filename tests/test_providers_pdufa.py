"""PDUFA/AdCom catalyst provider (pdufa.py) — offline.

This suite carries the Blocker-2 fix: for a PDUFA/AdCom event that BOTH feeds report, the
provider emits ONE Catalyst whose sources list holds BOTH CatalystSources — Federal Register
(JSON, primary/GREEN) AND RTTNews (HTML, secondary/YELLOW) — sharing one external_ref, so a
single insert_catalyst writes both source rows and the two-source verify gate
(len(agreeing) >= 2 and has_primary) can actually fire. A single-feed event stays one-source
(cite-or-drop, never forced tradeable). The FR source carries its document publication_date for
point-in-time last_verified_at stamping (Plan 07). The provider NEVER sets last_verified_at and
NEVER verifies (Pitfall 4); RTTNews is discovery-only (Pitfall 6). ZERO live API here.
"""

import re

import pytest

from catalyst_trader.models import SourceType, Status
from catalyst_trader.providers import _http, pdufa

_FR = re.compile(r"https://www\.federalregister\.gov.*")
_RTT = re.compile(r"https://www\.rttnews\.com.*")

_TICKERS = ["KURA", "CDEX", "SOME"]
_MAP = {"KURA": ["Ziftomenib", "Kura Oncology"], "CDEX": ["Cardiodex"]}


@pytest.fixture(autouse=True)
def _isolate():
    _http._clear_cache()
    yield
    _http._clear_cache()


def _both(httpx_mock, load_fixture, load_text_fixture):
    httpx_mock.add_response(url=_FR, json=load_fixture("fedregister"))
    httpx_mock.add_response(url=_RTT, text=load_text_fixture("rttnews.html"))


def _by_ticker(catalysts, ticker):
    return next((c for c in catalysts if c.ticker == ticker), None)


def test_pdufa_merges_two_sources_same_event(httpx_mock, load_fixture, load_text_fixture):
    _both(httpx_mock, load_fixture, load_text_fixture)
    out = pdufa.fetch(_TICKERS, "2026-08-01", "2026-12-31", company_map=_MAP)

    kura = _by_ticker(out, "KURA")
    assert kura is not None
    # ONE Catalyst carrying BOTH sources under one external_ref
    types = sorted(s.source_type for s in kura.sources)
    assert types == [SourceType.primary, SourceType.secondary]
    assert kura.external_ref and "KURA" in kura.external_ref
    # both agree + a primary present -> the two-source gate CAN clear post-insert
    agreeing = [s for s in kura.sources if s.agrees]
    assert len(agreeing) >= 2 and any(s.source_type == SourceType.primary for s in agreeing)


def test_pdufa_fr_source_carries_publication_date(httpx_mock, load_fixture, load_text_fixture):
    _both(httpx_mock, load_fixture, load_text_fixture)
    out = pdufa.fetch(_TICKERS, "2026-08-01", "2026-12-31", company_map=_MAP)

    kura = _by_ticker(out, "KURA")
    fr = next(s for s in kura.sources if s.source_type == SourceType.primary)
    rtt = next(s for s in kura.sources if s.source_type == SourceType.secondary)
    # publication_date = the FR document publication_date, DISTINCT from the event date
    assert fr.published_date == "2026-08-10"
    assert fr.reported_date == "2026-11-14"
    assert fr.published_date != fr.reported_date
    assert kura.event_date == "2026-11-14"
    # RTTNews (discovery) leaves publication_date None
    assert rtt.published_date is None


def test_pdufa_single_source_stays_one_source(httpx_mock, load_fixture, load_text_fixture):
    _both(httpx_mock, load_fixture, load_text_fixture)
    out = pdufa.fetch(_TICKERS, "2026-08-01", "2026-12-31", company_map=_MAP)

    cdex = _by_ticker(out, "CDEX")  # FR-only (no RTTNews match)
    assert cdex is not None
    assert len(cdex.sources) == 1
    assert cdex.sources[0].source_type == SourceType.primary
    assert cdex.status == Status.unverified  # one source -> untradeable, never forced


def test_pdufa_does_not_set_last_verified_at(httpx_mock, load_fixture, load_text_fixture):
    _both(httpx_mock, load_fixture, load_text_fixture)
    out = pdufa.fetch(_TICKERS, "2026-08-01", "2026-12-31", company_map=_MAP)
    assert out  # non-empty
    assert all(c.last_verified_at is None for c in out)  # verify/ingest owns it (Pitfall 4)


def test_pdufa_drops_row_without_source_url(httpx_mock, load_fixture, load_text_fixture):
    _both(httpx_mock, load_fixture, load_text_fixture)
    out = pdufa.fetch(_TICKERS, "2026-08-01", "2026-12-31", company_map=_MAP)
    assert _by_ticker(out, "SOME") is None  # URL-less RTTNews row dropped (cite-or-drop)


def test_pdufa_one_source_degrades_other_still_runs(httpx_mock, load_text_fixture):
    httpx_mock.add_response(url=_FR, status_code=403)  # FR down
    httpx_mock.add_response(url=_RTT, text=load_text_fixture("rttnews.html"))
    out = pdufa.fetch(_TICKERS, "2026-08-01", "2026-12-31", company_map=_MAP)

    kura = _by_ticker(out, "KURA")
    assert kura is not None  # RTTNews-only catalyst still emitted (no raise)
    assert len(kura.sources) == 1
    assert kura.sources[0].source_type == SourceType.secondary
    assert _by_ticker(out, "CDEX") is None  # FR-only event gone when FR degrades
