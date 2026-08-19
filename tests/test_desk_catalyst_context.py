"""desk/catalyst_context.py (7.8-S1) — the live catalyst_context hook, offline TDD.

Fully offline: fake price source + fake analog source + fake base-rate proxy are injected; NO live
network, NO run_structured. The money-critical invariants under test:
  - the hook returns the EXACT {entry, risk_inputs} shape run_portfolio consumes, with all 6
    analog_gaps keys, p_loss = 1 - p_positive, gap = median analog DOWN move, target_up/down = the
    split analog magnitudes, prices.target = the close series;
  - NO analogs -> gap = abs(params hard_veto_drop) + target_up/down = the _NO_ANALOG_GAPS 0.0 default;
  - NO inverse peer -> the honest single-leg default (peer branches 0.0, prices.peer=[]) whose dict,
    fed to risk.validate_hedge, yields None (no fabricated hedge);
  - a degraded price source (None/[]) or a base-rate proxy that yields None -> entry=None honest skip,
    NEVER an exception, NEVER a fabricated p_loss;
  - no-look-ahead: the injected proxy/price/analog sources are read at the passed as_of, never future.
"""

from catalyst_trader import kb
from catalyst_trader.backtest.engine import _NO_ANALOG_GAPS
from catalyst_trader.desk import risk
from catalyst_trader.desk.catalyst_context import make_catalyst_context

_CATALYST = {"ticker": "ACME", "catalyst_type": "pdufa", "event_date": "2026-11-15",
             "catalyst_id": "ACME:2026-11-15"}
_AS_OF = "2026-11-10"


def _analogs(moves):
    return [{"outcome": {"move": m}} for m in moves]


def _price_source(closes):
    def _src(conn, ticker, as_of):
        return list(closes)
    return _src


def _analog_source(analogs):
    def _src(conn, ticker, catalyst, as_of):
        return list(analogs)
    return _src


def _proxy(side, p, ev):
    def _pf(ticker, as_of, conn, params):
        return side, p, ev
    return _pf


def _params():
    return kb.BOOTSTRAP_DEFAULT


async def test_givenFakeSourcesWithMixedAnalogs_whenAwaited_thenShapeAndValues():
    hook = make_catalyst_context(
        price_source=_price_source([10.0, 11.0, 12.0]),
        analog_source=_analog_source(_analogs([0.4, -0.2, 0.6, -0.3])),
        proxy_fn=_proxy("long", 0.6, 0.05),
        params=_params(),
    )
    out = await hook(None, "ACME", _CATALYST, _AS_OF)

    assert out["entry"] == 12.0                         # last close
    ri = out["risk_inputs"]
    assert set(ri) == {"p_loss", "gap", "analog_gaps", "prices"}
    assert abs(ri["p_loss"] - 0.4) < 1e-12             # 1 - p_positive
    assert abs(ri["gap"] - 0.25) < 1e-12               # median of down moves [0.2, 0.3]
    ag = ri["analog_gaps"]
    assert set(ag) == set(_NO_ANALOG_GAPS)             # ALL 6 keys, always
    assert abs(ag["target_up"] - 0.5) < 1e-12          # median up [0.4, 0.6]
    assert abs(ag["target_down"] - (-0.25)) < 1e-12    # -median down (negative branch)
    assert ri["prices"]["target"] == [10.0, 11.0, 12.0]
    assert ri["prices"]["peer"] == []


async def test_givenNoAnalogs_whenAwaited_thenGapFallsBackToHardVetoDrop():
    hook = make_catalyst_context(
        price_source=_price_source([9.0, 9.5]),
        analog_source=_analog_source([]),
        proxy_fn=_proxy("long", 0.55, 0.03),
        params=_params(),
    )
    out = await hook(None, "ACME", _CATALYST, _AS_OF)
    ri = out["risk_inputs"]
    assert abs(ri["gap"] - abs(_params()["weekly"]["hard_veto_drop"])) < 1e-12   # 0.15, no new const
    assert ri["analog_gaps"]["target_up"] == 0.0        # _NO_ANALOG_GAPS default
    assert ri["analog_gaps"]["target_down"] == 0.0


async def test_givenNoInversePeer_whenAwaited_thenSingleLegDefaultAndValidateHedgeNone(db, embed):
    hook = make_catalyst_context(
        price_source=_price_source([20.0, 21.0]),
        analog_source=_analog_source(_analogs([0.3, -0.1])),
        proxy_fn=_proxy("long", 0.6, 0.04),
        params=_params(),
    )
    out = await hook(db, "ACME", _CATALYST, _AS_OF)
    ag = out["risk_inputs"]["analog_gaps"]
    assert ag["peer_up"] == 0.0 and ag["peer_down"] == 0.0
    assert ag["w_peer"] == 0.0 and ag["w_target"] == 1.0
    assert out["risk_inputs"]["prices"]["peer"] == []
    # the honest single-leg default fed to validate_hedge yields None (no fabricated hedge)
    hedge = risk.validate_hedge(
        db, embed, "ACME", _CATALYST, out["entry"], "2026-11-17",
        ag, out["risk_inputs"]["prices"],
    )
    assert hedge is None


async def test_givenPriceSourceEmpty_whenAwaited_thenEntryNoneNoException():
    hook = make_catalyst_context(
        price_source=_price_source([]),
        analog_source=_analog_source(_analogs([0.3, -0.1])),
        proxy_fn=_proxy("long", 0.6, 0.04),
        params=_params(),
    )
    out = await hook(None, "ACME", _CATALYST, _AS_OF)
    assert out["entry"] is None                         # degrade: caller skips the leg


async def test_givenProxyYieldsNone_whenAwaited_thenEntryNoneHonestSkip():
    hook = make_catalyst_context(
        price_source=_price_source([10.0, 11.0]),
        analog_source=_analog_source(_analogs([0.3, -0.1])),
        proxy_fn=_proxy(None, None, None),             # no measured base-rate cell
        params=_params(),
    )
    out = await hook(None, "ACME", _CATALYST, _AS_OF)
    assert out["entry"] is None                         # never a fabricated p_loss = 1 - None


async def test_givenProxyRaises_whenAwaited_thenEntryNoneHonestSkip():
    def _raiser(ticker, as_of, conn, params):
        raise ValueError("no measured cell")

    hook = make_catalyst_context(
        price_source=_price_source([10.0, 11.0]),
        analog_source=_analog_source(_analogs([0.3, -0.1])),
        proxy_fn=_raiser,
        params=_params(),
    )
    out = await hook(None, "ACME", _CATALYST, _AS_OF)
    assert out["entry"] is None                         # ValueError/KeyError degrade, no raise


async def test_givenAsOf_whenAwaited_thenSourcesReadAtAsOfNoLookAhead():
    seen = {}

    def _price(conn, ticker, as_of):
        seen["price_as_of"] = as_of
        return [10.0]

    def _analog(conn, ticker, catalyst, as_of):
        seen["analog_as_of"] = as_of
        return []

    def _pf(ticker, as_of, conn, params):
        seen["proxy_as_of"] = as_of
        return "long", 0.6, 0.03

    hook = make_catalyst_context(price_source=_price, analog_source=_analog,
                                 proxy_fn=_pf, params=_params())
    await hook(None, "ACME", _CATALYST, _AS_OF)
    assert seen["price_as_of"] == _AS_OF                # never a future date
    assert seen["analog_as_of"] == _AS_OF
    assert seen["proxy_as_of"] == _AS_OF


async def test_givenLiveQuoteOverride_whenAwaited_thenEntryUsesQuoteElseClose():
    analogs = _analog_source(_analogs([0.2, -0.1]))
    # override present -> entry is the live quote
    hook = make_catalyst_context(price_source=_price_source([10.0, 11.0]), analog_source=analogs,
                                 proxy_fn=_proxy("long", 0.6, 0.03), params=_params(),
                                 quote_override=lambda tk: 15.0)
    out = await hook(None, "ACME", _CATALYST, _AS_OF)
    assert out["entry"] == 15.0
    # override degrades to None -> entry falls back to the cached close
    hook2 = make_catalyst_context(price_source=_price_source([10.0, 11.0]), analog_source=analogs,
                                  proxy_fn=_proxy("long", 0.6, 0.03), params=_params(),
                                  quote_override=lambda tk: None)
    out2 = await hook2(None, "ACME", _CATALYST, _AS_OF)
    assert out2["entry"] == 11.0
