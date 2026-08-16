"""Nasdaq earnings-calendar provider (FMP fallback) -> provenance-tagged earnings Catalysts.

The 6.9 plan deferred this; the live shakedown then hit an FMP earnings-calendar 402 (key tier),
so a fallback is now required to avoid zero earnings coverage. Nasdaq's calendar is per-DAY:
``GET https://api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD`` (browser UA required) returns
``{"data": {"rows": [{"symbol", ...}]}}`` — the rows carry NO date, so the query date IS the event
date. Each emitted Catalyst carries its OWN honest provenance (source_origin=nasdaq_earnings,
source_name="Nasdaq", the real per-day api.nasdaq.com URL) — it NEVER reuses fmp_earnings. A 403/
timeout/empty day degrades to [] (never raise, never fabricate) via the shared _http base.
"""

import logging
from datetime import date, timedelta

from catalyst_trader.dates import classify, now_iso, parse_precision
from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    CatalystType,
    DateType,
    SourceOrigin,
    SourceType,
)
from catalyst_trader.providers._http import get_json

logger = logging.getLogger(__name__)

_URL = "https://api.nasdaq.com/api/calendar/earnings"




def _days(start: str, end: str):
    """Yield each ISO calendar day in [start, end] inclusive (the per-day Nasdaq calendar)."""
    d, last = date.fromisoformat(start), date.fromisoformat(end)
    while d <= last:
        yield d.isoformat()
        d += timedelta(days=1)


def fetch(tickers: list[str], start: str, end: str) -> list[Catalyst]:
    """Earnings catalysts for ``tickers`` across [start, end], one Nasdaq calendar call per day.

    Filtered to the requested universe; each Catalyst carries honest Nasdaq provenance. Degrades
    to [] on 403/timeout/empty — never raises, never fabricates a date.
    """
    wanted = {t.upper() for t in tickers}
    now = now_iso()
    out: list[Catalyst] = []
    for day in _days(start, end):
        data = get_json("nasdaq", _URL, params={"date": day}, ua="browser", ttl_s=300)
        rows = ((data or {}).get("data") or {}).get("rows") or []  # None on degrade/no-earnings
        source_url = f"{_URL}?date={day}"
        for row in rows:
            symbol = str(row.get("symbol", "")).upper()
            if symbol not in wanted:
                continue
            source = CatalystSource(
                source_name="Nasdaq",
                source_url=source_url,
                source_type=SourceType.secondary,
                reported_date=day,
                date_type=DateType.estimated,
                retrieved_at=now,
            )
            out.append(
                Catalyst(
                    ticker=symbol,
                    catalyst_type=CatalystType.earnings,
                    event_date=day,
                    date_precision=parse_precision(day),
                    uncertainty_type=classify(
                        day, DateType.estimated.value, source_count=1, has_primary=False
                    ),
                    source_origin=SourceOrigin.nasdaq_earnings,  # honest, never fmp_earnings
                    external_ref=symbol,
                    sources=[source],
                )
            )
    return out


def fetch_earnings_with_fallback(fmp_fn, nasdaq_fn):
    """Return callable(tickers, start, end): try ``fmp_fn`` first, fall back to ``nasdaq_fn`` only
    when FMP degrades (None/[]/raises). Both degraded -> [] (no fabrication). Never raises."""

    def _fetch(tickers: list[str], start: str, end: str) -> list[Catalyst]:
        try:
            events = fmp_fn(tickers, start, end)
        except Exception as exc:  # ponytail: fmp raises on no-key/402 -> degrade to Nasdaq
            logger.warning("FMP earnings degraded (%s) — falling back to Nasdaq", exc)
            events = None
        if events:
            return events
        try:
            return nasdaq_fn(tickers, start, end) or []
        except Exception as exc:  # ponytail: last-resort degrade — earnings is never fatal
            logger.warning("Nasdaq earnings fallback degraded (%s) — returning []", exc)
            return []

    return _fetch
