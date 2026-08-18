"""Synthetic-history fixture helper — deterministic, fully offline backtest seed.

`seed_history` writes a multi-week weekly-OHLCV history (incl. delisted names whose
history is RETAINED — survivorship-free) + dated, verified catalysts (each stamped
with a realistic `last_verified_at`) + the per-as_of universe cohort, all through the
SHIPPED writers (store.upsert_bars LIST-arg, store.insert_catalyst, universe.build.
build_snapshot) — never raw SQL. Every backtest test seeds through this so the suite
runs with zero network / zero live API.

The price walk mirrors tests/test_price_store.py::_series (seeded numpy RNG), so the
same args produce byte-identical bars.
"""

from __future__ import annotations

import zlib
from datetime import date, timedelta

import numpy as np

from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    CatalystType,
    DatePrecision,
    SourceOrigin,
    SourceType,
    Status,
    Uncertainty,
)
from catalyst_trader.store import insert_catalyst, upsert_bars
from catalyst_trader.universe.build import build_snapshot

_MONDAY = "2024-01-01"  # a Monday — matches _series


def week_ends(n: int, *, start: str = _MONDAY) -> list[str]:
    """N consecutive weekly Mondays (ISO) from `start` — the deterministic week cursor."""
    d0 = date.fromisoformat(start)
    return [(d0 + timedelta(days=7 * i)).isoformat() for i in range(n)]


def _series(ticker: str, weeks: list[str], *, start_close: float, seed: int) -> list[dict]:
    """Deterministic weekly OHLCV for `ticker` across the given week_end dates.

    Mirrors test_price_store::_series: a seeded Gaussian random walk, so identical
    (ticker, weeks, start_close, seed) yields byte-identical bars.
    """
    rng = np.random.default_rng(seed)
    close = start_close
    bars = []
    for wk in weeks:
        ret = rng.normal(0, 0.03)
        close = close * (1 + ret)
        high = close * (1 + abs(rng.normal(0, 0.01)))
        low = close * (1 - abs(rng.normal(0, 0.01)))
        bars.append({
            "week_end": wk,
            "open": round(close * (1 - ret), 4),
            "high": round(high, 4),
            "low": round(low, 4),
            "close": round(close, 4),
            "volume": round(float(rng.integers(1_000_000, 5_000_000)), 1),
        })
    return bars


def _seed_for(ticker: str) -> int:
    """Stable per-ticker RNG seed so each name gets a distinct-but-reproducible walk.

    crc32 (not builtin hash) — builtin str hash is PYTHONHASHSEED-salted per process,
    which would break the cross-run byte-identical guarantee.
    """
    return zlib.crc32(ticker.encode()) % (2**31)


def seed_history(
    conn,
    *,
    tickers,
    weeks,
    delisted=(),
    catalysts=(),
    start: str = _MONDAY,
    start_close: float = 10.0,
) -> list[str]:
    """Seed a deterministic offline multi-week history; return the list of week_end dates.

    Args:
        tickers: names to give a weekly OHLCV series.
        weeks: an int (N Mondays from `start`) or an explicit list of week_end ISO dates.
        delisted: subset of `tickers` marked delisted — their bars carry delisted=True and
            their history is RETAINED (survivorship-free); still present in the universe cohort.
        catalysts: iterable of dicts, each:
            {"ticker", "event_date",
             "catalyst_type"?=pdufa, "last_verified_at"?=override,
             "verified_days_before"?=5}
            Inserted verified (is_tradeable passes) and stamped with last_verified_at
            (default a few days before event_date; override to push it AFTER a week for a
            look-ahead test).
        start_close/start: price-walk anchor.
    """
    wk_list = week_ends(weeks, start=start) if isinstance(weeks, int) else list(weeks)
    delisted_set = set(delisted)

    # 1) price bars through the shipped LIST-arg writer (delisted history retained)
    for tk in tickers:
        bars = _series(tk, wk_list, start_close=start_close, seed=_seed_for(tk))
        upsert_bars(conn, tk, bars, delisted=(tk in delisted_set))

    # 2) one append-only universe cohort at the first week (universe_as_of returns it for
    #    every later week). density/liquidity criteria are disabled so every seeded name —
    #    including delisted — lands in the cohort (survivorship-free).
    seed_rows = [
        {"ticker": tk, "company_name": tk, "market_cap": None, "adv_usd": None,
         "therapeutic_area": None, "delisted": (tk in delisted_set)}
        for tk in tickers
    ]
    build_snapshot(
        conn, wk_list[0], seed_rows,
        criteria={"min_catalyst_density": 0, "min_market_cap": 0, "min_adv_usd": 0},
    )
    # Bitemporal bridge (07.6): build_snapshot stamps recorded_at=now_iso() (correct for LIVE, where
    # a cohort built today IS knowable today), but this fixture fabricates a HISTORICAL cohort — so
    # backdate its knowable time to its contemporaneous as_of_date (mirrors migration 011's backfill).
    # Without this, the gateway would gate a 2024 cohort on a 2026 recorded_at and deny it at replay.
    conn.execute("UPDATE universe_snapshot SET recorded_at = as_of_date")
    conn.commit()

    # 3) dated, verified catalysts stamped with last_verified_at
    for spec in catalysts:
        event_date = spec["event_date"]
        lva = spec.get("last_verified_at")
        if lva is None:
            days = spec.get("verified_days_before", 5)
            lva = (date.fromisoformat(event_date) - timedelta(days=days)).isoformat()
        c = Catalyst(
            ticker=spec["ticker"],
            company_name=spec["ticker"],
            catalyst_type=spec.get("catalyst_type", CatalystType.pdufa),
            event_date=event_date,
            date_precision=DatePrecision.day,
            uncertainty_type=Uncertainty.firm,
            status=Status.verified,
            source_origin=SourceOrigin.curated_pdufa,
            last_verified_at=lva,
            external_ref=f"{spec['ticker']}:{event_date}",
            sources=[CatalystSource(
                source_name="FDA",
                source_url="https://www.fda.gov/x",
                source_type=SourceType.primary,
                reported_date=event_date,
                date_type="actual",
                retrieved_at=f"{lva}T00:00:00Z",
            )],
        )
        insert_catalyst(conn, c)
        # insert_catalyst stamps the version's knowable time = last_verified_at (07.6), so the
        # gateway's catalyst gate is contemporaneous with the fixture — no manual backdate needed.
    conn.commit()

    return wk_list


def _self_check() -> None:
    """Smoke test the other tasks build on: seed → read back through the shipped guards."""
    from catalyst_trader import db as _db
    from catalyst_trader.store import bars_asof, tradeable_catalysts
    from catalyst_trader.universe.build import universe_as_of

    conn = _db.connect(":memory:")
    _db.migrate(conn)
    wk = seed_history(
        conn,
        tickers=["AAAA", "DEAD"],
        weeks=6,
        delisted=["DEAD"],
        catalysts=[{"ticker": "AAAA", "event_date": wk3}
                   for wk3 in [week_ends(6)[3]]],
    )

    # delisted name's history is RETAINED and readable point-in-time
    dead = bars_asof(conn, "DEAD", wk[-1])
    assert len(dead) == 6, dead
    assert all(b["delisted"] is True for b in dead), "delisted history must be retained"

    # a live name reads back, no future bar leaks
    live = bars_asof(conn, "AAAA", wk[2])
    assert len(live) == 3, live
    assert all(b["week_end"] <= wk[2] for b in live)

    # universe cohort contains both names (survivorship-free)
    names = {u.ticker for u in universe_as_of(conn, wk[-1])}
    assert names == {"AAAA", "DEAD"}, names

    # the seeded catalyst is tradeable AND carries a stamped last_verified_at
    cats = tradeable_catalysts(conn)
    assert len(cats) == 1, cats
    c = cats[0]
    assert c.ticker == "AAAA" and c.status == Status.verified
    assert c.last_verified_at is not None and c.last_verified_at < c.event_date

    # determinism: same args → byte-identical bars
    conn2 = _db.connect(":memory:")
    _db.migrate(conn2)
    seed_history(conn2, tickers=["AAAA", "DEAD"], weeks=6, delisted=["DEAD"])
    assert bars_asof(conn2, "AAAA", wk[-1]) == bars_asof(conn, "AAAA", wk[-1])

    conn.close()
    conn2.close()
    print("synth_history self-check: OK")


if __name__ == "__main__":
    _self_check()
