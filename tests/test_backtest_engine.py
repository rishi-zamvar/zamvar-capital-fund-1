"""BACK-02: Layer A — the mechanical, NO-LLM backtest of the CORRECTED strategy.

Money-honesty invariants under test:
  - Layer A NEVER calls the LLM desk (grep-gate on the source + a monkeypatch-to-raise test).
  - the catalyst-leg DIRECTION is a base-rate P(positive) proxy COMPUTED via
    classify_drop -> _match_trigger -> weekly_base_rate (BLOCKER-2: never read off the
    null-bearing catalyst thesis row), exposed as a named swappable knob (default base_rate).
  - catalyst legs flow from the 07-02 last_verified_at-filtered event set (verification
    look-ahead impossible at the engine level).
  - held-through binaries fill at the pessimistic gap-open far side; no zero-trade weeks.
  - the baseline distribution reports win_rate / avg win-loss / Sharpe / Sortino / max-DD /
    hedge-effectiveness.

Fully offline: every test seeds through tests/synth_history.py::seed_history.
"""

import numpy as np
import pytest
from pydantic import ValidationError

from catalyst_trader import db as _db
from catalyst_trader.backtest.engine import (
    DIRECTION_PROXIES,
    BacktestResult,
    BaselineDistribution,
    LegOutcome,
    baseline_distribution,
    resolve_direction_proxy,
    run_layer_a,
)
from catalyst_trader.quant import weekly as qw
from catalyst_trader.store import upsert_bars

from tests.synth_history import seed_history, week_ends


# --------------------------------------------------------------------------- helpers


class _R:
    """A stand-in ToolResult (only .detail / .value) for monkeypatched quant tools."""

    def __init__(self, detail=None, value=None):
        self.detail = detail or {}
        self.value = value


def _conn():
    conn = _db.connect(":memory:")
    _db.migrate(conn)
    return conn


def _leg(**over):
    base = dict(ticker="ABCD", side="long", entry=10.0, fill=10.2, exit="2024-02-01",
                realized_ret=0.02, held_through=False, is_catalyst=False, hedge_ret=None,
                p=0.6, size_pct=0.02)
    base.update(over)
    return LegOutcome(**base)


def _dist(**over):
    base = dict(win_rate=0.5, avg_win=0.02, avg_loss=0.01, sharpe=1.0, sortino=1.2,
                max_drawdown=-0.05, hedge_effectiveness=None, n_trades=4, n_weeks=2)
    base.update(over)
    return base


# ============================== Task 1: contracts + the direction_proxy knob ==========


def test_baseline_distribution_contract_forbids_extra():
    BaselineDistribution(**_dist())  # a valid distribution constructs
    with pytest.raises(ValidationError):
        BaselineDistribution(**_dist(), stray=1)  # a stray field is rejected (extra=forbid)
    with pytest.raises(ValidationError):
        BacktestResult(week="2024-02-01", legs=[_leg()], stray=1)


def test_direction_proxy_registry_swappable():
    assert set(DIRECTION_PROXIES) >= {"base_rate", "long_runup"}
    assert resolve_direction_proxy() is DIRECTION_PROXIES["base_rate"]        # default = base_rate
    assert resolve_direction_proxy("long_runup") is DIRECTION_PROXIES["long_runup"]
    with pytest.raises(ValueError):
        resolve_direction_proxy("nope")


def test_direction_proxy_base_rate_computes_via_classify_drop_and_weekly_base_rate(monkeypatch):
    calls = []

    def fake_classify(ticker, as_of, store, conn, *, params):
        calls.append("classify_drop")
        return _R(detail={"ret": -0.06, "drop_class": "idio_no_news", "turnover_flag": "low"})

    def fake_base_rate(ticker, trigger, drop_class, turnover, as_of, store, conn, *, params,
                       window_years=None):
        calls.append(("weekly_base_rate", trigger, drop_class, turnover))
        return _R(value=0.73, detail={"mean_next": 0.03})

    monkeypatch.setattr(qw, "classify_drop", fake_classify)
    monkeypatch.setattr(qw, "weekly_base_rate", fake_base_rate)

    side, p = resolve_direction_proxy("base_rate")("ABCD", "2024-02-01", None, object(),
                                                   params={"weekly": {}})
    assert side == "long"
    assert p == 0.73                                     # the COMPUTED base rate, passed through
    assert "classify_drop" in calls
    # trigger was DERIVED via _match_trigger(ret=-0.06) -> drop_le_-0.05 and fed to weekly_base_rate
    # (NOT read off the catalyst row, which carries trigger=None) — BLOCKER-2 closed.
    assert any(c[0] == "weekly_base_rate" and c[1] == "drop_le_-0.05"
               for c in calls if isinstance(c, tuple))


def test_direction_proxy_never_returns_none_or_coinflip(monkeypatch):
    monkeypatch.setattr(qw, "classify_drop", lambda *a, **k: _R(
        detail={"ret": -0.11, "drop_class": "idio_no_news", "turnover_flag": "low"}))
    monkeypatch.setattr(qw, "weekly_base_rate", lambda *a, **k: _R(value=0.61,
                                                                   detail={"mean_next": 0.02}))
    side, p = resolve_direction_proxy("base_rate")("ABCD", "2024-02-01", None, object(),
                                                   params={"weekly": {}})
    assert side == "long"
    assert p is not None
    assert p != 0.5      # a COMPUTED base rate — never the 0.5 coin-flip / None default
    assert p == 0.61


# ============================== Task 2: run_layer_a — the deterministic loop ==========

# CAT's crafted decision-week drop (trigger) + hold-week down-gap, reused across the loop tests.
_CAT_BARS = [
    {"week_end": None, "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.0, "volume": 2_000_000.0},
    {"week_end": None, "open": 9.9, "high": 10.0, "low": 9.3, "close": 9.4, "volume": 2_000_000.0},  # -6% vs 10.0 -> drop_le_-0.05
    {"week_end": None, "open": 7.0, "high": 8.0, "low": 6.0, "close": 7.5, "volume": 2_000_000.0},   # gap-open down at 7.0
]


def _seed_std(conn, *, cat_verified_at=None):
    """A small offline universe (XBI required by classify_drop) with ONE verified catalyst on CAT,
    CAT's bars crafted for a decision-week trigger drop + a hold-week down-gap."""
    weeks = week_ends(12)
    cat = {"ticker": "CAT", "event_date": weeks[6], "last_verified_at": cat_verified_at or weeks[4]}
    seed_history(conn, tickers=["XBI", "AAAA", "BBBB", "CAT", "DEAD"], weeks=12,
                 delisted=["DEAD"], catalysts=[cat])
    bars = [dict(b, week_end=weeks[4 + i]) for i, b in enumerate(_CAT_BARS)]
    upsert_bars(conn, "CAT", bars)
    return weeks


def _run_results(conn, **kw):
    out = run_layer_a(conn, None, **kw)
    return out[0] if isinstance(out, tuple) else out   # Task 3 makes it a (results, dist) tuple


def test_layer_a_never_calls_run_desk(monkeypatch):
    import catalyst_trader.desk.orchestrator as orch
    import catalyst_trader.desk.weekly as dweekly

    def _boom(*a, **k):
        raise AssertionError("Layer A must be NO-LLM — the LLM desk was invoked")

    monkeypatch.setattr(orch, "run_desk", _boom)
    monkeypatch.setattr(dweekly, "run_weekly", _boom)

    conn = _conn()
    weeks = _seed_std(conn)
    results = _run_results(conn, start=weeks[2], end=weeks[10])
    assert results  # ran end-to-end without ever touching the LLM desk (proves NO-LLM)


def test_layer_a_no_zero_trade_week():
    conn = _conn()
    weeks = _seed_std(conn)
    results = _run_results(conn, start=weeks[2], end=weeks[10])
    assert len(results) == 9
    for wk in results:
        assert len(wk.legs) >= 1  # defensive fallback -> never a zero-trade week (WEEK-03)


def test_layer_a_held_through_fills_at_gap_open():
    conn = _conn()
    weeks = _seed_std(conn)
    results = _run_results(conn, start=weeks[5], end=weeks[5], slippage=0.01)
    cat_legs = [l for l in results[0].legs if l.ticker == "CAT" and l.is_catalyst]
    assert cat_legs, "the verified catalyst should have produced a held-through leg"
    leg = cat_legs[0]
    assert leg.held_through is True
    assert leg.fill == pytest.approx(7.0 * (1 - 0.01))   # the gap OPEN far side
    assert leg.fill != pytest.approx(6.0 * (1 - 0.01))   # NOT the action-bar low / a jumped stop


def test_layer_a_catalyst_direction_is_computed_base_rate(monkeypatch):
    seen = []

    def fake_base_rate(ticker, trigger, drop_class, turnover, as_of, store, conn, *, params,
                       window_years=None):
        seen.append((ticker, trigger))
        return _R(value=0.66, detail={"mean_next": 0.02})

    monkeypatch.setattr(qw, "weekly_base_rate", fake_base_rate)
    conn = _conn()
    weeks = _seed_std(conn)
    cat_legs = [l for wk in _run_results(conn, start=weeks[5], end=weeks[5])
                for l in wk.legs if l.ticker == "CAT" and l.is_catalyst]
    assert cat_legs
    assert cat_legs[0].p == 0.66   # the COMPUTED base-rate p (never None/0.5) — BLOCKER-2 closed
    # the trigger was COMPUTED via classify_drop -> _match_trigger, not read off the null catalyst row
    assert any(tk == "CAT" and trig == "drop_le_-0.05" for tk, trig in seen)


def test_layer_a_reuses_tools_not_recompute(monkeypatch):
    used = []

    def sentinel(ticker, trigger, drop_class, turnover, as_of, store, conn, *, params,
                 window_years=None):
        used.append(ticker)
        return _R(value=0.58, detail={"mean_next": 0.015})

    monkeypatch.setattr(qw, "weekly_base_rate", sentinel)
    conn = _conn()
    weeks = _seed_std(conn)
    cat_legs = [l for wk in _run_results(conn, start=weeks[5], end=weeks[5])
                for l in wk.legs if l.ticker == "CAT" and l.is_catalyst]
    assert cat_legs and cat_legs[0].p == 0.58   # used the SHIPPED weekly_base_rate (no re-derivation)
    assert "CAT" in used


def test_layer_a_excludes_catalyst_verified_after_as_of():
    conn = _conn()
    # verified AFTER the week it would trade in (last_verified_at = weeks[8] > as_of weeks[5])
    weeks = _seed_std(conn, cat_verified_at=week_ends(12)[8])
    results = _run_results(conn, start=weeks[5], end=weeks[5])
    # NOT in the 07-02 filtered event set at weeks[5] -> no catalyst leg; and thesis_scan's
    # unguarded catalyst-precedence keeps CAT out of the statistical sleeve too -> no CAT leg at all.
    assert not any(l.ticker == "CAT" for l in results[0].legs)


# ============================== Task 3: baseline distribution assembly ================


def _wk(week, *legs):
    return BacktestResult(week=week, legs=list(legs))


def _hand_results():
    return [
        _wk("2024-01-08", _leg(realized_ret=0.10, size_pct=0.02),
            _leg(realized_ret=-0.04, size_pct=0.02)),
        _wk("2024-01-15", _leg(realized_ret=0.06, size_pct=0.02, hedge_ret=-0.01)),
        _wk("2024-01-22", _leg(realized_ret=-0.02, size_pct=0.02, hedge_ret=0.03)),
    ]


def test_baseline_distribution_hand_computed():
    d = baseline_distribution(_hand_results(), periods_per_year=52)
    # trade-level: rets = [0.10, -0.04, 0.06, -0.02]
    assert d.win_rate == pytest.approx(0.5)          # 2 of 4 made money (strict > 0)
    assert d.avg_win == pytest.approx((0.10 + 0.06) / 2)
    assert d.avg_loss == pytest.approx((0.04 + 0.02) / 2)
    # hedge-effectiveness: over target-down periods (only week3, target -0.02) the hedge (+0.03) offset
    assert d.hedge_effectiveness == pytest.approx(1.0)
    # max-DD on the size-weighted compounded weekly equity (independent numpy check)
    wr = [0.02 * 0.10 + 0.02 * -0.04, 0.02 * 0.06, 0.02 * -0.02]
    eq = np.cumprod([1 + x for x in wr])
    expected_dd = float((eq / np.maximum.accumulate(eq) - 1).min())
    assert d.max_drawdown == pytest.approx(expected_dd)
    assert d.max_drawdown < 0
    assert d.n_trades == 4 and d.n_weeks == 3


def test_baseline_distribution_periods_per_year_required():
    results = _hand_results()
    d52 = baseline_distribution(results, periods_per_year=52)
    d13 = baseline_distribution(results, periods_per_year=13)
    assert d52.sharpe == pytest.approx(d13.sharpe * (52 / 13) ** 0.5)   # scales with freq (footgun cured)
    assert d52.sortino == pytest.approx(d13.sortino * (52 / 13) ** 0.5)


def test_baseline_distribution_empty_raises():
    with pytest.raises(ValueError):
        baseline_distribution([])                                    # no weeks
    with pytest.raises(ValueError):
        baseline_distribution([BacktestResult(week="2024-01-01", legs=[])])  # no legs -> no baseline


def test_run_layer_a_returns_results_and_distribution():
    conn = _conn()
    weeks = _seed_std(conn)
    results, dist = run_layer_a(conn, None, start=weeks[2], end=weeks[10])
    assert isinstance(dist, BaselineDistribution)
    assert dist.n_weeks == len(results) == 9
    assert dist.n_trades >= 9
    assert 0.0 <= dist.win_rate <= 1.0
