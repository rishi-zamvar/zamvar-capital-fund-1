"""tests/test_desk_diligence_inputs.py (7.8-S2 Task 1) — the (DiligenceInput, market_data) binding.

Every money field is either honestly SOURCED (options/liquidity/hedge) or honestly DEGRADED
(financials + ownership OMITTED -> the ungrounded -> NO-GO path, never a fabricated number).
All offline: fake sources, no CBOE/EDGAR/network, no LLM.

Corrected-contract coverage (plan-checker overrides, verified against code):
  B1  financials is UNCONDITIONALLY omitted (edgar.fundamentals does not expose cash/burn/runway).
  B2  options seam is nested + nullable: read cboe["options_quote"], None -> honest sentinel; inject
      catalyst_date=event_date; every options structure carries days_to_event.
  C1  underlying_quote["bid"] can be None -> coerce to 0 (zero_liquidity's .get default never fires).
  C4  ownership UNCONDITIONALLY omitted (no insider_net source) -> degrade flag, never a partial dict.
"""

from datetime import date

from catalyst_trader.contracts import DiligenceInput
from catalyst_trader.desk import risk
from catalyst_trader.desk.diligence import DILIGENCE_PARAMS, options_liquid, zero_liquidity
from catalyst_trader.desk.diligence_inputs import make_diligence_inputs

_AS_OF = "2026-08-19"
_EVENT = "2026-08-22"          # (as_of, +7d]; days_to_event = 3
_EXIT = "2026-08-26"


def _catalyst(ticker="ACME"):
    return {"ticker": ticker, "catalyst_type": "pdufa", "event_date": _EVENT,
            "catalyst_id": f"{ticker}:{_EVENT}"}


def _risk_inputs():
    return {"p_loss": 0.4, "gap": 0.15,
            "analog_gaps": {"target_up": 0.2, "target_down": -0.3, "peer_up": 0.0,
                            "peer_down": 0.0, "w_target": 1.0, "w_peer": 0.0},
            "prices": {"target": [6.4, 6.5, 6.6], "peer": []}}


def _cboe_liquid():
    """A CBOE fetch with a LIVE ATM pair (passes the options_liquid gate)."""
    return {
        "options_quote": {"call_bid": 0.5, "call_ask": 0.6, "put_bid": 0.5, "put_ask": 0.6,
                          "call_oi": 200, "put_oi": 200, "expiry": "2026-09-19"},
        "underlying_quote": {"bid": 6.4, "volume": 1000, "oi": 400},
        "underlying_price": 6.5,
    }


def _build(*, options_source, trial_source=None, entry=6.5, catalyst=None, as_of=_AS_OF):
    factory = make_diligence_inputs(options_source=options_source, trial_source=trial_source)
    return factory(None, "ACME", catalyst or _catalyst(), entry=entry,
                   risk_inputs=_risk_inputs(), exit_by_date=_EXIT, pair=None, as_of=as_of)


def test_givenAllSources_buildsSourcedMoneyData():
    dd_input, md, degraded = _build(options_source=lambda t: _cboe_liquid())
    assert isinstance(dd_input, DiligenceInput)
    assert dd_input.ticker == "ACME" and dd_input.pair is None
    # sourced money dims present; degraded dims omitted (B1/C4)
    assert set(md) == {"options", "liquidity_quote", "hedge", "trial"}
    assert "financials" not in md and "ownership" not in md


def test_optionsFromCboe():
    _, md, _ = _build(options_source=lambda t: _cboe_liquid())
    q = md["options"]["quote"]
    assert q["call_bid"] == 0.5 and q["put_bid"] == 0.5 and q["expiry"] == "2026-09-19"
    assert q["catalyst_date"] == _EVENT                 # injected by us (B2 — provider omits it)
    assert md["options"]["underlying_price"] == 6.5     # == entry
    assert md["options"]["days_to_event"] == 3          # (event - as_of).days
    assert options_liquid(q, params=DILIGENCE_PARAMS) is True


def test_optionsDegradeToSentinel():
    # cboe["options_quote"] is None (illiquid: no live ATM pair) -> honest call_bid=0 sentinel.
    illiquid = {"options_quote": None, "underlying_quote": {"bid": 6.4, "volume": 10, "oi": 0},
                "underlying_price": 6.5}
    _, md, _ = _build(options_source=lambda t: illiquid)
    q = md["options"]["quote"]
    assert q["call_bid"] == 0 and q["put_bid"] == 0
    assert q["expiry"] == _EVENT and q["catalyst_date"] == _EVENT
    assert md["options"]["days_to_event"] == 3          # sentinel STILL carries days_to_event
    assert options_liquid(q, params=DILIGENCE_PARAMS) is False   # -> historical-gap fallback (grounded)

    # cboe fetch itself None (403/timeout) -> same honest sentinel.
    _, md2, _ = _build(options_source=lambda t: None)
    assert md2["options"]["quote"]["call_bid"] == 0
    assert options_liquid(md2["options"]["quote"], params=DILIGENCE_PARAMS) is False


def test_liquidityFromUnderlyingQuote():
    _, md, _ = _build(options_source=lambda t: _cboe_liquid())
    assert md["liquidity_quote"] == {"bid": 6.4, "volume": 1000, "oi": 400}
    # cboe None -> all-zero liquidity (conservative -> honest NO-GO, never fabricated liquidity).
    _, md2, _ = _build(options_source=lambda t: None)
    assert md2["liquidity_quote"] == {"bid": 0.0, "volume": 0.0, "oi": 0.0}


def test_noneBidCoercion_noTypeError():
    # C1: underlying_quote["bid"] can be None; coerce to 0 so zero_liquidity's `None <= 0` never raises.
    junk = {"options_quote": None, "underlying_quote": {"bid": None, "volume": None, "oi": 0},
            "underlying_price": 6.5}
    _, md, _ = _build(options_source=lambda t: junk)
    assert md["liquidity_quote"]["bid"] == 0.0
    assert zero_liquidity(md["liquidity_quote"]) is True    # would TypeError if bid stayed None


def test_hedgeReusesCatalystContext(db, embed):
    ri = _risk_inputs()
    _, md, _ = _build(options_source=lambda t: _cboe_liquid())
    assert md["hedge"] == {"entry": 6.5, "exit_by_date": _EXIT,
                           "analog_gaps": ri["analog_gaps"], "prices": ri["prices"]}
    # honest single-leg: feed the produced hedge dict to validate_hedge (pair=None) -> None (no fab).
    hedge = risk.validate_hedge(db, embed, "ACME", _catalyst(), md["hedge"]["entry"],
                                md["hedge"]["exit_by_date"], md["hedge"]["analog_gaps"],
                                md["hedge"]["prices"], candidate_peer=None)
    assert hedge is None


def test_financialsAlwaysOmitted_B1():
    # B1: edgar.fundamentals does NOT expose cash_usd/monthly_burn_usd/months_to_catalyst, so we OMIT
    # financials entirely (financials_context(None) -> None -> ungrounded -> forced NO-GO). Honest.
    _, md, degraded = _build(options_source=lambda t: _cboe_liquid())
    assert "financials" not in md
    assert any("financials" in f for f in degraded)


def test_ownershipAlwaysOmitted_C4():
    # C4: no insider_net source -> OMIT the WHOLE ownership key (a partial dict KeyErrors downstream),
    # append a degrade flag. Never a fabricated insider_net.
    _, md, degraded = _build(options_source=lambda t: _cboe_liquid())
    assert "ownership" not in md
    assert any("insider_net" in f for f in degraded)


def test_trialNonMoney_defaultsNone():
    _, md, _ = _build(options_source=lambda t: _cboe_liquid())
    assert md["trial"] is None                             # non-money; None is fine (no NO-GO)
    _, md2, _ = _build(options_source=lambda t: _cboe_liquid(),
                       trial_source=lambda t: {"phase": "3", "status": "completed"})
    assert md2["trial"] == {"phase": "3", "status": "completed"}


def test_daysToEvent_scopedToAsOf():
    # C3: options/edgar are now-snapshots (no serving.asof read), but days_to_event IS scoped to as_of.
    _, md, _ = _build(options_source=lambda t: _cboe_liquid(), as_of="2026-08-20")
    assert md["options"]["days_to_event"] == (date.fromisoformat(_EVENT) - date(2026, 8, 20)).days == 2
