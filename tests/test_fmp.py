"""FMP earnings-calendar + confirmed provider — parsed offline against the Wave-0 fixtures.

The confirmed endpoint promotes a symbol's date_type estimated -> actual so verify can
treat it as promotable. Missing key fails loudly (no placeholder, no silent empty).
"""

import pytest

from catalyst_trader.config import settings
from catalyst_trader.models import (
    CatalystType,
    DatePrecision,
    DateType,
    SourceOrigin,
    SourceType,
    Uncertainty,
)
from catalyst_trader.providers import fmp

TICKERS = ["VRTX", "REGN", "SRPT", "BMRN"]


@pytest.fixture
def _key(monkeypatch):
    monkeypatch.setattr(settings, "fmp_api_key", "TESTKEY")


def _mock_both(httpx_mock, load_fixture):
    httpx_mock.add_response(json=load_fixture("fmp_earnings_calendar"))
    httpx_mock.add_response(json=load_fixture("fmp_earnings_confirmed"))


def test_parses_earnings_with_provenance(httpx_mock, load_fixture, _key):
    _mock_both(httpx_mock, load_fixture)
    out = fmp.fetch_earnings(TICKERS, "2026-07-01", "2026-08-31")
    assert len(out) == 4
    by_ticker = {c.ticker: c for c in out}
    vrtx = by_ticker["VRTX"]
    assert vrtx.catalyst_type is CatalystType.earnings
    assert vrtx.source_origin is SourceOrigin.fmp_earnings
    assert vrtx.date_precision is DatePrecision.day
    s = vrtx.sources[0]
    assert s.source_name == "FMP"
    assert s.source_type is SourceType.secondary
    assert s.reported_date == "2026-08-04"
    assert s.retrieved_at


def test_confirmed_marked_actual_calendar_only_estimated(httpx_mock, load_fixture, _key):
    _mock_both(httpx_mock, load_fixture)
    out = {c.ticker: c for c in fmp.fetch_earnings(TICKERS, "2026-07-01", "2026-08-31")}
    # VRTX + REGN are in the confirmed fixture -> actual (promotable)
    assert out["VRTX"].sources[0].date_type is DateType.actual
    assert out["REGN"].sources[0].date_type is DateType.actual
    # SRPT + BMRN calendar-only -> estimated
    assert out["SRPT"].sources[0].date_type is DateType.estimated
    assert out["BMRN"].sources[0].date_type is DateType.estimated
    # estimated calendar day -> window; confirmed(actual) single-source -> soft
    assert out["SRPT"].uncertainty_type is Uncertainty.window
    assert out["VRTX"].uncertainty_type is Uncertainty.soft


def test_filters_to_requested_tickers(httpx_mock, load_fixture, _key):
    _mock_both(httpx_mock, load_fixture)
    out = fmp.fetch_earnings(["VRTX"], "2026-07-01", "2026-08-31")
    assert [c.ticker for c in out] == ["VRTX"]


def test_missing_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "fmp_api_key", None)
    with pytest.raises(RuntimeError):
        fmp.fetch_earnings(["VRTX"], "2026-07-01", "2026-08-31")


def test_no_hardcoded_key_the_settings_key_is_sent(httpx_mock, load_fixture, _key):
    _mock_both(httpx_mock, load_fixture)
    fmp.fetch_earnings(["VRTX"], "2026-07-01", "2026-08-31")
    assert dict(httpx_mock.get_requests()[0].url.params)["apikey"] == "TESTKEY"
