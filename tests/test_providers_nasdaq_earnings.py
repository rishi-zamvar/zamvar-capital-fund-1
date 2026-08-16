"""Nasdaq earnings provider (nasdaq_earnings.py) + FMP-first fallback combinator — offline.

Activated because FMP's earnings-calendar 402'd on the 6.9 live run. Two money-path guards:
(1) the Nasdaq Catalyst carries HONEST provenance — source_origin=SourceOrigin.nasdaq_earnings and
CatalystSource(source_name="Nasdaq", real api.nasdaq.com source_url), NEVER a reused fmp_earnings;
(2) the fallback tries FMP first and only drops to Nasdaq when FMP degrades (None/[]/raises) — and
both-empty returns [] (never a fabricated date). ZERO live API in this suite.
"""

import pytest

from catalyst_trader.models import CatalystType, SourceOrigin
from catalyst_trader.providers import _http, nasdaq_earnings


@pytest.fixture(autouse=True)
def _isolate():
    _http._clear_cache()
    yield
    _http._clear_cache()


def test_nasdaq_earnings_parses_catalysts(httpx_mock, load_fixture):
    httpx_mock.add_response(json=load_fixture("nasdaq_earnings"))
    out = nasdaq_earnings.fetch(["KURA"], "2026-08-04", "2026-08-04")
    assert len(out) == 1  # IOVA in the fixture is filtered out (not requested)
    c = out[0]
    assert c.ticker == "KURA"
    assert c.catalyst_type is CatalystType.earnings
    assert c.event_date == "2026-08-04"  # the per-day calendar query date is the event date
    # HONEST provenance — its OWN origin, not a reused fmp_earnings
    assert c.source_origin is SourceOrigin.nasdaq_earnings
    s = c.sources[0]
    assert s.source_name == "Nasdaq"
    assert "api.nasdaq.com/api/calendar/earnings" in s.source_url
    assert "2026-08-04" in s.source_url  # real per-day URL, not a placeholder


def test_nasdaq_earnings_403_degrades(httpx_mock):
    httpx_mock.add_response(status_code=403)
    assert nasdaq_earnings.fetch(["KURA"], "2026-08-04", "2026-08-04") == []  # no raise, no fab


def test_fallback_uses_fmp_when_ok():
    def fmp_fn(tickers, start, end):
        return ["FMP_EVENT"]

    def nasdaq_fn(tickers, start, end):
        raise AssertionError("Nasdaq must NOT be called when FMP yields events")

    combined = nasdaq_earnings.fetch_earnings_with_fallback(fmp_fn, nasdaq_fn)
    assert combined(["KURA"], "2026-08-04", "2026-08-04") == ["FMP_EVENT"]


@pytest.mark.parametrize("fmp_degrade", [[], None])
def test_fallback_switches_when_fmp_degrades(fmp_degrade):
    # FMP 402 shows up as [] (or None) — fall through to Nasdaq.
    combined = nasdaq_earnings.fetch_earnings_with_fallback(
        lambda t, s, e: fmp_degrade, lambda t, s, e: ["NASDAQ_EVENT"]
    )
    assert combined(["KURA"], "2026-08-04", "2026-08-04") == ["NASDAQ_EVENT"]


def test_fallback_switches_when_fmp_raises():
    # fmp.fetch_earnings raises RuntimeError on no-key and propagates the 402 HTTPStatusError.
    def fmp_fn(tickers, start, end):
        raise RuntimeError("FMP_API_KEY not set")

    combined = nasdaq_earnings.fetch_earnings_with_fallback(
        fmp_fn, lambda t, s, e: ["NASDAQ_EVENT"]
    )
    assert combined(["KURA"], "2026-08-04", "2026-08-04") == ["NASDAQ_EVENT"]


def test_fallback_both_empty_returns_empty():
    combined = nasdaq_earnings.fetch_earnings_with_fallback(
        lambda t, s, e: [], lambda t, s, e: []
    )
    assert combined(["KURA"], "2026-08-04", "2026-08-04") == []  # never fabricated
