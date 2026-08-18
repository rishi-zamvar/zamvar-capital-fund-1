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
import math
import re
import statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import edgar
from edgar import get_company_tickers  # SEC company_tickers.json (bundled offline; no new dep)

from catalyst_trader.csvrows import read_csv_rows
from catalyst_trader.dates import now_iso
from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    CatalystType,
    DatePrecision,
    DateType,
    SourceOrigin,
    SourceType,
    Status,
    Uncertainty,
)
from catalyst_trader.providers import clinicaltrials, options_cboe
from catalyst_trader.providers._http import get_json, get_text
from catalyst_trader.providers.edgar import _set_identity, fundamentals  # reuse SEC-UA + fundamentals
from catalyst_trader.providers.pdufa_edgar import (
    _EFTS_QUERIES,
    _EFTS_URL,
    _exhibit_url,
    _extract,
)
from catalyst_trader.providers.prices import get_daily_bars, get_weekly_bars
from catalyst_trader.store import insert_catalyst
from catalyst_trader.universe.build import SEED_CSV, _add_months, build_snapshot

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

# Cached SEC company_tickers normalized-name index (Plan 05 Task 2); loaded once, degrades to {}.
_SEC_MAP: dict[str, list[tuple[str, int]]] | None = None


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


# ── SEC company_tickers normalized-EXACT sponsor resolution (UNIV-01b) ──────────────────────

# Trailing corporate suffixes stripped before comparison. DISTINCTIVE biotech tokens
# (therapeutics/pharmaceuticals/bio/sciences/etc.) are DELIBERATELY absent -> kept -> so two
# different "X Therapeutics" never collapse into a false merge (they stay ambiguous -> review).
_CORP_SUFFIXES = frozenset({
    "inc", "incorporated", "corp", "corporation", "ltd", "limited", "co", "company",
    "plc", "llc", "lp", "llp", "sa", "ag", "nv", "holdings", "group",
})


def _norm_name(s: str | None) -> str:
    """Normalize a company/sponsor name for EXACT comparison: casefold, drop periods, replace
    remaining punctuation with spaces, collapse whitespace, and strip TRAILING corporate suffixes.
    Distinctive tokens (therapeutics/bio/sciences/…) are retained so distinct entities never merge."""
    if not s:
        return ""
    s = s.casefold().replace(".", "")
    tokens = re.sub(r"[^a-z0-9]+", " ", s).split()
    while tokens and tokens[-1] in _CORP_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def _load_sec_map() -> dict[str, list[tuple[str, int]]]:
    """Build {normalized_name -> [(ticker, cik), …]} from SEC company_tickers.json (edgartools,
    bundled offline). A load failure degrades to {} -> every unmapped sponsor routes to review
    (no crash, NO fuzzy fallback)."""
    try:
        df = get_company_tickers(clean_name=False)  # raw names; OUR _norm_name is the sole authority
        index: dict[str, list[tuple[str, int]]] = {}
        for cik, ticker, company in zip(df["cik"], df["ticker"], df["company"], strict=False):
            key = _norm_name(company)
            if not key or not ticker:
                continue
            index.setdefault(key, []).append((str(ticker), int(cik)))
        return index
    except Exception as e:  # noqa: BLE001 — SEC map load degraded -> everything routes to review
        logger.warning("discover: SEC company_tickers load degraded -> sponsors route to review: %s", e)
        return {}


def _sec_map() -> dict[str, list[tuple[str, int]]]:
    """Cached SEC normalized-name index (load once)."""
    global _SEC_MAP
    if _SEC_MAP is None:
        _SEC_MAP = _load_sec_map()
    return _SEC_MAP


def _resolve_sponsor_exact(lead: str, sec_map: dict[str, list[tuple[str, int]]]) -> tuple[str, int] | None:
    """NORMALIZED-EXACT resolution ONLY. Exactly ONE distinct (ticker, cik) hit -> that pair (CIK
    from the SEC map, recycling-safe). ZERO hits -> None (review). >1 DISTINCT hit -> None (ambiguous
    -> review, NEVER pick one). Never fuzzy / never string-distance."""
    hits = sec_map.get(_norm_name(lead))
    if not hits:
        return None
    distinct = set(hits)  # exact-duplicate rows collapse; genuinely different entities stay ambiguous
    if len(distinct) != 1:
        return None
    return next(iter(distinct))


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


def _admit_ctgov_study(
    study: dict, rev: dict[str, str], out: dict[int, dict], sec_map: dict[str, list[tuple[str, int]]]
) -> None:
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
    if ticker:
        # Curated map wins first (Plan 01) — resolve its CIK via edgartools.
        cik = _resolve_cik(ticker)
        if cik is None:
            return  # cannot key by CIK -> drop (ticker-recycling safety needs the CIK)
    else:
        # Gap the curated map leaves: SEC company_tickers normalized-EXACT match ONLY. CIK comes
        # straight from the SEC map (recycling-safe). Anything less than exact / ambiguous -> review.
        resolved = _resolve_sponsor_exact(lead, sec_map)
        if resolved is None:
            _queue_sponsor_review(lead, nct)  # cite-or-drop: never fuzzy-match a sponsor to a ticker
            return
        ticker, cik = resolved

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
    sponsor_map: dict[str, list[str]] | None = None,
) -> dict[int, dict]:
    """UNFILTERED near-term interventional Ph2/Ph3 CT.gov studies -> CIK-keyed candidate dict.

    Runs the shipped provider BACKWARD (no query.spons) over the archiving get_json layer: every page
    is rate-limited (deep pagination otherwise 429s) and persisted to the raw-snapshot lake, and a
    mid-pagination degrade returns the pages fetched SO FAR — fetched data is NEVER discarded. Each
    study's leadSponsor.name reverse-maps to a ticker; an unmapped sponsor routes to the human-review
    queue (never fuzzy). Any degrade -> the partial-or-empty dict, never a raise.
    """
    rev = _reverse_sponsor_map(sponsor_map or clinicaltrials.load_sponsor_map())
    sec_map = _sec_map()  # SEC company_tickers normalized-exact fallback for unmapped sponsors
    out: dict[int, dict] = {}
    page_token: str | None = None
    while True:
        params = {
            "filter.advanced": (
                # Essie: enum fields take OR-groups, NOT COVER[...] (COVER[PHASE2,...] -> 400
                # "Invalid coverage"). Verified live 2026-08-17.
                f"AREA[PrimaryCompletionDate]RANGE[{date_from},{date_to}] "
                "AND (AREA[Phase]PHASE2 OR AREA[Phase]PHASE3) "
                "AND AREA[StudyType]INTERVENTIONAL"
            ),
            "fields": clinicaltrials.FIELDS,
            "pageSize": 100,
            "countTotal": "true",
        }
        if page_token:
            params["pageToken"] = page_token
        data = get_json("ctgov_discover", f"{clinicaltrials.BASE}/studies", params=params)
        if not data:  # 429/5xx/parse degrade -> STOP but KEEP pages already fetched (never discard)
            logger.warning(
                "discover_ctgov: page fetch degraded — keeping %d candidates fetched so far", len(out)
            )
            break
        for study in data.get("studies", []):
            _admit_ctgov_study(study, rev, out, sec_map)
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return out


# ── EDGAR unfiltered efts PDUFA discovery ──────────────────────────────────────────────────


def discover_edgar(
    date_from: str, date_to: str, *, seen_accessions: set[str] | None = None
) -> dict[int, dict]:
    """UNFILTERED efts PDUFA/AdCom pass (NO universe-CIK intersection) -> CIK-keyed candidate dict.

    The primary new-name engine: efts carries ticker+CIK per hit for free. For each hit resolve the
    ticker from display_names[0] (NON-anchored regex, take last) and CIK = int(ciks[0]); fetch the
    exhibit, run the shipped _extract, and admit only HIGH-confidence PDUFA/AdCom extractions. No
    parseable ticker OR no CIK -> drop (cite-or-drop). MEDIUM extractions are handled on the live
    pdufa_edgar path's review CSV — not double-handled here. Any efts/exhibit failure degrades.

    `seen_accessions` may be shared by a multi-year caller so the SAME 8-K re-indexed across window
    edges counts ONCE across the whole trailing window (defaults to a per-call set).
    """
    seen_accessions = seen_accessions if seen_accessions is not None else set()
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
            for cand in _extract(html, src.get("file_date"), items=src.get("items"), doc=doc):
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
                        "filing_date": src.get("file_date"),  # earliest-filed dedup key (point-in-time)
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
    sponsor_map: dict[str, list[str]] | None = None,
    edgar_years: int = 5,
    edgar_window: tuple[str, str] | None = None,
) -> dict[int, dict]:
    """Merge CT.gov reverse-sponsor + unfiltered efts PDUFA into ONE CIK-keyed candidate set.

    A CIK found by any feed accumulates the UNION of its catalysts and all its source_feeds — never
    a duplicate CIK row. Only live-parity types survive into the merged evidence. Any feed failing
    degrades to its own {}; the merge still returns every other feed's candidates.

    (date_from, date_to) is the CT.gov forward primaryCompletionDate window. efts filters on FILING
    date, so by default the pass runs a MULTI-YEAR TRAILING window: `edgar_years` (default 5) per-year
    windows [date_from - (y+1)yr, date_from - y] (PDUFA-announcing 8-Ks were filed months BEFORE the
    catalyst — the Plan-01 live note). This breadth DOUBLES as the warm-start historical-catalyst
    backfill: a name recurring across years accumulates its full catalyst history under one CIK,
    deduped by accession ACROSS years. An explicit `edgar_window` bypasses the loop for a single
    offline window; a single year's efts page degrading keeps the other years' candidates.
    """
    ctgov = discover_ctgov(date_from, date_to, sponsor_map=sponsor_map)
    if edgar_window:
        edgar_feeds = [discover_edgar(*edgar_window)]
    else:
        seen: set[str] = set()  # shared across years -> cross-window accession dedup
        edgar_feeds = [
            discover_edgar(
                _add_months(date_from, -12 * (y + 1)),
                _add_months(date_from, -12 * y),
                seen_accessions=seen,
            )
            for y in range(edgar_years)
        ]

    merged: dict[int, dict] = {}
    for feed in (ctgov, *edgar_feeds):
        for cik, cand in feed.items():
            # Membership evidence gate: a CIK is a candidate only if it has >=1 live-parity catalyst
            # (pdufa/adcom/trial_readout). But once it qualifies, carry ALL its catalysts (incl.
            # earnings) so they persist for the playbook — the scorer's type filter keeps earnings out
            # of the universe score. An earnings-only CIK (no live-parity anywhere) is never a candidate.
            if not any(c["type"] in LIVE_PARITY_TYPES for c in cand["catalysts"]):
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
            entry["catalysts"].extend(cand["catalysts"])
            entry["source_feeds"] |= set(cand["source_feeds"])
            entry["company_name"] = entry["company_name"] or cand.get("company_name")
    return merged


# ══════════════════════════════════════════════════════════════════════════════════════════
# Plan 06 — realized catalyst-move computation + warm-start backfill (UNIV-06)
# ══════════════════════════════════════════════════════════════════════════════════════════

_MOVE_WINDOW = (-1, 2)  # trading-day offsets around event_date: T-1 (day before) .. T+2 (2 days after)


def _move_window_str(window: tuple[int, int] = _MOVE_WINDOW) -> str:
    return f"({window[0]},{window[1]})"


def _realized_catalyst_move(ticker: str, event_date: str, *, window: tuple[int, int] = _MOVE_WINDOW):
    """Realized % move around a catalyst from DAILY closes: abs(close(T+2)/close(T-1) - 1).

    window=(-1, 2) trading days: T-1 = the trading day before the event, T+2 = the 2nd trading day
    after. Returns (realized_move, move_window_str, knowable_asof, source_grade) where knowable_asof
    is the ISO date of the T+2 close — the move is NOT knowable before then (point-in-time, NO
    look-ahead). None (cite-or-drop, NEVER imputed) when:
      - event_date has no day precision (YYYY / YYYY-MM) -> can't locate T-1/T+2,
      - no daily data in the window,
      - the window is not fully present (e.g. T+2 has not closed yet -> future catalyst).

    Uses get_daily_bars (the daily subset) — NOT weekly bars, which cannot give T-1->T+2 daily
    close-to-close granularity.
    """
    if len(event_date) != 10:  # YYYY or YYYY-MM -> no tradable day to anchor on
        return None
    lo, hi = window
    # buffer wide enough to find T-1 and T+2 trading days across weekends/holidays
    start = (date.fromisoformat(event_date) - timedelta(days=14)).isoformat()
    end = (date.fromisoformat(event_date) + timedelta(days=14)).isoformat()
    bars = get_daily_bars(ticker, start, end)
    if not bars:
        return None
    bars = sorted(bars, key=lambda b: b["week_end"])  # week_end holds the raw trade date for daily bars
    dates = [b["week_end"] for b in bars]
    t0 = next((i for i, d in enumerate(dates) if d >= event_date), None)  # event day (or next trade day)
    if t0 is None:
        return None
    i_lo, i_hi = t0 + lo, t0 + hi
    if i_lo < 0 or i_hi >= len(bars):
        return None  # window not fully present (insufficient history / T+2 not yet closed)
    c_lo, c_hi = bars[i_lo].get("close"), bars[i_hi].get("close")
    if not c_lo or not c_hi:
        return None
    move = abs(c_hi / c_lo - 1.0)
    knowable_asof = bars[i_hi]["week_end"]  # the T+2 close date — when the move became knowable
    grade = bars[i_hi].get("source_grade") or bars[i_hi].get("_grade")
    # no look-ahead: the realized move is stamped knowable only as of T+2's close; the walk-forward
    # filters on knowable_asof so nothing reads this move as-of a date before then.
    return move, _move_window_str(window), knowable_asof, grade


def _name_move_stat(moves: list[float], *, stat: str = "median") -> float | None:
    """Per-name statistic over its per-catalyst moves (default median). None if no computable move."""
    if not moves:
        return None
    return statistics.median(moves)


def _date_precision(event_date: str) -> str:
    return {10: "day", 7: "month", 4: "year"}.get(len(event_date), "day")


def _to_catalyst_model(candidate: dict, c: dict) -> Catalyst:
    """Map a discovered historical catalyst to a resolved curated_pdufa Catalyst for the backfill.

    source_origin=curated_pdufa (already whitelisted), status=resolved (settled historical), a
    CatalystSource carrying the discovery provenance (no date without a source), external_ref=the
    source_url -> idempotent by (ticker, external_ref) via insert_catalyst.
    """
    return Catalyst(
        ticker=candidate["ticker"],
        company_name=candidate.get("company_name"),
        catalyst_type=CatalystType(c["type"]),
        event_date=c["event_date"],
        date_precision=DatePrecision(_date_precision(c["event_date"])),
        uncertainty_type=Uncertainty.firm,  # historical, settled
        status=Status.resolved,
        source_origin=SourceOrigin.curated_pdufa,
        external_ref=c.get("source_url"),  # idempotency key with ticker
        sources=[CatalystSource(
            source_name=next(iter(candidate.get("source_feeds") or {"edgar"})),
            source_url=c.get("source_url"),
            source_type=SourceType.primary,
            reported_date=c["event_date"],
            date_type=DateType.actual,  # a settled historical catalyst
            retrieved_at=c.get("fetch_ts") or now_iso(),
        )],
    )


def _upsert_move(conn, catalyst_id: int, move: float, move_window: str, knowable_asof: str,
                 source_grade: str | None) -> None:
    """Persist/refresh the realized move (UNIQUE(catalyst_id, move_window) -> idempotent recompute)."""
    conn.execute(
        "INSERT INTO catalyst_move "
        "(catalyst_id, realized_move, move_window, knowable_asof, source_grade, computed_at) "
        "VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(catalyst_id, move_window) DO UPDATE SET "
        "realized_move=excluded.realized_move, knowable_asof=excluded.knowable_asof, "
        "source_grade=excluded.source_grade, computed_at=excluded.computed_at",
        (catalyst_id, move, move_window, knowable_asof, source_grade, now_iso()),
    )
    conn.commit()


def _dedup_catalysts(catalysts: list[dict]) -> list[dict]:
    """Collapse duplicate 8-Ks referencing the SAME event to ONE catalyst, keyed by
    (event_date, catalyst_type) — the ticker is fixed per candidate. Multiple filings recap the same
    PDUFA date (AUTL x6, CAPR x5, ...) -> keep the EARLIEST-filed instance (earliest knowable date =
    correct point-in-time provenance). filing_date is the sort key (falls back to event_date/fetch_ts
    for feeds like CT.gov that carry no filing_date)."""
    best: dict[tuple, dict] = {}
    for c in catalysts:
        key = (c["event_date"], c["type"])
        stamp = c.get("filing_date") or c.get("event_date") or c.get("fetch_ts") or ""
        cur = best.get(key)
        if cur is None or stamp < (cur.get("filing_date") or cur.get("event_date") or cur.get("fetch_ts") or ""):
            best[key] = c
    return list(best.values())


def dedupe_persisted_catalysts(conn) -> int:
    """E7: collapse cross-source duplicates in the STORE — same (ticker, event_date, type) persisted
    via different paths (e.g. nasdaq-earnings seed + a reclassified 8-K) that `_dedup_catalysts`
    (in-memory, per-candidate) never sees together. Keeps the EARLIEST-created id (earliest-filed
    provenance), cascade-deletes the redundant rows' moves/versions/sources. Returns rows deleted.
    Idempotent — re-running finds nothing. Call after the backfill/ingest writes."""
    groups = conn.execute(
        "SELECT group_concat(id) ids FROM catalyst GROUP BY ticker, event_date, catalyst_type "
        "HAVING COUNT(*) > 1"
    ).fetchall()
    deleted = 0
    for g in groups:
        ids = sorted(int(x) for x in (g["ids"] if isinstance(g, dict) else g[0]).split(","))
        for d in ids[1:]:  # keep ids[0] (earliest), drop the rest
            for t in ("catalyst_move", "catalyst_version", "catalyst_source"):
                conn.execute(f"DELETE FROM {t} WHERE catalyst_id=?", (d,))
            conn.execute("DELETE FROM catalyst WHERE id=?", (d,))
            deleted += 1
    conn.commit()
    return deleted


def _persist_backfill(conn, candidate: dict) -> list[int]:
    """Persist a candidate's historical catalysts (catalyst table) + their point-in-time realized
    moves (catalyst_move table) as the warm-start backfill. Idempotent: re-running upserts by
    (ticker, external_ref) and UNIQUE(catalyst_id, move_window), never duplicating. Attaches the
    per-name median realized move + n_moves to the candidate (read by the move screen). Returns the
    persisted catalyst ids. A single catalyst failing to persist degrades (skip), never raises.

    ALL catalyst types are persisted (incl. earnings) so earnings stay for the playbook; the backward
    universe scorer (_registry_moves) excludes non-parity types at the SQL level, so this does NOT
    pollute membership. Duplicate 8-Ks about one event are collapsed FIRST (one catalyst per event).
    """
    ids: list[int] = []
    moves: list[float] = []
    for c in _dedup_catalysts(candidate.get("catalysts", [])):
        try:
            cid = insert_catalyst(conn, _to_catalyst_model(candidate, c))
        except Exception as e:  # noqa: BLE001 — a bad row degrades, never sinks the backfill
            logger.warning("discover: backfill persist degraded for %s %s: %s",
                           candidate.get("ticker"), c.get("event_date"), e)
            continue
        ids.append(cid)
        mv = _realized_catalyst_move(candidate["ticker"], c["event_date"])
        if mv is not None:
            move, move_window, knowable_asof, grade = mv
            _upsert_move(conn, cid, move, move_window, knowable_asof, grade)
            if c["type"] in LIVE_PARITY_TYPES:
                moves.append(move)  # per-name candidate stat stays universe-relevant (earnings excluded)
    candidate["realized_move_median"] = _name_move_stat(moves)
    candidate["n_moves"] = len(moves)
    return ids


# ══════════════════════════════════════════════════════════════════════════════════════════
# Plan 07 — BACKWARD membership: proven-PDUFA-volatility score from the STORE (UNIV-07, ZERO API)
# ══════════════════════════════════════════════════════════════════════════════════════════

_DEFAULT_BIG_MOVE = 0.15          # |move| >= this counts as a "big move"
_DEFAULT_MIN_EVENTS = 2           # a name needs >=2 measured PAST events to be scorable
_DEFAULT_TARGET_UNIVERSE_SIZE = 80  # replaces target_lambda for membership (N is an OUTPUT <= this)
# UNIV-09: score every live-parity measurable move, not just pdufa. Every counted move is still a
# real day-precision measured move (month-precision events never got a catalyst_move row). One shared
# default tuple keeps _registry_moves/score_registry/select_members in sync (DRY).
_LIVE_PARITY_SCORE_TYPES = ("pdufa", "trial_readout", "adcom")
# UNIV-10: absolute median-move floor — a scorable name whose median measured |move| is below this
# is NEVER a member, regardless of pool size or the percentile-cut (deletes the weak ~1% tail
# deterministically). Overridable per-call via criteria["min_median_move"] for the live-run tune.
_DEFAULT_MIN_MEDIAN_MOVE = 0.10


def _name_volatility(
    moves: list[float], *, big_move: float = _DEFAULT_BIG_MOVE, min_events: int = _DEFAULT_MIN_EVENTS
) -> dict | None:
    """Backward per-name volatility from its PAST |move| list -> {median_move, big_move_frac,
    n_moves, vol_score}, or None if n_moves < min_events (insufficient history — NEVER a fabricated
    score from one event). realized_move is stored as an absolute magnitude already; abs() here is a
    defensive no-op so a hand-seeded signed move can't skew the median.

    # ponytail: composite score default (median magnitude * (1 + big-move frequency)) — the
    # calibration knob; both components are reported so the percentile cut stays auditable.
    """
    mags = [abs(m) for m in moves]
    if len(mags) < min_events:
        return None
    median_move = statistics.median(mags)
    big_move_frac = sum(1 for m in mags if m >= big_move) / len(mags)
    return {
        "median_move": median_move,
        "big_move_frac": big_move_frac,
        "n_moves": len(mags),
        "vol_score": median_move * (1 + big_move_frac),
    }


def _registry_moves(conn, *, catalyst_types: tuple[str, ...] = _LIVE_PARITY_SCORE_TYPES) -> dict[str, dict]:
    """Read the persisted registry (catalyst_move JOIN catalyst) grouped by ticker, scoped to
    `catalyst_types` (operator default 'pdufa') -> {ticker: {"ticker","company_name","moves":[...]}}.
    ZERO API (store-only). Only past + day-precision events ever got a catalyst_move row, so every
    read value is a real measured move. An absent/empty table -> {} (degrade)."""
    placeholders = ",".join("?" for _ in catalyst_types)
    rows = conn.execute(
        f"SELECT c.ticker AS ticker, c.company_name AS company_name, cm.realized_move AS realized_move "
        f"FROM catalyst_move cm JOIN catalyst c ON cm.catalyst_id = c.id "
        f"WHERE c.catalyst_type IN ({placeholders})",
        tuple(catalyst_types),
    ).fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        entry = out.setdefault(
            r["ticker"], {"ticker": r["ticker"], "company_name": r["company_name"], "moves": []}
        )
        entry["moves"].append(r["realized_move"])
        entry["company_name"] = entry["company_name"] or r["company_name"]
    return out


def score_registry(
    conn, *, big_move: float = _DEFAULT_BIG_MOVE, min_events: int = _DEFAULT_MIN_EVENTS,
    catalyst_types: tuple[str, ...] = _LIVE_PARITY_SCORE_TYPES,
) -> tuple[list[dict], list[dict]]:
    """Score every registry name BACKWARD from its persisted past moves (ZERO API). Returns
    (scorable, insufficient): scorable = names with n>=min_events (each record = ticker/company_name/
    moves + the vol fields median_move/big_move_frac/n_moves/vol_score); insufficient = the
    <min_events names (ticker + n_moves) for the honest watch list (no fabricated score). An
    empty/absent registry -> ([], [])."""
    scorable: list[dict] = []
    insufficient: list[dict] = []
    for name in _registry_moves(conn, catalyst_types=catalyst_types).values():
        vol = _name_volatility(name["moves"], big_move=big_move, min_events=min_events)
        if vol is None:
            insufficient.append({"ticker": name["ticker"], "n_moves": len(name["moves"])})
        else:
            scorable.append({**name, **vol})
    return scorable, insufficient


def select_members(
    conn, as_of: str, *, target_size: int = _DEFAULT_TARGET_UNIVERSE_SIZE,
    big_move: float = _DEFAULT_BIG_MOVE, min_events: int = _DEFAULT_MIN_EVENTS,
    min_median_move: float = _DEFAULT_MIN_MEDIAN_MOVE,
    catalyst_types: tuple[str, ...] = _LIVE_PARITY_SCORE_TYPES, criteria: dict | None = None,
) -> tuple[list[dict], list[dict], dict]:
    """BACKWARD percentile-cut membership (UNIV-02b/03/07). Returns (members, rejected, report).

    1. score_registry (store-read, ZERO API) -> (scorable, insufficient).
    2. rank scorable by vol_score DESC (cheap).
    3. walk the ranked list, checking tradeability via the repurposed screen_candidates path
       (ADV floor, cap floor, relaxed optionable — free-first/cached); a tradeable name -> members,
       a non-tradeable -> rejected (with the screen reasons). STOP admitting once len(members) >=
       target_size OR the pool is exhausted. This IS "remove the lowest percentile until it fits":
       the low-scorers are never reached (frugal — no tradeability API on the tail).
    4. N = len(members) — an OUTPUT (<= target_size; honest under-fill when scorable+tradeable <
       target, reported, never padded). cut_percentile = 1 - N/n_scorable.
    """
    floor = (criteria or {}).get("min_median_move", min_median_move)
    scorable, insufficient = score_registry(
        conn, big_move=big_move, min_events=min_events, catalyst_types=catalyst_types
    )
    n_scorable = len(scorable)
    ranked = sorted(scorable, key=lambda r: r["vol_score"], reverse=True)

    # UNIV-10: apply the median-move floor as an ABSOLUTE gate FIRST — a sub-floor name is rejected
    # and never screened/admitted, regardless of pool size or remaining target slots. Then the
    # percentile-cut walk fills the target from the ABOVE-FLOOR survivors only. Pre-partitioning
    # (not interleaving with the target break) keeps the floor absolute AND n_below_floor exact.
    below_floor = [r for r in ranked if r["median_move"] < floor]
    above_floor = [r for r in ranked if r["median_move"] >= floor]

    members: list[dict] = []
    rejected: list[dict] = [
        {"ticker": r["ticker"], "median_move": r["median_move"], "vol_score": r.get("vol_score"),
         "reasons": ["below_move_floor"]}
        for r in below_floor
    ]
    for rec in above_floor:
        # A store-scored pseudo-candidate for the tradeability screen; realized_move_median carries
        # the backward median so screen_candidates attaches it (no move recompute, no network).
        cand = {**rec, "cik": None, "catalysts": [], "realized_move_median": rec["median_move"]}
        admitted, screen_rej = screen_candidates({0: cand}, as_of, criteria=criteria)
        if admitted:
            members.append(admitted[0])
        else:
            rejected.append(screen_rej[0])
        if len(members) >= target_size:
            break  # target filled — the lower-scoring tail is never screened (frugal)

    N = len(members)
    report = {
        "n_scorable": n_scorable,
        "n_insufficient": len(insufficient),
        "N": N,
        "target_size": target_size,
        "target_reached": N >= target_size,
        "cut_percentile": round(1 - N / n_scorable, 4) if n_scorable else 0.0,
        "min_median_move": floor,
        "n_below_floor": len(below_floor),
        "big_move": big_move,
        "min_events": min_events,
        "members": [
            {"ticker": m["ticker"], "vol_score": m.get("vol_score"),
             "median_move": m.get("median_move"), "big_move_frac": m.get("big_move_frac"),
             "n_moves": m.get("n_moves")}
            for m in members
        ],
        "insufficient_history": [r["ticker"] for r in insufficient],
    }
    return members, rejected, report


# ══════════════════════════════════════════════════════════════════════════════════════════
# Plan 02 — screen (UNIV-02) + measure-and-grow (UNIV-03) + write (UNIV-04/05)
# ══════════════════════════════════════════════════════════════════════════════════════════

# Tradeability thresholds (research §A.2 + live-close finding 3 / decision C). Tradeable ADV floor
# $5M; a $2-5M name is KEPT + size_tiny (the IVA/MASH lesson — don't drop a thin-but-real name); a
# $200M market-cap FLOOR (no CEILING — a large-cap binary-catalyst biotech, BBIO/AXSM/PRAX, must
# qualify). The fixed realized-move threshold gate is RETIRED (Plan 07 pivot) — the BACKWARD
# vol_score percentile-cut in select_members is the membership judgement; these floors are
# tradeability only. Override per-call via `criteria`.
_DEFAULT_MIN_ADV_USD = 5_000_000
_SIZE_TINY_FLOOR = 2_000_000
_DEFAULT_MIN_MARKET_CAP = 200_000_000

_BASE_RATE_NOTE = (
    "per-name catalyst base rate (~2/yr) is a DERIVED estimate from FORWARD discovered evidence; "
    "recalibrate from measured trailing store density once Phase 7.5 backfills the historical "
    "catalyst table."
)


def _dollar_adv(ticker: str, as_of: str, *, window_months: int = 3) -> float | None:
    """Daily dollar-ADV proxy = mean(close*volume) over a trailing weekly window / 5. [] -> None.
    # ponytail: weekly->daily is a /5 proxy, not a true daily ADV — flagged, tighten only if a
    # size decision ever hinges on it (per-trade sizing reads the live desk, not this build gate)."""
    bars = get_weekly_bars(ticker, _add_months(as_of, -window_months), as_of)
    vals = [b["close"] * b["volume"] for b in (bars or []) if b.get("close") and b.get("volume")]
    if not vals:
        return None
    return sum(vals) / len(vals) / 5.0


def _market_cap(ticker: str, as_of: str) -> tuple[float | None, dict | None]:
    """(market_cap, fundamentals) = shares_outstanding * latest close from the price cascade.
    A missing datum (no fundamentals / no shares / no close) -> (None, fundamentals-or-None)."""
    fund = fundamentals(ticker)
    if not fund:
        return None, None
    shares = fund.get("shares_outstanding")
    if shares is None:
        return None, fund
    bars = get_weekly_bars(ticker, _add_months(as_of, -1), as_of)
    close = bars[-1]["close"] if bars else None
    if close is None:
        return None, fund
    return shares * close, fund


def _optionable(ticker: str) -> bool | None:
    """UNIV-02c (relaxed): True iff a live ATM options pair exists with bid>0 on BOTH legs — i.e.
    the name "has listed options at all". None on degrade (fetch None).

    # ponytail: universe layer = 'has options at all' (bid>0 both legs); the STRICT OI>=100 +
    # spread/mid<0.6 liquidity gate is a PER-TRADE check on FRESH quotes in
    # desk/diligence.options_liquid + zero_liquidity — delayed build-time EOD quotes make per-strike
    # spread unreliable (INSM: OI 996 but delayed spread/mid 1.18 -> the old gate false-rejected an
    # obviously-liquid name), so it is DELIBERATELY not a membership gate. This reverses the
    # Blocker-2 tightening for the universe layer ONLY — no guard deleted, relocated in intent.
    # expiry-at/after-catalyst is likewise a per-TRADE check (the catalyst date isn't fixed at
    # universe-build time) — deferred to the desk.
    """
    q = options_cboe.fetch(ticker)
    if q is None:
        return None
    oq = q.get("options_quote")
    if not oq:
        return False  # no live ATM pair
    return oq["call_bid"] > 0 and oq["put_bid"] > 0


_TA_FALLBACK: dict[str, str] | None = None


def _ta_fallback(ticker: str) -> str | None:
    """Curated therapeutic-area from the shipped seed universe CSV (a fallback for names whose TA
    the discovery feeds don't carry). Cached; unknown ticker -> None."""
    global _TA_FALLBACK
    if _TA_FALLBACK is None:
        _TA_FALLBACK = {}
        try:
            for r in read_csv_rows(SEED_CSV):
                ta = (r.get("therapeutic_area") or "").strip()
                if ta:
                    _TA_FALLBACK[r["ticker"].strip().upper()] = ta
        except Exception as e:  # noqa: BLE001 — missing/unreadable seed CSV -> empty fallback
            logger.warning("discover: TA fallback load degraded: %s", e)
    return _TA_FALLBACK.get(ticker.upper())


def screen_candidates(
    candidates: dict[int, dict], as_of: str, *, criteria: dict | None = None
) -> tuple[list[dict], list[dict]]:
    """TRADEABILITY-ONLY screen (Plan 07 pivot). Returns (admitted, rejected) = (tradeable,
    not-tradeable), each record carrying its screen datums, flags, reasons, and catalyst provenance.

    Admit iff ALL of: dollar-ADV >= $5M (or $2-5M -> admit + size_tiny), market-cap >= $200M FLOOR
    (NO ceiling — a large-cap binary-catalyst biotech qualifies), optionable (relaxed: bid>0 both
    legs), and a readable cap. A None on ADV/cap/optionability -> DROP with a reason (cite-or-drop,
    NEVER imputed). Runway is attached (None is legit when a filer isn't burning) and flagged, not a
    hard drop. The per-name realized_move_median/n_moves are ATTACHED for ranking/report but are NO
    LONGER a gate — the fixed move_threshold gate is retired; the BACKWARD volatility judgement lives
    in select_members' vol_score percentile-cut.
    """
    criteria = criteria or {}
    min_adv = criteria.get("min_adv_usd", _DEFAULT_MIN_ADV_USD)
    tiny_floor = criteria.get("size_tiny_floor", _SIZE_TINY_FLOOR)
    min_cap = criteria.get("min_market_cap", _DEFAULT_MIN_MARKET_CAP)

    admitted: list[dict] = []
    rejected: list[dict] = []
    for cand in candidates.values():
        ticker = cand["ticker"]
        adv = _dollar_adv(ticker, as_of)
        cap, fund = _market_cap(ticker, as_of)
        opt = _optionable(ticker)
        runway = fund.get("cash_runway_months") if fund else None
        ta = cand.get("therapeutic_area") or _ta_fallback(ticker) or "unknown"
        move_stat, n_moves = _candidate_move_stat(cand)

        flags: dict = {}
        reasons: list[str] = []

        # ADV floor + size-tiny tier
        if adv is None:
            reasons.append("adv_unreadable")
        elif adv < tiny_floor:
            reasons.append(f"adv_usd {adv:.0f} < {tiny_floor:.0f}")
        elif adv < min_adv:
            flags["size_tiny"] = True

        # market-cap FLOOR only (the CEILING is removed — large-cap binary catalysts qualify)
        if cap is None:
            reasons.append("market_cap_unreadable")
        elif cap < min_cap:
            reasons.append(f"market_cap {cap:.0f} < {min_cap:.0f}")

        # optionability (relaxed universe gate — bid both legs; strict OI/spread is per-trade)
        if opt is None:
            reasons.append("optionability_unreadable")
        elif not opt:
            reasons.append("not_optionable")

        # realized-move is ATTACHED (below) for ranking/report — NOT a gate (move_threshold retired)

        # cash-runway sanity (informational; None is legit when a filer is not burning)
        if runway is None:
            flags["runway_unknown"] = True

        rec = {
            **cand,
            "therapeutic_area": ta,
            "adv_usd": adv,
            "market_cap": cap,
            "cash_runway_months": runway,
            "realized_move_median": move_stat,
            "n_moves": n_moves,
            "flags": flags,
            "reasons": reasons,
            "delisted": cand.get("delisted", False),
        }
        (rejected if reasons else admitted).append(rec)
    return admitted, rejected


def _candidate_move_stat(cand: dict) -> tuple[float | None, int]:
    """The candidate's per-name realized-move statistic + count. Prefers the value attached by
    _persist_backfill (build_universe path); falls back to computing it live from the candidate's
    live-parity catalysts (standalone screen use / tests)."""
    if "realized_move_median" in cand:
        return cand["realized_move_median"], cand.get("n_moves", 0)
    moves: list[float] = []
    for c in cand.get("catalysts", []):
        if c["type"] not in LIVE_PARITY_TYPES:
            continue
        mv = _realized_catalyst_move(cand["ticker"], c["event_date"])
        if mv is not None:
            moves.append(mv[0])
    return _name_move_stat(moves), len(moves)


def _enforce_diversity(admitted: list[dict], *, max_per_ta: int = 4) -> list[dict]:
    # ponytail: off the build path since 06.12-07 (the backward percentile-cut is the sole membership
    # gate now); kept defined + tested, retire in cleanup.
    """Cap any single therapeutic-area cluster at `max_per_ta`, keeping the densest-catalyst names;
    demote the rest (append 'ta_cluster_full' to their reasons). Dataset-quality gate so cohort
    cells (catalyst_type x TA x drop_regime) later populate — not just risk. Returns the kept list."""
    by_ta: dict[str, list[dict]] = defaultdict(list)
    for r in admitted:
        by_ta[r.get("therapeutic_area") or "unknown"].append(r)
    kept: list[dict] = []
    for recs in by_ta.values():
        ranked = sorted(recs, key=lambda r: len(r.get("catalysts", [])), reverse=True)
        kept.extend(ranked[:max_per_ta])
        for demoted in ranked[max_per_ta:]:
            demoted.setdefault("reasons", []).append("ta_cluster_full")
    return kept


def _count_tradeable_catalysts(shortlist: list[dict], window: tuple[str, str] | None = None) -> int:
    """Count live-parity tradeable catalysts (pdufa|adcom|trial_readout — earnings NEVER) across the
    shortlist, optionally restricted to `window` = (date_from, date_to)."""
    n = 0
    for r in shortlist:
        for c in r.get("catalysts", []):
            if c["type"] not in LIVE_PARITY_TYPES:
                continue
            if window and not (window[0] <= c["event_date"] <= window[1]):
                continue
            n += 1
    return n


def _weekly_lambda(shortlist: list[dict], window_months: int) -> float:
    """Projected weekly catalyst rate = annualized live-parity count / 52."""
    n = _count_tradeable_catalysts(shortlist)
    return (n * (12.0 / window_months)) / 52.0


def size_to_density(
    screened: list[dict],
    as_of: str,
    *,
    target_lambda: float = 1.75,
    safety_cap: int = 90,
    window_months: int = 12,
) -> tuple[list[dict], dict]:
    # ponytail: off the build path since 06.12-07 (superseded by select_members' backward
    # percentile-cut over vol_score); kept defined + tested, retire in cleanup.
    """Measure-and-grow: N is an OUTPUT. Rank the screened candidates by realized catalyst-MOVE
    magnitude (biggest movers first; live-parity catalyst count is the tiebreaker), grow the
    shortlist one at a time, and STOP when projected weekly lambda >= target_lambda OR the shortlist
    hits safety_cap OR the pool is exhausted (honest under-fill — do NOT over-grow to chase target;
    the defensive/statistical sleeve backstops lean weeks). target_lambda default 1.75 is the
    average across the year (locked decision), NOT >=1 every single week.

    Returns (shortlist, density_report). N is len(shortlist) — never a hard-coded 80.
    """
    # ponytail: derived base rate, recalibrate from measured store density once Phase 7.5 backfills.
    # Rank by move magnitude (the screen's central metric); a None move sorts last (shouldn't occur
    # post-screen, but stays safe). Catalyst count breaks ties among equal movers.
    ranked = sorted(
        screened,
        key=lambda r: (
            r["realized_move_median"] if r.get("realized_move_median") is not None else -1.0,
            sum(1 for c in r.get("catalysts", []) if c["type"] in LIVE_PARITY_TYPES),
        ),
        reverse=True,
    )
    shortlist: list[dict] = []
    for cand in ranked:
        if len(shortlist) >= safety_cap:
            break
        shortlist.append(cand)
        if _weekly_lambda(shortlist, window_months) >= target_lambda:
            break

    measured = _weekly_lambda(shortlist, window_months)
    n_cats = _count_tradeable_catalysts(shortlist)
    report = {
        "measured_lambda": round(measured, 4),
        "n_admitted": len(shortlist),
        "target_lambda": target_lambda,
        "target_reached": measured >= target_lambda,
        "per_name_rate_used": round(n_cats / len(shortlist), 3) if shortlist else 0.0,
        "base_rate_recalibration_note": _BASE_RATE_NOTE,
        "lean_week_estimate": round(52 * math.exp(-measured)) if measured > 0 else 52,
        "safety_cap": safety_cap,
        "window_months": window_months,
        "pool_size": len(screened),
    }
    return shortlist, report


def _to_seed_row(rec: dict) -> dict:
    """Map a screened/admitted record to a build_snapshot seed_row (keyed by ticker downstream; the
    CIK stays in the admission audit trail as the recycling-safe source of truth)."""
    return {
        "ticker": rec["ticker"],
        "company_name": rec.get("company_name"),
        "market_cap": rec.get("market_cap"),
        "adv_usd": rec.get("adv_usd"),
        "therapeutic_area": rec.get("therapeutic_area"),
        "delisted": "true" if rec.get("delisted") else "false",
    }


_TRADEOFF_NOTE = (
    "UNIV-05: >=1 tradeable catalyst/week is about SELECTION, not throughput — a broader universe "
    "gives the weekly desk more to CHOOSE from, it does not mean trade-all. The per-catalyst "
    "diligence + verify + human gate still gate every trade; automated screening + per-name "
    "provenance compensate for the lost per-name eyeballing that a hand-picked list allowed."
)


def build_universe(
    conn, as_of: str, *, target_lambda: float = 1.75, criteria: dict | None = None,
    date_from: str | None = None, date_to: str | None = None, edgar_years: int = 5,
) -> dict:
    """Orchestrate discover+backfill -> select_members (BACKWARD percentile-cut) -> build_snapshot
    into a survivorship-free append-only `universe_as_of` cohort, returning a run summary with
    per-name vol_score provenance + the honest breadth/depth tradeoff (Plan 07 pivot).

    Membership is now BACKWARD-looking: discovery + _persist_backfill persist the 5-yr PDUFA registry
    (catalyst + catalyst_move) UNCHANGED, then select_members READS THAT STORE (zero API) to score
    each name from its proven past moves and percentile-cut to the tradeable target. The old
    screen -> diversity -> size_to_density path is retired (those helpers stay defined + tested, OFF
    the build path). `target_lambda` is kept for signature back-compat but is no longer used.

    CRITICAL (Blocker 1): build_snapshot re-applies its OWN store-density floor via _catalyst_density
    over the `catalyst` table, so we pass min_catalyst_density=0 — the backward vol_score cut +
    tradeability floors are the gates, NOT the store-density floor. The floor stays disabled even
    though _persist_backfill makes the catalyst table non-empty, because a partial backfill would
    otherwise trap the cohort empty.
    """
    date_from = date_from or as_of
    date_to = date_to or _add_months(as_of, 12)

    # CT.gov = forward completion window; efts = MULTI-YEAR (5yr) TRAILING filing window (PDUFA-
    # announcing 8-Ks are filed months before the catalyst — a forward filing window returns 0;
    # the 5yr breadth doubles as the warm-start historical-catalyst backfill). Verified live.
    candidates = discover_candidates(date_from, date_to, edgar_years=edgar_years)

    # Warm-start backfill: persist each candidate's historical catalysts + point-in-time realized
    # moves BEFORE scoring, so select_members reads real moves from the store (zero API) + the
    # playbook seed is written. UNCHANGED from Plan 06 — this IS the registry the scorer reads.
    backfilled_ids: list[int] = []
    for cand in candidates.values():
        backfilled_ids += _persist_backfill(conn, cand)
    # E7: collapse any cross-source (ticker,event_date,type) dupes the per-candidate dedup can't see
    dedupe_persisted_catalysts(conn)

    target_size = (criteria or {}).get("target_universe_size", _DEFAULT_TARGET_UNIVERSE_SIZE)
    members, rejected, select_report = select_members(
        conn, as_of, target_size=target_size, criteria=criteria
    )

    seed_rows = [_to_seed_row(r) for r in members]
    # ponytail: min_catalyst_density=0 here because the store-density floor is disabled this phase
    # (Blocker 1); it re-engages once Phase 7.5 backfills the full trailing history.
    build_criteria = {
        "min_catalyst_density": 0,
        "min_adv_usd": _DEFAULT_MIN_ADV_USD,
        "min_market_cap": _DEFAULT_MIN_MARKET_CAP,
        **(criteria or {}),
    }
    included_count = build_snapshot(conn, as_of, seed_rows, criteria=build_criteria)

    admissions = []
    for r in members:
        admissions.append({
            "ticker": r["ticker"],
            "cik": r.get("cik"),
            "therapeutic_area": r.get("therapeutic_area"),
            "market_cap": r.get("market_cap"),
            "adv_usd": r.get("adv_usd"),
            "flags": r.get("flags", {}),
            "vol_score": r.get("vol_score"),
            "median_move": r.get("median_move"),
            "big_move_frac": r.get("big_move_frac"),
            "n_moves": r.get("n_moves"),
        })

    # DENSITY (UNIV-10): a BACKWARD proxy — sum of members' measured moves / the trailing-window
    # weeks (edgar_years * 52). ZERO extra API (reads the n_moves already attached). NOTE: this is a
    # historical measured-moves-per-week figure across the cohort, NOT a forward tradeable-catalyst
    # guarantee — the live re-run reports it vs the ~1/week SELECTION goal, not as throughput.
    n_member_moves = sum(m.get("n_moves", 0) for m in members)
    weeks = edgar_years * 52
    events_per_week = round(n_member_moves / weeks, 3) if weeks else 0.0

    return {
        "as_of": as_of,
        "n_candidates": len(candidates),
        # backward density proxy (zero-API; historical moves/week, not a forward guarantee)
        "n_member_moves": n_member_moves,
        "events_per_week": events_per_week,
        "density_note": (
            "BACKWARD proxy: historical measured member-moves / trailing weeks "
            "(edgar_years*52) — NOT a forward tradeable-catalyst guarantee"
        ),
        # backward-membership fields (Plan 07 pivot)
        "n_scorable": select_report["n_scorable"],
        "N": select_report["N"],  # OUTPUT: len(members) <= target_size (honest under-fill)
        "target_size": select_report["target_size"],
        "target_reached": select_report["target_reached"],
        "cut_percentile": select_report["cut_percentile"],
        "n_insufficient": select_report["n_insufficient"],
        "insufficient_history": select_report["insufficient_history"],
        # included_count is build_snapshot's RETURNED count of rows written included=1 — a DISTINCT
        # field from N so the two reconcile (Blocker 3); a large gap means the store-density trap
        # (Blocker 1) re-appeared, or size_tiny names fell under the snapshot's $5M floor.
        "included_count": included_count,
        "select_report": select_report,
        "admissions": admissions,
        "n_rejected": len(rejected),
        # warm-start-backfill stats (the registry the scorer reads)
        "n_backfilled_catalysts": len(backfilled_ids),
        "n_moves_persisted": sum(c.get("n_moves", 0) for c in candidates.values()),
        "tradeoff": _TRADEOFF_NOTE,
    }
