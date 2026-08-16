"""CBOE delayed-quotes JSON -> the build_card options seam (INGEST-01, YELLOW).

The provider's ONE job: turn CBOE's free delayed-quotes chain into the exact shapes the
downstream diligence gate consumes, and nothing more. It emits:
  - options_quote: a COMPLETE dict of the 7 MARKET-DATA keys
    {call_bid, call_ask, put_bid, put_ask, call_oi, put_oi, expiry} OR None — NEVER partial,
    because the downstream diligence liquidity gate uses raising subscripts (a subset = KeyError).
    The 8th gate key, catalyst_date, is the TICKER's next-catalyst date the provider CANNOT know,
    so assemble_raw (Plan 07) injects it before build_card runs. This provider does NOT import or
    run the liquidity gate itself — that is build_card's job.
  - underlying_quote: {bid, volume, oi} — the exact keys the inline hard-fail signal reads via
    .get(). bid/volume are the underlying stock's; oi is the selected ATM call+put open interest
    (the honest "is this options market alive" proxy; 0 when no live pair qualifies).
  - iv30 / term_spread / straddle_move_pct / straddle_median / underlying_price + a per-field
    provenance sub-dict (grade yellow, source_url under https://cdn.cboe.com).

Pitfall 2 (junk IV): select near-the-money contracts with a LIVE bid>0 on BOTH legs. If none
qualify (all no-bid / iv=0 junk), options_quote=None AND iv30=None — a junk IV is NEVER surfaced
as a trusted iv30. The straddle move is delegated to quant.implied_move (model-free) — the
provider does no money arithmetic itself. _http degrade (403/timeout) -> return None, never raise.
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone

from catalyst_trader.providers._http import get_json
from catalyst_trader.quant import options as _quant

logger = logging.getLogger(__name__)

_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{ticker}.json"


def _f(x):
    """Number or numeric string -> float; None on junk (mirrors prices._f)."""
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _parse_occ(sym: str):
    """OCC option symbol -> (expiry_iso, cp, strike). Last 15 chars are always YYMMDD+C/P+strike*1000."""
    strike = int(sym[-8:]) / 1000
    cp = sym[-9]
    d = sym[-15:-9]
    return f"20{d[0:2]}-{d[2:4]}-{d[4:6]}", cp, strike


def _atm_live_pair(records, spot):
    """The near-the-money call+put with a LIVE bid>0 on BOTH legs (Pitfall 2). None if none qualify."""
    calls = {r["strike"]: r for r in records if r["cp"] == "C" and r["bid"] > 0}
    puts = {r["strike"]: r for r in records if r["cp"] == "P" and r["bid"] > 0}
    common = set(calls) & set(puts)
    if not common:
        return None
    strike = min(common, key=lambda s: abs(s - spot))
    return calls[strike], puts[strike]


def fetch(ticker: str) -> dict | None:
    """CBOE delayed quotes for ``ticker`` -> the build_card options seam, or None on degrade.

    Returns a dict with a complete-or-None options_quote (see module docstring) plus
    underlying_quote/iv30/term_spread/straddle_move_pct/straddle_median/underlying_price and
    provenance. None only when _http degrades (403/timeout/bad-JSON) or the payload is unusable.
    """
    url = _URL.format(ticker=ticker.upper())
    payload = get_json("cboe", url, ua="browser", ttl_s=300)
    if not payload:
        return None
    data = payload.get("data") or {}
    spot = _f(data.get("current_price"))
    if spot is None or spot <= 0:
        return None

    parsed = []
    for o in data.get("options") or []:
        sym = o.get("option")
        if not sym or len(sym) < 15:
            continue
        try:
            expiry, cp, strike = _parse_occ(sym)
        except ValueError:
            continue
        parsed.append({
            "expiry": expiry, "cp": cp, "strike": strike,
            "bid": _f(o.get("bid")) or 0.0, "ask": _f(o.get("ask")) or 0.0,
            "oi": int(o.get("open_interest") or 0), "iv": _f(o.get("iv")),
        })

    by_expiry = defaultdict(list)
    for r in parsed:
        by_expiry[r["expiry"]].append(r)

    pair, near_expiry = None, None
    for e in sorted(by_expiry):
        pair = _atm_live_pair(by_expiry[e], spot)
        if pair:
            near_expiry = e
            break

    now = datetime.now(timezone.utc).isoformat()
    prov = {"source_url": url, "fetch_ts": now, "grade": "yellow"}
    fields = ("options_quote", "underlying_quote", "iv30", "term_spread",
              "straddle_move_pct", "underlying_price")
    provenance = {k: prov for k in fields}

    # No live ATM pair -> emit market data we DO have, but options_quote=None + iv30=None
    # (Pitfall 2: never trust a junk IV). oi=0 -> the hard-fail signal fires downstream, honestly.
    if pair is None:
        return {
            "options_quote": None, "iv30": None, "term_spread": None,
            "straddle_move_pct": None, "straddle_median": None,
            "underlying_price": spot,
            "underlying_quote": {"bid": _f(data.get("bid")), "volume": _f(data.get("volume")), "oi": 0},
            "provenance": provenance,
        }

    call, put = pair
    options_quote = {
        "call_bid": call["bid"], "call_ask": call["ask"],
        "put_bid": put["bid"], "put_ask": put["ask"],
        "call_oi": call["oi"], "put_oi": put["oi"],
        "expiry": near_expiry,  # NO catalyst_date — assemble_raw injects it downstream
    }

    # Term structure: next-later expiry ATM call IV minus the near one (contango positive).
    term_spread = None
    if call["iv"] is not None:
        for e in sorted(by_expiry):
            if e <= near_expiry:
                continue
            later = _atm_live_pair(by_expiry[e], spot)
            if later and later[0]["iv"] is not None:
                term_spread = later[0]["iv"] - call["iv"]
                break

    call_mid = (call["bid"] + call["ask"]) / 2
    put_mid = (put["bid"] + put["ask"]) / 2
    straddle_move_pct = _quant.implied_move(spot, call_mid=call_mid, put_mid=put_mid).value

    iv30 = _f(data.get("iv30"))  # trusted only because a live ATM pair qualified (Pitfall 2)
    if iv30 is not None and iv30 <= 0:
        iv30 = None

    return {
        "options_quote": options_quote,
        "underlying_quote": {
            "bid": _f(data.get("bid")),
            "volume": _f(data.get("volume")),
            "oi": call["oi"] + put["oi"],
        },
        "iv30": iv30,
        "term_spread": term_spread,
        "straddle_move_pct": straddle_move_pct,
        "straddle_median": None,  # trailing median is caller-supplied downstream (F4), not a snapshot
        "underlying_price": spot,
        "provenance": provenance,
    }
