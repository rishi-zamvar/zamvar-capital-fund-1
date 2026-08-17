"""options_cboe ATM-selection regression (06.12-04) — the live-close bug fix.

The provider used to pick the EARLIEST expiry with ANY bid>0 ATM pair, which on real chains is a
thin near-dated WEEKLY whose only quoted strikes sit far from spot — producing a deep-OTM "ATM"
quote (VERA spot $31.71 -> a ~$0.20 call) and wrongly failing liquid names as not_optionable.

The fix: select the LIQUID ATM pair — strike NEAREST TO SPOT with bid>0 on BOTH legs AND real open
interest (MIN_ATM_OI) within a near-spot band (ATM_BAND) — preferring a STANDARD MONTHLY
(3rd-Friday) expiry over thin weeklies. The Pitfall-2 junk-IV guard is preserved: no liquid ATM
anywhere -> options_quote=None AND iv30=None. ZERO live API in this suite.
"""

import pytest

from catalyst_trader.providers import _http, options_cboe

_QUOTE_KEYS = {"call_bid", "call_ask", "put_bid", "put_ask", "call_oi", "put_oi", "expiry"}


@pytest.fixture(autouse=True)
def _isolate():
    _http._clear_cache()
    yield
    _http._clear_cache()


def _payload(spot, options):
    return {"data": {"symbol": "T", "current_price": spot, "bid": spot - 0.05,
                     "volume": 500000, "iv30": 0.70, "options": options}}


def test_monthly_atm_chosen_over_weekly_far_otm(httpx_mock, load_fixture):
    """The exact 17/20-rejection regression: earliest weekly has only a far-OTM common pair (and a
    later near-spot liquid weekly), but the standard MONTHLY clean ATM is chosen — not the weekly."""
    httpx_mock.add_response(json=load_fixture("cboe_weekly_vs_monthly_atm"))
    raw = options_cboe.fetch("VERA")

    q = raw["options_quote"]
    assert q is not None
    assert q["expiry"] == "2026-09-18"          # the standard 3rd-Friday MONTHLY, not the 08-28 weekly
    assert q["call_bid"] == 2.10 and q["put_bid"] == 2.20  # near-spot $32 pair, NOT the $0.20 deep-OTM $40 call
    assert q["call_oi"] == 300 and q["put_oi"] == 280


def test_atm_oi_floor(httpx_mock):
    """A near-spot pair with call_oi+put_oi below MIN_ATM_OI (a 1-lot ghost) does NOT qualify."""
    opts = [
        {"option": "T260918C00032000", "bid": 2.1, "ask": 2.3, "iv": 0.7, "open_interest": 1, "volume": 0},
        {"option": "T260918P00032000", "bid": 2.2, "ask": 2.4, "iv": 0.71, "open_interest": 1, "volume": 0},
    ]
    httpx_mock.add_response(json=_payload(31.71, opts))
    raw = options_cboe.fetch("T")
    assert raw["options_quote"] is None          # 1+1 OI < MIN_ATM_OI -> rejected
    assert raw["iv30"] is None                    # no liquid ATM -> junk IV not surfaced


def test_atm_near_spot_band(httpx_mock):
    """A chain whose only bid>0 common strikes are far from spot (beyond ATM_BAND) yields no ATM
    pair — the provider does NOT return a far-OTM strike as 'ATM'."""
    opts = [
        {"option": "T260918C00040000", "bid": 0.20, "ask": 0.30, "iv": 0.95, "open_interest": 500, "volume": 5},
        {"option": "T260918P00040000", "bid": 8.30, "ask": 8.70, "iv": 0.93, "open_interest": 500, "volume": 1},
    ]
    httpx_mock.add_response(json=_payload(31.71, opts))  # |40/31.71-1| = 0.26 > ATM_BAND
    raw = options_cboe.fetch("T")
    assert raw["options_quote"] is None
    assert raw["iv30"] is None


def test_junk_iv_guard_preserved(httpx_mock):
    """No liquid ATM anywhere (only no-bid deep-OTM junk) -> options_quote None AND iv30 None."""
    opts = [
        {"option": "T260918C00050000", "bid": 0.0, "ask": 0.05, "iv": 0.0, "open_interest": 0, "volume": 0},
        {"option": "T260918P00050000", "bid": 0.0, "ask": 0.05, "iv": 0.0, "open_interest": 0, "volume": 0},
    ]
    httpx_mock.add_response(json=_payload(31.71, opts))
    raw = options_cboe.fetch("T")
    assert raw["options_quote"] is None            # Pitfall 2 intact
    assert raw["iv30"] is None
    assert raw["underlying_quote"]["oi"] == 0       # honest "market is dead" -> hard-fail downstream


def test_output_contract_unchanged(httpx_mock, load_fixture):
    """On a clean chain the 7 options_quote keys are all present + the top-level contract is intact
    (no consumer KeyError from a partial dict / renamed key)."""
    httpx_mock.add_response(json=load_fixture("cboe_weekly_vs_monthly_atm"))
    raw = options_cboe.fetch("VERA")

    assert set(raw["options_quote"]) == _QUOTE_KEYS
    assert "catalyst_date" not in raw["options_quote"]
    assert set(raw["underlying_quote"]) == {"bid", "volume", "oi"}
    for k in ("options_quote", "underlying_quote", "iv30", "term_spread",
              "straddle_move_pct", "straddle_median", "underlying_price", "provenance"):
        assert k in raw
    assert raw["iv30"] == 0.72                       # trusted only because a liquid ATM qualified
    assert raw["underlying_quote"]["oi"] == 300 + 280
    # straddle move off the SELECTED monthly $32 pair (mids), delegated to quant.implied_move
    assert raw["straddle_move_pct"] == pytest.approx((2.20 + 2.30) / 31.71)


def test_term_spread_off_fixed_pair(httpx_mock, load_fixture):
    """term_spread uses a LATER-expiry qualifying ATM pair (the fixed liquid qualifier), not the old
    far-OTM one: 10-16 monthly $32 iv (0.75) minus the selected 09-18 monthly $32 iv (0.70)."""
    httpx_mock.add_response(json=load_fixture("cboe_weekly_vs_monthly_atm"))
    raw = options_cboe.fetch("VERA")
    assert raw["term_spread"] == pytest.approx(0.75 - 0.70)
