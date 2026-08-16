"""Shared httpx base (_http) — cache + rate-limit + retry + UA + degrade, offline.

Every assertion runs against pytest-httpx (no network). Proves the INGEST-02
discipline lives in one place: a >=5-min TTL cache that skips the wire, a
degrade-to-None-never-raise-never-fabricate envelope on 403/timeout/bad-JSON,
and per-endpoint User-Agent (browser for YELLOW hosts, SEC-declared-UA from
settings for EDGAR).
"""

import httpx
import pytest

from catalyst_trader.config import settings
from catalyst_trader.providers import _http

URL = "https://example.com/data"


@pytest.fixture(autouse=True)
def _isolate():
    """Clear the module-level cache + rate-limit state around every test."""
    _http._clear_cache()
    yield
    _http._clear_cache()


def test_http_caches_within_ttl(httpx_mock):
    httpx_mock.add_response(url=URL, json={"v": 1})
    first = _http.get_json("demo", URL)
    second = _http.get_json("demo", URL)
    assert first == {"v": 1}
    assert second == {"v": 1}
    assert len(httpx_mock.get_requests()) == 1  # second served from cache


def test_http_403_returns_none_not_raises(httpx_mock):
    httpx_mock.add_response(url=URL, status_code=403)
    assert _http.get_json("demo", URL) is None


def test_http_timeout_returns_none(httpx_mock):
    httpx_mock.add_exception(httpx.TimeoutException("slow"), url=URL)
    assert _http.get_json("demo", URL) is None


def test_http_bad_json_returns_none(httpx_mock):
    httpx_mock.add_response(url=URL, text="<html>not json</html>")
    assert _http.get_json("demo", URL) is None  # never fabricate


def test_http_sec_ua_from_settings(httpx_mock, monkeypatch):
    monkeypatch.setattr(settings, "sec_user_agent", "Zamvar Capital contact@example.com")
    httpx_mock.add_response(url=URL, json={"ok": True})
    _http.get_json("edgar", URL, ua="sec")
    assert httpx_mock.get_requests()[0].headers["User-Agent"] == "Zamvar Capital contact@example.com"


def test_http_sec_ua_unset_raises_config_error(monkeypatch):
    monkeypatch.setattr(settings, "sec_user_agent", None)
    with pytest.raises(RuntimeError):
        _http.get_json("edgar", URL, ua="sec")


def test_http_browser_ua_sent(httpx_mock):
    httpx_mock.add_response(url=URL, json={"ok": True})
    _http.get_json("demo", URL)  # default ua="browser"
    assert "Mozilla" in httpx_mock.get_requests()[0].headers["User-Agent"]


def test_http_get_text_returns_string(httpx_mock):
    httpx_mock.add_response(url=URL, text="<html>hi</html>")
    assert _http.get_text("demo", URL) == "<html>hi</html>"


def test_http_get_text_degrades_to_none(httpx_mock):
    httpx_mock.add_response(url=URL, status_code=403)
    assert _http.get_text("demo", URL) is None
