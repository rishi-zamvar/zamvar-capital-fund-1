"""Our own authoritative, free PDUFA/AdCom catalyst source from SEC 8-K/PR filings.

Discovers PDUFA 8-Ks via EDGAR full-text search (efts, CIK-filtered to the universe), fetches the
matched exhibit (RAW HTML, as the live .htm delivers), normalizes HTML->text (tag-strip) FIRST,
then deterministically regex-extracts the date verbatim-adjacent to a PDUFA/target-action/goal/
AdCom keyword (no-LLM-dates, cite-or-drop), and emits a Catalyst with a SINGLE source_name=
"SEC EDGAR" primary source — which self-verifies via the DATA-03 amendment ("SEC EDGAR" is already
in verify.AUTHORITATIVE_SUFFICIENT) with ZERO verify.py change.

The offline-green/live-broken trap is closed here: live 8-K exhibits are raw HTML where tags
routinely split the keyword from the date (`...target action date</span> of <span>April 28,
2027`), which breaks the adjacency regex. So _extract runs an HTML->text normalization (tags ->
spaces, adjacency restored) BEFORE the regex. Fixtures are real-HTML-shaped, not clean .txt.

Discipline:
  - no-LLM-dates / cite-or-drop: emit only a date that appears verbatim adjacent to a keyword in
    the fetched filing; a bare date (no keyword) or an unparseable date is DROPPED, never imputed.
  - HIGH confidence (single unambiguous keyword+date, "PDUFA" token present) -> emitted as a
    Catalyst (auto-verifies). MEDIUM/LOW (multiple candidate dates / "target action date" without
    a "PDUFA" token / ambiguous AdCom date) -> appended to the curated-CSV review queue as
    #-commented rows (loader skips them -> a human uncomments to confirm), NOT emitted as tradeable.
  - point-in-time: the 8-K filing_date is carried as the source's published_date (anti-look-ahead,
    feeds ingest._pit_stamp) — never now()/event_date. The provider NEVER sets last_verified_at and
    NEVER verifies; emitted Catalysts flow through the existing insert->verify pipeline.
  - degrade-not-raise: any efts/exhibit/edgartools failure degrades the affected unit to [] / skip.
"""

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import edgar

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
from catalyst_trader.providers.edgar import _set_identity  # reuse the SEC-UA declaration
from catalyst_trader.providers.pdufa import _norm_date  # reuse the "%B %d, %Y" -> ISO primitive

logger = logging.getLogger(__name__)

_EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
# One query per keyword phrase (research §1.2). Same 8-K may surface under several -> deduped by
# accession downstream. AdCom phrase discovers advisory-committee 8-Ks alongside PDUFA ones.
_EFTS_QUERIES = ('"PDUFA target action date"', '"target action date"', '"advisory committee meeting"')

# The human-review queue is the EXISTING curated CSV (verify.load_curated_pdufa skips #-comment
# rows). MEDIUM/LOW candidates land here as #-commented rows so a human uncomments to confirm.
# Module constant so tests monkeypatch it to tmp_path and exercise the real append/idempotency.
_CURATED_CSV = Path("data/pdufa_curated.csv")

# Capture "Month DD, YYYY" immediately following a PDUFA/target-action/goal keyword (research §1.2),
# run AFTER HTML->text normalization so a tag-split keyword/date has been rejoined.
_PDUFA_RX = re.compile(
    r"(?:PDUFA\s+)?(?:target\s+action|goal)\s+date\s+(?:of|set\s+for|is|:)?\s*"
    r"([A-Z][a-z]+\.?\s+\d{1,2},\s+\d{4})",
    re.I,
)
_ADCOM_RX = re.compile(
    r"advisory\s+committee\s+meeting[^.]{0,80}?(?:on|scheduled\s+for)\s+"
    r"([A-Z][a-z]+\.?\s+\d{1,2},\s+\d{4})",
    re.I,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(html: str) -> str:
    """HTML -> plain text with tags collapsed to spaces so a `</span> of <span>`-split keyword/date
    rejoins into "...target action date of April 28, 2027" and the ~40-char adjacency holds. bs4 is
    already installed (ladder rung 5, no new dep); a raw regex tag-strip is the fallback."""
    try:
        from bs4 import BeautifulSoup

        text = BeautifulSoup(html or "", "html.parser").get_text(separator=" ")
    except Exception:  # noqa: BLE001 — bs4 import/parse failure -> regex fallback, never crash
        import html as _htmllib

        text = _htmllib.unescape(re.sub(r"<[^>]+>", " ", html or ""))
    return re.sub(r"\s+", " ", text).strip()


def _extract(html: str, filing_date: str) -> list[dict]:
    """Normalize the RAW HTML, then deterministically pull each keyword-adjacent date.

    Returns candidate dicts {catalyst_type, event_date (ISO), confidence, matched_keyword,
    filing_date}. no-LLM-dates + cite-or-drop: a match whose date does not parse is dropped; a
    date with no adjacent keyword is never captured. Confidence is a doc-level judgement:
      HIGH   = a single distinct date AND a "PDUFA" token present in some match (unambiguous).
      MEDIUM = multiple DISTINCT candidate dates, OR target-action/goal without a "PDUFA" token,
               OR an AdCom-only date -> routed to the human-review queue, never auto-tradeable.
    """
    text = _normalize(html)
    cands: list[dict] = []
    for rx, ctype in ((_PDUFA_RX, CatalystType.pdufa), (_ADCOM_RX, CatalystType.adcom)):
        for m in rx.finditer(text):
            iso = _norm_date(m.group(1))
            if not iso:  # cite-or-drop: unparseable date never emitted
                continue
            cands.append(
                {
                    "catalyst_type": ctype,
                    "event_date": iso,
                    "matched_keyword": m.group(0),
                    "has_pdufa": "pdufa" in m.group(0).lower(),
                }
            )
    if not cands:
        return []

    distinct_dates = {c["event_date"] for c in cands}
    if len(distinct_dates) > 1 or not any(c["has_pdufa"] for c in cands):
        confidence = "MEDIUM"  # ambiguous / no PDUFA token -> human confirm
    else:
        confidence = "HIGH"  # single unambiguous PDUFA date

    # Dedupe by (type, date) — the date repeats 3x in a real filing; keep one candidate per date.
    seen: dict[tuple, dict] = {}
    for c in cands:
        key = (c["catalyst_type"], c["event_date"])
        if key not in seen:
            seen[key] = {
                "catalyst_type": c["catalyst_type"],
                "event_date": c["event_date"],
                "confidence": confidence,
                "matched_keyword": c["matched_keyword"],
                "filing_date": filing_date,
            }
    return list(seen.values())


def _company_name(display_names) -> str | None:
    """"Immunome, Inc. (IMNM)" -> "Immunome, Inc." (strip the trailing "(TICKER)")."""
    if not display_names:
        return None
    return re.sub(r"\s*\([^)]*\)\s*$", "", display_names[0]).strip() or None


def _exhibit_url(cik: int, accession: str, doc: str) -> str:
    """Build the SEC Archives exhibit URL from the matched CIK + accession + doc filename."""
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{doc}"


def _cik_map(tickers: list[str]) -> dict[int, str]:
    """{int CIK -> TICKER} resolved via edgartools Company(ticker).cik (edgar.py's pattern).
    A ticker that does not resolve is skipped (degrade, never raise)."""
    _set_identity()  # config error only if the SEC UA is unset (raises, not a degrade)
    out: dict[int, str] = {}
    for t in tickers:
        try:
            out[int(edgar.Company(t).cik)] = t.upper()
        except Exception as e:  # noqa: BLE001 — unknown ticker / edgartools error -> skip
            logger.warning("pdufa_edgar: CIK resolution degraded for %s: %s", t, e)
    return out


def _discover(date_from: str, date_to: str, universe: set[int], cik_map: dict[int, str]) -> dict:
    """efts full-text discovery, CIK-filtered to the universe (exact CIK ∩, NO fuzzy title).
    Returns {accession -> hit-meta}, deduped across the keyword-phrase queries."""
    hits: dict[str, dict] = {}
    for q in _EFTS_QUERIES:
        params = {"q": q, "forms": "8-K", "startdt": date_from, "enddt": date_to}
        data = get_json("edgar_efts", _EFTS_URL, params=params, ua="sec")
        if not data:  # efts degraded -> try the next phrase (each degrades independently)
            continue
        for hit in data.get("hits", {}).get("hits", []):
            src = hit.get("_source", {})
            hit_ciks = {int(c) for c in src.get("ciks", []) if str(c).strip().isdigit()}
            matched = hit_ciks & universe  # exact CIK match — no fuzzy title attribution
            if not matched:
                continue
            _id = hit.get("_id", "")
            if ":" not in _id:  # need "<accession>:<doc>" to build the exhibit URL
                continue
            accession, doc = _id.split(":", 1)
            cik = next(iter(matched))
            hits.setdefault(
                accession,
                {
                    "ticker": cik_map[cik],
                    "cik": cik,
                    "doc": doc,
                    "file_date": src.get("file_date"),
                    "company_name": _company_name(src.get("display_names")),
                },
            )
    return hits


def _to_catalyst(hit: dict, accession: str, url: str, cand: dict) -> Catalyst:
    event_date = cand["event_date"]
    return Catalyst(
        ticker=hit["ticker"],
        company_name=hit.get("company_name"),
        catalyst_type=cand["catalyst_type"],
        event_date=event_date,
        date_precision=parse_precision(event_date),
        uncertainty_type=classify(
            event_date, DateType.estimated.value, source_count=1, has_primary=True
        ),
        source_origin=SourceOrigin.curated_pdufa,  # the PDUFA/AdCom bucket (DB-constrained, no migration)
        external_ref=f"pdufa_edgar:{hit['ticker']}:{accession}",  # own ref — no FR/RTTNews/curated collision
        sources=[
            CatalystSource(
                source_name="SEC EDGAR",  # verbatim — the AUTHORITATIVE_SUFFICIENT key (self-verifies)
                source_url=url,
                source_type=SourceType.primary,  # required by _authoritative_single
                reported_date=event_date,
                date_type=DateType.estimated,  # announced target, not realized
                published_date=hit["file_date"],  # transport-only -> point-in-time last_verified_at
                retrieved_at=_now(),
            )
        ],
        # last_verified_at deliberately unset — the insert->verify pipeline owns it.
    )


def _queue_review(hit: dict, url: str, cand: dict) -> None:
    """Append a MEDIUM/LOW candidate to the curated-CSV review queue as a #-commented row (so
    verify.load_curated_pdufa SKIPS it -> a human uncomments to confirm). Idempotent: the exact
    row is written at most once, so a daily re-run never duplicates it."""
    row = f"# {hit['ticker']},{cand['catalyst_type'].value},{cand['event_date']},SEC EDGAR,{url},primary"
    path = Path(_CURATED_CSV)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if row in existing:
        return  # already queued (idempotent)
    with open(path, "a", encoding="utf-8") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write(row + "\n")


def fetch(
    tickers: list[str],
    date_from: str,
    date_to: str,
    *,
    company_map: dict[str, list[str]] | None = None,
) -> list[Catalyst]:
    """PDUFA/AdCom 8-K catalysts in [date_from, date_to] for ``tickers`` -> list[Catalyst].

    Discovers PDUFA 8-Ks via efts (CIK-filtered to the universe), fetches each matched exhibit
    (RAW HTML), HTML-normalizes then regex-extracts the keyword-adjacent date, and emits a
    self-verifying single-source "SEC EDGAR" primary Catalyst for HIGH-confidence extractions.
    MEDIUM/LOW extractions route to the injectable review CSV (human confirm), never emitted.
    ``company_map`` is accepted for signature-parity with pdufa.fetch (CIK attribution needs no
    name map). Any efts/exhibit/edgartools failure degrades the affected unit to [] / skip.
    """
    cik_map = _cik_map(tickers)
    if not cik_map:  # no ticker resolved -> nothing to discover
        return []

    hits = _discover(date_from, date_to, set(cik_map), cik_map)

    out: list[Catalyst] = []
    for accession, hit in hits.items():
        url = _exhibit_url(hit["cik"], accession, hit["doc"])
        html = get_text("edgar_8k", url, ua="sec")
        if not html:  # exhibit degraded -> skip this hit, others still emit
            continue
        for cand in _extract(html, hit["file_date"]):
            if cand["confidence"] == "HIGH":
                out.append(_to_catalyst(hit, accession, url, cand))
            else:  # MEDIUM/LOW -> human-review queue, never auto-tradeable
                _queue_review(hit, url, cand)
    return out
