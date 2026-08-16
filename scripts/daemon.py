"""PIPE-01 — the always-on data daemon: a THIN `--once` entrypoint over a stateless `run_cycle`.

`run_cycle` does ONE full pass then exits — fetch (via the shared provider registry) -> snapshot
(auto via _http) -> UPSERT (the existing ingest/store paths, unchanged) -> detect_gaps -> backfill
-> write .monitor/data_health.json — then RETURNS. There is NO long-lived loop and NO queue:
launchd is the supervisor + crash-recovery, and store idempotency is the resumability (a double-run
writes no duplicate rows; a mid-cycle crash just re-runs cleanly).

  .venv/bin/python scripts/daemon.py --once     # one accuracy-first cycle (what launchd runs)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

# allow `python scripts/daemon.py` (no package install) to find catalyst_trader
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from catalyst_trader import db as _db  # noqa: E402
from catalyst_trader import ingest, pipeline  # noqa: E402
from catalyst_trader.config import settings  # noqa: E402
from catalyst_trader.providers import prices, registry  # noqa: E402

logger = logging.getLogger(__name__)


class _DivergenceTap(logging.Handler):
    """Count the cross-check divergence warnings the cascade ALREADY logs during THIS cycle — the
    same log-tap the shakedown uses. An HONEST per-cycle count, not a rolling window over
    unpersisted logger.warning lines."""

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.divergences = 0

    def emit(self, record):
        try:
            if "cross-check divergence" in record.getMessage():
                self.divergences += 1
        except Exception:  # a broken format string must never sink the cycle
            pass


def _window(weeks: int, now: datetime) -> tuple[str, str]:
    """[start, end] Friday-anchored: `weeks` back from the most recent COMPLETED Friday before now."""
    today = now.date()
    end_d = today - timedelta(days=((today.weekday() - 4) % 7) or 7)
    start_d = end_d - timedelta(weeks=weeks - 1)
    return start_d.isoformat(), end_d.isoformat()


def _prev_source_states(health_path: str | None) -> dict:
    """The previous cycle's per-source states (for consec_fail continuity) — {} on first run."""
    try:
        with open(health_path or pipeline.DEFAULT_HEALTH_PATH, encoding="utf-8") as f:
            return json.load(f).get("sources", {})
    except Exception:
        return {}


def _source_states(conn, cadence, now, prev) -> dict:
    """Per-source health from the PERSISTED price_bar fetch timestamps: last_success (freshest
    retrieved_at), degraded (fetch older than 2x cadence — a dead/degrading source), and consec_fail
    carried forward from the previous cycle (reset to 0 on a fresh success).

    Health is keyed off EVERY source that participated in the cross-check (the agreeing_sources set),
    not just the emitted REFERENCE source. yfinance is always the highest-grade of the always-on pair
    so it is always the ref — grouping by the `source` column alone made nasdaq (a cross-check partner
    on ~all bars) invisible, so a silently-dying partner would never show as degraded. Reading
    agreeing_sources surfaces every real participant."""
    last: dict[str, str] = {}
    for r in conn.execute("SELECT source, agreeing_sources, retrieved_at FROM price_bar").fetchall():
        srcs = {s for s in (r["agreeing_sources"] or "").split(",") if s} | {r["source"]}
        for s in srcs:
            if r["retrieved_at"] and r["retrieved_at"] > last.get(s, ""):
                last[s] = r["retrieved_at"]
    states = {}
    for source, mx in last.items():
        stale = prices.is_stale(mx, cadence.get("prices", 86_400), now=now)
        prev_fail = (prev.get(source) or {}).get("consec_fail", 0)
        states[source] = {"last_success": mx,
                          "consec_fail": (prev_fail + 1) if stale else 0,
                          "degraded": stale}
    return states


def run_cycle(conn, providers=None, cadence=None, *, universe_csv="data/seed_universe.csv",
              window_weeks: int = 52, now: datetime | None = None, health_path=None) -> dict:
    """ONE idempotent, crash-safe pass: ingest the seed universe over the accuracy-first window
    through the existing 6.9 ingest/store/cascade paths, self-heal (detect_gaps -> backfill through
    the SAME ingest path), tap the cycle's cross-check divergences, then write data_health.json and
    RETURN. A degraded source never raises into the cycle (ingest._safe / the cascade fail over);
    it is recorded in data_health.json, never fatal."""
    now = now or datetime.now(timezone.utc)
    cadence = cadence or registry.CADENCE
    start, end = _window(window_weeks, now)
    if providers is None:
        providers = registry.build_providers(settings, end=end)
    universe = [r["ticker"] for r in ingest._load_seed(universe_csv)]

    tap = _DivergenceTap()
    pkg = logging.getLogger("catalyst_trader")
    pkg.addHandler(tap)
    try:
        ingest.ingest_history(conn, start=start, end=end, providers=providers,
                              universe_csv=universe_csv)
        gaps = pipeline.detect_gaps(conn, universe, (start, end), cadence, now=now)
        pipeline.backfill(conn, providers, gaps, (start, end), universe_csv=universe_csv)
        gaps = pipeline.detect_gaps(conn, universe, (start, end), cadence, now=now)  # post-heal snapshot
    finally:
        pkg.removeHandler(tap)

    source_states = _source_states(conn, cadence, now, _prev_source_states(health_path))
    path = pipeline.write_data_health(conn, source_states, gaps, tap.divergences, path=health_path)
    return {"window": (start, end), "gaps": gaps,
            "divergences_this_cycle": tap.divergences, "data_health": path}


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description="Fund 1 always-on data daemon (one --once cycle).")
    ap.add_argument("--once", action="store_true",
                    help="run exactly one cycle and exit (the only mode — launchd supervises)")
    ap.parse_args(argv)  # --once is the default/only behaviour; parse for a clean CLI + --help
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    conn = _db.connect(settings.db_path)
    _db.migrate(conn)
    try:
        result = run_cycle(conn)
    finally:
        conn.close()
    print(json.dumps(result, default=str))
    return result


if __name__ == "__main__":
    main()
