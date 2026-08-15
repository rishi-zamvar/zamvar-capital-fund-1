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
