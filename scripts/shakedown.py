"""INGEST-05 — the LIVE shakedown. NOT a pytest test (project rule: zero live API in the suite).

`python -m scripts.shakedown` live-ingests the real seed universe over the free sources, then runs
the mechanical Layer-A backtest (`run_layer_a`) + `thesis_scan` on the ingested REAL data end-to-end,
and emits a structured edge-case report. The offline proxy `tests/test_shakedown_offline.py` proves
the IDENTICAL wiring against fixtures — that is the pytest phase gate; this script is the operator-
directed verification.

The whole point: stress-test everything built in Phase 6.9 on the redundant, cross-checked free feed.
Degrade-never-crash, never-fabricate (a degraded source is a LOGGED edge case, not an invented value),
and surface `tradeable_catalyst_count` as a first-class line so a thin/vacuous backtest (few catalysts
had >=2 free in-window sources) is SURFACED honestly, never hidden.
"""

from __future__ import annotations

import functools
import json
import logging
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from catalyst_trader import db as _db
from catalyst_trader import ingest, store
from catalyst_trader.backtest.engine import run_layer_a
from catalyst_trader.config import settings
from catalyst_trader.quant import weekly as qw
from catalyst_trader.universe import build as universe_build

logger = logging.getLogger(__name__)

_PKG_LOGGER = "catalyst_trader"  # every provider/cascade warning propagates here
_STALE_SI_DAYS = 45              # FINRA is bi-monthly + ~T+9 business days -> normal age <~30d
EDGE_KEYS = ("illiquid", "missing_bars", "divergence_count", "stale", "delisting",
             "ticker_mismatch", "gaps", "rate_limit", "tradeable_catalyst_count")


# --- the edge-case tap: read the structured warnings the cascade ALREADY logs -----------------


class _EdgeCapture(logging.Handler):
    """Captures WARNING+ records emitted anywhere under the `catalyst_trader` package during the
    live ingest and buckets them by the message each provider already logs — no new instrumentation,
    we just tap the honest degrade/divergence warnings already in the code."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record):
        try:
            self.messages.append(record.getMessage())
        except (TypeError, ValueError):  # a broken format string must never sink the shakedown
            self.messages.append(record.msg if isinstance(record.msg, str) else repr(record.msg))

    def matching(self, *needles):
        return [m for m in self.messages if any(n in m for n in needles)]


# --- helpers ----------------------------------------------------------------------------------


def _fridays(start: str, end: str) -> list[str]:
    """The Friday week_end anchors in [start, end] — the coverage denominator."""
    d, end_d = date.fromisoformat(start), date.fromisoformat(end)
    out = []
    while d <= end_d:
        if d.weekday() == 4:  # Fri
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _latest_week(conn) -> str | None:
    row = conn.execute("SELECT MAX(week_end) w FROM price_bar").fetchone()
    return row["w"] if row else None


def _edge_report(conn, capture: _EdgeCapture, seed: list[dict], start: str, end: str) -> dict:
    """Assemble the structured edge-case report from the ingested store + the captured warnings."""
    listed = [r["ticker"] for r in seed if not r["delisted"]]
    listed_set = set(listed)
    fridays = set(_fridays(start, end))

    present = conn.execute("SELECT ticker, week_end FROM price_bar").fetchall()
    weeks_by_ticker: dict[str, set[str]] = {}
    for row in present:
        weeks_by_ticker.setdefault(row["ticker"], set()).add(row["week_end"])

    # coverage over the LISTED names (delisted retained but not part of the expected denominator)
    expected = len(fridays) * len(listed)
    present_listed = sum(
        len(weeks & fridays) for tk, weeks in weeks_by_ticker.items() if tk in listed_set
    )
    coverage_pct = round(100 * present_listed / expected, 1) if expected else 0.0

    ticker_mismatch = sorted(tk for tk in listed if not weeks_by_ticker.get(tk))
    partial = {tk: weeks_by_ticker[tk] & fridays
               for tk in listed if weeks_by_ticker.get(tk) and (weeks_by_ticker[tk] & fridays) != fridays}
    missing_bars = sorted(partial)
    # gaps: the specific (ticker, friday) holes for names that DO have some bars (holiday/tz/anchor)
    gap_pairs = [(tk, wk) for tk, weeks in partial.items() for wk in sorted(fridays - weeks)]

    delisting = sorted(r["ticker"] for r in seed if r["delisted"])

    # tradeable_catalyst_count — the honesty line: verified AND point-in-time-valid inside [start,end]
    tradeable = [c for c in store.tradeable_catalysts(conn)
                 if c.last_verified_at and start <= c.last_verified_at <= end]

    # illiquid / stale — read the persisted card per listed name at end (latest <= end)
    illiquid, stale = [], []
    for tk in listed:
        card = store.card_asof(conn, tk, end)
        if not card:
            continue
        if card.get("options", {}).get("options_liquid") is False:  # quote present, gate rejected
            illiquid.append(tk)
        si_date = card.get("positioning", {}).get("si_settlement_date")
        if si_date:
            try:
                age = (date.fromisoformat(end) - date.fromisoformat(str(si_date)[:10])).days
                if age > _STALE_SI_DAYS:
                    stale.append({"ticker": tk, "si_settlement_date": si_date, "age_days": age})
            except (ValueError, TypeError):
                pass

    # cross-check redundancy: how many bars were confirmed by >=2 agreeing sources vs single-source
    # (the honest measure of whether the "redundant cross-checked feed" actually cross-checked).
    prov = conn.execute("SELECT source, agreeing_sources FROM price_bar").fetchall()
    confirmed = sum(1 for r in prov if r["agreeing_sources"] and "," in r["agreeing_sources"])
    bars_by_source = Counter(r["source"] for r in prov)

    divergences = capture.matching("cross-check divergence")
    rate_limit = capture.matching("429", "Too Many", "rate limit", "RateLimit")
    # "returning None"/"no CIK" catch the provider-level degrades that don't say "degraded"
    # (e.g. EDGAR: no ticker->CIK map -> every name dark) so the report doesn't undercount them.
    degraded = Counter(m for m in capture.matching(
        "degraded", "failed", "returning None", "no CIK")
        if "cross-check divergence" not in m)

    return {
        "coverage": {"expected_name_weeks": expected, "present_name_weeks": present_listed,
                     "pct": coverage_pct, "fridays_in_window": len(fridays),
                     "listed_names": len(listed)},
        "cross_check": {"total_bars": len(prov), "confirmed_2plus": confirmed,
                        "unconfirmed_single": len(prov) - confirmed,
                        "confirmed_pct": round(100 * confirmed / len(prov), 1) if prov else 0.0,
                        "bars_by_source": dict(bars_by_source)},
        "tradeable_catalyst_count": len(tradeable),
        "tradeable_catalysts": [{"ticker": c.ticker, "type": c.catalyst_type.value,
                                 "event_date": c.event_date, "last_verified_at": c.last_verified_at}
                                for c in tradeable],
        "illiquid": sorted(illiquid),
        "missing_bars": missing_bars,
        "divergence_count": len(divergences),
        "divergences": divergences[:50],
        "stale": stale,
        "delisting": delisting,
        "ticker_mismatch": ticker_mismatch,
        "gaps": {"count": len(gap_pairs), "sample": [f"{tk}@{wk}" for tk, wk in gap_pairs[:30]]},
        "rate_limit": len(rate_limit),
        "degraded": {"unique": len(degraded), "total": sum(degraded.values()),
                     "by_message": dict(degraded.most_common(20))},
    }


def run_shakedown(conn, embed, providers, *, start, end,
                  universe_csv="data/seed_universe.csv") -> dict:
    """The SHARED orchestration exercised by BOTH the offline test (stub providers + in-memory conn)
    and the live `main` (real providers): ingest the seed universe -> build the point-in-time universe
    cohort -> run_layer_a + thesis_scan on the ingested data -> a structured edge-case report incl.
    the first-class `tradeable_catalyst_count`. Degrade-never-crash; never fabricate.
    """
    seed = ingest._load_seed(universe_csv)

    # (1) live-ingest, tapping the cascade's warnings for divergence/degrade/rate-limit edge cases.
    capture = _EdgeCapture()
    pkg_log = logging.getLogger(_PKG_LOGGER)
    pkg_log.addHandler(capture)
    try:
        ingest_stats = ingest.ingest_history(conn, start=start, end=end, providers=providers,
                                             universe_csv=universe_csv)
    finally:
        pkg_log.removeHandler(capture)

    # (2) build the point-in-time universe cohort so run_layer_a's event set sees the real universe.
    # (build_event_set reads universe_as_of; without a cohort the statistical sleeve gets nothing.)
    seed_rows = universe_build._load_seed(universe_csv)
    if not universe_build.universe_as_of(conn, start):
        universe_build.build_snapshot(conn, start, seed_rows)

    # (3) run_layer_a on the ingested REAL data (reused unchanged). A ValueError (no results/legs)
    # is surfaced honestly, not swallowed as a fake zero baseline.
    try:
        results, dist = run_layer_a(conn, embed, start=start, end=end)
        backtest = {"distribution": dist.model_dump(), "n_weeks": len(results)}
    except ValueError as exc:
        backtest = {"error": str(exc)}

    # (4) thesis_scan shape on the latest ingested week, over the full seed universe. thesis_scan
    # can raise (e.g. XBI sector-reference bars missing) — that is itself an edge case, surfaced,
    # NOT a crash of the shakedown (degrade-never-crash).
    scan = {"week_end": None, "n_rows": 0, "n_eligible": 0}
    week = _latest_week(conn)
    if week is not None:
        params = _load_params(conn)
        try:
            rows = qw.thesis_scan([r["ticker"] for r in seed], week, store, conn,
                                  params=params).detail["rows"]
            scan = {"week_end": week, "n_rows": len(rows),
                    "n_eligible": sum(1 for r in rows if r["eligible"]),
                    "by_type": dict(Counter(r["thesis_type"] for r in rows))}
        except (ValueError, KeyError) as exc:
            scan = {"week_end": week, "n_rows": 0, "n_eligible": 0, "error": str(exc)}

    report = _edge_report(conn, capture, seed, start, end)
    report["window"] = {"start": start, "end": end}
    report["ingest_stats"] = ingest_stats
    report["backtest"] = backtest
    report["thesis_scan"] = scan
    return report


def _load_params(conn):
    from catalyst_trader import kb
    return kb.load_params(conn, "weekly")


# --- the LIVE wiring (real providers) ---------------------------------------------------------


def _recent_si_settlement(end: str) -> str:
    """The most recent FINRA settlement date (15th / EOM) published by `end` (~T+9 business days).
    Picks the latest of {15th, month-end} that is >= 12 calendar days before end."""
    from calendar import monthrange
    e = date.fromisoformat(end)
    cutoff = e - timedelta(days=12)
    candidates = []
    for back in range(3):  # this month + two prior
        y, m = e.year, e.month - back
        while m <= 0:
            y, m = y - 1, m + 12
        candidates.append(date(y, m, 15))
        candidates.append(date(y, m, monthrange(y, m)[1]))
    valid = sorted(d for d in candidates if d <= cutoff)
    return valid[-1].isoformat()


def _live_providers(end: str) -> dict:
    """Wire the REAL free providers into the ingest seam. Each degrades to None/[] independently
    (ingest._safe / the cascade), so a missing key or a source outage is a LOGGED edge case.

    The per-ticker datum providers (options/finra/edgar) are week-INVARIANT but ingest_history calls
    them once per (ticker, week_end); memoize per ticker so a degrading endpoint isn't re-hit 52x
    (a shakedown-run optimization — the data is genuinely per-ticker; _http already caches successes,
    this also caches the degrade so a dead source is queried once, not weekly)."""

    from catalyst_trader.providers import (
        clinicaltrials,
        edgar,
        finra,
        fmp,
        options_cboe,
        pdufa,
        prices,
    )
    si_date = _recent_si_settlement(end)

    @functools.cache
    def _options(tk):
        return options_cboe.fetch(tk)

    @functools.cache
    def _finra(tk):
        return finra.fetch(tk, si_date)

    @functools.cache
    def _edgar(tk):
        return edgar.fetch(tk)

    return {
        "prices": lambda tk, s, e: prices.get_weekly_bars(tk, s, e),
        "options": _options,
        "finra": _finra,
        "edgar": _edgar,
        "financials": None,  # FMP fundamentals slot — optional (Plan 07 documented degrade)
        "clinicaltrials": lambda tks, s, e: clinicaltrials.fetch_trial_readouts(tks, s, e),
        "earnings": lambda tks, s, e: fmp.fetch_earnings(tks, s, e),  # RuntimeError if no key -> _safe
        "pdufa": lambda tks, s, e, company_map=None: pdufa.fetch(tks, s, e, company_map=company_map),
    }


def _window(weeks: int = 52) -> tuple[str, str]:
    """[start, end] Friday-anchored: `weeks` back from the most recent COMPLETED Friday."""
    today = datetime.now().astimezone().date()
    # most recent Friday strictly before today (a completed week)
    end_d = today - timedelta(days=((today.weekday() - 4) % 7) or 7)
    start_d = end_d - timedelta(weeks=weeks - 1)
    return start_d.isoformat(), end_d.isoformat()


def _source_availability() -> dict:
    """Which GREEN/keyed sources are active vs absent this run (honest provenance for the report)."""
    return {
        "alpha_vantage (GREEN price)": bool(settings.alpha_vantage_api_key),
        "tiingo (GREEN price)": bool(settings.tiingo_api_key),
        "fmp (earnings)": bool(settings.fmp_api_key),
        "sec_user_agent (EDGAR)": bool(settings.sec_user_agent),
        "yfinance+nasdaq (always-on price)": True,
    }


def _print_report(report: dict, availability: dict) -> None:
    w, cov, bt = report["window"], report["coverage"], report["backtest"]
    print("\n" + "=" * 78)
    print(f"  LIVE SHAKEDOWN (INGEST-05)  {w['start']} .. {w['end']}")
    print("=" * 78)
    print("\nSource availability:")
    for name, on in availability.items():
        print(f"  [{'ON ' if on else 'off'}] {name}")
    print("\nIngest:", report["ingest_stats"])
    print(f"\nCoverage: {cov['present_name_weeks']}/{cov['expected_name_weeks']} name-weeks "
          f"= {cov['pct']}%  ({cov['listed_names']} listed x {cov['fridays_in_window']} Fridays)")
    xc = report["cross_check"]
    print(f"Cross-check: {xc['confirmed_2plus']}/{xc['total_bars']} bars confirmed by >=2 sources "
          f"({xc['confirmed_pct']}%); bars_by_source={xc['bars_by_source']}")
    print(f"\nTRADEABLE-CATALYST-COUNT: {report['tradeable_catalyst_count']}  "
          "(verified + point-in-time-valid inside the window — the honesty line)")
    for c in report["tradeable_catalysts"]:
        print(f"    - {c['ticker']} {c['type']} event={c['event_date']} verified@{c['last_verified_at']}")

    print("\nLayer-A baseline distribution (real data):")
    if "distribution" in bt:
        for k, v in bt["distribution"].items():
            print(f"    {k:20s} {v}")
    else:
        print(f"    (no baseline) {bt.get('error')}")

    sc = report["thesis_scan"]
    print(f"\nthesis_scan @ {sc['week_end']}: {sc['n_rows']} rows, {sc['n_eligible']} eligible, "
          f"by_type={sc.get('by_type')}")

    print("\nEdge cases:")
    print(f"    ticker_mismatch (0 bars):     {report['ticker_mismatch']}")
    print(f"    missing_bars (partial):       {report['missing_bars']}")
    print(f"    gaps (holiday/tz holes):      {report['gaps']['count']}  {report['gaps']['sample'][:8]}")
    print(f"    cross-source divergences:     {report['divergence_count']}")
    for d in report["divergences"][:8]:
        print(f"        · {d}")
    print(f"    illiquid options (gate=False):{report['illiquid']}")
    print(f"    stale FINRA SI (>{_STALE_SI_DAYS}d):    {report['stale']}")
    print(f"    delisted (retained):          {report['delisting']}")
    print(f"    rate-limit hits:              {report['rate_limit']}")
    deg = report["degraded"]
    print(f"    degraded-source warnings:     {deg['total']} ({deg['unique']} distinct)")
    for msg, n in deg["by_message"].items():
        print(f"        · x{n}  {msg}")
    print("=" * 78 + "\n")


def main() -> dict:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    start, end = _window()
    availability = _source_availability()

    conn = _db.connect(":memory:")
    _db.migrate(conn)
    try:
        report = run_shakedown(conn, None, _live_providers(end), start=start, end=end)
    finally:
        conn.close()

    report["source_availability"] = availability
    _print_report(report, availability)

    out = Path(__file__).resolve().parents[1] / ".planning" / "phases" / \
        "06.9-free-data-ingestion-layer" / "06.9-08-shakedown-report.json"
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"Report artifact: {out}")
    return report


if __name__ == "__main__":
    main()
