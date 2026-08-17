"""Shared httpx base (_http) — cache + rate-limit + retry + UA + degrade, offline.

Every assertion runs against pytest-httpx (no network). Proves the INGEST-02
discipline lives in one place: a >=5-min TTL cache that skips the wire, a
degrade-to-None-never-raise-never-fabricate envelope on 403/timeout/bad-JSON,
and per-endpoint User-Agent (browser for YELLOW hosts, SEC-declared-UA from
settings for EDGAR).
"""

import json
import os
from pathlib import Path

import httpx
import pytest

from catalyst_trader.config import settings
from catalyst_trader.providers import _http

URL = "https://example.com/data"


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Clear cache/rate-limit state and point the raw-snapshot lake at tmp_path
    so no test writes into the repo's data/raw."""
    _http._clear_cache()
    monkeypatch.setattr(settings, "raw_snapshot_dir", str(tmp_path))
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


# ── Raw-snapshot lake (PIPE-06) ──────────────────────────────────────────────


def test_successful_fetch_writes_snapshot(httpx_mock, tmp_path):
    httpx_mock.add_response(url=URL, json={"v": 1})
    _http.get_json("demo", URL)
    path = _http.snapshot_path("demo", URL)
    assert path is not None
    p = Path(path)
    assert p.exists()
    assert str(tmp_path) in str(p)
    assert "demo" in p.parts  # data/raw/{source}/...
    assert p.suffix == ".json"
    # Archived bytes are the raw response, re-parseable.
    assert json.loads(p.read_text()) == {"v": 1}


def test_degrade_writes_no_snapshot(httpx_mock, tmp_path):
    httpx_mock.add_response(url=URL, status_code=403)
    assert _http.get_json("demo", URL) is None
    assert list(tmp_path.rglob("*.json")) == []
    assert _http.snapshot_path("demo", URL) is None


def test_cache_hit_no_double_write(httpx_mock, tmp_path):
    httpx_mock.add_response(url=URL, json={"v": 1})
    _http.get_json("demo", URL)
    _http.get_json("demo", URL)  # in-TTL repeat -> cache path, no re-archive
    assert len(httpx_mock.get_requests()) == 1
    assert len(list(tmp_path.rglob("*.json"))) == 1


def test_reparse_from_snapshot_offline(httpx_mock):
    """load_snapshot re-parses an archived file with ZERO network."""
    fixture = Path(__file__).parent / "fixtures" / "raw_snapshot_sample.json"
    obj = _http.load_snapshot(fixture)
    assert obj == {"symbol": "KURA", "raw": True, "value": 42}
    assert httpx_mock.get_requests() == []  # no refetch


def test_load_snapshot_text(tmp_path):
    p = tmp_path / "snap.txt"
    p.write_text("<html>raw</html>")
    assert _http.load_snapshot(p) == "<html>raw</html>"


def test_prune_bounds_lake_by_age(tmp_path):
    old_dir = tmp_path / "demo" / "2020" / "01"
    old_dir.mkdir(parents=True)
    old = old_dir / "a_20200101T000000.json"
    old.write_text('{"x": 1}')
    os.utime(old, (0, 0))  # epoch — very old
    new_dir = tmp_path / "demo" / "2026" / "08"
    new_dir.mkdir(parents=True)
    recent = new_dir / "b_20260816T000000.json"
    recent.write_text('{"x": 2}')

    removed = _http.prune_snapshots(older_than_days=30)
    assert old in [Path(r) for r in removed]
    assert not old.exists()
    assert recent.exists()


def test_prune_bounds_lake_by_size(tmp_path):
    d = tmp_path / "demo" / "2026" / "08"
    d.mkdir(parents=True)
    older = d / "a_20260816T000001.json"
    older.write_text("x" * 100)
    os.utime(older, (1000, 1000))
    newer = d / "b_20260816T000002.json"
    newer.write_text("y" * 100)
    os.utime(newer, (2000, 2000))

    _http.prune_snapshots(max_bytes=150)  # keep newest under cap
    assert not older.exists()  # oldest evicted first
    assert newer.exists()


# ── get_text(json_body=) POST-text transport (FINRA NDJSON enabler) ───────────


def test_get_text_posts_json_body(httpx_mock):
    httpx_mock.add_response(url=URL, method="POST", text="a\nb\nc")  # NDJSON body
    body = {"compareFilters": [{"fieldName": "issueSymbolIdentifier", "compareType": "EQUAL"}]}
    out = _http.get_text("finra", URL, json_body=body)
    assert out == "a\nb\nc"
    req = httpx_mock.get_requests()[0]
    assert req.method == "POST"
    assert json.loads(req.content) == body


def test_persistent_read_through_reuses_lake(monkeypatch):
    """Frugality read-through: an archived response for the exact request is reused within the TTL
    (no re-call) and ignored once stale — so a re-run never re-fetches data we already have."""
    from catalyst_trader.providers import _http

    _http._clear_cache()
    key = _http._key("json", "testsrc", "https://x.test/a", {"q": "1"}, None)
    _http._write_snapshot(key, "testsrc", "json", '{"v": 42}')
    # within TTL -> served from the lake (parsed)
    assert _http._read_persistent(key, "testsrc", "json", 3600) == {"v": 42}
    # stale (ttl 0) -> None -> caller falls through to a real fetch
    assert _http._read_persistent(key, "testsrc", "json", 0) is None
    # a request we never archived -> None
    other = _http._key("json", "testsrc", "https://x.test/b", None, None)
    assert _http._read_persistent(other, "testsrc", "json", 3600) is None
