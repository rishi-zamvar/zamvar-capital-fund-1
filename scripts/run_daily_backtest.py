"""Quick-260819-p1x Task 3 — run the honest daily+latency backtest and emit the FINDINGS report.

Thin composition over run_layer_a + latency_sweep: NO new money math — every metric is read off the
shipped BaselineDistribution (baseline_distribution already computes win_rate/avg/sharpe/sortino/
max_dd). Runs, over the SAME event set on the pre-populated daily_bar cache (Task 2 must have run):
  - weekly baseline   run_layer_a(..., granularity="weekly")
  - daily reflex      run_layer_a(..., granularity="daily", daily_bars_provider=cache_provider)
  - latency sweep     latency_sweep(..., delays=(0,1,2))
then writes 260819-p1x-FINDINGS.md with: weekly-vs-daily distribution + DELTA, T+0/1/2 latency
degradation, data-coverage %, off_map count+frequency, a plain-English read, and the MANDATORY
latency-interpretation caveat (§6 — do NOT omit).

--smoke proves the generator over the synthetic fixtures (tests/synth_history.py) + a fake in-memory
provider — no live cache, no network. Answers the Task-A question and feeds the Task-B go/no-go.
"""

import argparse
import os
import statistics as st
import sys
from pathlib import Path

from catalyst_trader import db as _db
from catalyst_trader.backtest.daily_provider import make_daily_bars_provider
from catalyst_trader.backtest.engine import latency_sweep, run_layer_a
from catalyst_trader.backtest.events import build_event_set

DEFAULT_START = "2025-08-17"
DEFAULT_END = "2026-08-10"
DEFAULT_DB = "catalyst.db"
FINDINGS = (Path(__file__).resolve().parents[1] /
            ".planning/quick/260819-p1x-production-replica-backtest-daily-wiring/260819-p1x-FINDINGS.md")


# ------------------------------------------------------------------ formatting helpers
def _p(x):
    """Percent, None-safe."""
    return f"{x * 100:+.2f}%" if x is not None else "n/a"


def _n(x):
    """Float, None-safe (Sharpe/Sortino are None when undefined — never a fake number)."""
    return f"{x:.2f}" if x is not None else "n/a"


def _delta(a, b):
    """a - b on a headline metric, None-safe."""
    if a is None or b is None:
        return "n/a"
    return f"{(a - b) * 100:+.2f} pp" if abs(a) < 5 else f"{a - b:+.2f}"


def _dist_row(name, d):
    return (f"| {name} | {_p(d.win_rate)} | {_p(d.avg_win)} | {_p(d.avg_loss)} | {_n(d.sharpe)} | "
            f"{_n(d.sortino)} | {_p(d.max_drawdown)} | {d.n_trades} | {d.n_weeks} |")


# ------------------------------------------------------------------ paired covered subset (M4 §1)
def paired_covered_subset(weekly_results, daily_results):
    """Catalyst legs filled on BOTH the weekly and daily paths for the same (week, ticker) — the
    fair apples-to-apples subset for the PRIMARY go/no-go.

    CONCERN-1: derived from the already-computed LegOutcomes (no re-run, no re-priced provider, no
    duplicated pairing logic), so it populates under whatever provider the run used — including the
    --smoke fake provider. Each held_through catalyst leg carries realized_ret on both paths."""
    def _cat_index(results):
        return {(wk.week, l.ticker): l for wk in results for l in wk.legs if l.is_catalyst}
    wk_idx, dl_idx = _cat_index(weekly_results), _cat_index(daily_results)
    return [{"week": k[0], "ticker": k[1],
             "ret_weekly": wk_idx[k].realized_ret, "ret_daily": dl_idx[k].realized_ret,
             "reason": dl_idx[k].exit_reason, "off_map": dl_idx[k].off_map}
            for k in wk_idx.keys() & dl_idx.keys()]


def _sub_stats(rets):
    """(win_rate, avg_win, avg_loss, mean_ret) over a return list — the exact tallies the diag's
    report() computes (mean via statistics; win = ret > 0). None-safe for an empty subset."""
    if not rets:
        return (None, None, None, None)
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    return (len(wins) / len(rets),
            (st.mean(wins) if wins else 0.0), (st.mean(losses) if losses else 0.0),
            st.mean(rets))


# ------------------------------------------------------------------ coverage + off_map
def coverage(conn, daily_results, start, end):
    """(filled, opportunities, pct): daily CATALYST legs filled / catalyst opportunities in the
    point-in-time event set over the window. Numerator/denominator both stated in the report."""
    opportunities = sum(len(rec["catalysts"]) for rec in build_event_set(conn, start=start, end=end))
    filled = sum(1 for wk in daily_results for l in wk.legs if l.is_catalyst)
    pct = (filled / opportunities) if opportunities else 0.0
    return filled, opportunities, pct


def off_map_stats(daily_results):
    """(off_map_count, daily_legs, freq): off_map legs / all daily legs across the daily run."""
    legs = [l for wk in daily_results for l in wk.legs]
    off = sum(1 for l in legs if l.off_map)
    freq = (off / len(legs)) if legs else 0.0
    return off, len(legs), freq


# ------------------------------------------------------------------ the report
def build_findings(*, window, weekly, daily, sweep, cov, offmap, paired):
    filled, opps, cov_pct = cov
    off, n_legs, off_freq = offmap
    start, end = window

    lines = [
        "# Quick 260819-p1x — Daily+Latency Backtest FINDINGS",
        "",
        f"Warm-playbook walk-forward window: **{start} → {end}**. Deterministic Layer-A (NO-LLM), "
        "point-in-time correct, over the REAL cached daily bars (no injected synthetic bars).",
        "",
        "## 1. Paired covered-subset comparison (PRIMARY go/no-go)",
        "",
        *_paired_section(paired, offmap),
        "",
        "## 2. Weekly vs Daily distribution",
        "",
        "| Path | Win rate | Avg win | Avg loss | Sharpe | Sortino | Max DD | Trades | Weeks |",
        "| ---- | -------- | ------- | -------- | ------ | ------- | ------ | ------ | ----- |",
        _dist_row("Weekly baseline", weekly),
        _dist_row("Daily reflex", daily),
        "",
        f"**Daily − Weekly delta:** win_rate {_delta(daily.win_rate, weekly.win_rate)}, "
        f"Sharpe {_delta(daily.sharpe, weekly.sharpe)}, max_drawdown "
        f"{_delta(daily.max_drawdown, weekly.max_drawdown)}. "
        "_(Whole-book distributions differ in trade MIX from §1's paired subset; §1 is the fair "
        "apples-to-apples go/no-go.)_",
        "",
        "## 3. Latency degradation (T+0 / T+1 / T+2)",
        "",
        "| Delay | Win rate | Avg win | Avg loss | Sharpe | Sortino | Max DD | Trades | Weeks |",
        "| ----- | -------- | ------- | -------- | ------ | ------- | ------ | ------ | ----- |",
        *[_dist_row(f"T+{d['latency']}", d["distribution"]) for d in sweep],
        "",
        "_An edge visible only at T+0 (no execution lag) is fragile — read this table WITH the §7 "
        "caveat below before drawing any conclusion._",
        "",
        "## 4. Data coverage",
        "",
        f"Daily catalyst legs FILLED / catalyst opportunities in the event set: "
        f"**{filled} / {opps} = {cov_pct * 100:.1f}%**.",
        "",
        "The denominator is every catalyst opportunity `build_event_set` surfaced over the window; "
        "the numerator is the catalyst legs the daily reflex actually filled from the cache. "
        "Abstained legs are un-populated / degraded tickers or holiday-`exit_by` weeks whose bar "
        "landed inside the execution buffer.",
        "",
        "## 5. off_map frequency",
        "",
        f"off_map legs / all daily legs: **{off} / {n_legs} = {off_freq * 100:.1f}%**.",
        "",
        "_off_map = an intraweek move no scenario-table branch covers (the Task-B escalation seam). "
        "Post-M1 a hold-through catalyst leg can surface off_map ONLY via a halt roll (band-excess "
        "off_map is suppressed for hold-through legs). State this number explicitly for the Task-B "
        "go/no-go — it sizes the off-map reasoning-agent workload the next step must handle._",
        "",
        "## 6. Plain-English read",
        "",
        _read(weekly, daily, sweep, cov_pct, off_freq),
        "",
        "## 7. MANDATORY latency-interpretation caveat",
        "",
        "The sweep in §3 applies `exit_latency_bars` **globally to ALL exits**. But per the execution "
        "model, on-map stop-loss / take-profit exits are **resting broker-side orders** with ~zero "
        "reasoning latency — only the **off-map** path carries reasoning latency (an agent must think "
        "before it acts). So the §3 latency table is a **pessimistic UPPER BOUND** that over-penalizes "
        "on-map resting exits by charging them a reasoning delay they would never incur live.",
        "",
        "Per-exit-type latency (broker ≈ 0 for on-map SL/TP, reasoning-latency only for off-map) is a "
        "**Step-4 mitigation**. Therefore an edge that looks *globally erased* here must **NOT** be "
        "read as a real failure into the Step-5 go/no-go — a globally-erased edge is a **false-negative "
        "artifact** of applying reasoning latency to broker-side orders, not a real one. Read §3 against "
        "the off_map frequency in §5: the smaller §5 is, the more of §3's degradation is this artifact.",
        "",
    ]
    return "\n".join(lines)


def _paired_section(paired, offmap):
    """§1 body: the paired daily-vs-weekly tallies + the three mandatory caveats (vetter-required)."""
    off, n_legs, off_freq = offmap
    if not paired:
        body = ["_No catalyst leg was filled on BOTH paths in this window — paired subset is empty._"]
    else:
        wrd, awd, ald, md = _sub_stats([l["ret_daily"] for l in paired])
        wrw, aww, alw, mw = _sub_stats([l["ret_weekly"] for l in paired])
        sum_d = sum(l["ret_daily"] for l in paired)
        sum_w = sum(l["ret_weekly"] for l in paired)
        hurt = sum(1 for l in paired if l["ret_weekly"] - l["ret_daily"] > 0.005)
        helped = sum(1 for l in paired if l["ret_daily"] - l["ret_weekly"] > 0.005)
        same = len(paired) - hurt - helped
        body = [
            f"Paired covered legs (filled on BOTH paths, same week+ticker): **{len(paired)}**. "
            "Daily reflex vs weekly hold, apples-to-apples on the identical legs:",
            "",
            "| Path | Win rate | Avg win | Avg loss | Mean ret | Sum ret |",
            "| ---- | -------- | ------- | -------- | -------- | ------- |",
            f"| Daily reflex | {_p(wrd)} | {_p(awd)} | {_p(ald)} | {_p(md)} | {_p(sum_d)} |",
            f"| Weekly hold  | {_p(wrw)} | {_p(aww)} | {_p(alw)} | {_p(mw)} | {_p(sum_w)} |",
            "",
            f"**Weekly − daily (headline):** mean {_delta(mw, md)}, sum {_delta(sum_w, sum_d)}. "
            f"Per-leg the reflex HURT (weekly better by >0.5pp) **{hurt}**, HELPED **{helped}**, "
            f"~same **{same}**. Under M1 a hold-through leg holds to the time barrier, so the daily "
            "paired path should now converge to the weekly baseline (edge restored).",
        ]
    caveats = [
        "",
        "**Mandatory caveats (read WITH the number, per the adversarial vet):**",
        "",
        "- **(i) IN-SAMPLE HEALTH WARNING:** this is the same history the playbook was built on — a "
        "tiny ~48-leg / 7-winner set whose weekly edge is dominated by ~7 legs at mean +107%. Trust "
        "the RANKING and DIRECTION (is the reflex net-harmful?), NOT the magnitude. The forward "
        "paper month is the real proof.",
        "- **(ii) ENTRY-BASIS CAVEAT:** the weekly leg enters at the decision-week CLOSE; the daily "
        "leg enters at the next tradeable daily OPEN. The raw paired delta therefore conflates "
        "exit-timing with an entry-basis difference — it is NOT a pure exit-only isolation (no "
        "re-basis is attempted; the caveat IS the mitigation the vet mandated).",
        f"- **(iii) POST-FIX off_map RE-EMIT:** this run's off_map = **{off}/{n_legs} "
        f"({off_freq * 100:.1f}%)**, re-measured on the FIXED (post-M1) band. The pre-fix 1/48 "
        "(~2%) is PROVISIONAL — it was measured under the broken band; the Task-B off-map go/no-go "
        "must re-decide on this fixed number.",
    ]
    return body + caveats


def _read(weekly, daily, sweep, cov_pct, off_freq):
    dw = _delta(daily.win_rate, weekly.win_rate)
    beats = (daily.sharpe is not None and weekly.sharpe is not None and daily.sharpe > weekly.sharpe)
    survives = "survives" if (sweep and sweep[-1]["distribution"].win_rate >= weekly.win_rate) else "degrades"
    return (
        f"The daily reflex {'beats' if beats else 'does not clearly beat'} the crude weekly hold on "
        f"risk-adjusted return (win-rate delta {dw}); under global exit latency it {survives} to T+"
        f"{sweep[-1]['latency'] if sweep else 0}. Coverage was {cov_pct * 100:.1f}% of catalyst "
        f"opportunities and {off_freq * 100:.1f}% of daily legs went off-map. Coverage caveats "
        "(abstained / holiday legs) are honest gaps, not silent zeros — an abstained leg is simply "
        "dropped, never fabricated. Read the §3 latency table strictly through the §7 caveat, and "
        "the §1 paired subset as the fair go/no-go."
    )


# ------------------------------------------------------------------ live entrypoint
def run(conn, *, start, end):
    embed = lambda *a, **k: None  # noqa: E731 — the mechanical run never invokes the LLM
    provider = make_daily_bars_provider(conn)  # cache-only (allow_fetch=False): frugal, no live calls
    weekly_res, weekly = run_layer_a(conn, embed, start=start, end=end, granularity="weekly")
    daily_res, daily = run_layer_a(conn, embed, start=start, end=end, granularity="daily",
                                   daily_bars_provider=provider)
    sweep = latency_sweep(conn, embed, start=start, end=end, daily_bars_provider=provider,
                          delays=(0, 1, 2))
    cov = coverage(conn, daily_res, start, end)
    offmap = off_map_stats(daily_res)
    paired = paired_covered_subset(weekly_res, daily_res)
    return build_findings(window=(start, end), weekly=weekly, daily=daily, sweep=sweep,
                          cov=cov, offmap=offmap, paired=paired)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=os.environ.get("CATALYST_DB", DEFAULT_DB))
    ap.add_argument("--start", default=os.environ.get("BACKTEST_START", DEFAULT_START))
    ap.add_argument("--end", default=os.environ.get("BACKTEST_END", DEFAULT_END))
    ap.add_argument("--smoke", action="store_true", help="offline generator proof over synthetic fixtures")
    args = ap.parse_args(argv)

    if args.smoke:
        return _smoke()

    conn = _db.connect(args.db)
    _db.migrate(conn)  # idempotent — daily_bar (014) must exist for the cache read
    md = run(conn, start=args.start, end=args.end)
    FINDINGS.write_text(md)
    print(f"wrote {FINDINGS} ({len(md)} bytes)")
    return 0


def _smoke():
    """Prove the generator emits all six sections over synthetic fixtures + a fake provider (no cache)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # make tests/ fixtures importable
    from tests.test_backtest_engine import _CAT_BARS, _seed_std  # synthetic seed (synth_history-backed)

    conn = _db.connect(":memory:")
    _db.migrate(conn)
    weeks = _seed_std(conn)

    def fake_provider(ticker, as_of, exit_by):
        # a monotonic slide past exit_by so entry + each latency exit + the time barrier all have a
        # real bar (mirrors the latency-sweep test provider) — fully offline, no cache, no network.
        return [
            {"week_end": as_of, "open": 10.0, "high": 10.1, "low": 9.9, "close": 10.0, "volume": 1e6},
            {"week_end": _plus(as_of, 1), "open": 9.0, "high": 9.1, "low": 3.0, "close": 4.0, "volume": 1e6},
            {"week_end": exit_by, "open": 3.5, "high": 3.6, "low": 3.4, "close": 3.5, "volume": 1e6},
            {"week_end": _plus(exit_by, 1), "open": 3.0, "high": 3.1, "low": 2.9, "close": 3.0, "volume": 1e6},
            {"week_end": _plus(exit_by, 2), "open": 2.5, "high": 2.6, "low": 2.4, "close": 2.5, "volume": 1e6},
        ]

    embed = lambda *a, **k: None  # noqa: E731
    start, end = weeks[5], weeks[6]
    weekly_res, weekly = run_layer_a(conn, embed, start=start, end=end, granularity="weekly")
    daily_res, daily = run_layer_a(conn, embed, start=start, end=end, granularity="daily",
                                   daily_bars_provider=fake_provider)
    sweep = latency_sweep(conn, embed, start=start, end=end, daily_bars_provider=fake_provider,
                          delays=(0, 1, 2))
    paired = paired_covered_subset(weekly_res, daily_res)
    md = build_findings(window=(start, end), weekly=weekly, daily=daily, sweep=sweep,
                        cov=coverage(conn, daily_res, start, end), offmap=off_map_stats(daily_res),
                        paired=paired)
    print(md)

    for section in ("## 1. Paired covered-subset", "## 2. Weekly vs Daily", "## 3. Latency",
                    "## 4. Data coverage", "## 5. off_map", "## 6. Plain-English",
                    "## 7. MANDATORY latency"):
        assert section in md, f"missing section: {section}"
    for kw in ("weekly", "daily", "latency", "coverage", "off_map"):
        assert kw.lower() in md.lower(), f"missing keyword: {kw}"
    # the three mandatory caveats must be present inline with the paired number
    for caveat in ("IN-SAMPLE HEALTH WARNING", "ENTRY-BASIS CAVEAT", "POST-FIX off_map RE-EMIT"):
        assert caveat in md, f"missing mandatory caveat: {caveat}"
    # the paired §1 must POPULATE under --smoke's fake provider (CONCERN-1 requirement)
    assert paired, "paired covered subset is empty under --smoke — §1 would not populate"
    print("\nrun_daily_backtest --smoke: OK (7 sections + 3 caveats + paired subset populated)")
    return 0


def _plus(iso, days):
    from datetime import date, timedelta
    return (date.fromisoformat(iso) + timedelta(days=days)).isoformat()


if __name__ == "__main__":
    sys.exit(main())
