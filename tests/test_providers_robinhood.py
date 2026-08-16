"""Plan 06.11-03 — providers/robinhood.py: the read-only Robinhood MCP-tool DATA adapter.

Offline suite. The adapter is a degrade-to-None wrapper over an INJECTABLE
`mcp_call(tool_name, args) -> dict` seam (the Claude Agent SDK MCP surface, NOT `_http`).
We NEVER touch a real MCP / network here — `mcp_call` is a mock, and the fixtures MIRROR the
REAL probed 2026-08-16 responses (`.planning/research/robinhood-probe-results.md`), whose numbers
are all STRING-typed, so the adapter must float()-coerce with a None-guard.

Proves, for all four slots (quotes_rt / fundamentals / portfolio / historicals):
- degrade-to-None when mcp_call is None/absent OR raises (mirrors the macro/FRED-key gate),
- the normalized shape + float coercion from the real probed fixtures,
- read-only discipline (no order-mutating tool token in the module source),
plus the registry slots being None without an `rh_mcp_call` binding and callable when bound.
"""

from types import SimpleNamespace

from catalyst_trader.providers import registry, robinhood

# --- REAL probed fixtures (2026-08-16), copied VERBATIM — string-typed numbers ----------------

RH_QUOTES = {"data": {"results": [{
    "quote": {
        "symbol": "IONS", "last_trade_price": "57.21", "last_non_reg_trade_price": "56.18",
        "adjusted_previous_close": "55.87", "previous_close": "55.87",
        "previous_close_date": "2026-08-13", "bid_price": "56.53", "ask_price": "68.00",
        "has_traded": True, "state": "active",
    },
    "close": {
        "symbol": "IONS", "date": "2026-08-13", "price": "55.87",
        "interpolated": False, "source": "sip-list-exchange-close",
    },
}]}}

RH_FUNDAMENTALS = {"data": {"results": [{
    "symbol": "IONS", "open": "55.16", "high": "57.10", "low": "55.16", "volume": "1353684",
    "market_date": "2026-08-14", "high_52_weeks": "86.74", "low_52_weeks": "41.705",
    "float": "162910507.568", "market_cap": "9507405118.82", "pb_ratio": "21.0447",
    "pe_ratio": "-16.48", "shares_outstanding": "166184322.999", "dividend_yield": None,
    "sector": "Health Technology", "industry": "Pharmaceuticals: Major",
}]}}

RH_PORTFOLIO = {"data": {
    "total_value": "0", "equity_value": "0", "cash": "0",
    "buying_power": {"buying_power": "0.0000", "display_currency": "USD"}, "currency": "USD",
}}

RH_HISTORICALS = {"data": {"results": [{"historicals": [
    {"begins_at": "2026-08-13", "open_price": "55.16", "high_price": "57.10",
     "low_price": "55.16", "close_price": "55.87", "volume": "1353684"},
    {"begins_at": "2026-08-14", "open_price": "55.87", "high_price": "58.00",
     "low_price": "55.50", "close_price": "57.21", "volume": "1400000"},
]}]}}


def _mcp(mapping):
    """A fake mcp_call(tool_name, args) -> dict, returning the fixture for the tool."""
    return lambda tool_name, args: mapping[tool_name]


def _raiser(*_a, **_k):
    raise RuntimeError("MCP disconnected mid-call")


# --- quotes_rt --------------------------------------------------------------------------------


def test_quotes_rt_disconnected_returns_none():
    assert robinhood.quotes_rt(["IONS"], mcp_call=None) is None


def test_quotes_rt_shape_when_connected():
    out = robinhood.quotes_rt(["IONS"], mcp_call=_mcp({"get_equity_quotes": RH_QUOTES}))
    q = out["IONS"]
    assert q["last"] == 57.21 and isinstance(q["last"], float)
    assert q["bid"] == 56.53
    assert q["ask"] == 68.00
    assert q["prev_close"] == 55.87
    assert q["official_close"] == 55.87
    assert q["close_date"] == "2026-08-13"
    assert q["provenance"]["source_name"] == "Robinhood"
    assert q["provenance"]["grade"] == "yellow"
    assert "fetch_ts" in q["provenance"]


def test_quotes_rt_mcp_error_degrades():
    assert robinhood.quotes_rt(["IONS"], mcp_call=_raiser) is None


# --- fundamentals / float (the gap-filler) ----------------------------------------------------


def test_fundamentals_shape_fills_float():
    out = robinhood.fundamentals("IONS", mcp_call=_mcp({"get_equity_fundamentals": RH_FUNDAMENTALS}))
    assert out["float"] == 162910507.568 and isinstance(out["float"], float)
    assert out["shares_outstanding"] == 166184322.999
    assert out["market_cap"] == 9507405118.82
    assert out["high_52_weeks"] == 86.74
    assert out["low_52_weeks"] == 41.705
    assert out["provenance"]["source_name"] == "Robinhood"
    assert out["provenance"]["grade"] == "yellow"


def test_fundamentals_disconnected_returns_none():
    assert robinhood.fundamentals("IONS", mcp_call=None) is None
    assert robinhood.fundamentals("IONS", mcp_call=_raiser) is None


# --- portfolio --------------------------------------------------------------------------------


def test_portfolio_shape_when_connected():
    out = robinhood.portfolio(mcp_call=_mcp({"get_portfolio": RH_PORTFOLIO}))
    assert out["total_value"] == 0.0 and isinstance(out["total_value"], float)
    assert out["equity_value"] == 0.0
    assert out["cash"] == 0.0
    assert out["buying_power"] == 0.0
    assert out["provenance"]["grade"] == "yellow"


def test_portfolio_disconnected_returns_none():
    assert robinhood.portfolio(mcp_call=None) is None
    assert robinhood.portfolio(mcp_call=_raiser) is None


# --- historicals (cross-check VOTE only, NOT the bulk source) ---------------------------------


def test_historicals_degrade_and_shape():
    assert robinhood.historicals("IONS", mcp_call=None) is None
    assert robinhood.historicals("IONS", mcp_call=_raiser) is None
    bars = robinhood.historicals("IONS", mcp_call=_mcp({"get_equity_historicals": RH_HISTORICALS}))
    assert isinstance(bars, list) and len(bars) == 2
    assert bars[0]["close"] == 55.87 and isinstance(bars[0]["close"], float)
    assert bars[1]["close"] == 57.21
    assert bars[0]["date"] == "2026-08-13"
    assert bars[1]["volume"] == 1400000.0


# --- string-number coercion across all slots --------------------------------------------------


def test_string_numbers_coerced():
    q = robinhood.quotes_rt(["IONS"], mcp_call=_mcp({"get_equity_quotes": RH_QUOTES}))["IONS"]
    f = robinhood.fundamentals("IONS", mcp_call=_mcp({"get_equity_fundamentals": RH_FUNDAMENTALS}))
    p = robinhood.portfolio(mcp_call=_mcp({"get_portfolio": RH_PORTFOLIO}))
    h = robinhood.historicals("IONS", mcp_call=_mcp({"get_equity_historicals": RH_HISTORICALS}))
    for v in (q["last"], q["bid"], f["float"], f["shares_outstanding"], p["cash"], h[0]["open"]):
        assert isinstance(v, float)  # never a str


def test_missing_number_none_guarded():
    """A null/absent numeric field coerces to None, never a crash, never fabricated."""
    payload = {"data": {"results": [{
        "quote": {"symbol": "X", "last_trade_price": None, "bid_price": "1.0",
                  "ask_price": "2.0", "adjusted_previous_close": "1.5"},
        "close": {"symbol": "X", "date": "2026-08-13", "price": None},
    }]}}
    q = robinhood.quotes_rt(["X"], mcp_call=_mcp({"get_equity_quotes": payload}))["X"]
    assert q["last"] is None
    assert q["official_close"] is None
    assert q["bid"] == 1.0


# --- read-only discipline ---------------------------------------------------------------------


def test_read_only_no_order_tools():
    import inspect
    src = inspect.getsource(robinhood)
    for token in ("place_equity_order", "place_option_order", "cancel", "exercise", "review_order"):
        assert token not in src, f"read-only discipline violated: {token!r} in robinhood.py"


# --- registry slots (Task 2) — gated on the rh_mcp_call binding, mirroring macro/FRED ---------


def _settings(**kw):
    base = dict(fred_api_key=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_registry_rh_slots_none_without_binding():
    providers = registry.build_providers(_settings(), end="2026-08-16")
    for slot in ("quotes_rt", "float", "portfolio", "rh_historicals"):
        assert providers[slot] is None  # None until the SDK binds settings.rh_mcp_call


def test_registry_rh_slots_present_when_bound():
    call = _mcp({"get_equity_fundamentals": RH_FUNDAMENTALS})
    providers = registry.build_providers(_settings(rh_mcp_call=call), end="2026-08-16")
    for slot in ("quotes_rt", "float", "portfolio", "rh_historicals"):
        assert callable(providers[slot])
    # the float slot routes through robinhood.fundamentals with the injected mcp_call
    assert providers["float"]("IONS")["float"] == 162910507.568
