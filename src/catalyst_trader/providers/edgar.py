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

import edgar

from catalyst_trader.config import settings
from catalyst_trader.dates import now_iso

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
            "fetch_ts": now_iso(),
            "grade": "green",
        },
    }


def _period_months(period: str | None) -> int | None:
    """'2026-Q3' -> 9, '2026-FY' -> 12 (cumulative YTD span of an OCF fact); unknown -> None."""
    if not period:
        return None
    return _YTD_MONTHS.get(period.split("-")[-1])


def _monthly_burn(ocf_meta: dict | None) -> float | None:
    """Average monthly operating cash burn (USD), or None. Needs a genuine burn (OCF < 0) over a
    known cumulative period. Not burning (OCF >= 0), missing OCF, or an unknown period -> None.
    The single burn derivation reused by BOTH _runway_months and fundamentals (no duplication)."""
    if not ocf_meta:
        return None
    ocf = ocf_meta.get("value")
    months = _period_months(ocf_meta.get("period"))
    if ocf is None or not months or ocf >= 0:
        return None
    return -ocf / months


def _runway_months(cash_meta: dict | None, ocf_meta: dict | None) -> float | None:
    """cash / average monthly operating burn, or None. Never a fabricated/negative runway: needs
    cash AND a genuine burn (OCF < 0) over a known period. Not burning (OCF >= 0), missing
    cash/OCF, or an unknown period -> None."""
    if not cash_meta:
        return None
    cash = cash_meta.get("value")
    monthly_burn = _monthly_burn(ocf_meta)
    if cash is None or not monthly_burn:
        return None
    return round(cash / monthly_burn, 1)


def fundamentals(ticker: str) -> dict | None:
    """XBRL float/runway gap-filler for ``ticker`` ->
    {shares_outstanding, cash_usd, monthly_burn_usd, cash_runway_months, provenance}, or None.

    From edgartools' STANDARDIZED facts (synonym-resolved, robust across filers):
    common_shares_outstanding, cash_and_equivalents, operating_cash_flow. cash_usd/monthly_burn_usd
    are the raw money-dim figures (monthly_burn_usd reuses _monthly_burn — the SAME derivation
    cash_runway_months uses); cash_runway_months is model-free arithmetic (cash / monthly operating
    burn). Each is None when the underlying fact is missing or the company is not burning (never
    fabricated). Any edgartools error / no usable facts -> None (degrade).
    """
    _set_identity()  # config error if no UA (raises, not a degrade)
    try:
        company = edgar.Company(ticker)  # ticker->CIK resolved by edgartools
        facts = company.get_facts()
        shares = facts.get_concept("common_shares_outstanding", return_metadata=True)
        cash = facts.get_concept("cash_and_equivalents", return_metadata=True)
        ocf = facts.get_concept("operating_cash_flow", return_metadata=True)
    except Exception as e:  # noqa: BLE001 — degrade on ANY edgartools failure, never crash pipeline
        logger.warning("edgar.fundamentals degraded for %s: %s", ticker, e)
        return None

    if not shares and not cash:  # no usable XBRL facts on record
        return None

    # point-in-time honesty: carry the freshest fact's filing date in provenance
    latest = max(
        (m for m in (shares, cash, ocf) if m and m.get("filing_date")),
        key=lambda m: m["filing_date"],
        default=None,
    )
    return {
        "shares_outstanding": shares.get("value") if shares else None,
        "cash_usd": cash.get("value") if cash else None,
        "monthly_burn_usd": _monthly_burn(ocf),
        "cash_runway_months": _runway_months(cash, ocf),
        "provenance": {
            "source_url": f"https://data.sec.gov/api/xbrl/companyfacts/CIK{getattr(company, 'cik', 0):010d}.json",
            "fetch_ts": now_iso(),
            "filing_date": str(latest["filing_date"]) if latest else None,
            "grade": "green",
        },
    }


def insider_net(ticker: str, *, since: str, until: str) -> float | None:
    """Net insider Form-4 signal for ``ticker`` over [since, until] (both ISO) -> net shares, or None.

    Sums each Form-4's TransactionSummary.net_change (+buy / -sell shares — robust; net_value can be
    None when a txn carries no price). Semantics:
      - a genuinely quiet tape (NO Form-4 in the window) -> 0.0 (a REAL datum, grounds ownership).
      - an edgartools error (unknown ticker / API failure) -> None (degrade, never raise).
      - a single unparseable filing is SKIPPED; the good ones still sum. All-fail -> None.
    Window is the caller's concern (since/until) — no magic literal here. SEC-UA gated like fetch.
    """
    _set_identity()  # config error if no UA (raises, not a degrade)
    try:
        company = edgar.Company(ticker)  # ticker->CIK resolved by edgartools
        filings = company.get_filings(form="4", filing_date=f"{since}:{until}")
    except Exception as e:  # noqa: BLE001 — degrade on ANY edgartools failure, never crash pipeline
        logger.warning("edgar.insider_net degraded for %s: %s", ticker, e)
        return None

    if not filings:  # quiet tape = a real 0, grounded (NOT a miss)
        return 0.0

    total, parsed = 0.0, 0
    for f in filings:
        try:
            nc = f.obj().get_ownership_summary().net_change
        except Exception:  # noqa: BLE001 — skip a single unparseable filing, keep the good ones
            continue
        if nc is not None:
            total += float(nc)
            parsed += 1
    return total if parsed else None  # all-fail -> degrade (None), never a fabricated 0
