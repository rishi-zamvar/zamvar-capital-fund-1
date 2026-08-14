"""ClinicalTrials.gov API v2 client — trial-readout catalysts, partial-date-aware.

Two verified gotchas shape this parser (see 01-RESEARCH.md):
  1. ``primaryCompletionDateStruct.date`` is often month-only (``2027-04``) — routed
     through the canonical ``dates`` classifier, never coerced to a day.
  2. ``query.spons`` is fuzzy — it returns studies where the company is only a
     *collaborator*. We keep a study only if its ``leadSponsor.name`` is the ticker's
     curated legal name (``data/ticker_sponsor_map.csv``).
"""

import csv
import time
from datetime import datetime, timezone
from pathlib import Path

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

BASE = "https://clinicaltrials.gov/api/v2"
FIELDS = "NCTId,BriefTitle,Phase,OverallStatus,PrimaryCompletionDate,LeadSponsorName"
_DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_sponsor_map(path: str | Path | None = None) -> dict[str, list[str]]:
    """ticker -> [exact legal leadSponsor name(s)] from the curated CSV (# lines ignored)."""
    csv_path = Path(path) if path else _DATA_DIR / "ticker_sponsor_map.csv"
    rows = [
        ln
        for ln in csv_path.read_text().splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    out: dict[str, list[str]] = {}
    for row in csv.DictReader(rows):
        out.setdefault(row["ticker"].strip(), []).append(row["legal_sponsor_name"].strip())
    return out


def _parse_study(study: dict, ticker: str, allowed_sponsors: set[str]) -> Catalyst | None:
    ps = study.get("protocolSection", {})
    lead = ps.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name")
    if lead not in allowed_sponsors:  # lead-sponsor filter (collaborator gotcha)
        return None
    pcd = ps.get("statusModule", {}).get("primaryCompletionDateStruct")
    if not pcd or not pcd.get("date"):
        return None  # no date -> nothing to attribute
    raw_date = pcd["date"]
    ctype = pcd.get("type", "ESTIMATED")  # ESTIMATED | ACTUAL
    nct = ps.get("identificationModule", {}).get("nctId")
    date_type = DateType.estimated if ctype == "ESTIMATED" else DateType.actual
    source = CatalystSource(
        source_name="ClinicalTrials.gov",
        source_url=f"https://clinicaltrials.gov/study/{nct}",
        source_type=SourceType.primary,
        reported_date=raw_date,
        date_type=date_type,  # DATA-04: persist the source's own precision typing
        retrieved_at=_now(),
    )
    return Catalyst(
        ticker=ticker,
        company_name=lead,
        catalyst_type=CatalystType.trial_readout,
        event_date=raw_date,
        date_precision=parse_precision(raw_date),
        uncertainty_type=classify(raw_date, ctype, source_count=1, has_primary=True),
        source_origin=SourceOrigin.clinicaltrials_gov,
        external_ref=nct,
        sources=[source],
    )


def fetch_trial_readouts(
    tickers: list[str],
    date_from: str,
    date_to: str,
    *,
    client: httpx.Client | None = None,
    sponsor_map: dict[str, list[str]] | None = None,
) -> list[Catalyst]:
    """Trial readouts whose primaryCompletionDate falls in [date_from, date_to].

    Attributed to a ticker only when the study's *lead* sponsor is that ticker's
    curated legal name. Returns Catalysts with provenance already attached.
    """
    if sponsor_map is None:
        sponsor_map = load_sponsor_map()
    own_client = client is None
    client = client or httpx.Client(transport=httpx.HTTPTransport(retries=2))

    out: list[Catalyst] = []
    first_request = True
    try:
        for ticker in tickers:
            legal_names = sponsor_map.get(ticker, [])
            allowed = set(legal_names)
            for name in legal_names:
                page_token: str | None = None
                while True:
                    if not first_request:
                        time.sleep(settings.ctgov_request_spacing_s)
                    first_request = False
                    params = {
                        "filter.advanced": (
                            f"AREA[PrimaryCompletionDate]RANGE[{date_from},{date_to}]"
                        ),
                        "query.spons": name,
                        "fields": FIELDS,
                        "pageSize": 100,
                        "countTotal": "true",
                    }
                    if page_token:
                        params["pageToken"] = page_token
                    resp = client.get(f"{BASE}/studies", params=params)
                    resp.raise_for_status()
                    data = resp.json()
                    for study in data.get("studies", []):
                        catalyst = _parse_study(study, ticker, allowed)
                        if catalyst is not None:
                            out.append(catalyst)
                    page_token = data.get("nextPageToken")
                    if not page_token:
                        break
    finally:
        if own_client:
            client.close()
    return out
