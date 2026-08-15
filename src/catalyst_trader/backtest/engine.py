"""backtest/engine.py — Layer A: the mechanical, NO-LLM backtest of the CORRECTED strategy (BACK-02).

Layer A measures the CONFIGURED strategy — the base-rate ASSUMPTIONS are the moat (PROJECT.md
"assumptions are the moat, not the models"), NOT the LLM's incremental edge (that is Layer B, 07-05,
labelled biased-optimistic). So this module RE-EXPRESSES the shipped weekly cadence mechanics
deterministically WITHOUT ever invoking the LLM debate desk or the LLM weekly cadence runner. Every
money number comes from the shipped deterministic tools (thesis_scan / classify_drop / _match_trigger /
weekly_base_rate / size_for_survival / validate_hedge / select_book / fill_price) — nothing is re-derived.

The catalyst-leg DIRECTION is a base-rate P(positive) proxy COMPUTED the way the statistical sleeve
derives it (desk/weekly.py L116-119): classify_drop -> _match_trigger -> weekly_base_rate. A catalyst
thesis row carries trigger=None / p=None / no drop_class, so the proxy NEVER reads them off the row — it
COMPUTES them (BLOCKER-2). Catalyst legs flow from the 07-02 point-in-time event set (already
last_verified_at <= as_of filtered), so a catalyst verified after the simulated week can never be traded.

Fully offline over the synthetic event set; reproducible (same fixtures -> same baseline).
"""

from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, ConfigDict

from .. import store
from ..desk.portfolio import Candidate, select_book
from ..desk.risk import size_for_survival, validate_hedge
from ..quant import weekly as qw
from ..quant.performance import (
    avg_win_loss,
    hedge_effectiveness,
    max_drawdown,
    sharpe,
    sortino,
    win_rate,
)
from .events import build_event_set
from .fill import fill_price

# validate_hedge needs analog gaps + prices; the synthetic fixture seeds no hedge peers, so the
# call returns None before it ever reads these (honest single-leg fallback, HEDGE-04). Kept as an
# explicit empty structure so the point-in-time KB read is the only thing that would fill it.
# ponytail: real analog gaps come from the point-in-time KB read; empty is the honest offline default.
_NO_ANALOG_GAPS = {
    "target_up": 0.0, "target_down": 0.0, "peer_up": 0.0, "peer_down": 0.0,
    "w_target": 1.0, "w_peer": 0.0,
}


# ============================== contracts =============================================


class LegOutcome(BaseModel):
    """One filled leg's audit trail: entry -> pessimistic exit fill -> realized return."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    ticker: str
    side: str
    entry: float
    fill: float          # the exit fill price (pessimistic gap-open / far-side, slippage-worsened)
    exit: str            # the one-week exit date
    realized_ret: float
    held_through: bool
    is_catalyst: bool
    hedge_ret: float | None = None
    p: float | None = None       # the direction-proxy P(positive) that sized the leg (None = defensive)
    size_pct: float


class BacktestResult(BaseModel):
    """One backtest WEEK: the legs that were actually traded (never empty — no zero-trade weeks)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    week: str
    legs: list[LegOutcome]


class BaselineDistribution(BaseModel):
    """The honest baseline the go/no-go gate (07-05) consumes. Sharpe/Sortino/hedge-effectiveness
    are None when undefined (too few weeks / no down weeks / no hedged pairs) — never a fake number."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    win_rate: float
    avg_win: float
    avg_loss: float
    sharpe: float | None
    sortino: float | None
    max_drawdown: float
    hedge_effectiveness: float | None
    n_trades: int
    n_weeks: int


# ============================== the direction_proxy knob ==============================


def _base_rate_direction(ticker, as_of, store_mod, conn, *, params):
    """Base-rate P(positive) for a catalyst leg, COMPUTED the way the statistical sleeve derives it
    (desk/weekly.py L116-119): classify_drop -> _match_trigger -> weekly_base_rate.

    The catalyst thesis row carries trigger=None / p=None / no drop_class, so this NEVER reads them off
    the row — it computes them (BLOCKER-2). Returns ("long", p). No measured trigger cell -> (None, None):
    an honest skip (the leg is simply not taken), NEVER a coin-flip / None default masquerading as an edge.
    """
    cd = qw.classify_drop(ticker, as_of, store_mod, conn, params=params).detail
    trigger = qw._match_trigger(cd["ret"])
    if trigger is None:
        return None, None
    p = qw.weekly_base_rate(ticker, trigger, cd["drop_class"], cd["turnover_flag"],
                            as_of, store_mod, conn, params=params).value
    return "long", p


def _long_runup_direction(ticker, as_of, store_mod, conn, *, params):
    """The BETA-BET comparison knob: unconditional always-long at p=0.5.

    # ponytail: exists ONLY as the naive 'just be long into the catalyst' comparison baseline that
    #           base_rate is measured AGAINST — base_rate is the default that carries the moat.
    """
    return "long", 0.5


DIRECTION_PROXIES = {"base_rate": _base_rate_direction, "long_runup": _long_runup_direction}


def resolve_direction_proxy(name: str = "base_rate"):
    """Resolve a named direction proxy. Default = base_rate (the computed P(positive) moat)."""
    if name not in DIRECTION_PROXIES:
        raise ValueError(f"unknown direction_proxy {name!r}; use one of {sorted(DIRECTION_PROXIES)}")
    return DIRECTION_PROXIES[name]


# ============================== run_layer_a (Task 2) + baseline (Task 3) ==============


def run_layer_a(conn, embed, *, start, end, params=None, target_weekly=0.01,
                direction_proxy="base_rate", slippage=0.0, latency_cfg=None,
                weekly_budget=0.10, heat_cap=1.0, periods_per_year=52):
    raise NotImplementedError  # Task 2


def baseline_distribution(results, *, periods_per_year=52):
    raise NotImplementedError  # Task 3
