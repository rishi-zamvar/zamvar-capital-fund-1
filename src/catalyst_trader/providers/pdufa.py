"""AdCom catalyst feed: Federal Register (GREEN, primary) -> list[Catalyst].

Federal Register is the government publication of record for FDA advisory-committee (AdCom)
meetings — a single authoritative primary source. It is listed in
``verify.AUTHORITATIVE_SUFFICIENT``, so an FR-attributed AdCom notice self-verifies on the
single-source path (DATA-03 amendment) and becomes tradeable without a second feed.

PDUFA action dates are sourced separately by ``providers/pdufa_edgar`` (the SEC-8K tracker) and
the hand-curated ``data/pdufa_curated.csv`` review queue — this provider covers the FR AdCom half.

Discipline:
  - The FR source carries its document ``publication_date`` (transport-only) so the ingest loop
    can stamp ``last_verified_at`` point-in-time. This provider does NOT set last_verified_at and
    does NOT verify (Pitfall 4) — emitted Catalysts flow through the existing insert->verify pipeline.
  - date_type is ``estimated``: a PDUFA/AdCom date is an ANNOUNCED TARGET, not a realized event
    (mirrors verify.load_curated_pdufa; ``actual`` is reserved for realized). The authority
    distinction the verify gate reads is source_type (primary), not date_type.
  - cite-or-drop / date-or-drop: an unattributable, undated, or URL-less notice is DROPPED. The
    feed fetches through _http and degrades to [] on 403/timeout — never raise, never fabricate.
"""

import logging
import re
from datetime import datetime

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

_FR_URL = "https://www.federalregister.gov/api/v1/documents.json"

# A full-month-name date embedded in FR free text: "November 14, 2026".
_DATE_RX = re.compile(r"([A-Z][a-z]+\.?\s+\d{1,2},\s+\d{4})")


def _norm_date(raw: str) -> str | None:
    """Normalize an FR date string to ISO YYYY-MM-DD, or None if unparseable."""
    s = (raw or "").strip().replace(".", "")
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _fr_event_date(doc: dict) -> str | None:
    """The meeting/event date announced in the FR notice (dates field, then title) — or None.

    Distinct from publication_date. date-or-drop: if we cannot cite a parseable event date we
    do not fabricate one.
    """
    for text in (doc.get("dates", ""), doc.get("title", "")):
        m = _DATE_RX.search(text or "")
        if m:
            iso = _norm_date(m.group(1))
            if iso:
                return iso
    return None


def _attribute(title: str, company_map: dict[str, list[str]]) -> str | None:
    """Map an FR notice to a universe ticker via drug/company names appearing in its title."""
    t = (title or "").lower()
    for ticker, names in company_map.items():
        if any(name.lower() in t for name in names):
            return ticker
    return None


def _ctype(fr_title: str) -> CatalystType:
    blob = (fr_title or "").lower()
    if "advisory committee" in blob or "adcom" in blob:
        return CatalystType.adcom
    return CatalystType.pdufa


def _parse_fr(results, tickers: set[str], company_map: dict[str, list[str]]) -> dict:
    """FR documents -> {(ticker, iso_event_date): doc}. Drops unattributable/undated/uncitable."""
    out: dict[tuple[str, str], dict] = {}
    for doc in results or []:
        title = doc.get("title", "")
        ticker = _attribute(title, company_map)
        if not ticker or ticker not in tickers:
            continue
        if not doc.get("html_url"):  # cite-or-drop
            continue
        event_date = _fr_event_date(doc)
        if not event_date:  # date-or-drop
            continue
        out[(ticker, event_date)] = doc
    return out


def fetch(
    tickers: list[str],
    date_from: str,
    date_to: str,
    *,
    company_map: dict[str, list[str]] | None = None,
) -> list[Catalyst]:
    """AdCom catalysts in [date_from, date_to] for ``tickers`` -> list[Catalyst].

    ``company_map`` (ticker -> [drug/company name strings]) attributes Federal Register notices
    to a universe ticker. Each attributed notice yields ONE single-source primary Catalyst;
    Federal Register is authoritative-sufficient, so it verifies on the single-source path. The
    feed degrades to [] on outage; the provider never verifies and never sets last_verified_at.
    """
    tickers_set = {t.upper() for t in tickers}
    company_map = company_map or {}

    fr_params = {
        "conditions[term]": "advisory committee",
        "conditions[agencies][]": "food-and-drug-administration",
        "conditions[publication_date][gte]": date_from,
        "conditions[publication_date][lte]": date_to,
        # tuple (not list) so the _http cache key stays hashable; httpx repeats it the same way
        "fields[]": ("document_number", "title", "publication_date", "html_url", "dates"),
        "per_page": 100,
    }
    fr_json = get_json("federal_register", _FR_URL, params=fr_params, ua="browser")
    fr_by_key = _parse_fr((fr_json or {}).get("results", []), tickers_set, company_map)

    out: list[Catalyst] = []
    for (ticker, event_date), doc in fr_by_key.items():
        source = CatalystSource(
            source_name="Federal Register",
            source_url=doc.get("html_url"),
            source_type=SourceType.primary,
            reported_date=event_date,
            date_type=DateType.estimated,  # announced target, not realized
            published_date=doc.get("publication_date"),  # transport-only (point-in-time stamp)
            retrieved_at=now_iso(),
        )
        out.append(
            Catalyst(
                ticker=ticker,
                company_name=None,
                catalyst_type=_ctype(doc.get("title", "")),
                event_date=event_date,
                date_precision=parse_precision(event_date),
                uncertainty_type=classify(
                    event_date,
                    DateType.estimated.value,
                    source_count=1,
                    has_primary=True,
                ),
                source_origin=SourceOrigin.curated_pdufa,  # the PDUFA/AdCom bucket (DB-constrained)
                # Deterministic ref so re-runs are idempotent.
                external_ref=f"pdufa:{ticker}:{event_date}",
                sources=[source],
                # last_verified_at deliberately unset — the insert->verify pipeline owns it.
            )
        )
    return out
