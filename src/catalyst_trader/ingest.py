"""INGEST-03/04 — the provider<->store seam + the historical ingestion loop.

Two pieces, ZERO new dependencies, every write funneled through the EXISTING idempotent UPSERT
paths (store.upsert_bars / insert_catalyst / write_card) so the ingested rows are read back by
thesis_scan / bars_asof / build_event_set through the SAME signatures — no downstream contract
change, no ``live=True/False`` boolean threaded through the desk. The store IS the seam; the only
toggle is WHO populates it (fixtures in tests, real providers here), resolved at this entrypoint.

1. ``assemble_raw(providers, ticker, week_end)`` — builds the exact ``raw`` dict
   ``desk.company_scan.build_card`` consumes from the real datum providers (CBOE options / FINRA
   short-interest / EDGAR filings / optional financials) + the catalyst-window fields derived from
   the ticker's upcoming catalysts. THE injection seam: it stamps
   ``options_quote["catalyst_date"] = <next-catalyst event_date>`` so the CBOE 7-market-key quote
   becomes the COMPLETE 8-key quote ``options_liquid`` needs (no KeyError). A None quote — or no
   upcoming catalyst to gate against — stays None and ``build_card`` degrades to the in-house path.
   NEVER a partial dict, never a ``catalyst_date=None`` that would crash the expiry compare.

2. ``ingest_history(conn, *, start, end, providers, universe_csv=...)`` — iterates the seed
   universe over ``[start, end]``: prices -> ``upsert_bars`` (cross-check provenance + survivorship-
   aware); catalysts -> ``insert_catalyst`` THEN ``verify_catalyst`` (the providers only insert; the
   loop VERIFIES), stamping a POINT-IN-TIME ``last_verified_at`` from the authoritative (FR primary)
   source's IN-MEMORY ``published_date`` (NOT now, NOT event_date — either reintroduces the Phase-7
   look-ahead leak, BACK-01); cards -> ``assemble_raw`` + ``build_card`` + ``write_card``. Idempotent
   by construction (every write UPSERTs on its natural key) — a double run yields identical counts.
"""

import csv
import logging
from collections import defaultdict
from datetime import date

from catalyst_trader import store
from catalyst_trader.calendar import verify
from catalyst_trader.desk.company_scan import build_card
from catalyst_trader.models import SourceType, Status

logger = logging.getLogger(__name__)


# --- helpers ---------------------------------------------------------------------------------


def _safe(fn, *args, **kwargs):
    """Call an optional provider, degrading a missing/raising provider to None — the loop drops
    that datum and continues (never crash the seam, never fabricate)."""
    if fn is None:
        return None
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # a provider degrade must not sink the ingest
        logger.warning("provider %s degraded: %s", getattr(fn, "__name__", fn), exc)
        return None


def _event_date(cat):
    """The event_date off a Catalyst object or a plain dict."""
    return getattr(cat, "event_date", None) if not isinstance(cat, dict) else cat.get("event_date")


def _as_date(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


def _catalyst_window(catalysts, week_end):
    """(next_catalyst_iso, days_to_catalyst, catalysts_4w) from the ticker's upcoming catalysts —
    the nearest event on/after week_end, its day distance, and how many fall within 4 weeks."""
    wk = _as_date(week_end)
    upcoming = sorted(d for d in (_as_date(_event_date(c)) for c in catalysts) if d and wk and d >= wk)
    if not upcoming:
        return None, None, 0
    nxt = upcoming[0]
    return nxt.isoformat(), (nxt - wk).days, sum(1 for d in upcoming if (d - wk).days <= 28)


# --- 1. the injection seam -------------------------------------------------------------------


def assemble_raw(providers, ticker, week_end):
    """Build the exact ``raw`` dict ``build_card`` consumes, from the real providers, injecting
    catalyst_date into the CBOE quote. ``providers`` is a dict of callables (tests inject stubs):
    ``options``/``finra``/``edgar``/``financials`` take ``(ticker)``; ``catalysts`` takes
    ``(ticker)`` -> the ticker's catalysts (window fields derived here)."""
    opt = _safe(providers.get("options"), ticker) or {}
    fin = _safe(providers.get("finra"), ticker) or {}
    fil = _safe(providers.get("edgar"), ticker) or {}
    bal = _safe(providers.get("financials"), ticker) or {}
    catalysts = _safe(providers.get("catalysts"), ticker) or []

    next_catalyst, days_to_catalyst, catalysts_4w = _catalyst_window(catalysts, week_end)

    # THE seam fix: the live 7-key CBOE quote becomes the complete 8-key options_liquid shape.
    # No upcoming catalyst -> nothing to gate options against -> degrade to None (never a partial
    # dict, never a catalyst_date=None that would crash options_liquid's expiry compare).
    options_quote = opt.get("options_quote")
    if options_quote is not None:
        options_quote = {**options_quote, "catalyst_date": next_catalyst} if next_catalyst else None

    return {
        "options_quote": options_quote,
        "underlying_quote": opt.get("underlying_quote"),
        "iv30": opt.get("iv30"),
        "term_spread": opt.get("term_spread"),
        "straddle_move_pct": opt.get("straddle_move_pct"),
        "straddle_median": opt.get("straddle_median"),
        "underlying_price": opt.get("underlying_price"),
        "short_interest": fin.get("short_interest"),
        "days_to_cover": fin.get("days_to_cover"),
        "si_settlement_date": fin.get("si_settlement_date"),
        "cash_runway_months": bal.get("cash_runway_months"),
        "seen_accessions": fil.get("seen_accessions", []),
        "live_shelf": fil.get("live_shelf"),
        "days_to_catalyst": days_to_catalyst,
        "next_catalyst": next_catalyst,
        "catalysts_4w": catalysts_4w,
        # ponytail: F2/F3 inputs need an NCT tracker + a competitor map (not this plan's scope);
        # None => those flags simply never fire, honest degradation, not fabrication.
        "competitor_next_7d": None,
        "nct_snapshots": None,
    }


# --- 2. the historical ingestion loop --------------------------------------------------------


def _load_seed(csv_path):
    """The seed universe rows (# comment lines skipped) -> [{ticker, company_name, delisted}]."""
    lines = [ln for ln in open(csv_path, encoding="utf-8").read().splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    return [{
        "ticker": r["ticker"].strip(),
        "company_name": (r.get("company_name") or "").strip(),
        "delisted": (r.get("delisted") or "").strip().lower() == "true",
    } for r in csv.DictReader(lines)]


def _upsert_price_bars(conn, ticker, bars, *, delisted):
    """Funnel get_weekly_bars output into store.upsert_bars, preserving each bar's cross-check
    provenance by grouping the batch on (source, grade, agreeing_sources)."""
    groups = defaultdict(list)
    for b in bars:
        groups[(b.get("source"), b.get("source_grade"),
                ",".join(sorted(b.get("agreeing_sources") or [])) or None)].append(b)
    for (source, grade, agreeing), gbars in groups.items():
        store.upsert_bars(conn, ticker, gbars, delisted=delisted,
                          source=source or "fixture", source_grade=grade, agreeing_sources=agreeing)


def _pit_stamp(cat):
    """The POINT-IN-TIME last_verified_at for a verified catalyst: the authoritative (primary-
    preferred — mirrors verify_catalyst's selection, NOT sources[0]) agreeing source's OWN
    publication_date, read from the IN-MEMORY Catalyst (published_date is transport-only, never
    persisted). NOT now(), NOT event_date — either reintroduces the Phase-7 look-ahead leak
    (BACK-01). None when the primary source has no publication_date -> the catalyst stays
    unstamped (excluded by build_event_set), never a fabricated stamp."""
    agreeing = [s for s in cat.sources if s.agrees]
    authoritative = next(
        (s for s in agreeing if s.source_type == SourceType.primary),
        agreeing[0] if agreeing else None,
    )
    return authoritative.published_date if authoritative else None


def _fetch_catalysts(providers, tickers, start, end, company_map):
    """clinicaltrials + fmp earnings + pdufa -> one Catalyst list; each feed degrades to []."""
    out = []
    out += _safe(providers.get("clinicaltrials"), tickers, start, end) or []
    out += _safe(providers.get("earnings"), tickers, start, end) or []
    out += _safe(providers.get("pdufa"), tickers, start, end, company_map=company_map) or []
    return out


def ingest_history(conn, *, start, end, providers, universe_csv="data/seed_universe.csv"):
    """Ingest the seed universe over [start, end] through the existing idempotent write-paths.

    Prices -> upsert_bars (cross-check provenance, survivorship-aware). Catalysts -> insert_catalyst
    THEN verify_catalyst (the providers only insert; the loop VERIFIES), stamping a point-in-time
    last_verified_at from the FR primary source's in-memory published_date. Cards -> assemble_raw +
    build_card + write_card, one per (ticker, week_end) that has bars. Idempotent by construction.
    """
    seed = _load_seed(universe_csv)
    tickers = [r["ticker"] for r in seed]

    # (1) prices -> upsert_bars; remember each ticker's real bar weeks for card-building.
    weeks_by_ticker = {}
    for r in seed:
        bars = _safe(providers.get("prices"), r["ticker"], start, end) or []
        _upsert_price_bars(conn, r["ticker"], bars, delisted=r["delisted"])
        weeks_by_ticker[r["ticker"]] = sorted({b["week_end"] for b in bars})

    # (2) catalysts -> insert THEN verify THEN point-in-time stamp (FedRegister ticker attribution
    # via the curated company_map built from the seed universe — mirrors clinicaltrials' sponsor_map).
    company_map = {r["ticker"]: [r["company_name"]] for r in seed if r["company_name"]}
    cats_by_ticker = defaultdict(list)
    verified = 0
    for cat in _fetch_catalysts(providers, tickers, start, end, company_map):
        cid = store.insert_catalyst(conn, cat)
        if verify.verify_catalyst(conn, cid) is Status.verified:
            stamp = _pit_stamp(cat)
            if stamp is not None:  # null publication_date -> stays unstamped (excluded downstream)
                conn.execute("UPDATE catalyst SET last_verified_at=? WHERE id=?", (stamp, cid))
                conn.commit()
                verified += 1
        cats_by_ticker[cat.ticker].append(cat)

    # (3) cards -> assemble_raw + build_card + write_card, per (ticker, week_end) with bars.
    card_providers = {
        "options": providers.get("options"),
        "finra": providers.get("finra"),
        "edgar": providers.get("edgar"),
        "financials": providers.get("financials"),
        "catalysts": lambda tk: cats_by_ticker.get(tk, []),
    }
    cards = 0
    for ticker in tickers:
        for week_end in weeks_by_ticker.get(ticker, []):
            raw = assemble_raw(card_providers, ticker, week_end)
            card = build_card(conn, ticker, week_end, raw, thesis_row={})
            store.write_card(conn, ticker, week_end, card, source="ingest")
            cards += 1

    return {"tickers": len(tickers), "verified_catalysts": verified, "cards": cards}
