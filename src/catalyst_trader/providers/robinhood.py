"""Robinhood Agentic MCP — the read-only DATA adapter (RH-DATA-01).

A pluggable, READ-ONLY adapter over the Claude Agent SDK MCP tool surface — NOT `_http`. RH data
does not flow through httpx; the tools are consumed by the SDK runtime. We model that as an
INJECTABLE callable ``mcp_call(tool_name, args) -> dict`` so the adapter is testable offline and,
crucially, DEGRADES TO None whenever the MCP is disconnected (``mcp_call`` is None/absent) or the
call raises — the exact shape of the macro/FRED-key gate in registry.py. There is NO top-level hard
import of the SDK/MCP: the daemon runs headless and the callable is runtime-bound at desk startup
(``settings.rh_mcp_call``, RH-DATA-03 live-binding).

Slots (all read-only, all degrade-to-None, never fabricate):
  - quotes_rt   <- get_equity_quotes        PRIMARY real-time last + bid/ask + official close
  - fundamentals<- get_equity_fundamentals  PRIMARY float + shares_outstanding (FILLS THE FLOAT GAP)
  - portfolio   <- get_portfolio            ledger reconciliation (agentic account 560662892, $0)
  - historicals <- get_equity_historicals   RAW bars, a cross-check VOTE (NOT the bulk-history source)

Discipline: NOT sole-source — the free stack stays the spine; RH is primary-for-realtime/float plus
a cross-check vote. Read tools ONLY — this module references no order-mutating tool (no buy / sell /
modify / redeem the position); the four functions below are the entire surface. The account-safety
guarantee (agentic account $0, only the agentic_allowed account is actionable) makes even a mistaken
write inert — but this adapter is read-only regardless. The REAL probed responses are STRING-typed
numbers, so every numeric field is float()-coerced
with a None-guard (a null/absent value stays None — never coerced to 0, never fabricated). Provenance
is stamped source_name="Robinhood", grade="yellow" (broker-grade authenticated, but the live broker
and not the free spine).
"""

from __future__ import annotations

import logging

from catalyst_trader.dates import now_iso

logger = logging.getLogger(__name__)

_ACCOUNT = "560662892"  # the only agentic_allowed account (empty $0); read-only regardless


def _f(x):
    """A string/number RH value -> float, or None (None-guard). Never coerces null to 0, never fabricates."""
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _provenance() -> dict:
    return {"source_name": "Robinhood", "grade": "yellow",
            "fetch_ts": now_iso()}


def _call(mcp_call, tool_name, args):
    """Invoke the injected MCP callable, degrading to None when it is absent/None or raises."""
    if mcp_call is None:
        return None
    try:
        return mcp_call(tool_name, args)
    except Exception as exc:  # noqa: BLE001 — a disconnected/erroring MCP degrades, never crashes the desk
        logger.warning("robinhood MCP %s degraded: %s", tool_name, exc)
        return None


def quotes_rt(tickers, *, mcp_call=None) -> dict | None:
    """Real-time quotes for the passed (trade-candidate) tickers, keyed by symbol, or None (degrade).

    get_equity_quotes -> {SYM: {last, bid, ask, prev_close, official_close, close_date, provenance}}.
    All numbers float()-coerced with a None-guard (the real values are strings). Gated to the passed
    tickers only (don't over-query the broker). mcp_call None / raising / empty -> None.
    """
    data = _call(mcp_call, "get_equity_quotes", {"symbols": list(tickers)})
    results = (data or {}).get("data", {}).get("results")
    if not results:
        return None
    out = {}
    for r in results:
        quote = r.get("quote") or {}
        close = r.get("close") or {}
        symbol = quote.get("symbol") or close.get("symbol")
        if not symbol:
            continue
        out[symbol] = {
            "last": _f(quote.get("last_trade_price")),
            "bid": _f(quote.get("bid_price")),
            "ask": _f(quote.get("ask_price")),
            "prev_close": _f(quote.get("adjusted_previous_close")),
            "official_close": _f(close.get("price")),
            "close_date": close.get("date"),
            "provenance": _provenance(),
        }
    return out or None


def fundamentals(ticker, *, mcp_call=None) -> dict | None:
    """Fundamentals for one ticker — THE float-gap filler — or None (degrade).

    get_equity_fundamentals -> {float, shares_outstanding, market_cap, high_52_weeks, low_52_weeks,
    provenance}. float can be fractional ("162910507.568"); float()-coerced + None-guarded.
    """
    data = _call(mcp_call, "get_equity_fundamentals", {"symbols": [ticker]})
    results = (data or {}).get("data", {}).get("results")
    if not results:
        return None
    r = results[0]
    return {
        "float": _f(r.get("float")),
        "shares_outstanding": _f(r.get("shares_outstanding")),
        "market_cap": _f(r.get("market_cap")),
        "high_52_weeks": _f(r.get("high_52_weeks")),
        "low_52_weeks": _f(r.get("low_52_weeks")),
        "provenance": _provenance(),
    }


def portfolio(*, mcp_call=None) -> dict | None:
    """The agentic account's ledger (value/cash/buying_power), or None (degrade).

    get_portfolio(560662892) -> {total_value, equity_value, cash, buying_power, provenance}. All
    float()-coerced + None-guarded. Ledger reconciliation only — read-only regardless of the $0 balance.
    """
    data = _call(mcp_call, "get_portfolio", {"account_number": _ACCOUNT})
    d = (data or {}).get("data")
    if not d:
        return None
    bp = d.get("buying_power")
    buying_power = bp.get("buying_power") if isinstance(bp, dict) else bp
    return {
        "total_value": _f(d.get("total_value")),
        "equity_value": _f(d.get("equity_value")),
        "cash": _f(d.get("cash")),
        "buying_power": _f(buying_power),
        "provenance": _provenance(),
    }


def historicals(ticker, *, mcp_call=None, interval="day", span="year") -> list | None:
    """RAW (adjustment_type="none") OHLCV bars for one ticker, or None (degrade).

    get_equity_historicals -> [{date, open, high, low, close, volume}] (all float()-coerced). A
    cross-check VOTE into the price cascade — NOT the bulk-history source (keep the free spine for that).
    """
    data = _call(mcp_call, "get_equity_historicals",
                 {"symbols": [ticker], "adjustment_type": "none", "interval": interval, "span": span})
    results = (data or {}).get("data", {}).get("results")
    if not results:
        return None
    bars = results[0].get("historicals") or []
    return [{
        "date": b.get("begins_at"),
        "open": _f(b.get("open_price")),
        "high": _f(b.get("high_price")),
        "low": _f(b.get("low_price")),
        "close": _f(b.get("close_price")),
        "volume": _f(b.get("volume")),
    } for b in bars] or None
