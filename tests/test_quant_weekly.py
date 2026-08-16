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
from catalyst_trader.quant.weekly import classify_drop, thesis_scan, weekly_base_rate


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


# --- Task 2: weekly_base_rate ----------------------------------------------------------------


def _rep(pattern, times):
    return pattern * times


def test_weekly_base_rate_shrinks_thin_n(db):
    # THIN: only 5 drop events, every one bounces -> raw p = 1.0 (must NOT be quoted raw).
    store.upsert_bars(db, "THIN", _bars(_rep([-0.06, 0.03], 5)))
    # cohort filler: 2 drops/cycle, one bounces one doesn't -> parent rate ~0.5.
    store.upsert_bars(db, "FILL", _bars(_rep([-0.06, 0.03, -0.06, -0.02], 12)))
    as_of = "2099-01-01"  # far-future: score full point-in-time history for both name + cohort
    r = weekly_base_rate("THIN", "drop_le_-0.05", "idio_no_news", None, as_of, store, db,
                         params=_params(db))
    d = r.detail
    assert d["n_name"] == 5 and d["p_raw"] == pytest.approx(1.0)
    assert d["cohort_level"] == "universe" and d["p_cohort"] == pytest.approx(0.5, abs=0.05)
    # shrunk sits STRICTLY between the raw per-name rate and the parent cohort.
    assert d["p_cohort"] < d["p_shrunk"] < d["p_raw"]
    assert r.value == pytest.approx(d["p_shrunk"])
    assert d["shrink_prior_weight"] == 30 and d["shrunk"] is True


def test_weekly_base_rate_ample_n_prior_washes_out(db):
    store.upsert_bars(db, "AMPLE", _bars(_rep([-0.06, 0.03], 600)))
    store.upsert_bars(db, "FILL", _bars(_rep([-0.06, 0.03, -0.06, -0.02], 12)))
    as_of = "2099-01-01"
    r = weekly_base_rate("AMPLE", "drop_le_-0.05", "idio_no_news", None, as_of, store, db,
                         params=_params(db), window_years=100)
    d = r.detail
    assert d["n_name"] >= 500 and d["shrunk"] is False
    assert abs(d["p_shrunk"] - d["p_raw"]) < 0.05  # prior negligible at ample n


def test_weekly_base_rate_anchor_equals_execution_anchor(db):
    store.upsert_bars(db, "AN", _bars(_rep([-0.06, 0.03], 5)))
    as_of = "2099-01-01"  # far-future: score full point-in-time history for both name + cohort
    r = weekly_base_rate("AN", "drop_le_-0.05", "idio_no_news", None, as_of, store, db,
                         params=_params(db))
    assert r.detail["anchor"] == "MON_OPEN"  # the default execution anchor
    # the SAME single anchor param drives the measurement window (the trap): change it -> flows through.
    r2 = weekly_base_rate("AN", "drop_le_-0.05", "idio_no_news", None, as_of, store, db,
                          params=_params(db, anchor="FRI_CLOSE"))
    assert r2.detail["anchor"] == "FRI_CLOSE"


def test_weekly_base_rate_missing_param_and_unknown_trigger_raise(db):
    store.upsert_bars(db, "NM", _bars(_rep([-0.06, 0.03], 5)))
    as_of = "2099-01-01"  # far-future: score full point-in-time history for both name + cohort
    with pytest.raises(KeyError):
        weekly_base_rate("NM", "drop_le_-0.05", "idio_no_news", None, as_of, store, db,
                         params=_params(db, shrink_prior_weight=None))
    with pytest.raises(ValueError):
        weekly_base_rate("NM", "drop_le_-0.99", "idio_no_news", None, as_of, store, db,
                         params=_params(db))


# --- Task 3: thesis_scan ---------------------------------------------------------------------


def _rows_by_ticker(result):
    return {x["ticker"]: x for x in result.detail["rows"]}


def test_thesis_scan_eligibility_bar(db):
    # ELIG: a -6% drop with a strong, deep, positive-mean bounce history -> passes ALL 4 gates.
    store.upsert_bars(db, "XBI", _bars(_osc(120)))
    store.upsert_bars(db, "ELIG", _bars(_rep([0.03, -0.06], 60)))
    we = _bars(_rep([0.03, -0.06], 60))[-1]["week_end"]
    row = _rows_by_ticker(thesis_scan(["ELIG"], we, store, db, params=_params(db)))["ELIG"]
    assert row["eligible"] is True and row["veto_reasons"] == []
    assert row["thesis_type"] == "mean_reversion"
    assert row["n_effective"] >= 30 and row["trigger"] == "drop_le_-0.05"


def test_thesis_scan_15pct_hard_veto(db):
    # KNIFE: a -16% week with a PERFECT bounce history is STILL never eligible (falling-knife veto).
    store.upsert_bars(db, "XBI", _bars(_osc(80)))
    store.upsert_bars(db, "KNIFE", _bars(_rep([0.10, -0.16], 40)))
    we = _bars(_rep([0.10, -0.16], 40))[-1]["week_end"]
    row = _rows_by_ticker(thesis_scan(["KNIFE"], we, store, db, params=_params(db)))["KNIFE"]
    assert row["eligible"] is False
    assert "hard_veto_drop" in row["veto_reasons"]


def test_thesis_scan_row_for_every_name_including_no_edge(db):
    store.upsert_bars(db, "XBI", _bars(_osc(120)))
    store.upsert_bars(db, "ELIG", _bars(_rep([0.03, -0.06], 60)))
    store.upsert_bars(db, "FLAT", _bars(_osc(120, amp=0.01)))  # never triggers a cell
    we = _bars(_rep([0.03, -0.06], 60))[-1]["week_end"]
    rows = _rows_by_ticker(thesis_scan(["ELIG", "FLAT"], we, store, db, params=_params(db)))
    assert set(rows) == {"ELIG", "FLAT"}  # WEEK-02: a row for EVERY name every week
    assert rows["FLAT"]["trigger"] is None and rows["FLAT"]["eligible"] is False
    assert "no_trigger" in rows["FLAT"]["veto_reasons"]  # a valid 'no measured edge' read


def test_thesis_scan_catalyst_precedence(db):
    # a name with a tradeable catalyst INSIDE the hold window is a catalyst row (Workflow-1 preempts).
    store.upsert_bars(db, "XBI", _bars(_osc(40)))
    store.upsert_bars(db, "CAT", _bars(_rep([0.03, -0.06], 20)))
    we = _bars(_rep([0.03, -0.06], 20))[-1]["week_end"]
    fut = (date.fromisoformat(we) + timedelta(days=3)).isoformat()  # inside the upcoming hold week
    store.insert_catalyst(db, _verified_catalyst("CAT", fut))
    row = _rows_by_ticker(thesis_scan(["CAT"], we, store, db, params=_params(db)))["CAT"]
    assert row["thesis_type"] == "catalyst"
    assert "catalyst_precedence" in row["veto_reasons"]


# --- cohort caching: behaviour-preserving equivalence (O(U^2) -> O(U)) -----------------------


def _cohort_events_ref(store_mod, kb_conn, target, as_of, lookback, op, thr):
    """Reference (pre-refactor) cohort pool: rescan every ticker != target. The cached
    total-minus-target path must return byte-identical counts to this."""
    from catalyst_trader.quant.weekly import _trigger_hit, _weekly_returns
    rows = kb_conn.execute(
        "SELECT DISTINCT ticker FROM price_bar WHERE ticker != ?", (target,)
    ).fetchall()
    up = n = 0
    for r in rows:
        rets = _weekly_returns(store_mod.bars_asof(kb_conn, r[0], as_of, lookback_weeks=lookback))
        for i in range(len(rets) - 1):
            if _trigger_hit(rets[i], op, thr):
                n += 1
                if rets[i + 1] > 0:
                    up += 1
    return up, n


def _seed_cohort_universe(db):
    """A varied multi-ticker universe (all five trigger cells exercised) + XBI."""
    store.upsert_bars(db, "XBI", _bars(_osc(160)))
    patterns = {
        "AAA": _rep([0.03, -0.06], 70),
        "BBB": _rep([-0.06, 0.03, -0.06, -0.02], 40),
        "CCC": _rep([0.10, -0.16], 50),
        "DDD": _rep([0.07, -0.11, 0.02, -0.03], 40),
        "EEE": _osc(160, amp=0.01),
        "FFF": _rep([-0.06, 0.03], 80),
        "GGG": _rep([0.06, -0.12, 0.03, -0.07], 35),
        "HHH": _rep([0.03, -0.06, 0.03, 0.03], 40),
    }
    for tk, p in patterns.items():
        store.upsert_bars(db, tk, _bars(p))
    db.commit()
    return list(patterns.keys())


def test_cohort_events_cache_matches_full_rescan(db):
    """The cached total-minus-target pool == the per-target rescan for every ticker x trigger,
    including a ticker with no bars (subtracting a (0,0) contribution)."""
    from catalyst_trader.quant.weekly import _TRIGGERS, _cohort_events
    universe = _seed_cohort_universe(db)
    as_of = _bars(_rep([0.03, -0.06], 70))[-1]["week_end"]
    lookback = kb.load_params(db, "weekly")["weekly"]["window_years"] * 52
    cache: dict = {}
    for tk in universe + ["ZZZ_NO_BARS"]:
        for _trig, (op, thr) in _TRIGGERS.items():
            ref = _cohort_events_ref(store, db, tk, as_of, lookback, op, thr)
            cached = _cohort_events(store, db, tk, as_of, lookback, op, thr, cache=cache)
            uncached = _cohort_events(store, db, tk, as_of, lookback, op, thr)
            assert cached == ref  # cache path identical to full rescan
            assert uncached == ref  # no-cache path identical to full rescan


def test_thesis_scan_identical_with_and_without_shared_cache(db):
    """thesis_scan (shared cohort cache) == per-name scans with no shared cache — byte-for-byte."""
    universe = _seed_cohort_universe(db)
    we = _bars(_rep([0.03, -0.06], 70))[-1]["week_end"]
    params = _params(db)
    shared = thesis_scan(universe, we, store, db, params=params).detail["rows"]
    per_name = [thesis_scan([tk], we, store, db, params=params).detail["rows"][0] for tk in universe]
    assert shared == per_name
