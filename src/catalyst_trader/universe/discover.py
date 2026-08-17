"""Data-driven universe discovery (UNIV-01..05) — source, screen, size, write.

The engine that GROWS the tradeable universe from our OWN free data instead of hand-picking:

1. discover_candidates (Plan 01, UNIV-01): two free feeds, both the REVERSE of how the shipped
   providers run today, merged into ONE CIK-keyed candidate set (CIK-keyed so a recycled ticker
   can never merge two legal entities — Pitfall 3):
     - CT.gov reverse-sponsor: an UNFILTERED near-term interventional Ph2/Ph3 primaryCompletionDate
       query -> leadSponsor.name -> ticker via the INVERTED ticker_sponsor_map. A lead sponsor not
       in the curated map is DROPPED to a human-review queue (cite-or-drop), NEVER fuzzy-matched.
     - EDGAR unfiltered efts PDUFA: the shipped pdufa_edgar efts pass with NO universe-CIK
       intersection; the ticker is resolved PER HIT from display_names ("Name (TICKER) (CIK ...)").

Only live-parity catalyst TYPES count as discovery evidence (PDUFA + trial readout + AdCom — the
exact set our shipped free providers emit; earnings/late-breakers have no free live source, so the
backtestable set == the live-emittable set). Every network unit degrades to {}/skip on failure.

Discipline: FREE data only; provenance/cite-or-drop; no-LLM-dates; survivorship-free; NO new dep,
NO migration; the shipped providers (clinicaltrials, pdufa_edgar, prices, options_cboe, edgar,
universe/build) are REUSED unchanged.
"""

import logging
import re
from pathlib import Path

import edgar
import httpx

from catalyst_trader.dates import now_iso
from catalyst_trader.providers import clinicaltrials
from catalyst_trader.providers._http import get_json, get_text
from catalyst_trader.providers.edgar import _set_identity  # reuse the SEC-UA declaration
from catalyst_trader.providers.pdufa_edgar import (
    _EFTS_QUERIES,
    _EFTS_URL,
    _exhibit_url,
    _extract,
)

logger = logging.getLogger(__name__)

# The live-parity discovery set — the ONLY catalyst types that count as evidence (must match what
# the shipped free providers emit; earnings/conference late-breakers have no free live source).
LIVE_PARITY_TYPES = frozenset({"pdufa", "adcom", "trial_readout"})

# The CT.gov unknown-lead-sponsor review queue (mirror pdufa_edgar's MEDIUM->CSV pattern): a lead
# sponsor absent from the curated map lands here as a #-commented row for a human to map->ticker,
# NEVER fuzzy-attributed. Module constant so tests monkeypatch it to tmp_path.
_SPONSOR_REVIEW_CSV = Path("data/ctgov_sponsor_review.csv")

# Ticker parsed per efts hit from display_names[0]. NON-anchored on purpose: real display_names
# trail a "(CIK 0001234567)" paren, so an anchored r"\(...\)$" would match the CIK paren and drop
# EVERY hit (zeroing the primary new-name engine). The letter class never matches "CIK 000..."
# (space + digits), so findall yields only the real (TICKER) paren(s); take the last.
_TICKER_RX = re.compile(r"\(([A-Z][A-Z.]{0,5})\)")


# ── shared helpers ───────────────────────────────────────────────────────────────────────


def _reverse_sponsor_map(sponsor_map: dict[str, list[str]]) -> dict[str, str]:
    """Invert load_sponsor_map()'s {ticker -> [legal names]} to {name.casefold(): ticker}.

    Multiple legal names for one ticker (e.g. BBIO's QED + Calcilytix subsidiaries) all map back
    to that ticker. casefold keys so the CT.gov leadSponsor.name compares case-insensitively.
    """
    rev: dict[str, str] = {}
    for ticker, names in sponsor_map.items():
        for name in names:
            rev[name.casefold()] = ticker
    return rev


def _resolve_cik(ticker: str) -> int | None:
    """ticker -> int CIK via the edgartools package (edgar.Company(ticker).cik), mirroring
    edgar.py's _set_identity() pattern. Unknown ticker / edgartools error -> None (degrade)."""
    try:
        _set_identity()
        return int(edgar.Company(ticker).cik)
    except Exception as e:  # noqa: BLE001 — unknown ticker / edgartools error -> skip, never raise
        logger.warning("discover: CIK resolution degraded for %s: %s", ticker, e)
        return None


def _ticker_from_display(display_name: str | None) -> str | None:
    """"Immunome, Inc. (IMNM) (CIK 0001476964)" -> "IMNM"; no letter-paren -> None (cite-or-drop)."""
    if not display_name:
        return None
    matches = _TICKER_RX.findall(display_name)
    return matches[-1] if matches else None  # last (real ticker) paren; CIK paren never matches


# ── CT.gov reverse-sponsor discovery ───────────────────────────────────────────────────────


def _queue_sponsor_review(lead: str, nct: str | None) -> None:
    """Append an unmapped CT.gov lead sponsor to the human-review queue as a #-commented row
    (cite-or-drop, NEVER fuzzy-attributed). Idempotent: the exact row is written at most once."""
    row = f"# {lead},{nct or ''}"  # a human maps this legal name -> ticker, then uncomments
    path = Path(_SPONSOR_REVIEW_CSV)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if row in existing:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write(row + "\n")


def _admit_ctgov_study(study: dict, rev: dict[str, str], out: dict[int, dict]) -> None:
    """Admit one CT.gov study to the candidate set (or route its unmapped sponsor to review)."""
    ps = study.get("protocolSection", {})
    phases = ps.get("designModule", {}).get("phases") or []
    if not any(p in ("PHASE2", "PHASE3") for p in phases):
        return  # readout-density driver: only Ph2/Ph3 interventional count (query also filters)
    lead = ps.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name")
    if not lead:
        return
    pcd = ps.get("statusModule", {}).get("primaryCompletionDateStruct") or {}
    event_date = pcd.get("date")
    if not event_date:
        return  # no date -> nothing to attribute (no-LLM-dates)
    nct = ps.get("identificationModule", {}).get("nctId")

    ticker = rev.get(lead.casefold())
    if not ticker:
        _queue_sponsor_review(lead, nct)  # cite-or-drop: never fuzzy-match a sponsor to a ticker
        return
    cik = _resolve_cik(ticker)
    if cik is None:
        return  # cannot key by CIK -> drop (ticker-recycling safety needs the CIK)

    cand = out.setdefault(
        cik,
        {"cik": cik, "ticker": ticker, "company_name": lead, "catalysts": [], "source_feeds": {"ctgov"}},
    )
    cand["catalysts"].append(
        {
            "type": "trial_readout",
            "event_date": event_date,
            "source_url": f"https://clinicaltrials.gov/study/{nct}",
            "fetch_ts": now_iso(),
            "grade": "green",  # CT.gov registry primaryCompletionDate — authoritative primary
        }
    )


def discover_ctgov(
    date_from: str,
    date_to: str,
    *,
    client: httpx.Client | None = None,
    sponsor_map: dict[str, list[str]] | None = None,
) -> dict[int, dict]:
    """UNFILTERED near-term interventional Ph2/Ph3 CT.gov studies -> CIK-keyed candidate dict.

    Runs the shipped provider BACKWARD: no query.spons — query primaryCompletionDate broadly, then
    reverse-map each study's leadSponsor.name to a ticker. An unmapped sponsor routes to the
    human-review queue (never fuzzy). CT.gov HTTP error / empty -> {} (degrade, never raise).
    """
    rev = _reverse_sponsor_map(sponsor_map or clinicaltrials.load_sponsor_map())
    own_client = client is None
    client = client or httpx.Client(transport=httpx.HTTPTransport(retries=2))
    out: dict[int, dict] = {}
    try:
        page_token: str | None = None
        while True:
            params = {
                "filter.advanced": (
                    f"AREA[PrimaryCompletionDate]RANGE[{date_from},{date_to}] "
                    "AND AREA[Phase]COVER[PHASE2,PHASE3] "
                    "AND AREA[StudyType]COVER[INTERVENTIONAL]"
                ),
                "fields": clinicaltrials.FIELDS,
                "pageSize": 100,
                "countTotal": "true",
            }
            if page_token:
                params["pageToken"] = page_token
            resp = client.get(f"{clinicaltrials.BASE}/studies", params=params)
            resp.raise_for_status()
            data = resp.json() or {}
            for study in data.get("studies", []):
                _admit_ctgov_study(study, rev, out)
            page_token = data.get("nextPageToken")
            if not page_token:
                break
    except Exception as e:  # noqa: BLE001 — any CT.gov failure degrades the whole feed to {}
        logger.warning("discover_ctgov degraded: %s", e)
        return {}
    finally:
        if own_client:
            client.close()
    return out


# ── EDGAR unfiltered efts PDUFA discovery ──────────────────────────────────────────────────


def discover_edgar(date_from: str, date_to: str) -> dict[int, dict]:
    """UNFILTERED efts PDUFA/AdCom pass (NO universe-CIK intersection) -> CIK-keyed candidate dict.

    The primary new-name engine: efts carries ticker+CIK per hit for free. For each hit resolve the
    ticker from display_names[0] (NON-anchored regex, take last) and CIK = int(ciks[0]); fetch the
    exhibit, run the shipped _extract, and admit only HIGH-confidence PDUFA/AdCom extractions. No
    parseable ticker OR no CIK -> drop (cite-or-drop). MEDIUM extractions are handled on the live
    pdufa_edgar path's review CSV — not double-handled here. Any efts/exhibit failure degrades.
    """
    seen_accessions: set[str] = set()
    out: dict[int, dict] = {}
    for q in _EFTS_QUERIES:
        params = {"q": q, "forms": "8-K", "startdt": date_from, "enddt": date_to}
        data = get_json("edgar_efts", _EFTS_URL, params=params, ua="sec")
        if not data:  # this phrase degraded -> try the next (each degrades independently)
            continue
        for hit in data.get("hits", {}).get("hits", []):
            src = hit.get("_source", {})
            ciks = [c for c in src.get("ciks", []) if str(c).strip().isdigit()]
            if not ciks:
                continue  # no CIK key -> drop (cite-or-drop)
            cik = int(ciks[0])
            display = src.get("display_names") or []
            ticker = _ticker_from_display(display[0] if display else None)
            if not ticker:
                continue  # no (TICKER) suffix -> drop (cite-or-drop), never keyed as "CIK"
            _id = hit.get("_id", "")
            if ":" not in _id:
                continue
            accession, doc = _id.split(":", 1)
            if accession in seen_accessions:
                continue  # same 8-K surfaces under several phrases -> dedupe by accession
            seen_accessions.add(accession)

            url = _exhibit_url(cik, accession, doc)
            html = get_text("edgar_8k", url, ua="sec")
            if not html:  # exhibit degraded -> skip this hit, others still emit
                continue
            company_name = _company_name_from_display(display[0] if display else None)
            for cand in _extract(html, src.get("file_date")):
                if cand["confidence"] != "HIGH":
                    continue  # MEDIUM -> pdufa_edgar's live review CSV, not double-handled here
                entry = out.setdefault(
                    cik,
                    {
                        "cik": cik,
                        "ticker": ticker,
                        "company_name": company_name,
                        "catalysts": [],
                        "source_feeds": {"edgar"},
                    },
                )
                entry["catalysts"].append(
                    {
                        "type": cand["catalyst_type"].value,
                        "event_date": cand["event_date"],
                        "source_url": url,
                        "fetch_ts": now_iso(),
                        "grade": "green",  # HIGH-confidence SEC EDGAR extraction (self-verifying)
                    }
                )
    return out


def _company_name_from_display(display_name: str | None) -> str | None:
    """"Immunome, Inc. (IMNM) (CIK 0001476964)" -> "Immunome, Inc." (strip trailing paren groups)."""
    if not display_name:
        return None
    return re.sub(r"(\s*\([^)]*\))+\s*$", "", display_name).strip() or None


# ── merge both free feeds by CIK ───────────────────────────────────────────────────────────


def discover_candidates(
    date_from: str,
    date_to: str,
    *,
    client: httpx.Client | None = None,
    sponsor_map: dict[str, list[str]] | None = None,
) -> dict[int, dict]:
    """Merge CT.gov reverse-sponsor + unfiltered efts PDUFA into ONE CIK-keyed candidate set.

    A CIK found by both feeds accumulates the UNION of its catalysts and both source_feeds — never
    a duplicate CIK row. Only live-parity types survive into the merged evidence. Either feed
    failing degrades to its own {}; the merge still returns the other feed's candidates.
    """
    ctgov = discover_ctgov(date_from, date_to, client=client, sponsor_map=sponsor_map)
    edgar_feed = discover_edgar(date_from, date_to)

    merged: dict[int, dict] = {}
    for feed in (ctgov, edgar_feed):
        for cik, cand in feed.items():
            live = [c for c in cand["catalysts"] if c["type"] in LIVE_PARITY_TYPES]
            if not live:
                continue
            entry = merged.setdefault(
                cik,
                {
                    "cik": cik,
                    "ticker": cand["ticker"],
                    "company_name": cand.get("company_name"),
                    "catalysts": [],
                    "source_feeds": set(),
                },
            )
            entry["catalysts"].extend(live)
            entry["source_feeds"] |= set(cand["source_feeds"])
            entry["company_name"] = entry["company_name"] or cand.get("company_name")
    return merged
