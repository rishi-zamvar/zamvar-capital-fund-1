"""Operator-directed LIVE universe expansion (Phase 06.12, Plan 03) — real feeds, real cohort.

Runs the full discover -> screen -> size_to_density -> build_universe path against the LIVE free
feeds (CT.gov v2 + unfiltered efts + price cascade + CBOE + edgartools) and writes a REAL
append-only, survivorship-free `universe_as_of` cohort of sourced (not hand-picked) names, plus an
honest JSON evidence report. OUTSIDE pytest (real network); never runs in CI.

Design (6.10 don't-babysit directive): this script is LAUNCHED in the background by the orchestrator
and touches a `<report>.done` signal on completion; the orchestrator waits on the signal and
re-engages. The script itself just runs to completion and writes the signal — no daemonization here.

Blocker-1/3 guard: the report carries build_snapshot's `included_count` (rows actually written
included=1) as the gated field, and cross-checks it against the count of included==1 rows read back
from `universe_as_of` — so an "N~80 but empty store" outcome is caught, not masked.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
from pathlib import Path

from catalyst_trader import db as _db
from catalyst_trader.universe import discover
from catalyst_trader.universe.build import universe_as_of

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

REPORT = Path(".planning/phases/06.12-universe-expansion/06.12-03-live-expand-report.json")
DONE = Path(str(REPORT) + ".done")

# move_threshold tuning knob (median catalyst move floor); override to hit the ~80 target.
MOVE_THRESHOLD = float(os.environ.get("MOVE_THRESHOLD", "0.10"))


def main() -> int:
    as_of = _dt.date.today().isoformat()
    print(f"=== LIVE UNIVERSE EXPANSION — as_of {as_of} — target_lambda 1.75 "
          f"move_threshold {MOVE_THRESHOLD} ===")
    DONE.unlink(missing_ok=True)  # clear any stale signal before the run

    conn = _db.connect("catalyst.db")
    _db.migrate(conn)
    # Clean re-run: drop any as_of=today cohort rows left by earlier debug runs so today's
    # authoritative cohort is written once (append-only across DAYS stays survivorship-free).
    conn.execute("DELETE FROM universe_snapshot WHERE as_of_date=?", (as_of,))
    conn.commit()
    try:
        summary = discover.build_universe(
            conn, as_of, target_lambda=1.75, criteria={"move_threshold": MOVE_THRESHOLD}
        )
        # Blocker-1/3 cross-check: the store's own included==1 count MUST equal included_count.
        cohort = universe_as_of(conn, as_of)
        store_included = [u.ticker for u in cohort if u.included]
        summary["store_included_count"] = len(store_included)
        summary["store_included_tickers"] = sorted(store_included)
        summary["reconciles"] = len(store_included) == summary.get("included_count")
    finally:
        conn.close()

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(summary, indent=2, default=str))

    inc = summary.get("included_count")
    print(json.dumps({
        "as_of": as_of,
        "n_candidates": summary.get("n_candidates"),
        "n_screened": summary.get("n_screened"),
        "n_admitted": summary.get("n_admitted"),
        "included_count": inc,
        "store_included_count": summary.get("store_included_count"),
        "reconciles": summary.get("reconciles"),
        "measured_lambda": summary.get("measured_lambda"),
        "target_reached": summary.get("target_reached"),
        "n_rejected": summary.get("n_rejected"),
    }, indent=2, default=str))
    print(f"\nFull report: {REPORT}")
    print("=== LIVE UNIVERSE EXPANSION COMPLETE ===")

    DONE.write_text(f"done {as_of} included_count={inc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
