"""PDUFA/AdCom catalyst feed: Federal Register (GREEN) + RTTNews (YELLOW) -> list[Catalyst].

The Blocker-2 fix lives here. For a PDUFA/AdCom event that BOTH feeds report, we emit ONE
Catalyst whose ``sources`` list carries BOTH CatalystSources — Federal Register (JSON,
primary) AND RTTNews (HTML, secondary) — under a single shared external_ref. That matters
because insert_catalyst DELETE+replaces the source rows for a given (ticker, external_ref):
emitting FR and RTTNews as two separate Catalysts with the same ref would make the second
overwrite the first's sources, so neither ever reaches the two-source verify gate
(len(agreeing) >= 2 and has_primary). Merging both sources into one Catalyst means a single
insert writes both rows and the gate can actually fire. No store.py change needed.

Discipline:
  - A single-feed event (only FR OR only RTTNews) emits a ONE-source Catalyst — it stays
    unverified/untradeable downstream (cite-or-drop, never forced tradeable).
  - The FR source carries its document ``publication_date`` (transport-only) so Plan 07 can
    stamp last_verified_at point-in-time. This provider does NOT set last_verified_at and does
    NOT verify (Pitfall 4) — emitted Catalysts flow through the existing insert->verify pipeline.
  - date_type is ``estimated`` for both sources: a PDUFA/AdCom date is an ANNOUNCED TARGET, not
    a realized event (mirrors verify.load_curated_pdufa; ``actual`` is reserved for realized).
    The GREEN/YELLOW authority distinction is source_type (primary vs secondary), which is what
    the verify gate reads — not date_type.
  - RTTNews is discovery-only (Pitfall 6): a row alone is never authoritative; any row lacking a
    citable source_url is DROPPED. Each feed fetches through _http and degrades to [] on
    403/timeout independently — never raise, never fabricate.
"""

import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from catalyst_trader.dates import classify, parse_precision
from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    CatalystType,
    DateType,
    SourceOrigin,
    SourceType,
)
from catalyst_trader.providers._http import get_json, get_text

logger = logging.getLogger(__name__)

_FR_URL = "https://www.federalregister.gov/api/v1/documents.json"
_RTT_URL = "https://www.rttnews.com/corpinfo/fdacalendar.aspx"

# A full-month-name date embedded in FR free text: "November 14, 2026".
_DATE_RX = re.compile(r"([A-Z][a-z]+\.?\s+\d{1,2},\s+\d{4})")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_date(raw: str) -> str | None:
    """Normalize an FR/RTTNews date string to ISO YYYY-MM-DD, or None if unparseable."""
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


def _ctype(fr_title: str, rtt_event: str) -> CatalystType:
    blob = f"{fr_title} {rtt_event}".lower()
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


def _parse_rttnews(html: str, tickers: set[str]) -> dict:
    """RTTNews FDA-calendar HTML -> {(ticker, iso_event_date): row}. Drops out-of-universe,
    undated, and URL-less rows (cite-or-drop, Pitfall 6)."""
    out: dict[tuple[str, str], dict] = {}
    soup = BeautifulSoup(html or "", "lxml")
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 6:  # header rows use <th> -> skipped; short/malformed rows ignored
            continue
        ticker = tds[1].get_text(strip=True).upper()
        if ticker not in tickers:
            continue
        event_date = _norm_date(tds[3].get_text(strip=True))
        if not event_date:
            continue
        link = tds[5].find("a")
        url = link.get("href").strip() if (link and link.get("href")) else None
        if not url:  # cite-or-drop: a discovery row with no citable URL is never emitted
            continue
        out[(ticker, event_date)] = {
            "company": tds[0].get_text(strip=True),
            "drug": tds[2].get_text(strip=True),
            "event": tds[4].get_text(strip=True),
            "url": url,
        }
    return out


def fetch(
    tickers: list[str],
    date_from: str,
    date_to: str,
    *,
    company_map: dict[str, list[str]] | None = None,
) -> list[Catalyst]:
    """PDUFA/AdCom catalysts in [date_from, date_to] for ``tickers`` -> list[Catalyst].

    ``company_map`` (ticker -> [drug/company name strings]) attributes Federal Register notices
    to a universe ticker; RTTNews rows carry their own ticker symbol. A corroborated event yields
    ONE 2-source Catalyst; a single-feed event yields a one-source (unverified) Catalyst. Each
    feed degrades independently; the provider never verifies and never sets last_verified_at.
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

    rtt_html = get_text("rttnews", _RTT_URL, ua="browser")
    rtt_by_key = _parse_rttnews(rtt_html or "", tickers_set)

    out: list[Catalyst] = []
    for key in fr_by_key.keys() | rtt_by_key.keys():
        ticker, event_date = key
        doc = fr_by_key.get(key)
        row = rtt_by_key.get(key)

        sources: list[CatalystSource] = []
        if doc is not None:
            sources.append(
                CatalystSource(
                    source_name="Federal Register",
                    source_url=doc.get("html_url"),
                    source_type=SourceType.primary,
                    reported_date=event_date,
                    date_type=DateType.estimated,  # announced target, not realized
                    published_date=doc.get("publication_date"),  # transport-only (Plan 07)
                    retrieved_at=_now(),
                )
            )
        if row is not None:
            sources.append(
                CatalystSource(
                    source_name="RTTNews",
                    source_url=row["url"],
                    source_type=SourceType.secondary,
                    reported_date=event_date,
                    date_type=DateType.estimated,  # discovery — never authoritative alone
                    retrieved_at=_now(),
                )
            )

        fr_title = doc.get("title", "") if doc else ""
        rtt_event = row.get("event", "") if row else ""
        has_primary = any(s.source_type == SourceType.primary for s in sources)
        out.append(
            Catalyst(
                ticker=ticker,
                company_name=(row or {}).get("company") or None,
                catalyst_type=_ctype(fr_title, rtt_event),
                event_date=event_date,
                date_precision=parse_precision(event_date),
                uncertainty_type=classify(
                    event_date,
                    DateType.estimated.value,
                    source_count=len(sources),
                    has_primary=has_primary,
                ),
                source_origin=SourceOrigin.curated_pdufa,  # the PDUFA/AdCom bucket (DB-constrained)
                # Deterministic ref so both sources land on ONE catalyst and re-runs are idempotent.
                external_ref=f"pdufa:{ticker}:{event_date}",
                sources=sources,
                # last_verified_at deliberately unset — the insert->verify pipeline owns it.
            )
        )
    return out
