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
def build_findings(*, window, weekly, daily, sweep, cov, offmap):
    filled, opps, cov_pct = cov
    off, n_legs, off_freq = offmap
    start, end = window
    t = [d["distribution"] for d in sweep]

    lines = [
        "# Quick 260819-p1x — Daily+Latency Backtest FINDINGS",
        "",
        f"Warm-playbook walk-forward window: **{start} → {end}**. Deterministic Layer-A (NO-LLM), "
        "point-in-time correct, over the REAL cached daily bars (no injected synthetic bars).",
        "",
        "## 1. Weekly vs Daily distribution",
        "",
        "| Path | Win rate | Avg win | Avg loss | Sharpe | Sortino | Max DD | Trades | Weeks |",
        "| ---- | -------- | ------- | -------- | ------ | ------- | ------ | ------ | ----- |",
        _dist_row("Weekly baseline", weekly),
        _dist_row("Daily reflex", daily),
        "",
        f"**Daily − Weekly delta (headline):** win_rate {_delta(daily.win_rate, weekly.win_rate)}, "
        f"Sharpe {_delta(daily.sharpe, weekly.sharpe)}, max_drawdown "
        f"{_delta(daily.max_drawdown, weekly.max_drawdown)}. "
        "_(This delta is the primary Task-B go/no-go input: does spending judgment at entry + "
        "reflexive intraweek exits beat the crude weekly hold?)_",
        "",
        "## 2. Latency degradation (T+0 / T+1 / T+2)",
        "",
        "| Delay | Win rate | Avg win | Avg loss | Sharpe | Sortino | Max DD | Trades | Weeks |",
        "| ----- | -------- | ------- | -------- | ------ | ------- | ------ | ------ | ----- |",
        *[_dist_row(f"T+{d['latency']}", d["distribution"]) for d in sweep],
        "",
        "_An edge visible only at T+0 (no execution lag) is fragile — read this table WITH the §6 "
        "caveat below before drawing any conclusion._",
        "",
        "## 3. Data coverage",
        "",
        f"Daily catalyst legs FILLED / catalyst opportunities in the event set: "
        f"**{filled} / {opps} = {cov_pct * 100:.1f}%**.",
        "",
        "The denominator is every catalyst opportunity `build_event_set` surfaced over the window; "
        "the numerator is the catalyst legs the daily reflex actually filled from the cache. "
        "Abstained legs are un-populated / degraded tickers or holiday-`exit_by` weeks whose bar "
        "landed inside the execution buffer.",
        "",
        "## 4. off_map frequency",
        "",
        f"off_map legs / all daily legs: **{off} / {n_legs} = {off_freq * 100:.1f}%**.",
        "",
        "_off_map = an intraweek move no scenario-table branch covers (the Task-B escalation seam). "
        "State this number explicitly for the Task-B go/no-go — it sizes the off-map reasoning-agent "
        "workload the next step must handle._",
        "",
        "## 5. Plain-English read",
        "",
        _read(weekly, daily, sweep, cov_pct, off_freq),
        "",
        "## 6. MANDATORY latency-interpretation caveat",
        "",
        "The sweep in §2 applies `exit_latency_bars` **globally to ALL exits**. But per the execution "
        "model, on-map stop-loss / take-profit exits are **resting broker-side orders** with ~zero "
        "reasoning latency — only the **off-map** path carries reasoning latency (an agent must think "
        "before it acts). So the §2 latency table is a **pessimistic UPPER BOUND** that over-penalizes "
        "on-map resting exits by charging them a reasoning delay they would never incur live.",
        "",
        "Per-exit-type latency (broker ≈ 0 for on-map SL/TP, reasoning-latency only for off-map) is a "
        "**Step-4 mitigation**. Therefore an edge that looks *globally erased* here must **NOT** be "
        "read as a real failure into the Step-5 go/no-go — a globally-erased edge is a **false-negative "
        "artifact** of applying reasoning latency to broker-side orders, not a real one. Read §2 against "
        "the off_map frequency in §4: the smaller §4 is, the more of §2's degradation is this artifact.",
        "",
    ]
    return "\n".join(lines)


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
        "dropped, never fabricated. Read the §2 latency table strictly through the §6 caveat."
    )


# ------------------------------------------------------------------ live entrypoint
def run(conn, *, start, end):
    embed = lambda *a, **k: None  # noqa: E731 — the mechanical run never invokes the LLM
    provider = make_daily_bars_provider(conn)  # cache-only (allow_fetch=False): frugal, no live calls
    _wk_res, weekly = run_layer_a(conn, embed, start=start, end=end, granularity="weekly")
    daily_res, daily = run_layer_a(conn, embed, start=start, end=end, granularity="daily",
                                   daily_bars_provider=provider)
    sweep = latency_sweep(conn, embed, start=start, end=end, daily_bars_provider=provider,
                          delays=(0, 1, 2))
    cov = coverage(conn, daily_res, start, end)
    offmap = off_map_stats(daily_res)
    return build_findings(window=(start, end), weekly=weekly, daily=daily, sweep=sweep,
                          cov=cov, offmap=offmap)


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
    _wk, weekly = run_layer_a(conn, embed, start=start, end=end, granularity="weekly")
    daily_res, daily = run_layer_a(conn, embed, start=start, end=end, granularity="daily",
                                   daily_bars_provider=fake_provider)
    sweep = latency_sweep(conn, embed, start=start, end=end, daily_bars_provider=fake_provider,
                          delays=(0, 1, 2))
    md = build_findings(window=(start, end), weekly=weekly, daily=daily, sweep=sweep,
                        cov=coverage(conn, daily_res, start, end), offmap=off_map_stats(daily_res))
    print(md)

    for section in ("## 1. Weekly vs Daily", "## 2. Latency", "## 3. Data coverage",
                    "## 4. off_map", "## 5. Plain-English", "## 6. MANDATORY latency"):
        assert section in md, f"missing section: {section}"
    for kw in ("weekly", "daily", "latency", "coverage", "off_map"):
        assert kw.lower() in md.lower(), f"missing keyword: {kw}"
    print("\nrun_daily_backtest --smoke: OK (all six sections present)")
    return 0


def _plus(iso, days):
    from datetime import date, timedelta
    return (date.fromisoformat(iso) + timedelta(days=days)).isoformat()


if __name__ == "__main__":
    sys.exit(main())
