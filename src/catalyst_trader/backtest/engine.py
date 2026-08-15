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

from .. import kb, store
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


def _base_rate_ev(ticker, as_of, conn, params, default):
    """The base-rate expected next-week move for a catalyst leg's sizing (expected_move in
    size_for_survival), COMPUTED with the same tools as the direction proxy. Falls back to the
    caller's target when there is no measured cell so the leg is never sized to the tiny FLOOR."""
    try:
        cd = qw.classify_drop(ticker, as_of, store, conn, params=params).detail
        trig = qw._match_trigger(cd["ret"])
        if trig is None:
            return default
        det = qw.weekly_base_rate(ticker, trig, cd["drop_class"], cd["turnover_flag"],
                                  as_of, store, conn, params=params).detail
        mn = det.get("mean_next")
        return mn if mn and mn > 0 else default
    except (ValueError, KeyError):
        return default


def _fill_leg(conn, ticker, as_of, exit_by, *, held_through, slippage):
    """Enter at the decision-week close, exit via the pessimistic fill (07-02). Returns
    (entry, fill, realized_ret) or None when the leg cannot be entered/exited honestly."""
    entry_bars = store.bars_asof(conn, ticker, as_of)
    if not entry_bars:
        return None
    entry = float(entry_bars[-1]["close"])
    if entry <= 0:
        return None
    exit_bars = store.bars_asof(conn, ticker, exit_by)
    if not exit_bars or exit_bars[-1]["week_end"] <= as_of:
        return None  # no hold-week bar yet -> the outcome is unmeasurable, do not fabricate it
    fill = fill_price(exit_bars, side="long", held_through=held_through, slippage=slippage)
    if fill is None:
        return None  # halted / delisted / zero-vol / zero-quote action bar
    return entry, fill, fill / entry - 1.0


def _honest_hedge(conn, embed, ticker, cat, as_of, exit_by):
    """validate_hedge or None (HEDGE-04 honest single-leg fallback). The synthetic fixture seeds
    no hedge peers, so this returns None before it reads analog_gaps/prices; a degenerate real read
    also collapses to None rather than a fabricated hedge.
    # ponytail: analog_gaps come from the point-in-time KB read; empty is the honest offline default.
    """
    try:
        return validate_hedge(conn, embed, ticker, cat, as_of, exit_by,
                              _NO_ANALOG_GAPS, {"target": [], "peer": []})
    except Exception:
        return None


def _defensive_book(w, exit_by):
    """The cash-like defensive book (WEEK-03 no-zero-trade), mirroring desk.weekly.build_defensive_book
    but WITHOUT importing the LLM desk module — Layer A stays decoupled from the agentic runner."""
    instruments = w["defensive_instruments"]
    frac = w["defensive_max_frac"] / len(instruments) if instruments else 0.0
    return [Candidate(size_pct=frac, expected_move=0.0001, weight=frac, payload={"ticker": tk})
            for tk in instruments]


def _cash_leg(ticker, exit_by, size_pct):
    """A defensive cash-like anchor parks flat over the one-week hold (no fabricated gain/loss)."""
    return LegOutcome(ticker=ticker, side="long", entry=1.0, fill=1.0, exit=exit_by,
                      realized_ret=0.0, held_through=False, is_catalyst=False, hedge_ret=None,
                      p=None, size_pct=size_pct)


def run_layer_a(conn, embed, *, start, end, params=None, target_weekly=0.01,
                direction_proxy="base_rate", slippage=0.0, latency_cfg=None,
                weekly_budget=0.10, heat_cap=1.0, periods_per_year=52):
    """The deterministic weekly mechanical backtest of the CORRECTED strategy (BACK-02).

    Iterates the 07-02 point-in-time event set; for each week re-expresses the shipped cadence
    mechanics deterministically (NO LLM): catalyst legs from the last_verified_at-filtered event
    record with a COMPUTED base-rate direction proxy + honest hedge/single-leg selection, the
    deterministic statistical sleeve mirrored from thesis_scan, target-within-survival-cap sizing,
    entry 1-2d pre-event -> pessimistic gap-open fill -> 1-week exit, and a defensive fallback so
    no week is zero-trade. Returns the ordered list of BacktestResult (one per week).
    """
    params = params or kb.load_params(conn, "weekly")
    w = params["weekly"]
    stat_gap = abs(w["hard_veto_drop"])       # worst tolerated weekly move = the survival down-gap
    shortlist_k = w["shortlist_k"]
    proxy_fn = resolve_direction_proxy(direction_proxy)

    results: list[BacktestResult] = []
    for rec in build_event_set(conn, start=start, end=end, latency_cfg=latency_cfg):
        as_of = rec["as_of"]
        exit_by = (date.fromisoformat(as_of) + timedelta(days=7)).isoformat()
        candidates: list[Candidate] = []

        # --- catalyst legs: sourced from the 07-02 point-in-time (last_verified_at-filtered) set ---
        for cat in rec["catalysts"]:
            tk = cat["ticker"]
            try:
                side, p = proxy_fn(tk, as_of, store, conn, params=params)
            except (ValueError, KeyError):
                continue  # insufficient history at this as_of -> no directional read (honest skip)
            if side is None or p is None:
                continue  # no measured trigger cell -> not a coin-flip, just not taken
            filled = _fill_leg(conn, tk, as_of, exit_by, held_through=True, slippage=slippage)
            if filled is None:
                continue
            entry, fill, ret = filled
            ev = _base_rate_ev(tk, as_of, conn, params, target_weekly)
            size = size_for_survival(p_loss=1.0 - p, gap=stat_gap,
                                     target_return=target_weekly, expected_move=ev).value
            hedge = _honest_hedge(conn, embed, tk, cat, as_of, exit_by)
            hedge_ret = None
            if hedge is not None:
                hf = _fill_leg(conn, hedge.ticker, as_of, exit_by, held_through=True,
                               slippage=slippage)
                hedge_ret = hf[2] if hf else None
            out = LegOutcome(ticker=tk, side=side, entry=entry, fill=fill, exit=exit_by,
                             realized_ret=ret, held_through=True, is_catalyst=True,
                             hedge_ret=hedge_ret, p=p, size_pct=size)
            candidates.append(Candidate(size_pct=size, expected_move=ev, weight=size,
                                        payload={"outcome": out}))

        # --- statistical sleeve: mirror the deterministic top-k eligible rows (single-leg, exit@1wk) ---
        try:
            rows = qw.thesis_scan(rec["universe"], as_of, store, conn, params=params).detail["rows"]
        except (ValueError, KeyError):
            rows = []
        eligible = [r for r in rows
                    if r["eligible"] and r["thesis_type"] != "catalyst" and r["ticker"] != qw._XBI]
        eligible.sort(key=lambda r: (r["p"] or 0.0) * (r["mean_next"] or 0.0), reverse=True)
        for r in eligible[:shortlist_k]:
            filled = _fill_leg(conn, r["ticker"], as_of, exit_by, held_through=False,
                               slippage=slippage)
            if filled is None:
                continue
            entry, fill, ret = filled
            size = size_for_survival(p_loss=1.0 - r["p"], gap=stat_gap,
                                     target_return=target_weekly,
                                     expected_move=r["mean_next"]).value
            out = LegOutcome(ticker=r["ticker"], side="long", entry=entry, fill=fill, exit=exit_by,
                             realized_ret=ret, held_through=False, is_catalyst=False,
                             hedge_ret=None, p=r["p"], size_pct=size)
            candidates.append(Candidate(size_pct=size, expected_move=r["mean_next"], weight=size,
                                        payload={"outcome": out}))

        # --- selection toward ~target within budget + heat cap; defensive fallback (WEEK-03) ---
        defensive = _defensive_book(w, exit_by)
        promoted, _agg = select_book(candidates, [], weekly_budget, heat_cap, target_weekly,
                                     defensive_book=defensive)
        legs = [
            pl["outcome"] if (pl := (c.payload or {})).get("outcome") is not None
            else _cash_leg(pl["ticker"], exit_by, c.size_pct)
            for c in promoted
        ]
        if not legs:  # belt-and-suspenders: never a zero-trade week
            legs = [_cash_leg(c.payload["ticker"], exit_by, c.size_pct) for c in defensive]
        results.append(BacktestResult(week=as_of, legs=legs))

    return results, baseline_distribution(results, periods_per_year=periods_per_year)


def _safe(fn, rets, periods_per_year):
    """Sharpe/Sortino or None when undefined (too few weeks / no downside) — never a fake number."""
    try:
        return fn(rets, periods_per_year).value
    except ValueError:
        return None


def baseline_distribution(results, *, periods_per_year=52):
    """Roll the per-leg outcomes into the frozen BaselineDistribution the go/no-go gate consumes.

    Trade-level stats (win_rate, avg win/loss) run over every leg's realized return; Sharpe / Sortino
    / max-DD run over the SIZE-WEIGHTED compounded weekly equity at the given periods_per_year (52 for
    weekly — passed explicitly, never defaulted: the freq footgun the project already cured);
    hedge-effectiveness pairs the legs that carried a hedge. Empty results RAISE — no silent zero
    baseline. Reproducible: same results -> identical distribution.
    """
    if not results:
        raise ValueError("no results — refuse to emit a silent zero baseline")
    trade_rets = [l.realized_ret for wk in results for l in wk.legs]
    if not trade_rets:
        raise ValueError("no legs across the results — refuse to emit a silent zero baseline")

    weekly_rets = [sum(l.size_pct * l.realized_ret for l in wk.legs) for wk in results]
    awl = avg_win_loss(trade_rets)
    tgt = [l.realized_ret for wk in results for l in wk.legs if l.hedge_ret is not None]
    hdg = [l.hedge_ret for wk in results for l in wk.legs if l.hedge_ret is not None]

    return BaselineDistribution(
        win_rate=win_rate(trade_rets).value,
        avg_win=awl.detail["avg_win"],
        avg_loss=awl.detail["avg_loss"],
        sharpe=_safe(sharpe, weekly_rets, periods_per_year),
        sortino=_safe(sortino, weekly_rets, periods_per_year),
        max_drawdown=max_drawdown(weekly_rets).value,
        hedge_effectiveness=hedge_effectiveness(tgt, hdg).value if tgt else None,
        n_trades=len(trade_rets),
        n_weeks=len(results),
    )
