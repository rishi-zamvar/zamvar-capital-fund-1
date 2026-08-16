"""Financial Modeling Prep (FMP) earnings provider — calendar + confirmed endpoints.

The calendar returns upcoming (estimated) earnings dates; the separate confirmed
endpoint lists company-confirmed announcements. A symbol in the confirmed set gets
``date_type=actual`` (the persisted "promotable" marker verify reads, DATA-04); a
calendar-only symbol stays ``estimated``. The API key is env-only — a missing key
raises loudly rather than hardcoding a placeholder or silently returning nothing.
"""

from datetime import datetime, timezone

import httpx

from catalyst_trader.config import settings
from catalyst_trader.dates import classify, parse_precision
from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    CatalystType,
    DateType,
    SourceOrigin,
    SourceType,
)

CALENDAR_URL = "https://financialmodelingprep.com/stable/earnings-calendar"
CONFIRMED_URL = "https://financialmodelingprep.com/stable/earnings-calendar-confirmed"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_earnings(
    tickers: list[str],
    date_from: str,
    date_to: str,
    *,
    client: httpx.Client | None = None,
) -> list[Catalyst]:
    """Earnings catalysts for ``tickers`` in [date_from, date_to], provenance attached.

    Raises RuntimeError if FMP_API_KEY is unset (caller degrades gracefully).
    """
    key = settings.fmp_api_key
    if key is None:
        raise RuntimeError("FMP_API_KEY not set")

    wanted = set(tickers)
    own_client = client is None
    client = client or httpx.Client(transport=httpx.HTTPTransport(retries=2))
    try:
        params = {"from": date_from, "to": date_to, "apikey": key}
        cal = client.get(CALENDAR_URL, params=params)
        cal.raise_for_status()
        calendar_rows = cal.json()
        # FMP returns a dict (e.g. {"Error Message": ...}) on error/rate-limit, not the
        # expected list of rows. Degrade to [] rather than crash the caller (degrade-never-crash).
        if not isinstance(calendar_rows, list):
            return []
        conf = client.get(CONFIRMED_URL, params=params)
        conf.raise_for_status()
        conf_rows = conf.json()
        # Same guard: a dict-shaped confirmed response just means "no confirmations known",
        # so the calendar rows stay estimated rather than losing all earnings data.
        confirmed_symbols = (
            {row["symbol"] for row in conf_rows} if isinstance(conf_rows, list) else set()
        )
    finally:
        if own_client:
            client.close()

    now = _now()
    out: list[Catalyst] = []
    for row in calendar_rows:
        symbol = row["symbol"]
        if symbol not in wanted:
            continue
        raw_date = row["date"]
        is_confirmed = symbol in confirmed_symbols
        # confirmed acts like ACTUAL, calendar-only like ESTIMATED (DATA-04)
        date_type = DateType.actual if is_confirmed else DateType.estimated
        source = CatalystSource(
            source_name="FMP",
            source_url=CALENDAR_URL,
            source_type=SourceType.secondary,
            reported_date=raw_date,
            date_type=date_type,
            retrieved_at=now,
        )
        out.append(
            Catalyst(
                ticker=symbol,
                catalyst_type=CatalystType.earnings,
                event_date=raw_date,
                date_precision=parse_precision(raw_date),
                uncertainty_type=classify(
                    raw_date, date_type.value, source_count=1, has_primary=False
                ),
                source_origin=SourceOrigin.fmp_earnings,
                external_ref=symbol,
                sources=[source],
            )
        )
    return out
