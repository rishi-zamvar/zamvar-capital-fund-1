"""Point-in-time universe builder (DATA-06).

Append-only by construction: each build writes a NEW `as_of_date` cohort and never
overwrites a prior one, so Phase 7's backtest is survivorship-free. Delisted names
are retained (`delisted=1`). Inclusion is driven by explicit criteria — catalyst
density (counted from the `catalyst` table), market cap, and liquidity (ADV $) —
and a name that fails a threshold is written `included=0` with a reason, never
silently dropped.

FMP-live enrichment of market_cap/adv_usd is a documented follow-up (RESEARCH
## Environment Availability): criteria degrade gracefully to the curated seed CSV.
"""

import csv
import json
import sqlite3
from calendar import monthrange
from pathlib import Path

from catalyst_trader.models import UniverseSnapshot

SEED_CSV = Path(__file__).resolve().parents[3] / "data" / "seed_universe.csv"

# ponytail: these are tuning knobs, not law. Start conservative; recalibrate once
# FMP-live market-cap/ADV enrichment lands. Override per-call via `criteria`.
DEFAULT_DENSITY_MONTHS = 6
DEFAULT_MIN_CATALYST_DENSITY = 1  # must have >=1 upcoming catalyst in the window
DEFAULT_MIN_MARKET_CAP = 200_000_000  # $200M — exclude micro-caps
DEFAULT_MIN_ADV_USD = 1_000_000  # $1M avg daily $ volume — liquidity floor


def _add_months(as_of: str, months: int) -> str:
    """Return the ISO date `months` after `as_of` (YYYY-MM-DD), clamping day-of-month."""
    y, m, d = (int(x) for x in as_of.split("-"))
    total = y * 12 + (m - 1) + months
    ny, nm0 = divmod(total, 12)
    nm = nm0 + 1
    return f"{ny:04d}-{nm:02d}-{min(d, monthrange(ny, nm)[1]):02d}"


def _num(v) -> float | None:
    if v is None or str(v).strip() == "":
        return None
    return float(v)


def _truthy(v) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y"}


def _load_seed(path: str | Path = SEED_CSV) -> list[dict]:
    """Read the seed CSV, skipping blank lines and `#` comments (template header)."""
    text = Path(path).read_text()
    lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    return [dict(r) for r in csv.DictReader(lines)]


def _catalyst_density(conn: sqlite3.Connection, ticker: str, as_of: str, window_end: str) -> int:
    """Count catalyst rows for `ticker` with event_date in [as_of, window_end].

    ISO date strings sort lexically, so mixed-precision dates (YYYY / YYYY-MM /
    YYYY-MM-DD) compare correctly against the window bounds.
    """
    return conn.execute(
        "SELECT COUNT(*) AS n FROM catalyst WHERE ticker=? AND event_date >= ? AND event_date <= ?",
        (ticker, as_of, window_end),
    ).fetchone()["n"]


def build_snapshot(
    conn: sqlite3.Connection,
    as_of_date: str,
    seed_rows: list[dict] | None = None,
    *,
    criteria: dict | None = None,
) -> int:
    """Write an append-only `as_of_date` universe cohort; return the count of included names.

    seed_rows columns: ticker, company_name, market_cap, adv_usd, therapeutic_area, delisted.
    Loaded from `data/seed_universe.csv` when omitted. Never overwrites a prior cohort.
    """
    criteria = criteria or {}
    density_months = criteria.get("density_months", DEFAULT_DENSITY_MONTHS)
    min_density = criteria.get("min_catalyst_density", DEFAULT_MIN_CATALYST_DENSITY)
    min_market_cap = criteria.get("min_market_cap", DEFAULT_MIN_MARKET_CAP)
    min_adv_usd = criteria.get("min_adv_usd", DEFAULT_MIN_ADV_USD)

    if seed_rows is None:
        seed_rows = _load_seed()

    window_end = _add_months(as_of_date, density_months)
    included_count = 0

    for r in seed_rows:
        ticker = r["ticker"].strip()
        market_cap = _num(r.get("market_cap"))
        adv_usd = _num(r.get("adv_usd"))
        therapeutic_area = (r.get("therapeutic_area") or "").strip() or None
        delisted = _truthy(r.get("delisted"))
        density = _catalyst_density(conn, ticker, as_of_date, window_end)

        reasons: list[str] = []
        if delisted:
            reasons.append("delisted (retained for backtest)")
        if density < min_density:
            reasons.append(f"catalyst_density {density} < {min_density}")
        if market_cap is not None and market_cap < min_market_cap:
            reasons.append(f"market_cap {market_cap:.0f} < {min_market_cap:.0f}")
        if adv_usd is not None and adv_usd < min_adv_usd:
            reasons.append(f"adv_usd {adv_usd:.0f} < {min_adv_usd:.0f}")

        included = 0 if reasons else 1
        criteria_json = json.dumps(
            {
                "catalyst_density": density,
                "market_cap": market_cap,
                "adv_usd": adv_usd,
                "therapeutic_area": therapeutic_area,
            }
        )
        conn.execute(
            "INSERT INTO universe_snapshot "
            "(as_of_date, ticker, included, delisted, criteria_json, reason) VALUES (?,?,?,?,?,?)",
            (as_of_date, ticker, included, 1 if delisted else 0, criteria_json,
             "; ".join(reasons) if reasons else None),
        )
        included_count += included

    conn.commit()
    return included_count


def universe_as_of(conn: sqlite3.Connection, as_of: str) -> list[UniverseSnapshot]:
    """Return the cohort from the latest as_of_date <= `as_of` (never a future cohort)."""
    latest = conn.execute(
        "SELECT MAX(as_of_date) AS d FROM universe_snapshot WHERE as_of_date <= ?", (as_of,)
    ).fetchone()["d"]
    if latest is None:
        return []
    rows = conn.execute(
        "SELECT * FROM universe_snapshot WHERE as_of_date=? ORDER BY ticker", (latest,)
    ).fetchall()
    return [
        UniverseSnapshot(
            as_of_date=r["as_of_date"],
            ticker=r["ticker"],
            included=bool(r["included"]),
            delisted=bool(r["delisted"]),
            criteria_json=r["criteria_json"],
            reason=r["reason"],
        )
        for r in rows
    ]
