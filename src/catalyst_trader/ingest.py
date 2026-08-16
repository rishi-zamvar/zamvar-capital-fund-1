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
