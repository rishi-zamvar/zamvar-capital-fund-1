"""FRED macro/rates/VIX regime provider (PIPE-04, GREEN, keyed, free instant key).

Fills the zero-coverage macro gap: Treasury rates (DGS10/DGS2) + the curve (T10Y2Y), the policy
rate (FEDFUNDS), free VIX history (VIXCLS), and CPI (CPIAUCSL) — the macro-regime context the desk
otherwise flies blind on. Env-first: reads settings.fred_api_key; when the key is ABSENT the
provider DEGRADES TO SKIP (returns None/{}), never raises, never blocks the pipeline — macro is
context, not a gate, so a missing key just means the daemon gets no macro that cycle.

FRED's series/observations JSON marks a missing datum (holiday / no-print) as the string ".";
we DROP it — never coerce to 0, never fabricate a rate. Fetched through the shared _http base
(cache / rate-limit / retry / UA / degrade) — no bespoke httpx client.
"""

import logging

from catalyst_trader.config import settings
from catalyst_trader.dates import now_iso
from catalyst_trader.providers._http import get_json

logger = logging.getLogger(__name__)

_URL = "https://api.stlouisfed.org/fred/series/observations"

# The standard macro-regime bundle: rates, curve, policy rate, VIX, CPI.
MACRO_SERIES = ("DGS10", "DGS2", "T10Y2Y", "FEDFUNDS", "VIXCLS", "CPIAUCSL")


def _f(x):
    """FRED value -> float, or None. The '.' missing-value sentinel returns None (dropped)."""
    if x is None or x == ".":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def fetch_series(series_id: str) -> dict | None:
    """One FRED series -> {series_id, observations:[{date, value:float}], latest, provenance}, or None.

    None (degrade-to-skip) when fred_api_key is absent (logged once) or on _http degrade
    (403/timeout/bad-JSON). '.' observations are dropped — never coerced to 0.
    """
    if not settings.fred_api_key:
        logger.info("FRED_API_KEY not set — skipping FRED %s (macro is context, not a gate)", series_id)
        return None

    data = get_json(
        "fred",
        _URL,
        params={"series_id": series_id, "api_key": settings.fred_api_key, "file_type": "json"},
        ua="browser",
    )
    if not data:
        return None

    observations = []
    for obs in data.get("observations", []):
        value = _f(obs.get("value"))
        if value is None:  # "." missing datum — drop it, never fabricate
            continue
        observations.append({"date": obs.get("date"), "value": value})

    return {
        "series_id": series_id,
        "observations": observations,
        "latest": observations[-1]["value"] if observations else None,
        "provenance": {
            "source_url": _URL,
            "fetch_ts": now_iso(),
            "grade": "green",
        },
    }


def fetch_macro() -> dict:
    """The macro-regime bundle {series_id: series_dict} for MACRO_SERIES.

    A degraded/absent series is simply omitted (never fabricated). {} when no key.
    """
    bundle = {}
    for series_id in MACRO_SERIES:
        series = fetch_series(series_id)
        if series is not None:
            bundle[series_id] = series
    return bundle
