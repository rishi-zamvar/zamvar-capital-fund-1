"""One-shot 1-year mechanical (Layer-A) backtest on REAL data.

Reuses the shakedown machinery (ingest_history -> run_layer_a) over a 52-week window on the
PERSISTENT catalyst.db (which already holds multi-year price history). Earnings are disabled for
this run: the earnings provider makes one Nasdaq call PER DAY (~365/yr) -- slow + stall-prone --
and earnings are NOT the +/-30-70% biotech catalyst this fund trades (CT.gov readouts + PDUFA are).
Result: a leak-free mechanical baseline on real historical CT.gov-readout + EDGAR-PDUFA catalysts.
Honest: if the tradeable-catalyst count is thin on the current 19-name universe, the go/no-go gate
says NO-GO -- that is the signal that the universe expansion (Phase 6.12) is needed, not a failure.
"""
from __future__ import annotations
import json
import logging
from pathlib import Path

from catalyst_trader import db as _db
from scripts.shakedown import run_shakedown, _live_providers, _window

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

WEEKS = 52
start, end = _window(WEEKS)
print(f"=== 1-YEAR MECHANICAL (Layer-A) BACKTEST — real data — window {start} .. {end} ===")

conn = _db.connect("catalyst.db")
_db.migrate(conn)
providers = _live_providers(end)
providers["earnings"] = None  # skip slow per-day earnings calls; not the target catalyst
try:
    rep = run_shakedown(conn, None, providers, start=start, end=end)
finally:
    conn.close()

summary = {
    "window": rep.get("window"),
    "coverage_pct": rep.get("coverage", {}).get("pct"),
    "cross_check": rep.get("cross_check"),
    "tradeable_catalyst_count": rep.get("tradeable_catalyst_count"),
    "tradeable_catalysts": rep.get("tradeable_catalysts"),
    "catalysts": rep.get("catalysts"),
    "backtest": rep.get("backtest"),
    "thesis_scan": rep.get("thesis_scan"),
    "degraded": rep.get("degraded"),
}
out = Path(".planning/backtest-1yr-result.json")
out.write_text(json.dumps(rep, indent=2, default=str))
print(json.dumps(summary, indent=2, default=str))
print(f"\nFull report: {out}")
print("=== BACKTEST RUN COMPLETE ===")
