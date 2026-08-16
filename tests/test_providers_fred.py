"""FRED macro/rates/VIX provider (fred.py) — offline (PIPE-04).

Money-adjacent correctness guards: FRED '.' missing-value observations are DROPPED, never coerced
to 0 (a fabricated rate would poison the macro regime read); the provider is env-first and
DEGRADES TO SKIP when fred_api_key is absent (macro is context, not a gate — it must never raise or
block the pipeline); every datum carries green provenance; the fetch routes through the shared
_http base (no bespoke httpx client). ZERO live API in this suite.
"""

import pytest

from catalyst_trader.config import settings
from catalyst_trader.providers import _http, fred


@pytest.fixture(autouse=True)
def _isolate():
    _http._clear_cache()
    yield
    _http._clear_cache()


def test_fred_parses_series_with_provenance(httpx_mock, load_fixture, monkeypatch):
    monkeypatch.setattr(settings, "fred_api_key", "FREDKEY")
    httpx_mock.add_response(json=load_fixture("fred_dgs10"))
    out = fred.fetch_series("DGS10")
    assert out["series_id"] == "DGS10"
    # 4 raw observations, one is "." -> 3 real data points, all float.
    assert [o["value"] for o in out["observations"]] == [4.21, 4.25, 4.23]
    assert all(isinstance(o["value"], float) for o in out["observations"])
    assert all("date" in o for o in out["observations"])
    assert out["latest"] == 4.23  # last real observation
    assert out["provenance"]["grade"] == "green"
    assert out["provenance"]["source_url"].startswith("https://api.stlouisfed.org")
    assert out["provenance"]["fetch_ts"]


def test_fred_drops_missing_dot_values(httpx_mock, load_fixture, monkeypatch):
    monkeypatch.setattr(settings, "fred_api_key", "FREDKEY")
    httpx_mock.add_response(json=load_fixture("fred_dgs10"))
    out = fred.fetch_series("DGS10")
    values = [o["value"] for o in out["observations"]]
    assert 0 not in values and 0.0 not in values  # "." NEVER coerced to 0
    assert len(out["observations"]) == 3  # the "." row is absent, not fabricated


def test_fred_no_key_degrades_to_skip(monkeypatch):
    monkeypatch.setattr(settings, "fred_api_key", None)
    # No httpx_mock requested: a network attempt would fail the test. It must not attempt one.
    assert fred.fetch_series("DGS10") is None
    assert fred.fetch_macro() == {}


def test_fred_403_degrades(httpx_mock, monkeypatch):
    monkeypatch.setattr(settings, "fred_api_key", "FREDKEY")
    httpx_mock.add_response(status_code=403)
    assert fred.fetch_series("DGS10") is None  # degrade, never raise


def test_fred_macro_bundle(httpx_mock, load_fixture, monkeypatch):
    monkeypatch.setattr(settings, "fred_api_key", "FREDKEY")
    # A degraded series (403) is simply absent from the bundle — never fabricated.
    httpx_mock.add_response(status_code=403, is_reusable=True, is_optional=True)
    httpx_mock.add_response(
        url__regex=r".*series_id=DGS10.*", json=load_fixture("fred_dgs10"), is_reusable=True
    )
    macro = fred.fetch_macro()
    assert "DGS10" in macro
    assert macro["DGS10"]["latest"] == 4.23
    assert macro["DGS10"]["provenance"]["grade"] == "green"
    # Every present series is keyed by its series_id and carries provenance.
    for sid, series in macro.items():
        assert series["series_id"] == sid
        assert series["provenance"]["grade"] == "green"
