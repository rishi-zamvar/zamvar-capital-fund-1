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

import logging
import random
import time

import httpx

from catalyst_trader.config import settings

logger = logging.getLogger(__name__)

# YELLOW endpoints (CBOE / Nasdaq / RTTNews) block non-browser agents.
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_MIN_SPACING_S = 1.0  # <=1 req/sec per host

# (kind, source, url, sorted-params) -> (value, expiry_monotonic)
_cache: dict[tuple, tuple[object, float]] = {}
_last_request: dict[str, float] = {}  # host -> last request monotonic time

# Degrade triggers: 403 etc (HTTPStatusError), timeouts/network (TransportError),
# and JSON-decode failures (json.JSONDecodeError subclasses ValueError).
_DEGRADE = (httpx.HTTPStatusError, httpx.TimeoutException, httpx.TransportError, ValueError)


def _clear_cache() -> None:
    """Test helper: reset cache + rate-limit state for isolation."""
    _cache.clear()
    _last_request.clear()


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
    key = (kind, source, url, tuple(sorted((params or {}).items())), repr(json_body))
    hit = _cache.get(key)
    if hit is not None and hit[1] > time.monotonic():
        return hit[0]

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
    except _DEGRADE as exc:
        logger.warning("%s degraded (%s) — returning None", source, exc)
        return None

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


def get_text(source, url, *, params=None, ua="browser", ttl_s=300, host_key=None) -> str | None:
    """Same discipline as get_json but returns raw text (RTTNews HTML / CSV)."""
    return _fetch("text", source, url, params, ua, ttl_s, host_key)
