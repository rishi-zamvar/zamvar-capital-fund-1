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
from collections import defaultdict
from pathlib import Path

import edgar

from catalyst_trader.csvrows import read_csv_rows
from catalyst_trader.dates import now_iso
from catalyst_trader.providers import clinicaltrials, options_cboe
from catalyst_trader.providers._http import get_json, get_text
from catalyst_trader.providers.edgar import _set_identity, fundamentals  # reuse SEC-UA + fundamentals
from catalyst_trader.providers.pdufa_edgar import (
    _EFTS_QUERIES,
    _EFTS_URL,
    _exhibit_url,
    _extract,
)
from catalyst_trader.providers.prices import get_weekly_bars
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
            _admit_ctgov_study(study, rev, out)
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


# ══════════════════════════════════════════════════════════════════════════════════════════
# Plan 02 — screen (UNIV-02) + measure-and-grow (UNIV-03) + write (UNIV-04/05)
# ══════════════════════════════════════════════════════════════════════════════════════════

# Screen thresholds (research §A.2). Tradeable ADV floor $5M; a $2-5M name is KEPT + size_tiny
# (the IVA/MASH lesson — don't drop a thin-but-real name); cap band $200M-$10B with a hedge-peer
# exception to ~$16B. Override any per-call via `criteria`.
_DEFAULT_MIN_ADV_USD = 5_000_000
_SIZE_TINY_FLOOR = 2_000_000
_DEFAULT_MIN_MARKET_CAP = 200_000_000
_DEFAULT_MAX_MARKET_CAP = 10_000_000_000
_HEDGE_PEER_MAX_MARKET_CAP = 16_000_000_000

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
    """True iff a live ATM options pair exists with bid>0 on BOTH legs AND call_oi+put_oi>=100 AND
    straddle spread/mid < 0.6 (research §A.2 liquidity gate — a loose oi>0 gate would admit OI=5 /
    90%-wide names as 'optionable' on a money path feeding implied-move + hedge legs). None on
    degrade (fetch None). # ponytail: expiry-at/after-catalyst is a per-TRADE check (the catalyst
    date isn't fixed at universe-build time) — deferred to the desk, noted here."""
    q = options_cboe.fetch(ticker)
    if q is None:
        return None
    oq = q.get("options_quote")
    if not oq:
        return False  # no live ATM pair with bid>0 both legs
    cb, ca, pb, pa = oq["call_bid"], oq["call_ask"], oq["put_bid"], oq["put_ask"]
    if not (cb > 0 and pb > 0):
        return False
    if (oq["call_oi"] + oq["put_oi"]) < 100:
        return False
    mid = (cb + ca) / 2 + (pb + pa) / 2
    spread = (ca - cb) + (pa - pb)
    if mid <= 0 or spread / mid >= 0.6:
        return False
    return True


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
    """Cull discovered candidates to tradeable + fit-able. Returns (admitted, rejected), each record
    carrying its screen datums, flags, reasons, and catalyst provenance.

    Admit iff ALL of: dollar-ADV >= $5M (or $2-5M -> admit + size_tiny), market-cap in [$200M,$10B]
    (or a hedge-peer flag to ~$16B), optionable, and a readable cap. A None on ADV/cap/optionability
    -> DROP with a reason (cite-or-drop, NEVER imputed). Runway is attached (None is legit when a
    filer isn't burning) and flagged, not a hard drop.
    """
    criteria = criteria or {}
    min_adv = criteria.get("min_adv_usd", _DEFAULT_MIN_ADV_USD)
    tiny_floor = criteria.get("size_tiny_floor", _SIZE_TINY_FLOOR)
    min_cap = criteria.get("min_market_cap", _DEFAULT_MIN_MARKET_CAP)
    max_cap = criteria.get("max_market_cap", _DEFAULT_MAX_MARKET_CAP)
    hedge_cap = criteria.get("hedge_peer_max_market_cap", _HEDGE_PEER_MAX_MARKET_CAP)

    admitted: list[dict] = []
    rejected: list[dict] = []
    for cand in candidates.values():
        ticker = cand["ticker"]
        adv = _dollar_adv(ticker, as_of)
        cap, fund = _market_cap(ticker, as_of)
        opt = _optionable(ticker)
        runway = fund.get("cash_runway_months") if fund else None
        ta = cand.get("therapeutic_area") or _ta_fallback(ticker) or "unknown"

        flags: dict = {}
        reasons: list[str] = []

        # ADV floor + size-tiny tier
        if adv is None:
            reasons.append("adv_unreadable")
        elif adv < tiny_floor:
            reasons.append(f"adv_usd {adv:.0f} < {tiny_floor:.0f}")
        elif adv < min_adv:
            flags["size_tiny"] = True

        # market-cap band + hedge-peer exception
        if cap is None:
            reasons.append("market_cap_unreadable")
        elif cap < min_cap:
            reasons.append(f"market_cap {cap:.0f} < {min_cap:.0f}")
        elif cap > max_cap:
            if cand.get("hedge_peer") and cap <= hedge_cap:
                flags["hedge_peer_band"] = True
            else:
                reasons.append(f"market_cap {cap:.0f} > {max_cap:.0f}")

        # optionability (money path — bid both legs + OI floor + spread ceiling)
        if opt is None:
            reasons.append("optionability_unreadable")
        elif not opt:
            reasons.append("not_optionable")

        # cash-runway sanity (informational; None is legit when a filer is not burning)
        if runway is None:
            flags["runway_unknown"] = True

        rec = {
            **cand,
            "therapeutic_area": ta,
            "adv_usd": adv,
            "market_cap": cap,
            "cash_runway_months": runway,
            "flags": flags,
            "reasons": reasons,
            "delisted": cand.get("delisted", False),
        }
        (rejected if reasons else admitted).append(rec)
    return admitted, rejected


def _enforce_diversity(admitted: list[dict], *, max_per_ta: int = 4) -> list[dict]:
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
    """Measure-and-grow: N is an OUTPUT. Rank the screened candidates densest-first, grow the
    shortlist one at a time, and STOP when projected weekly lambda >= target_lambda OR the shortlist
    hits safety_cap OR the pool is exhausted (honest under-fill — do NOT over-grow to chase target;
    the defensive/statistical sleeve backstops lean weeks). target_lambda default 1.75 is the
    average across the year (locked decision), NOT >=1 every single week.

    Returns (shortlist, density_report). N is len(shortlist) — never a hard-coded 80.
    """
    # ponytail: derived base rate, recalibrate from measured store density once Phase 7.5 backfills.
    ranked = sorted(
        screened,
        key=lambda r: sum(1 for c in r.get("catalysts", []) if c["type"] in LIVE_PARITY_TYPES),
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
    date_from: str | None = None, date_to: str | None = None,
) -> dict:
    """Orchestrate discover -> screen -> diversity -> size -> build_snapshot into a survivorship-free
    append-only `universe_as_of` cohort, returning a run summary with per-name provenance + the
    honest breadth/depth tradeoff.

    CRITICAL (Blocker 1): build_snapshot re-applies its OWN store-density floor via _catalyst_density
    over the (vacuous pre-7.5) `catalyst` table, so we pass min_catalyst_density=0 — discovery's
    size_to_density already enforces density from FORWARD evidence; the store-density floor is not
    meetable by design this phase and re-engages once 7.5 backfills the trailing history.
    """
    date_from = date_from or as_of
    date_to = date_to or _add_months(as_of, 12)

    # CT.gov = forward completion window; efts = MULTI-YEAR (5yr) TRAILING filing window (PDUFA-
    # announcing 8-Ks are filed months before the catalyst — a forward filing window returns 0;
    # the 5yr breadth doubles as the warm-start historical-catalyst backfill). Verified live.
    candidates = discover_candidates(date_from, date_to)
    admitted, rejected = screen_candidates(candidates, as_of, criteria=criteria)
    kept = _enforce_diversity(admitted)
    demoted = [r for r in admitted if r not in kept]
    rejected = rejected + demoted

    shortlist, density_report = size_to_density(kept, as_of, target_lambda=target_lambda)

    seed_rows = [_to_seed_row(r) for r in shortlist]
    # ponytail: min_catalyst_density=0 here because the catalyst table is empty pre-7.5; the
    # store-density floor re-engages once 7.5 backfills the trailing history.
    build_criteria = {
        "min_catalyst_density": 0,
        "min_adv_usd": _DEFAULT_MIN_ADV_USD,
        "min_market_cap": _DEFAULT_MIN_MARKET_CAP,
        **(criteria or {}),
    }
    included_count = build_snapshot(conn, as_of, seed_rows, criteria=build_criteria)

    admissions = []
    for r in shortlist:
        prov = (r.get("catalysts") or [{}])[0]
        admissions.append({
            "ticker": r["ticker"],
            "cik": r.get("cik"),
            "therapeutic_area": r.get("therapeutic_area"),
            "source_feeds": sorted(r.get("source_feeds", [])),
            "source_url": prov.get("source_url"),
            "fetch_ts": prov.get("fetch_ts"),
            "grade": prov.get("grade"),
            "flags": r.get("flags", {}),
            "n_catalysts": len(r.get("catalysts", [])),
        })

    return {
        "as_of": as_of,
        "n_candidates": len(candidates),
        "n_screened": len(kept),
        "n_admitted": density_report["n_admitted"],
        # included_count is build_snapshot's RETURNED count of rows written included=1 — a DISTINCT
        # field from n_admitted so the two reconcile; a large gap means the store-density trap
        # (Blocker 1) re-appeared, or size_tiny names fell under the snapshot's $5M floor.
        "included_count": included_count,
        "measured_lambda": density_report["measured_lambda"],
        "target_reached": density_report["target_reached"],
        "density_report": density_report,
        "admissions": admissions,
        "n_rejected": len(rejected),
        "tradeoff": _TRADEOFF_NOTE,
    }
