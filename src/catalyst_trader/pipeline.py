"""PIPE-02/07 — the self-heal + health primitives the daemon's run_cycle calls.

Three offline-testable functions, all thin plumbing over the ALREADY-BUILT 6.9 ingest/store paths:

  detect_gaps(conn, universe, window, cadence)  -> {price_weeks_missing, stale_sources, missing_cards}
  backfill(conn, providers, gaps, window)        -> re-feeds the gap set through ingest_history (idempotent)
  write_data_health(conn, source_states, gaps, divergences_this_cycle) -> .monitor/data_health.json

Backfill routes back through the SAME ingest.ingest_history write-path (upsert on the natural key),
so it never bypasses the point-in-time / catalyst-verify guards and a re-run writes no duplicate rows.
`divergences_this_cycle` is an HONEST per-cycle count (captured by run_cycle's log-tap), never a
fabricated rolling window; `coverage_pct` is derived from the PERSISTED price_bar.agreeing_sources.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from pathlib import Path

from catalyst_trader import ingest, store
from catalyst_trader.dates import now_iso
from catalyst_trader.providers import prices, registry  # registry.CADENCE re-exported for callers

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HEALTH_PATH = str(ROOT / ".monitor" / "data_health.json")


def _fridays(start: str, end: str) -> list[str]:
    """The Friday week_end anchors in [start, end] — the coverage denominator."""
    d, end_d = date.fromisoformat(start), date.fromisoformat(end)
    out = []
    while d <= end_d:
        if d.weekday() == 4:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def detect_gaps(conn, universe, window, cadence=None, *, now=None) -> dict:
    """Find the holes the daemon should self-heal:

    - price_weeks_missing: expected (universe x Friday) name-weeks with NO price_bar row.
    - stale_sources:       price sources whose freshest fetch is older than 2x their cadence.
    - missing_cards:       universe names with an upcoming catalyst but no company_card.
    """
    cadence = cadence or registry.CADENCE
    start, end = window
    fridays = _fridays(start, end)

    present: dict[str, set] = {}
    for r in conn.execute("SELECT ticker, week_end FROM price_bar").fetchall():
        present.setdefault(r["ticker"], set()).add(r["week_end"])
    price_weeks_missing = [f"{tk}@{wk}" for tk in universe
                           for wk in fridays if wk not in present.get(tk, set())]

    stale_sources = []
    for r in conn.execute("SELECT source, MAX(retrieved_at) mx FROM price_bar GROUP BY source").fetchall():
        if prices.is_stale(r["mx"], cadence.get("prices", 86_400), now=now):
            stale_sources.append(r["source"])

    universe_set = set(universe)
    missing_cards = []
    for r in conn.execute("SELECT DISTINCT ticker FROM catalyst WHERE event_date >= ?", (end,)).fetchall():
        tk = r["ticker"]
        if tk in universe_set and store.card_asof(conn, tk, end) is None:
            missing_cards.append(tk)

    return {"price_weeks_missing": price_weeks_missing,
            "stale_sources": sorted(stale_sources),
            "missing_cards": sorted(missing_cards)}


def backfill(conn, providers, gaps, window, *, universe_csv="data/seed_universe.csv",
             backfill_weeks=12):
    """Re-feed the gap set through the SAME ingest path with a WIDER window (idempotent via upsert).

    No new write path: backfill just re-runs ingest.ingest_history over a start pushed back
    `backfill_weeks`, so the point-in-time stamp + catalyst-verify guards still apply and a re-run
    writes no duplicate rows. A no-gap cycle is a no-op (no wasted re-ingest)."""
    if not (gaps["price_weeks_missing"] or gaps["missing_cards"]):
        return {"backfilled": False, "reason": "no gaps"}
    start, end = window
    wider_start = (date.fromisoformat(start) - timedelta(weeks=backfill_weeks)).isoformat()
    ingest.ingest_history(conn, start=wider_start, end=end, providers=providers,
                          universe_csv=universe_csv)
    return {"backfilled": True, "window": (wider_start, end)}


def _coverage_pct(conn) -> float:
    """Cross-check coverage: % of persisted bars confirmed by >=2 agreeing sources (a comma in the
    agreeing_sources column). Real, derived from the persisted column — never fabricated."""
    rows = conn.execute("SELECT agreeing_sources FROM price_bar").fetchall()
    total = len(rows)
    if not total:
        return 0.0
    confirmed = sum(1 for r in rows if r["agreeing_sources"] and "," in r["agreeing_sources"])
    return round(100 * confirmed / total, 1)


def write_data_health(conn, source_states, gaps, divergences_this_cycle, *, path=None) -> str:
    """Write .monitor/data_health.json — the pipeline-health snapshot the monitor renders + alerts on.

    {updated, sources:{name:{last_success,consec_fail,degraded}}, coverage_pct, stale_sources, gaps,
     divergences_this_cycle, degraded}. `divergences_this_cycle` is the per-cycle count (passed in
     from the log-tap); `coverage_pct` is derived from the persisted agreeing_sources column."""
    path = path or DEFAULT_HEALTH_PATH
    payload = {
        "updated": now_iso(),
        "sources": source_states,
        "coverage_pct": _coverage_pct(conn),
        "stale_sources": gaps.get("stale_sources", []),
        "gaps": {"price_weeks_missing": len(gaps.get("price_weeks_missing", [])),
                 "missing_cards": len(gaps.get("missing_cards", [])),
                 "stale_sources": len(gaps.get("stale_sources", []))},
        "divergences_this_cycle": divergences_this_cycle,
        "degraded": any(s.get("degraded") for s in source_states.values()),
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=2, default=str))
    return path
