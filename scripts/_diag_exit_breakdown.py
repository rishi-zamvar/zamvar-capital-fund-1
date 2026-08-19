"""DIAGNOSTIC (throwaway) — Quick 260819-p1x root-cause instrumentation.

Re-runs the DAILY catalyst-leg path exactly as engine.run_layer_a does, but captures per-leg:
  ticker, as_of, event_date, exit_date, exit_reason, off_map, realized_ret (daily reflex)
AND the paired WEEKLY held-through gap-open fill for the SAME leg (apples-to-apples).

Tallies:
  1. exit-reason breakdown x pre/post-event, with PnL contribution.
  2. paired daily-vs-weekly return on the SAME covered legs (fair subset comparison).
  3. how much of the avg_win collapse is pre-event exits.

Cache-only (allow_fetch=False) — no live API calls. NOT shipped code; delete after use.
"""

from __future__ import annotations

import statistics as st

from catalyst_trader import db as _db, kb
from catalyst_trader.backtest.daily_provider import make_daily_bars_provider
from catalyst_trader.backtest.engine import (
    _base_rate_ev,
    _ev_from_mean_next,
    _fill_leg,
    resolve_direction_proxy,
)
from catalyst_trader.backtest.events import build_event_set
from catalyst_trader.quant import weekly as qw

START, END, DB = "2025-08-17", "2026-08-10", "catalyst.db"


def collect(conn):
    params = kb.load_params(conn, "weekly")
    w = params["weekly"]
    stat_gap = abs(w["hard_veto_drop"])
    target_weekly = 0.01
    proxy_fn = resolve_direction_proxy("base_rate")
    provider = make_daily_bars_provider(conn)  # allow_fetch=False (frugal cache-only)

    from datetime import date, timedelta
    legs = []
    for rec in build_event_set(conn, start=START, end=END):
        as_of = rec["as_of"]
        exit_by = (date.fromisoformat(as_of) + timedelta(days=7)).isoformat()
        view = qw.as_of_view(conn, as_of)
        for cat in rec["catalysts"]:
            tk = cat["ticker"]
            event_date = cat["event_date"]
            try:
                side, p, ev_raw = proxy_fn(tk, as_of, view, conn, params=params)
            except (ValueError, KeyError):
                continue
            if side is None or p is None:
                continue
            ev = (_ev_from_mean_next(ev_raw, target_weekly) if ev_raw is not None
                  else _base_rate_ev(tk, as_of, conn, params, target_weekly, store_view=view))
            daily = _fill_leg(conn, tk, as_of, exit_by, held_through=True, slippage=0.0,
                              granularity="daily", daily_bars_provider=provider,
                              up_move=ev, vol_move=stat_gap, params=params, exit_latency_bars=0)
            if daily is None:
                continue  # abstained (not covered)
            _entry_d, _fill_d, ret_daily, reflex = daily
            weekly = _fill_leg(conn, tk, as_of, exit_by, held_through=True, slippage=0.0)
            ret_weekly = weekly[2] if weekly else None
            exit_date = reflex["exit"]
            legs.append({
                "ticker": tk, "as_of": as_of, "event_date": event_date, "exit_date": exit_date,
                "reason": reflex["reason"], "off_map": reflex["off_map"],
                "pre_event": exit_date < event_date,
                "ret_daily": ret_daily, "ret_weekly": ret_weekly,
                "p": p, "ev": ev,
            })
    return legs


def _stats(rets):
    rets = [r for r in rets if r is not None]
    if not rets:
        return (0, None, None, None)
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    aw = st.mean(wins) if wins else 0.0
    al = st.mean(losses) if losses else 0.0
    return (len(rets), len(wins) / len(rets), aw, al)


def report(legs):
    print(f"\n=== COVERED CATALYST LEGS: {len(legs)} ===\n")

    # 1. exit-reason x pre/post-event
    print("--- exit-reason breakdown (daily reflex) ---")
    print(f"{'reason':8} {'n':>3} {'pre-evt':>7} {'post-evt':>8} {'mean_ret':>9} {'sum_ret':>8}")
    reasons = {}
    for l in legs:
        reasons.setdefault(l["reason"], []).append(l)
    for r, ls in sorted(reasons.items()):
        pre = sum(1 for x in ls if x["pre_event"])
        post = len(ls) - pre
        rets = [x["ret_daily"] for x in ls]
        print(f"{r:8} {len(ls):>3} {pre:>7} {post:>8} {st.mean(rets)*100:>8.2f}% {sum(rets)*100:>7.2f}%")

    # 2. pre vs post event overall
    print("\n--- pre-event vs post-event exits (daily reflex) ---")
    for label, sub in (("PRE-event ", [l for l in legs if l["pre_event"]]),
                       ("POST-event", [l for l in legs if not l["pre_event"]])):
        n, wr, aw, al = _stats([l["ret_daily"] for l in sub])
        print(f"{label}: n={n:>3} win={_pct(wr)} avg_win={_pct(aw)} avg_loss={_pct(al)} "
              f"sum_contrib={sum(l['ret_daily'] for l in sub)*100:+.1f}%")

    # 3. paired daily vs weekly on the SAME covered legs (apples-to-apples)
    print("\n--- APPLES-TO-APPLES: daily reflex vs weekly hold on the SAME covered legs ---")
    paired = [l for l in legs if l["ret_weekly"] is not None]
    nd, wrd, awd, ald = _stats([l["ret_daily"] for l in paired])
    nw, wrw, aww, alw = _stats([l["ret_weekly"] for l in paired])
    print(f"paired legs: {len(paired)}")
    print(f"  DAILY  : win={_pct(wrd)} avg_win={_pct(awd)} avg_loss={_pct(ald)} "
          f"mean_ret={_pct(st.mean([l['ret_daily'] for l in paired]))}")
    print(f"  WEEKLY : win={_pct(wrw)} avg_win={_pct(aww)} avg_loss={_pct(alw)} "
          f"mean_ret={_pct(st.mean([l['ret_weekly'] for l in paired]))}")
    dd = sum(l["ret_daily"] for l in paired)
    ww = sum(l["ret_weekly"] for l in paired)
    print(f"  SUM daily={dd*100:+.1f}%  SUM weekly={ww*100:+.1f}%  weekly-minus-daily={ (ww-dd)*100:+.1f}%")

    # 3b. per-leg: how many legs did the reflex HURT vs help vs same
    hurt = sum(1 for l in paired if l["ret_weekly"] - l["ret_daily"] > 0.005)
    help_ = sum(1 for l in paired if l["ret_daily"] - l["ret_weekly"] > 0.005)
    same = len(paired) - hurt - help_
    print(f"  reflex HURT (weekly better by >0.5pp): {hurt}   HELPED: {help_}   ~same: {same}")

    # 4. avg_win collapse attribution
    print("\n--- avg_win collapse attribution ---")
    wk_wins = [l["ret_weekly"] for l in paired if l["ret_weekly"] and l["ret_weekly"] > 0]
    dl_wins = [l["ret_daily"] for l in paired if l["ret_daily"] > 0]
    print(f"weekly avg_win on covered subset: {_pct(st.mean(wk_wins) if wk_wins else 0)}")
    print(f"daily  avg_win on covered subset: {_pct(st.mean(dl_wins) if dl_wins else 0)}")
    # legs that were weekly-winners but the daily reflex cut short
    cut = [l for l in paired if l["ret_weekly"] and l["ret_weekly"] > 0.05]
    cut_pre = [l for l in cut if l["pre_event"]]
    print(f"legs with weekly return >+5% (real catalyst winners): {len(cut)}")
    if cut:
        print(f"  of those, daily reflex mean return: {_pct(st.mean([l['ret_daily'] for l in cut]))} "
              f"(weekly mean: {_pct(st.mean([l['ret_weekly'] for l in cut]))})")
        print(f"  of those cut PRE-event: {len(cut_pre)} / {len(cut)}")

    # off_map
    print(f"\n--- off_map: {sum(1 for l in legs if l['off_map'])} / {len(legs)} covered legs ---")


def _pct(x):
    return f"{x*100:+.2f}%" if x is not None else "n/a"


if __name__ == "__main__":
    conn = _db.connect(DB)
    _db.migrate(conn)
    legs = collect(conn)
    report(legs)
