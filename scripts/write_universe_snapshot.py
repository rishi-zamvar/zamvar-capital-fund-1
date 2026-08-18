"""A2 — write the 73-name backward universe cohort, knowable throughout the backtest.

Membership is backward/hindsight (decided from realized moves) — by design the no-look-ahead rule
applies to PRICES + CATALYSTS, not universe membership. So the cohort is stamped as_of_date +
recorded_at = the day BEFORE the backtest start, making book.universe() return all 73 at every week.
Forces include (min_* = 0) since the 73 are already movement-screened. Idempotent-ish (append-only;
re-run writes a fresh cohort at the same as_of_date — dedupe by wiping that as_of_date first).
"""
import json, sqlite3
from catalyst_trader.universe import build

DROP = {"CMRX", "BXRXQ", "LIANY"}
AS_OF = "2025-08-16"                 # day before backtest start 2025-08-17
STAMP = "2025-08-16T00:00:00+00:00"  # recorded_at: knowable from the start
DB = "catalyst.db"

prof = json.load(open("data/universe_profiles.json"))
live = [r for r in prof if r["ticker"] not in DROP]
seed_rows = [{
    "ticker": r["ticker"],
    "company_name": (r.get("profile") or {}).get("company") or r.get("company"),
    "market_cap": None, "adv_usd": None,
    "therapeutic_area": (r.get("profile") or {}).get("indication"),
    "delisted": "false",
} for r in live]

conn = sqlite3.connect(DB); conn.row_factory = sqlite3.Row
# wipe any prior cohort at this as_of_date so re-runs don't stack
conn.execute("DELETE FROM universe_snapshot WHERE as_of_date=?", (AS_OF,)); conn.commit()

n = build.build_snapshot(conn, AS_OF, seed_rows,
                         criteria={"min_catalyst_density": 0, "min_market_cap": 0, "min_adv_usd": 0})
# build_snapshot stamps recorded_at=now; restamp to the early knowable date for this cohort
conn.execute("UPDATE universe_snapshot SET recorded_at=? WHERE as_of_date=?", (STAMP, AS_OF))
conn.commit()
print(f"wrote cohort as_of={AS_OF}: {n} included / {len(seed_rows)} seeded", flush=True)

# audit via the serving gateway at 3 cutoffs inside the backtest year
from catalyst_trader import serving
for cutoff in ("2025-09-01", "2026-01-15", "2026-08-10"):
    book = serving.asof(conn, cutoff=cutoff, latency_cfg=None)
    u = book.universe(cutoff)
    print(f"  gateway universe @ {cutoff}: {len(u)} names", flush=True)
open("scripts/.a2_snapshot.done", "w").write(json.dumps({"included": n, "seeded": len(seed_rows)}))
