"""SEC EDGAR submissions -> the two filings signals build_card consumes (INGEST-01, GREEN).

Scope is deliberately narrow: desk/company_scan.build_card reads only
``raw["seen_accessions"]`` (its F9 offering-signal flag) and ``raw["live_shelf"]``, so this
provider returns ONLY those two + provenance. Form-4 / 13F ownership are DEFERRED until a
consumer exists (YAGNI — RESEARCH Open Q3).

SEC requires a declared User-Agent carrying a contact email (Pitfall 3); a missing one is a
config error surfaced by _http (never send an empty UA). A 403/timeout, a missing CIK, or a
structure change degrades to None — never raise into the pipeline, never fabricate. Fetched
through the shared _http base (cache/rate-limit/retry/UA/degrade).
"""

import logging
from datetime import datetime, timezone

from catalyst_trader.providers._http import get_json

logger = logging.getLogger(__name__)

# S-3ASR is auto-effective on filing; a plain S-3 becomes a shelf once declared effective.
# ponytail: presence-of-form heuristic — the submissions feed carries no "effective" flag;
# tighten (join the EFFECT filing) only if a stale/withdrawn shelf produces a false F9.
_SHELF_FORMS = {"S-3", "S-3ASR"}


def fetch(ticker: str, cik: str | int | None = None) -> dict | None:
    """SEC submissions for ``ticker`` -> {seen_accessions, live_shelf, provenance}, or None.

    ``cik`` is required to address the submissions endpoint; when None we cannot query SEC and
    degrade to None (Plan 07 wires the curated ticker->CIK map). seen_accessions is a list of
    {accession, form, filing_date}; live_shelf is True iff a live S-3 shelf form is present.
    """
    if not cik:
        logger.warning("edgar: no CIK for %s — cannot query SEC, returning None", ticker)
        return None

    url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    data = get_json("edgar", url, ua="sec", ttl_s=300)  # raises on unset SEC UA (config error)
    if not data:
        return None

    recent = data.get("filings", {}).get("recent", {})
    accnos = recent.get("accessionNumber", [])
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    seen_accessions = [
        {"accession": a, "form": f, "filing_date": d}
        for a, f, d in zip(accnos, forms, dates)
    ]
    live_shelf = any(f in _SHELF_FORMS for f in forms)

    return {
        "seen_accessions": seen_accessions,
        "live_shelf": live_shelf,
        "provenance": {
            "source_url": url,
            "fetch_ts": datetime.now(timezone.utc).isoformat(),
            "grade": "green",
        },
    }
