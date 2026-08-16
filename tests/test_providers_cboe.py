"""CBOE delayed-quotes provider (options_cboe.py) — the build_card options seam, offline.

Money-path guards: options_quote is a COMPLETE 7-market-key dict OR None (never partial —
options_liquid uses raising subscripts downstream), catalyst_date is NOT emitted here
(assemble_raw injects it in Plan 07), junk iv=0/no-bid contracts never surface a trusted iv30
(Pitfall 2), and the straddle move comes from quant.implied_move — no hand arithmetic. The
provider does NOT run the liquidity gate (it has no catalyst_date). ZERO live API in this suite.
"""

import pytest

from catalyst_trader.providers import _http, options_cboe

_QUOTE_KEYS = {"call_bid", "call_ask", "put_bid", "put_ask", "call_oi", "put_oi", "expiry"}
_JUNK = {
    "data": {
        "symbol": "KURA",
        "current_price": 12.34,
        "bid": 12.30,
        "volume": 512345,
        "iv30": 0.85,
        "options": [
            {"option": "KURA260821C00050000", "bid": 0.00, "ask": 0.05, "iv": 0.00, "open_interest": 0, "volume": 0},
            {"option": "KURA260821P00050000", "bid": 0.00, "ask": 0.05, "iv": 0.00, "open_interest": 0, "volume": 0},
        ],
    }
}


@pytest.fixture(autouse=True)
def _isolate():
    _http._clear_cache()
    yield
    _http._clear_cache()


def test_cboe_emits_complete_7key_quote_or_none(httpx_mock, load_fixture):
    httpx_mock.add_response(json=load_fixture("cboe_kura"))
    raw = options_cboe.fetch("KURA")

    assert set(raw["options_quote"]) == _QUOTE_KEYS  # exactly the 7 market keys
    assert "catalyst_date" not in raw["options_quote"]  # assemble_raw injects it downstream
    assert set(raw["underlying_quote"]) == {"bid", "volume", "oi"}
    assert raw["provenance"]["iv30"]["source_url"].startswith("https://cdn.cboe.com")
    assert raw["provenance"]["iv30"]["grade"] == "yellow"

    q = raw["options_quote"]
    assert q == {
        "call_bid": 0.60, "call_ask": 0.75, "put_bid": 0.55, "put_ask": 0.70,
        "call_oi": 200, "put_oi": 180, "expiry": "2026-08-21",  # nearest-expiry ATM live pair
    }
    assert raw["underlying_quote"] == {"bid": 12.30, "volume": 512345, "oi": 380}
    assert raw["iv30"] == 0.85
    assert raw["underlying_price"] == 12.34
    assert raw["term_spread"] == pytest.approx(0.05)  # far ATM iv - near ATM iv
    assert raw["straddle_move_pct"] == pytest.approx((0.675 + 0.625) / 12.34)


def test_cboe_quote_is_never_partial(httpx_mock, load_fixture):
    httpx_mock.add_response(json=load_fixture("cboe_kura"))
    q = options_cboe.fetch("KURA")["options_quote"]
    assert q is None or set(q) == _QUOTE_KEYS  # full 7-key set OR None — never a subset


def test_cboe_straddle_move_uses_implied_move(httpx_mock, load_fixture, monkeypatch):
    from catalyst_trader.quant import options as quant_options

    calls = []
    real = quant_options.implied_move

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return real(*args, **kwargs)

    monkeypatch.setattr(quant_options, "implied_move", spy)
    httpx_mock.add_response(json=load_fixture("cboe_kura"))
    options_cboe.fetch("KURA")
    assert calls, "provider must delegate the straddle move to quant.implied_move (no hand math)"


def test_cboe_iv_zero_junk_none_not_trusted(httpx_mock):
    httpx_mock.add_response(json=_JUNK)
    raw = options_cboe.fetch("KURA")
    assert raw["options_quote"] is None  # no near-the-money live-bid pair qualifies
    assert raw["iv30"] is None  # junk IV is NEVER surfaced as a trusted iv30 (Pitfall 2)


def test_cboe_403_degrades_not_raises(httpx_mock):
    httpx_mock.add_response(status_code=403)
    assert options_cboe.fetch("KURA") is None  # _http degrade -> None, no exception
