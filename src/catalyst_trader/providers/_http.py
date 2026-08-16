"""Shared HTTP base for every httpx provider (CBOE, FINRA, EDGAR, Federal Register,
RTTNews, Nasdaq, Alpha Vantage, Tiingo).

The INGEST-02 discipline in ONE place so no Wave-2 provider re-invents it:
  - Cache: an in-module dict keyed on (kind, source, url, params) with a >=5-min
    TTL (default 300s). A repeat call inside the TTL returns the cached value and
    does NOT touch the network.
  - Rate-limit: sequential, <=1 req/sec per host, small jitter (mirrors the
    ctgov_request_spacing_s precedent).
  - Retry: httpx.HTTPTransport(retries=2) — the project-wide transport (fmp.py).
  - User-Agent: ua="browser" -> a browser UA (YELLOW hosts need it); ua="sec" ->
    settings.sec_user_agent (SEC requires a declared UA with contact email; a
    missing one is a config error, raised only when an SEC call is attempted).
  - Degrade: 403 / timeout / transport-error / bad-JSON -> return None (logged),
    NEVER raise into the pipeline, NEVER fabricate. Successful values are cached;
    degraded None is not, so a source can recover on the next call.
"""

import hashlib
import json
import logging
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from catalyst_trader.config import settings

logger = logging.getLogger(__name__)

# YELLOW endpoints (CBOE / Nasdaq / RTTNews) block non-browser agents.
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_MIN_SPACING_S = 1.0  # <=1 req/sec per host

# (kind, source, url, sorted-params, json-body-repr) -> (value, expiry_monotonic)
_cache: dict[tuple, tuple[object, float]] = {}
_last_request: dict[str, float] = {}  # host -> last request monotonic time
# Same key -> the raw-snapshot path written on its last successful (non-cache) fetch,
# so providers can record it as raw_snapshot_path in provenance.
_last_snapshot: dict[tuple, str] = {}

# Degrade triggers: 403 etc (HTTPStatusError), timeouts/network (TransportError),
# and JSON-decode failures (json.JSONDecodeError subclasses ValueError).
_DEGRADE = (httpx.HTTPStatusError, httpx.TimeoutException, httpx.TransportError, ValueError)


def _clear_cache() -> None:
    """Test helper: reset cache + rate-limit + snapshot state for isolation."""
    _cache.clear()
    _last_request.clear()
    _last_snapshot.clear()


def _key(kind, source, url, params, json_body) -> tuple:
    return (kind, source, url, tuple(sorted((params or {}).items())), repr(json_body))


# ── Raw-snapshot lake (research §3.4): archive every successful raw response so a
# fetch can be re-parsed offline (audit lever) and cited via raw_snapshot_path. ──


def _safe_name(key: tuple) -> str:
    """Filesystem-safe stem from the URL's last path segment + a short body/param hash."""
    _, _, url, params, jb = key
    u = httpx.URL(url)
    base = (u.path.rstrip("/").rsplit("/", 1)[-1] or u.host or "root")
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)[:40]
    sig = hashlib.sha1(f"{url}{params}{jb}".encode()).hexdigest()[:8]
    return f"{base}_{sig}"


def _write_snapshot(key: tuple, source: str, kind: str, raw_text: str) -> None:
    """Archive the raw response text under data/raw/{source}/{yyyy}/{mm}/. Best-effort:
    a write failure must never break the fetch."""
    now = datetime.now(timezone.utc)
    d = Path(settings.raw_snapshot_dir) / source / now.strftime("%Y") / now.strftime("%m")
    ext = "json" if kind == "json" else "txt"
    path = d / f"{_safe_name(key)}_{now.strftime('%Y%m%dT%H%M%S%f')}.{ext}"
    try:
        d.mkdir(parents=True, exist_ok=True)
        path.write_text(raw_text)
    except OSError as exc:  # ponytail: disk full/perm — degrade the archive, not the fetch
        logger.warning("raw snapshot write failed (%s) — continuing", exc)
        return
    _last_snapshot[key] = str(path)


def snapshot_path(source, url, *, kind="json", params=None, json_body=None) -> str | None:
    """The raw-snapshot path from the last successful fetch of this exact request, or None
    (degraded / never fetched). Providers record it as raw_snapshot_path in provenance."""
    return _last_snapshot.get(_key(kind, source, url, params, json_body))


def load_snapshot(path) -> object:
    """Re-parse an archived snapshot OFFLINE (no network): JSON files -> obj, else raw text."""
    p = Path(path)
    text = p.read_text()
    return json.loads(text) if p.suffix == ".json" else text


def prune_snapshots(*, max_bytes=None, older_than_days=None, base=None) -> list[str]:
    """Bound the lake: drop files older than `older_than_days`, then evict oldest until the
    total is under `max_bytes`. Returns the removed paths. Oldest-first by mtime."""
    root = Path(base) if base is not None else Path(settings.raw_snapshot_dir)
    if not root.exists():
        return []
    files = sorted((f for f in root.rglob("*") if f.is_file()), key=lambda f: f.stat().st_mtime)
    removed: list[str] = []

    if older_than_days is not None:
        cutoff = time.time() - older_than_days * 86400
        for f in list(files):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed.append(str(f))
                files.remove(f)

    if max_bytes is not None:
        total = sum(f.stat().st_size for f in files)
        for f in list(files):  # oldest first
            if total <= max_bytes:
                break
            total -= f.stat().st_size
            f.unlink()
            removed.append(str(f))

    return removed


def _resolve_ua(ua: str) -> str:
    if ua == "sec":
        if not settings.sec_user_agent:
            raise RuntimeError(
                "SEC_USER_AGENT not set — SEC requires a declared UA with contact email"
            )
        return settings.sec_user_agent
    return _BROWSER_UA


def _rate_limit(host: str) -> None:
    last = _last_request.get(host)
    if last is not None:
        wait = _MIN_SPACING_S - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait + random.uniform(0, 0.1))
    _last_request[host] = time.monotonic()


def _fetch(kind, source, url, params, ua, ttl_s, host_key, json_body=None):
    key = _key(kind, source, url, params, json_body)
    hit = _cache.get(key)
    if hit is not None and hit[1] > time.monotonic():
        return hit[0]  # cache path: no re-archive

    headers = {"User-Agent": _resolve_ua(ua)}  # raises on unset SEC UA (config error)
    _rate_limit(host_key or httpx.URL(url).host)
    try:
        with httpx.Client(transport=httpx.HTTPTransport(retries=2)) as client:
            # A JSON body -> POST (the FINRA Query API needs compareFilters in the body);
            # otherwise the plain GET. Same cache/rate-limit/retry/UA/degrade discipline either way.
            if json_body is not None:
                resp = client.post(url, params=params, json=json_body, headers=headers)
            else:
                resp = client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            value = resp.json() if kind == "json" else resp.text
            raw = resp.text  # archive the raw bytes on success only (not degrade/cache)
    except _DEGRADE as exc:
        logger.warning("%s degraded (%s) — returning None", source, exc)
        return None

    _write_snapshot(key, source, kind, raw)
    _cache[key] = (value, time.monotonic() + ttl_s)
    return value


def get_json(
    source, url, *, params=None, json_body=None, ua="browser", ttl_s=300, host_key=None
) -> dict | None:
    """Cached, rate-limited, retrying JSON fetch. None on degrade, never raises/fabricates.

    GET by default; pass ``json_body`` to POST it (FINRA's Query API takes its compareFilters
    in the request body). The body is part of the cache key so distinct queries don't collide.
    """
    return _fetch("json", source, url, params, ua, ttl_s, host_key, json_body)


def get_text(
    source, url, *, params=None, json_body=None, ua="browser", ttl_s=300, host_key=None
) -> str | None:
    """Same discipline as get_json but returns raw text (RTTNews HTML / CSV).

    Pass ``json_body`` to POST it and get the raw text back (FINRA's Query API takes its
    compareFilters in the body and answers with NDJSON) — symmetric with get_json.
    """
    return _fetch("text", source, url, params, ua, ttl_s, host_key, json_body)
