"""SEC EDGAR via edgartools -> filings signals (build_card contract) + XBRL fundamentals.

Two providers, both edgartools-backed (PIPE-03/08/09), both degrade-never-crash:

- ``fetch(ticker)`` keeps the EXACT contract desk/company_scan.build_card consumes —
  ``seen_accessions`` (list of {accession, form, filing_date}) + ``live_shelf`` (bool) — but
  resolves the CIK INTERNALLY via ``edgar.Company(ticker)`` (edgartools maps ticker->CIK), so the
  6.9 shakedown's "no CIK for TICKER" degrade is gone for every real universe name. Form-4/13F
  ownership stay DEFERRED (no consumer — YAGNI, RESEARCH Open Q3).
- ``fundamentals(ticker)`` is the float/runway gap-filler: ``shares_outstanding`` +
  ``cash_runway_months`` from edgartools' standardized XBRL facts, + provenance.

edgartools needs a declared contact-email UA (``set_identity``, from ``settings.sec_user_agent`` —
Pitfall 3); an unset one is the ONE legit config error (RuntimeError, matching _http's UA rule —
never send an empty UA). Any edgartools error / unknown ticker / missing facts degrades to None:
never raise into the pipeline, never fabricate (esp. never a fabricated/negative cash runway).
"""

import logging
from datetime import datetime, timezone

import edgar

from catalyst_trader.config import settings

logger = logging.getLogger(__name__)

# S-3ASR is auto-effective on filing; a plain S-3 becomes a shelf once declared effective.
# ponytail: presence-of-form heuristic — the feed carries no "effective" flag; tighten (join the
# EFFECT filing) only if a stale/withdrawn shelf produces a false F9.
_SHELF_FORMS = {"S-3", "S-3ASR"}
# Only the forms build_card reads: company_scan._OFFERING_FORMS {424B5, FWP} for F9 + S-3/S-3ASR
# for live_shelf. A narrow fetch is cheap AND keeps seen_accessions the exact offering surface.
# (edgartools prefix-matches, so "S-3" also pulls S-3/A amendments into seen_accessions.)
_TRACKED_FORMS = ["424B5", "FWP", "S-3", "S-3ASR"]

# A 10-Q's operating_cash_flow is period-to-date (cumulative), so the fiscal-period suffix maps to
# YTD months. ponytail: derived from the period string; if a filer reports non-cumulative quarterly
# OCF this mis-scales burn — tighten via the fact's period_start/period_end if it ever bites.
_YTD_MONTHS = {"Q1": 3, "Q2": 6, "Q3": 9, "Q4": 12, "FY": 12}


def _set_identity() -> None:
    """Declare the SEC UA once per call from settings; unset -> RuntimeError (config error)."""
    ua = settings.sec_user_agent
    if not ua:
        raise RuntimeError("SEC_USER_AGENT unset — edgartools needs a declared contact-email UA")
    edgar.set_identity(ua)


def _company_source_url(cik) -> str:
    return (
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
        f"&CIK={cik}&type=&dateb=&owner=include&count=40"
    )


def fetch(ticker: str) -> dict | None:
    """SEC filings for ``ticker`` -> {seen_accessions, live_shelf, provenance}, or None.

    CIK is resolved INTERNALLY by edgartools (no caller cik, no ticker->CIK map). seen_accessions
    is a list of {accession, form, filing_date}; live_shelf is True iff a live S-3 shelf is present.
    Unknown ticker / edgartools error / no tracked filings -> None (degrade, never raise).
    """
    _set_identity()  # config error if no UA (raises, not a degrade)
    try:
        company = edgar.Company(ticker)  # ticker->CIK resolved by edgartools
        filings = company.get_filings(form=_TRACKED_FORMS)
        rows = [
            {"accession": f.accession_no, "form": f.form, "filing_date": str(f.filing_date)}
            for f in filings
        ]
    except Exception as e:  # noqa: BLE001 — degrade on ANY edgartools failure, never crash pipeline
        logger.warning("edgar.fetch degraded for %s: %s", ticker, e)
        return None

    if not rows:  # no offering/shelf filings on record -> nothing for build_card to read
        return None

    return {
        "seen_accessions": rows,
        "live_shelf": any(r["form"] in _SHELF_FORMS for r in rows),
        "provenance": {
            "source_url": _company_source_url(getattr(company, "cik", None)),
            "fetch_ts": datetime.now(timezone.utc).isoformat(),
            "grade": "green",
        },
    }
