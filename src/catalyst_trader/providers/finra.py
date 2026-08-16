"""FINRA Query API -> consolidated short interest (INGEST-01, GREEN, no auth/key).

The free Query API beats the bulk files: a POST to consolidatedShortInterest returns exact
per-ticker rows. Pitfall 5 (hit live): sorting requires an EQUAL compareFilter on the partition
key ``settlementDate`` — an unfiltered query fails/returns unsorted — so we ALWAYS query by an
explicit settlement date (the 15th & EOM, published ~T+9 business days). si_settlement_date is
recorded as the actual settlement date so downstream freshness logic sees the real (bi-monthly)
age. A missing row for the ticker, or an _http degrade (403/timeout), returns None — never raise,
never fabricate. Fetched through the shared _http base (cache/rate-limit/retry/UA/degrade).
"""

import logging
from datetime import datetime, timezone

from catalyst_trader.providers._http import get_json

logger = logging.getLogger(__name__)

_URL = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"


def _f(x):
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def fetch(ticker: str, settlement_date: str = None) -> dict | None:
    """Consolidated short interest for ``ticker`` at ``settlement_date`` -> dict, or None.

    settlement_date defaults to None -> the caller is expected to pass the most recent published
    settlement date (15th/EOM). Returns {short_interest, days_to_cover, si_settlement_date,
    provenance:{source_url, fetch_ts, grade}}. None on degrade / no matching row.
    """
    ticker = ticker.upper()
    body = {
        "limit": 1000,
        # Pitfall 5: EQUAL filter on the partition key settlementDate is REQUIRED.
        "compareFilters": [
            {"compareType": "EQUAL", "fieldName": "settlementDate", "fieldValue": settlement_date}
        ],
        # Scope to the ticker server-side (domainFilters); we still guard the row match below.
        "domainFilters": [{"fieldName": "symbolCode", "values": [ticker]}],
    }
    rows = get_json("finra", _URL, json_body=body, ua="browser", ttl_s=300)
    if not rows:
        return None

    row = next((r for r in rows if str(r.get("symbolCode", "")).upper() == ticker), None)
    if row is None:
        return None

    short_interest = _f(row.get("currentShortPositionQuantity"))
    if short_interest is None:
        return None

    return {
        "short_interest": int(short_interest),
        "days_to_cover": _f(row.get("daysToCoverQuantity")),
        "si_settlement_date": row.get("settlementDate") or settlement_date,  # honest staleness
        "provenance": {
            "source_url": _URL,
            "fetch_ts": datetime.now(timezone.utc).isoformat(),
            "grade": "green",
        },
    }
