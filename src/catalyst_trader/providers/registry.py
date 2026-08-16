"""PIPE-01 — the ONE provider registry both the daemon and the shakedown wire through.

`build_providers(settings)` lifts what used to be `shakedown._live_providers`'s duplicated dict into
a single place and wires the Wave-1/2 providers into their slots: edgar.fetch -> `edgar`,
edgar.fundamentals -> `financials`, fred.fetch_macro -> `macro`, finra.fetch -> `finra`, and
`fetch_earnings_with_fallback(fmp.fetch_earnings, nasdaq_earnings.fetch)` -> `earnings`. The
per-ticker datum closures (`_options`/`_finra`/`_edgar`/`_financials`) KEEP their `@functools.cache`
memoization — "no behaviour change" includes the cache, so a degrading source is not re-hit 52x per
ticker within a run. `CADENCE` is the per-source refresh interval (seconds) driving "due" + staleness.
"""

from __future__ import annotations

import functools
from calendar import monthrange
from datetime import date, datetime, timedelta

# Per-source refresh cadence in SECONDS (research §3.1): prices daily-after-close, CBOE ~2x/day,
# FINRA/XBRL on-publication (weekly bound), catalysts + FRED daily. Drives the daemon's "due"
# decision and the is_stale threshold (2x cadence). Keyed by provider SLOT so every wired source
# has a cadence entry.
_DAY = 86_400
CADENCE: dict[str, int] = {
    "prices": _DAY,           # daily after close
    "options": _DAY // 2,     # CBOE ~2x/day
    "finra": 7 * _DAY,        # bi-monthly bulk, weekly-bound refresh
    "edgar": 7 * _DAY,        # XBRL filings, weekly
    "financials": 7 * _DAY,   # edgartools XBRL, weekly
    "macro": _DAY,            # FRED daily
    "clinicaltrials": _DAY,   # catalysts daily
    "earnings": _DAY,         # catalysts daily
    "pdufa": _DAY,            # curated catalysts daily
    "quotes_rt": 300,         # RH real-time quotes — intraday monitor cadence (5 min)
    "float": 7 * _DAY,        # RH fundamentals/float, weekly (like financials)
    "portfolio": _DAY,        # RH ledger reconciliation, daily
    "rh_historicals": _DAY,   # RH raw bars cross-check vote, daily
}


def recent_si_settlement(end: str) -> str:
    """The most recent FINRA settlement date (15th / EOM) published by ``end`` (~T+9 business days).
    Picks the latest of {15th, month-end} that is >= 12 calendar days before end. (Lifted verbatim
    from the shakedown's live wiring so FINRA fetches the right bi-monthly file.)"""
    e = date.fromisoformat(end)
    cutoff = e - timedelta(days=12)
    candidates = []
    for back in range(3):  # this month + two prior
        y, m = e.year, e.month - back
        while m <= 0:
            y, m = y - 1, m + 12
        candidates.append(date(y, m, 15))
        candidates.append(date(y, m, monthrange(y, m)[1]))
    valid = sorted(d for d in candidates if d <= cutoff)
    return valid[-1].isoformat()


def build_providers(settings, *, end: str | None = None) -> dict:
    """The SINGLE provider registry wired from ``settings``. ``end`` anchors the FINRA settlement
    file (defaults to today). Each slot degrades independently (ingest._safe / the cascade), so a
    missing key or a source outage is a LOGGED edge case, never a crash and never a fabricated value.

    The per-ticker datum providers (options/finra/edgar/financials) are week-INVARIANT but
    ingest_history calls them once per (ticker, week_end); the @functools.cache means a degrading
    endpoint is queried ONCE per ticker per run, not 52x.
    """
    from catalyst_trader.providers import (
        clinicaltrials,
        edgar,
        finra,
        fmp,
        fred,
        nasdaq_earnings,
        options_cboe,
        pdufa,
        prices,
        robinhood,
    )

    si_date = recent_si_settlement(end or date.today().isoformat())

    @functools.cache
    def _options(tk):
        return options_cboe.fetch(tk)

    @functools.cache
    def _finra(tk):
        return finra.fetch(tk, si_date)

    @functools.cache
    def _edgar(tk):
        return edgar.fetch(tk)

    @functools.cache
    def _financials(tk):
        return edgar.fundamentals(tk)

    # macro is context, not a gate: no FRED key -> degrade the whole slot to None (never crash).
    macro = (lambda: fred.fetch_macro()) if getattr(settings, "fred_api_key", None) else None

    # Robinhood MCP read slots (RH-DATA-01): the callable is runtime-bound by the SDK
    # (settings.rh_mcp_call, RH-DATA-03) — None until then, so each slot degrades to None EXACTLY
    # like macro/FRED. NOT sole-source (the free stack is the spine); rh_historicals is a DISTINCT
    # cross-check VOTE slot, deliberately NOT wired into the bulk `prices`/historical path.
    rh_call = getattr(settings, "rh_mcp_call", None)

    return {
        "prices": lambda tk, s, e: prices.get_weekly_bars(tk, s, e),
        "options": _options,
        "finra": _finra,
        "edgar": _edgar,
        "financials": _financials,          # edgartools XBRL float/runway gap-filler
        "macro": macro,                     # FRED macro-regime bundle (degrades to None w/o key)
        "clinicaltrials": lambda tks, s, e: clinicaltrials.fetch_trial_readouts(tks, s, e),
        "earnings": nasdaq_earnings.fetch_earnings_with_fallback(
            fmp.fetch_earnings, nasdaq_earnings.fetch),  # FMP-first, Nasdaq fallback
        "pdufa": lambda tks, s, e, company_map=None: pdufa.fetch(tks, s, e, company_map=company_map),
        # RH read slots — None until settings.rh_mcp_call is bound (mirrors macro/FRED gate).
        "quotes_rt": (lambda tks: robinhood.quotes_rt(tks, mcp_call=rh_call)) if rh_call else None,
        "float": (lambda tk: robinhood.fundamentals(tk, mcp_call=rh_call)) if rh_call else None,
        "portfolio": (lambda: robinhood.portfolio(mcp_call=rh_call)) if rh_call else None,
        "rh_historicals": (lambda tk: robinhood.historicals(tk, mcp_call=rh_call)) if rh_call else None,
    }
