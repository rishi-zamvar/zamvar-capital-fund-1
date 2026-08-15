"""Weekly universe-wide thesis engine (WEEK-02) — three deterministic frozen-ToolResult tools.

Fully offline against synthetic weekly bar series (no live FMP). Every threshold is read from
params["weekly"] (Plan 01); a missing weekly key must raise (no literal fallback in a tool body).
The money-critical invariants under test: sector-vs-idio split via correlation_beta, beta-binomial
shrinkage of thin per-name samples, the 4-part tradeability bar, and the -15% falling-knife veto.
"""

from datetime import date, timedelta

import pytest

from catalyst_trader import kb, store
from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    CatalystType,
    DatePrecision,
    SourceOrigin,
    SourceType,
    Status,
    Uncertainty,
)
from catalyst_trader.quant.weekly import classify_drop


# --- fixtures / builders ---------------------------------------------------------------------


def _bars(returns, *, start=1000.0, vol=2_000_000.0, first="2020-01-06", vols=None):
    """A weekly OHLCV series whose close-to-close returns are exactly `returns` (bar 0 = anchor)."""
    d = date.fromisoformat(first)
    v0 = vols[0] if vols else vol
    out = [{"week_end": d.isoformat(), "close": start, "volume": v0}]
    close = start
    for k, r in enumerate(returns):
        close *= 1.0 + r
        d += timedelta(days=7)
        out.append({"week_end": d.isoformat(), "close": close, "volume": (vols[k + 1] if vols else vol)})
    return out


def _osc(n, amp=0.02):
    """A non-constant XBI-style oscillation of length n (correlation_beta needs variance)."""
    return [amp if i % 2 == 0 else -amp for i in range(n)]


def _params(db, **overrides):
    """load_params('weekly') with per-key overrides; value None DELETES the key (missing-param tests)."""
    p = kb.load_params(db, "weekly")
    for k, v in overrides.items():
        if v is None:
            p["weekly"].pop(k, None)
        else:
            p["weekly"][k] = v
    return p


def _source(**over):
    base = dict(
        source_name="ClinicalTrials.gov",
        source_url="https://clinicaltrials.gov/study/NCT1",
        source_type=SourceType.primary,
        reported_date="2020-01-01",
        retrieved_at="2020-01-01T00:00:00Z",
    )
    base.update(over)
    return CatalystSource(**base)


def _verified_catalyst(ticker, event_date, ctype=CatalystType.trial_readout):
    return Catalyst(
        ticker=ticker,
        catalyst_type=ctype,
        event_date=event_date,
        date_precision=DatePrecision.day,
        uncertainty_type=Uncertainty.firm,
        status=Status.verified,
        source_origin=SourceOrigin.clinicaltrials_gov,
        sources=[_source()],
    )


# --- Task 1: classify_drop -------------------------------------------------------------------


def test_classify_drop_sector_vs_idio(db):
    # SECTOR: the name's move IS 1.5x XBI's move -> beta ~1.5, idio ~0 -> sector_beta.
    xbi_ret = [0.02, -0.03, 0.01, -0.04, 0.02, -0.03, 0.02, -0.04]
    store.upsert_bars(db, "XBI", _bars(xbi_ret))
    store.upsert_bars(db, "SECT", _bars([1.5 * r for r in xbi_ret]))
    we = _bars(xbi_ret)[-1]["week_end"]
    r = classify_drop("SECT", we, store, db, params=_params(db))
    assert r.tool == "classify_drop" and r.value is None
    assert r.detail["drop_class"] == "sector_beta"
    assert r.detail["beta"] == pytest.approx(1.5, abs=0.05)

    # IDIO: XBI's LAST return is ~0 so the name's drop is purely idiosyncratic, no catalyst.
    xbi2 = [0.02, -0.02, 0.03, -0.03, 0.01, -0.01, 0.02, 0.0]
    tgt2 = [0.04, -0.08, 0.06, -0.08, 0.03, -0.07, 0.05, -0.08]
    store.upsert_bars(db, "XBI", _bars(xbi2))
    store.upsert_bars(db, "IDIO", _bars(tgt2))
    we2 = _bars(tgt2)[-1]["week_end"]
    r2 = classify_drop("IDIO", we2, store, db, params=_params(db))
    assert r2.detail["drop_class"] == "idio_no_news"
    assert r2.detail["news_hits"] == []


def test_classify_drop_news_gate_busted_and_positive(db):
    xbi = [0.02, -0.02, 0.03, -0.03, 0.01, -0.01, 0.02, 0.0]  # last ~0 -> idio-dominated
    store.upsert_bars(db, "XBI", _bars(xbi))
    down = _bars([0.04, -0.08, 0.06, -0.08, 0.03, -0.07, 0.05, -0.08])
    store.upsert_bars(db, "BUST", down)
    we = down[-1]["week_end"]
    prev = down[-2]["week_end"]
    mid = (date.fromisoformat(prev) + timedelta(days=3)).isoformat()  # inside the drop week
    store.insert_catalyst(db, _verified_catalyst("BUST", mid))
    r = classify_drop("BUST", we, store, db, params=_params(db))
    assert r.detail["drop_class"] == "busted_catalyst"
    assert r.detail["news_hits"] and r.detail["news_hits"][0]["event_date"] == mid

    up = _bars([0.04, -0.08, 0.06, -0.08, 0.03, -0.07, 0.05, 0.08])  # last week UP
    store.upsert_bars(db, "POS", up)
    we2 = up[-1]["week_end"]
    prev2 = up[-2]["week_end"]
    mid2 = (date.fromisoformat(prev2) + timedelta(days=3)).isoformat()
    store.insert_catalyst(db, _verified_catalyst("POS", mid2))
    r2 = classify_drop("POS", we2, store, db, params=_params(db))
    assert r2.detail["drop_class"] == "positive_catalyst"


def test_classify_drop_turnover_flag_vs_trailing_median(db):
    store.upsert_bars(db, "XBI", _bars(_osc(8)))
    rets = [0.01, -0.06, 0.02, -0.06, 0.01, -0.06, 0.02, -0.06]
    base_vols = [1_000_000.0] * 8 + [1_000_000.0]
    # HIGH: last-week volume far above the trailing median.
    hi = list(base_vols)
    hi[-1] = 9_000_000.0
    store.upsert_bars(db, "THI", _bars(rets, vols=hi))
    we = _bars(rets)[-1]["week_end"]
    assert classify_drop("THI", we, store, db, params=_params(db)).detail["turnover_flag"] == "high"
    # LOW: last-week volume at/below the trailing median.
    lo = list(base_vols)
    lo[-1] = 1_000_000.0
    store.upsert_bars(db, "TLO", _bars(rets, vols=lo))
    assert classify_drop("TLO", we, store, db, params=_params(db)).detail["turnover_flag"] == "low"


def test_classify_drop_missing_weekly_param_raises(db):
    store.upsert_bars(db, "XBI", _bars(_osc(8)))
    store.upsert_bars(db, "NAME", _bars([0.01, -0.06, 0.02, -0.06, 0.01, -0.06, 0.02, -0.06]))
    we = _bars(_osc(8))[-1]["week_end"]
    with pytest.raises(KeyError):
        classify_drop("NAME", we, store, db, params=_params(db, beta_window_weeks=None))
