"""Multi-source price fetchers (prices.py) — RAW/unadjusted, Friday-anchored, offline.

The money-path guards live here: yfinance MUST be called with auto_adjust=False and store
the raw Close (never Adj Close); Alpha Vantage MUST use TIME_SERIES_WEEKLY (not _ADJUSTED);
Tiingo MUST read `close` (not `adjClose`). Adjusted prices bake future corporate-action
knowledge into a bar = look-ahead. Every source normalizes week_end to the shared Friday
anchor before returning. yfinance runs through an injected downloader; the JSON sources run
through pytest-httpx. ZERO live API in this suite.
"""

import pandas as pd
import pytest

from catalyst_trader.config import settings
from catalyst_trader.providers import _http, prices

START, END = "2026-08-01", "2026-08-31"


@pytest.fixture(autouse=True)
def _isolate():
    _http._clear_cache()
    yield
    _http._clear_cache()


def _fake_yf_df():
    """Monday-indexed weekly frame shaped like real yfinance 1.6.0: MultiIndex (field, ticker)
    columns + Adj Close DIFFERENT from raw Close (the trap). yfinance 1.6.0 returns columns
    [('Adj Close','TEST'), ('Close','TEST'), ...] even for a single ticker, so row["Close"] is a
    Series (the ticker sub-level), not a scalar — that is the all-None-bars bug this proves."""
    idx = pd.DatetimeIndex(["2026-08-03", "2026-08-10"])  # yfinance 1wk indexes by Monday
    return pd.DataFrame(
        {
            ("Open", "TEST"): [10.00, 10.60],
            ("High", "TEST"): [10.75, 11.60],
            ("Low", "TEST"): [9.95, 11.00],
            ("Close", "TEST"): [10.50, 11.40],    # RAW — what we must store
            ("Adj Close", "TEST"): [8.20, 9.00],  # split/div-adjusted — the look-ahead trap
            ("Volume", "TEST"): [3000.0, 6500.0],
        },
        index=idx,
    )


# ---- yfinance (YELLOW, always-on) --------------------------------------------------


def test_yf_parses_raw_bars():
    bars = prices._yf_weekly("TEST", START, END, downloader=lambda *a, **k: _fake_yf_df())
    assert [b["week_end"] for b in bars] == ["2026-08-07", "2026-08-14"]  # Monday -> Friday
    assert [b["close"] for b in bars] == [10.50, 11.40]  # raw Close, NOT Adj Close (8.20/9.00)
    assert bars[0]["open"] == 10.00 and bars[0]["high"] == 10.75 and bars[0]["low"] == 9.95
    assert all(b["_source"] == "yfinance" and b["_grade"] == "yellow" for b in bars)


def test_yf_called_with_auto_adjust_false():
    seen = {}

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return _fake_yf_df()

    prices._yf_weekly("TEST", START, END, downloader=spy)
    assert seen["auto_adjust"] is False  # money-critical: RAW prices only
    assert seen["interval"] == "1wk"


def test_yf_empty_returns_list():
    assert prices._yf_weekly("TEST", START, END, downloader=lambda *a, **k: pd.DataFrame()) == []
    assert prices._yf_weekly("TEST", START, END, downloader=lambda *a, **k: None) == []


# ---- Nasdaq (YELLOW, always-on) ----------------------------------------------------


def test_nasdaq_parses_and_resamples(httpx_mock, load_fixture):
    httpx_mock.add_response(json=load_fixture("nasdaq_hist"))
    bars = prices._nasdaq_daily("TEST", START, END)
    assert [b["week_end"] for b in bars] == ["2026-08-07", "2026-08-14"]
    # $-strings parsed to floats; daily rows collapsed to one weekly bar per Friday
    assert bars[0]["open"] == 10.00 and bars[0]["close"] == 10.50  # week open=first day, close=last
    assert bars[0]["high"] == 10.75 and bars[0]["low"] == 9.95
    assert bars[0]["volume"] == 3000.0  # summed
    assert bars[1]["close"] == 11.40
    assert all(b["_source"] == "nasdaq" and b["_grade"] == "yellow" for b in bars)


def test_nasdaq_degrade_returns_empty(httpx_mock):
    httpx_mock.add_response(status_code=403)  # assetclass=stocks degrades
    httpx_mock.add_response(status_code=403)  # ... and the assetclass=etf fallthrough too
    assert prices._nasdaq_daily("TEST", START, END) == []  # both degrade -> None -> []


def test_nasdaq_etf_fallthrough(httpx_mock, load_fixture):
    # An ETF (XBI/LABD) returns NO rows under assetclass=stocks -> the fetcher must retry
    # assetclass=etf so the sector reference isn't silently absent (live-shakedown finding).
    httpx_mock.add_response(json={"data": None})               # assetclass=stocks -> empty
    httpx_mock.add_response(json=load_fixture("nasdaq_hist"))  # assetclass=etf -> real rows
    bars = prices._nasdaq_daily("XBI", START, END)
    assert [b["week_end"] for b in bars] == ["2026-08-07", "2026-08-14"]
    assert all(b["_source"] == "nasdaq" and b["close"] is not None for b in bars)


# ---- Alpha Vantage (GREEN, keyed) --------------------------------------------------


def test_av_no_key_returns_empty(monkeypatch):
    monkeypatch.setattr(settings, "alpha_vantage_api_key", None)
    assert prices._av_weekly("TEST", START, END) == []  # skipped by cascade, no network


def test_av_parses_raw_weekly(httpx_mock, load_fixture, monkeypatch):
    monkeypatch.setattr(settings, "alpha_vantage_api_key", "AVKEY")
    httpx_mock.add_response(json=load_fixture("av_weekly"))
    bars = prices._av_weekly("TEST", START, END)
    assert [b["week_end"] for b in bars] == ["2026-08-07", "2026-08-14"]  # sorted, Friday-anchored
    # RAW "4. close" chosen, NOT "5. adjusted close" (8.20/9.00 in fixture)
    assert [b["close"] for b in bars] == [10.50, 11.40]
    assert bars[0]["open"] == 10.00 and bars[0]["volume"] == 3000.0
    assert all(b["_source"] == "alpha_vantage" and b["_grade"] == "green" for b in bars)
    # money-critical: non-adjusted endpoint
    req_url = str(httpx_mock.get_requests()[0].url)
    assert "TIME_SERIES_WEEKLY" in req_url and "_ADJUSTED" not in req_url


# ---- Tiingo (GREEN, keyed) ---------------------------------------------------------


def test_tiingo_no_key_returns_empty(monkeypatch):
    monkeypatch.setattr(settings, "tiingo_api_key", None)
    assert prices._tiingo_eod("TEST", START, END) == []


def test_tiingo_reads_close_not_adjclose(httpx_mock, load_fixture, monkeypatch):
    monkeypatch.setattr(settings, "tiingo_api_key", "TIINGOKEY")
    httpx_mock.add_response(json=load_fixture("tiingo_eod"))
    bars = prices._tiingo_eod("TEST", START, END)
    # fixture close != adjClose everywhere; the weekly close must be the RAW last-day close
    assert bars[0]["close"] == 10.50 and bars[1]["close"] == 11.40  # raw, not adjClose 8.30/9.00
    assert all(b["_source"] == "tiingo" and b["_grade"] == "green" for b in bars)


def test_tiingo_resampled_to_friday(httpx_mock, load_fixture, monkeypatch):
    monkeypatch.setattr(settings, "tiingo_api_key", "TIINGOKEY")
    httpx_mock.add_response(json=load_fixture("tiingo_eod"))
    bars = prices._tiingo_eod("TEST", START, END)
    assert [b["week_end"] for b in bars] == ["2026-08-07", "2026-08-14"]
    assert bars[0]["open"] == 10.00 and bars[0]["high"] == 10.75 and bars[0]["volume"] == 3000.0


# ---- Stooq (registered-but-disabled) ----------------------------------------------


def test_stooq_disabled_returns_empty():
    assert prices._stooq("TEST", START, END) == []  # IP-blocked from this machine; off by design
