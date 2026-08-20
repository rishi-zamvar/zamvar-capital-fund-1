"""tests/test_desk_diligence_inputs.py (7.8-S2 + S2.5) — the (DiligenceInput, market_data) binding.

Every money field is either honestly SOURCED (options/liquidity/hedge/financials/ownership) or
honestly DEGRADED (omit the key + flag -> the ungrounded -> NO-GO path, never a fabricated number).
All offline: fake sources, no CBOE/EDGAR/FINRA/network, no LLM.

Corrected-contract coverage (plan-checker overrides, verified against code):
  B2  options seam is nested + nullable: read cboe["options_quote"], None -> honest sentinel; inject
      catalyst_date=event_date; every options structure carries days_to_event.
  C1  underlying_quote["bid"] can be None -> coerce to 0 (zero_liquidity's .get default never fires).
  S2.5 financials is SOURCED from edgar.fundamentals {cash_usd, monthly_burn_usd} + months_to_catalyst,
      OMITTED + flagged when a fact is missing (was B1's unconditional omit).
  S2.5 ownership is SOURCED from FINRA + shares_outstanding + Form-4 insider_net as a WHOLE dict, or
      OMITTED + flagged (never a partial dict -> diligence.py:269 KeyError) (was C4's unconditional omit).
"""

from datetime import date, timedelta

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


def _fund(cash_usd=300_000_000.0, monthly_burn_usd=15_000_000.0, shares=65_000_000.0):
    """A fake edgar.fundamentals payload (the single fetch reused for financials + ownership shares)."""
    return {"shares_outstanding": shares, "cash_usd": cash_usd,
            "monthly_burn_usd": monthly_burn_usd, "cash_runway_months": 20.0, "provenance": {}}


def _finra_ok(short_interest=6_500_000, days_to_cover=4.2):
    return {"short_interest": short_interest, "days_to_cover": days_to_cover,
            "si_settlement_date": "2026-07-31"}


def _build(*, options_source, trial_source=None, financials_source=None, finra_source=None,
           insider_source=None, entry=6.5, catalyst=None, as_of=_AS_OF):
    # Money-dim sources default to OFFLINE fakes so every test stays network-free.
    factory = make_diligence_inputs(
        options_source=options_source, trial_source=trial_source,
        financials_source=financials_source or (lambda t: _fund()),
        finra_source=finra_source or (lambda t: _finra_ok()),
        insider_source=insider_source or (lambda t, since, until: -2000.0),
    )
    return factory(None, "ACME", catalyst or _catalyst(), entry=entry,
                   risk_inputs=_risk_inputs(), exit_by_date=_EXIT, pair=None, as_of=as_of)


def test_givenAllSources_buildsSourcedMoneyData():
    dd_input, md, degraded = _build(options_source=lambda t: _cboe_liquid())
    assert isinstance(dd_input, DiligenceInput)
    assert dd_input.ticker == "ACME" and dd_input.pair is None
    # S2.5: ALL money dims now grounded when every source lands -> no degrade flags.
    assert set(md) == {"options", "liquidity_quote", "hedge", "trial", "financials", "ownership"}
    assert degraded == []


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


def test_financialsSourced_whenFactsPresent():
    # S2.5: cash_usd + monthly_burn_usd from fundamentals + months_to_catalyst from (event - as_of).
    _, md, degraded = _build(options_source=lambda t: _cboe_liquid())
    assert md["financials"] == {"cash_usd": 300_000_000.0, "monthly_burn_usd": 15_000_000.0,
                                "months_to_catalyst": round(3 / 30.4375, 2)}
    assert not any("financials" in f for f in degraded)


def test_financialsOmitted_whenNotBurning():
    # monthly_burn_usd None (company not burning) -> ungrounded -> omit + flag (honest NO-GO).
    fund = _fund(monthly_burn_usd=None)
    _, md, degraded = _build(options_source=lambda t: _cboe_liquid(), financials_source=lambda t: fund)
    assert "financials" not in md
    assert any("financials" in f for f in degraded)


def test_financialsOmitted_whenFundamentalsNone():
    _, md, degraded = _build(options_source=lambda t: _cboe_liquid(), financials_source=lambda t: None)
    assert "financials" not in md
    assert any("financials" in f for f in degraded)


def test_ownershipSourced_fullDict():
    # S2.5: FINRA + shares + insider_net all present -> the WHOLE {si_pct, dtc, insider_net} dict.
    _, md, degraded = _build(options_source=lambda t: _cboe_liquid())
    assert md["ownership"] == {"short_interest_pct": 6_500_000 / 65_000_000,
                               "days_to_cover": 4.2, "insider_net": -2000.0}
    assert not any("ownership" in f for f in degraded)


def test_ownershipGrounds_onQuietInsiderTape():
    # insider_net == 0.0 (quiet tape) is a REAL datum (`is not None`) -> ownership STILL grounds.
    _, md, degraded = _build(options_source=lambda t: _cboe_liquid(),
                             insider_source=lambda t, since, until: 0.0)
    assert md["ownership"]["insider_net"] == 0.0
    assert "ownership" in md and not any("ownership" in f for f in degraded)


def test_ownershipOmitted_onAnyMiss_neverPartial():
    # A single missing leg OMITS the WHOLE key (a partial dict KeyErrors at diligence.py:269).
    _, md_f, deg_f = _build(options_source=lambda t: _cboe_liquid(), finra_source=lambda t: None)
    assert "ownership" not in md_f and any("ownership" in f for f in deg_f)

    _, md_s, _ = _build(options_source=lambda t: _cboe_liquid(),
                        financials_source=lambda t: _fund(shares=None))
    assert "ownership" not in md_s  # shares_outstanding missing

    _, md_i, _ = _build(options_source=lambda t: _cboe_liquid(),
                        insider_source=lambda t, since, until: None)
    assert "ownership" not in md_i  # insider_net genuine miss (None, not 0.0)


def test_ownershipInsiderWindow_scopedToParams():
    # since/until passed to insider_source = [as_of - form4_lookback_days, as_of].
    seen = {}
    _build(options_source=lambda t: _cboe_liquid(),
           insider_source=lambda t, since, until: seen.update(since=since, until=until) or -1.0)
    assert seen["until"] == _AS_OF
    assert seen["since"] == (date.fromisoformat(_AS_OF) - timedelta(days=90)).isoformat()


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


# ============================== Task 3 — DD sources FROM the research bundle ==============

from catalyst_trader.contracts import CatalystResearchBundle, Fact  # noqa: E402


def test_diligence_inputs_reads_bundle():
    # DD maps bundle FACTS -> the SAME market_data shape (byte-compatible DD contract).
    def _fake_bundle(conn, ticker, catalyst, as_of, **kw):
        return CatalystResearchBundle(
            ticker=ticker, catalyst=catalyst, as_of=as_of,
            options=Fact(value=_cboe_liquid(), evidence_ref="tool:options_cboe#x"),
            financials=Fact(value=_fund(), evidence_ref="tool:fundamentals#x"),
            ownership=Fact(value={"short_interest_pct": 0.1, "days_to_cover": 4.2,
                                  "insider_net": -2000.0}, evidence_ref="tool:short_interest#x"),
            trial=Fact(), degraded=[])

    factory = make_diligence_inputs(bundle_fn=_fake_bundle)
    _, md, degraded = factory(None, "ACME", _catalyst(), entry=6.5, risk_inputs=_risk_inputs(),
                              exit_by_date=_EXIT, pair=None, as_of=_AS_OF)
    assert set(md) == {"options", "liquidity_quote", "hedge", "trial", "financials", "ownership"}
    assert md["ownership"] == {"short_interest_pct": 0.1, "days_to_cover": 4.2, "insider_net": -2000.0}
    assert md["financials"]["cash_usd"] == 300_000_000.0
    assert md["options"]["quote"]["call_bid"] == 0.5 and md["liquidity_quote"]["bid"] == 6.4
    assert degraded == []


def test_no_double_sourcing():
    # The frugality win at the DD seam: each source is hit ONCE (via the bundle), never re-fetched.
    calls = {"options": 0, "financials": 0, "finra": 0, "insider": 0}

    def opt(t): calls.__setitem__("options", calls["options"] + 1); return _cboe_liquid()
    def fin(t): calls.__setitem__("financials", calls["financials"] + 1); return _fund()
    def fnr(t): calls.__setitem__("finra", calls["finra"] + 1); return _finra_ok()
    def ins(t, s, u): calls.__setitem__("insider", calls["insider"] + 1); return -2000.0

    factory = make_diligence_inputs(options_source=opt, financials_source=fin, finra_source=fnr,
                                    insider_source=ins, trial_source=lambda t: None)
    factory(None, "ACME", _catalyst(), entry=6.5, risk_inputs=_risk_inputs(),
            exit_by_date=_EXIT, pair=None, as_of=_AS_OF)
    assert calls == {"options": 1, "financials": 1, "finra": 1, "insider": 1}
