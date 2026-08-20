"""tests/test_desk_research_bundle.py (07.9-1.5) — the Catalyst Research Bundle substrate.

ONE deterministic research pass that computes every cited FACT once per catalyst, then hands the
identical ground truth to every consumer. Two invariants are TESTED here, not review notes:

  FIREWALL   the bundle carries FACTS ONLY — no interpretation field (score/thesis/verdict/dossier);
             a leaked interpretation is a type error (extra='forbid'), not a policy check.
  FRUGALITY  each free/cited source is invoked EXACTLY ONCE per catalyst (call-count spies).

Plus: honest-degrade (missing/raise -> null + flag, never fabricated), point-in-time (serving.asof
cutoff threaded), and cite-or-drop (every populated Fact carries a resolvable ref or inline citation).
All offline: fake injected sources, no network / EDGAR / FINRA / CBOE / LLM / real embedder.
"""

import pytest
from pydantic import ValidationError

from catalyst_trader.contracts import CatalystResearchBundle, Fact
from catalyst_trader.desk import evidence

_AS_OF = "2026-08-19"
_EVENT = "2026-08-22"


def _catalyst(ticker="ACME"):
    return {"ticker": ticker, "catalyst_type": "pdufa", "event_date": _EVENT,
            "catalyst_id": f"{ticker}:{_EVENT}", "phase": "III", "indication": "oncology"}


# ============================== Task 1 — contract + firewall =============================

# The interpretation vocabulary the substrate must NEVER carry (the firewall line, at the type level).
_INTERPRETATION_FIELDS = {"score", "confidence", "thesis", "verdict", "dossier", "recommendation",
                          "decision", "key_findings", "direction"}


def test_bundle_is_facts_only_no_interpretation_fields():
    leaked = _INTERPRETATION_FIELDS & set(CatalystResearchBundle.model_fields)
    assert leaked == set(), f"bundle leaked interpretation field(s): {leaked}"


def test_bundle_forbids_extra():
    # A stray interpretation field is rejected by the type (extra='forbid'), not by a policy pass.
    with pytest.raises(ValidationError):
        CatalystResearchBundle(ticker="ACME", catalyst=_catalyst(), score=0.7)


def test_bundle_facts_default_null():
    # An empty bundle validates with every fact value defaulting to None (an empty slot is a finding).
    b = CatalystResearchBundle(ticker="ACME", catalyst=_catalyst())
    for name in ("analogs", "financials", "trial", "options", "implied_move",
                 "ownership", "prices", "hedge_inputs"):
        assert getattr(b, name).value is None
    assert b.base_rates == [] and b.degraded == []


def test_fact_carries_ref():
    # tool-ref citation, inline citation, and empty are all valid...
    Fact(value=1.0, evidence_ref="tool:implied_move#abc123")
    Fact(value=0.089, citation={"source_name": "BIO", "source_url": "http://x", "quote": "q"})
    Fact()  # value None -> no citation required (an empty slot is honest)
    # ...but a POPULATED value with neither a ref nor a citation is REJECTED (cite-or-drop).
    with pytest.raises(ValidationError):
        Fact(value=1.0)


# ============================== Task 2 — build_research_bundle ============================

from catalyst_trader.desk.research_bundle import build_research_bundle  # noqa: E402


class _Spy:
    """Wrap a source fn, count calls, record args."""

    def __init__(self, fn):
        self._fn = fn
        self.calls = 0
        self.seen = []

    def __call__(self, *a, **kw):
        self.calls += 1
        self.seen.append((a, kw))
        return self._fn(*a, **kw)


def _analogs():
    return [{"outcome": {"move": 0.2}}, {"outcome": {"move": -0.3}}, {"outcome": {"move": 0.1}}]


def _base_rate(metric, phase=None, indication=None):
    return {"value": 0.575, "source_name": "IB guide", "source_url": "http://x",
            "quote": f"{metric} prior"}


def _fund():
    return {"shares_outstanding": 65_000_000.0, "cash_usd": 3.0e8, "monthly_burn_usd": 1.5e7,
            "cash_runway_months": 20.0, "provenance": {}}


def _cboe():
    return {"options_quote": {"call_bid": 0.5, "call_ask": 0.6, "put_bid": 0.5, "put_ask": 0.6,
                              "call_oi": 200, "put_oi": 200, "expiry": "2026-09-19"},
            "underlying_quote": {"bid": 6.4, "volume": 1000, "oi": 400}, "underlying_price": 6.5}


def _finra():
    return {"short_interest": 6_500_000, "days_to_cover": 4.2, "si_settlement_date": "2026-07-31"}


def _sources(**over):
    """The full offline injected-source kit (each replaceable via **over)."""
    src = {
        "analog_source": lambda conn, t, c, a: _analogs(),
        "base_rate_source": _base_rate,
        "financials_source": lambda t: _fund(),
        "trial_source": lambda t: {"phase": "3", "status": "completed"},
        "options_source": lambda t: _cboe(),
        "finra_source": lambda t: _finra(),
        "insider_source": lambda t, since, until: -2000.0,
        "price_source": lambda conn, t, a: [6.4, 6.5, 6.6],
    }
    src.update(over)
    return src


def _build(**over):
    return build_research_bundle(None, "ACME", _catalyst(), _AS_OF, cutoff=_AS_OF, **_sources(**over))


def test_computed_once():
    # FRUGALITY: wrap each source in a call-count spy; every source hit EXACTLY once (base_rate once
    # per DISTINCT metric — never the same metric twice; the single fundamentals fetch serves BOTH
    # financials cash/burn AND ownership shares).
    spies = {k: _Spy(v) for k, v in _sources().items()}
    build_research_bundle(None, "ACME", _catalyst(), _AS_OF, cutoff=_AS_OF, **spies)
    for name in ("analog_source", "financials_source", "options_source", "finra_source",
                 "insider_source", "price_source"):
        assert spies[name].calls == 1, f"{name} called {spies[name].calls}x (want 1)"
    metrics = [a[0] for (a, kw) in spies["base_rate_source"].seen]
    assert len(metrics) == len(set(metrics)), f"a base-rate metric was fetched twice: {metrics}"


def test_every_populated_fact_has_resolvable_ref():
    b = _build()
    single = [b.analogs, b.financials, b.trial, b.options, b.implied_move, b.ownership,
              b.prices, b.hedge_inputs]
    for f in single + b.base_rates:
        if f.value is None:
            continue
        if f.evidence_ref is not None:
            assert evidence.resolve(None, f.evidence_ref) is not None
        else:
            assert {"source_name", "source_url", "quote"} <= set(f.citation or {})


def test_honest_degrade_missing_source():
    # A missing financials source (and finra) yields NULL facts + degrade flags — NEVER a fabricated
    # number (not 0, not a guess): the value is honestly None.
    b = _build(financials_source=lambda t: None, finra_source=lambda t: None)
    assert b.financials.value is None
    assert b.ownership.value is None
    assert any("financials" in f for f in b.degraded)
    assert any("ownership" in f for f in b.degraded)


def test_insider_zero_grounds():
    # insider_net == 0.0 (a quiet tape) is a REAL datum -> ownership GROUNDS (not a degrade).
    b = _build(insider_source=lambda t, since, until: 0.0)
    assert b.ownership.value is not None
    assert b.ownership.value["insider_net"] == 0.0
    assert not any("ownership" in f for f in b.degraded)


def test_point_in_time():
    # The point-in-time as_of is threaded into the price source (no future read leaks into prices).
    seen = {}

    def _price(conn, t, a):
        seen["as_of"] = a
        return [6.4, 6.5, 6.6]

    b = _build(price_source=_price)
    assert seen["as_of"] == _AS_OF
    assert b.prices.value["target"] == [6.4, 6.5, 6.6]


def test_point_in_time_default_no_lookahead(db, embed):
    # The DEFAULT price source runs through serving.asof(conn, cutoff): an empty as-of db yields an
    # honest degrade (no crash, no LookAheadDenied for a knowable as_of).
    b = build_research_bundle(db, "ACME", _catalyst(), _AS_OF, cutoff=_AS_OF, embed=embed,
                              facts={"prices"})
    assert b.prices.value is None
    assert any("prices" in f for f in b.degraded)


def test_facts_only_output():
    b = _build()
    assert isinstance(b, CatalystResearchBundle)
    for leaked in _INTERPRETATION_FIELDS:
        assert not hasattr(b, leaked) or leaked not in type(b).model_fields

