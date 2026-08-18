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
from pathlib import Path

import edgar

from catalyst_trader.dates import classify, now_iso, parse_precision
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
# The trailing three are PRECISE completion-anchored result phrases (UNIV-08) so trial-RESULT 8-Ks
# surface at all; kept exact-phrase so per-hit exhibit-fetch volume stays proportional to real
# readouts (CLAUDE.md frugality — SEC EDGAR is rank-0 free, cache-served, accession-deduped).
_EFTS_QUERIES = (
    '"PDUFA target action date"', '"target action date"', '"advisory committee meeting"',
    '"topline results"', '"met the primary endpoint"', '"did not meet the primary endpoint"',
)

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

# UNIV-08: COMPLETION-anchored result phrases only (excludes bare "primary endpoint" trial-DESIGN/
# initiation language -> no false readout). A match means the filing ANNOUNCES a result; both the
# positive ("met") and the negative ("did not meet / failed to meet") are large measurable moves and
# both MUST count. Run AFTER _normalize (tag-strip), same as the PDUFA/AdCom regexes.
_READOUT_RX = re.compile(
    r"top-?line\s+(?:results|data)"
    r"|(?:met|achieved|did\s+not\s+meet|failed\s+to\s+meet)\s+(?:the|its)\s+primary\s+endpoint"
    r"|phase\s+[23]\s+(?:topline\s+)?(?:results|data)"
    r"|results\s+from\s+(?:the|its)\s+(?:pivotal|phase\s+[23])",
    re.I,
)

# Money-path false-positive guard (both branches). Earnings/deck/annual 8-Ks routinely mention a
# result phrase or a target-action date IN PASSING (a pipeline recap), which mis-fired the PDUFA and
# the readout branches -> ~11% fake readouts + ~13 fake pdufas, polluting the universe score. So an
# 8-K that IS an earnings/financial/deck/annual filing is NEVER a pdufa/readout: a genuine EARNINGS
# release is reclassified -> CatalystType.earnings (stored for the playbook, excluded from the
# universe by the scorer's type filter); a pure deck/annual/presentation is DROPPED (not an event).
# Signals, strongest first: (1) SEC 8-K Item 2.02 (Results of Operations and Financial Condition) ==
# earnings; else (2) an earnings/deck/annual keyword in the exhibit FILENAME or its opening title.
_EARNINGS_RX = re.compile(
    r"earnings"
    r"|quarterly\s+results"
    r"|financial\s+results"
    r"|results\s+of\s+operations"
    r"|financial\s+condition"
    r"|\bq[1-4]\s*20\d\d"
    r"|\b(?:first|second|third|fourth)\s+quarter\b",
    re.I,
)
_DECK_RX = re.compile(
    r"corporate\s*deck"
    r"|corporate\s+presentation"
    r"|investor\s+(?:presentation|deck)"
    r"|annual\s+report"
    r"|\b10-?[kq]\b",
    re.I,
)


def _financial_signal(items, doc: str | None, text: str) -> str | None:
    """"earnings" | "deck" | None — is this 8-K an earnings/deck/annual filing (NOT a real
    pdufa/readout)? Item 2.02 is the cleanest signal; the filename/opening-title keyword guard is the
    always-on backstop (scoped to the opening so forward-looking-statement boilerplate near the tail
    can't false-reject a genuine result 8-K). Earnings is checked before deck (item 2.02 == earnings).
    """
    if items and any(str(it).strip() == "2.02" for it in items):
        return "earnings"  # Item 2.02 == Results of Operations and Financial Condition
    hay = f"{doc or ''} {text[:500]}"  # exhibit filename + opening title/lede only
    if _EARNINGS_RX.search(hay):
        return "earnings"
    if _DECK_RX.search(hay):
        return "deck"
    return None




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


def _extract(html: str, filing_date: str, *, items=None, doc: str | None = None) -> list[dict]:
    """Normalize the RAW HTML, then deterministically pull each keyword-adjacent date.

    Returns candidate dicts {catalyst_type, event_date (ISO), confidence, matched_keyword,
    filing_date}. no-LLM-dates + cite-or-drop: a match whose date does not parse is dropped; a
    date with no adjacent keyword is never captured. Confidence is a doc-level judgement:
      HIGH   = a single distinct date AND a "PDUFA" token present in some match (unambiguous).
      MEDIUM = multiple DISTINCT candidate dates, OR target-action/goal without a "PDUFA" token,
               OR an AdCom-only date -> routed to the human-review queue, never auto-tradeable.

    ``items`` (efts _source.items 8-K codes) + ``doc`` (exhibit filename) gate the earnings/deck
    false-positive guard: an earnings/financial 8-K is reclassified -> a day-precision earnings
    catalyst (stored, excluded from the universe by the scorer's type filter); a pure deck/annual
    filing is dropped; a genuine pdufa/readout is unaffected. The guard runs FIRST so a pipeline
    recap of a target-action date or a result phrase inside an earnings/deck 8-K can't mis-fire.
    """
    text = _normalize(html)

    signal = _financial_signal(items, doc, text)
    if signal == "deck":
        return []  # a corporate deck / annual boilerplate is not a tradeable event -> drop
    if signal == "earnings":
        # a genuine earnings 8-K IS a real event (the filing day) -> store as CatalystType.earnings
        # for the playbook; excluded from the universe by _registry_moves' catalyst_type filter. No
        # day-precision filing_date -> no anchorable T-1..T+2 move -> cite-or-drop.
        if filing_date and len(filing_date) == 10:
            return [{
                "catalyst_type": CatalystType.earnings,
                "event_date": filing_date,
                "confidence": "HIGH",
                "matched_keyword": "earnings/financial 8-K",
                "filing_date": filing_date,
            }]
        return []

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
        # PDUFA/AdCom PRECEDENCE: the readout branch is the RESIDUAL — it fires ONLY when no
        # target-action/AdCom date was extracted, so one filing's move is never double-counted and a
        # PDUFA-acceptance 8-K that recaps trial data is never misclassified as a readout. The
        # readout event IS the announcement day (the filing_date), not an extracted future date; drop
        # unless the filing_date is day-precision (else no anchorable T-1..T+2 move -> cite-or-drop).
        # ponytail: readout date = the 8-K filing_date; add an adjacent-date regex only if a real
        # filing ever announces a result for a different past day.
        if filing_date and len(filing_date) == 10:
            m = _READOUT_RX.search(text)  # reuse the already-normalized text (no second normalize)
            if m:
                return [{
                    "catalyst_type": CatalystType.trial_readout,
                    "event_date": filing_date,
                    "confidence": "HIGH",
                    "matched_keyword": m.group(0),
                    "filing_date": filing_date,
                }]
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
                    "items": src.get("items"),  # 8-K item codes -> earnings/deck false-positive guard
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
                retrieved_at=now_iso(),
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
        for cand in _extract(html, hit["file_date"], items=hit.get("items"), doc=hit["doc"]):
            if cand["confidence"] == "HIGH":
                out.append(_to_catalyst(hit, accession, url, cand))
            else:  # MEDIUM/LOW -> human-review queue, never auto-tradeable
                _queue_review(hit, url, cand)
    return out
