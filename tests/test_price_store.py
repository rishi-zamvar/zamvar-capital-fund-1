"""Point-in-time weekly OHLCV price-bars store (WEEK-02).

The GATING data substrate the weekly thesis engine has no data without. Two money-critical
invariants live here:

1. SURVIVORSHIP-FREE: delisted universe names AND non-universe reference series (XBI) are
   retained and retrievable — a base rate computed only over survivors is a lie.
2. NO LOOK-AHEAD: `bars_asof(conn, ticker, as_of)` never returns a bar dated after `as_of`
   (mirrors universe.build.universe_as_of's "never a future cohort"). This is the single
   property that keeps every Wave-2 base rate honest.

All offline against deterministic synthetic fixtures — no live FMP dependency.
"""

import numpy as np

from catalyst_trader.store import bars_asof, upsert_bars


def _readback(conn, ticker: str) -> list[dict]:
    """Raw chronological readback (Task 1 is decoupled from Task 2's bars_asof)."""
    rows = conn.execute(
        "SELECT open, high, low, close, volume, delisted FROM price_bar "
        "WHERE ticker=? ORDER BY week_end",
        (ticker,),
    ).fetchall()
    return [
        {"open": r["open"], "high": r["high"], "low": r["low"], "close": r["close"],
         "volume": r["volume"], "delisted": bool(r["delisted"])}
        for r in rows
    ]


def _series(ticker: str, start_close: float, n: int, *, seed: int) -> list[dict]:
    """Deterministic weekly OHLCV series: `n` consecutive Mondays from 2024-01-01."""
    rng = np.random.default_rng(seed)
    bars = []
    close = start_close
    week = np.datetime64("2024-01-01")  # a Monday
    for _ in range(n):
        ret = rng.normal(0, 0.03)
        close = close * (1 + ret)
        high = close * (1 + abs(rng.normal(0, 0.01)))
        low = close * (1 - abs(rng.normal(0, 0.01)))
        bars.append({
            "week_end": str(week),
            "open": round(close * (1 - ret), 4),
            "high": round(high, 4),
            "low": round(low, 4),
            "close": round(close, 4),
            "volume": round(float(rng.integers(1_000_000, 5_000_000)), 1),
        })
        week = week + np.timedelta64(7, "D")
    return bars


# --- Task 1: migration + idempotent upsert write-path ----------------------------------------


def test_upsert_bars_round_trips_inserted_ohlcv(db):
    bars = _series("MREV", 10.0, 6, seed=1)
    n = upsert_bars(db, "MREV", bars)
    assert n == 6
    got = _readback(db, "MREV")
    assert len(got) == 6
    # exact OHLCV round-trip on the first bar
    for k in ("open", "high", "low", "close", "volume"):
        assert got[0][k] == bars[0][k]


def test_reupsert_same_week_updates_in_place_idempotent(db):
    bars = _series("MREV", 10.0, 4, seed=2)
    upsert_bars(db, "MREV", bars)
    # re-fetch the same weeks with a corrected close -> UPDATE, not a duplicate row
    bars2 = [dict(b) for b in bars]
    bars2[0]["close"] = 99.99
    upsert_bars(db, "MREV", bars2)
    got = _readback(db, "MREV")
    assert len(got) == 4, "re-upsert must update in place, never duplicate (ticker, week_end)"
    assert got[0]["close"] == 99.99


def test_xbi_reference_ticker_round_trips_like_any_name(db):
    # XBI is a non-universe reference series — the beta benchmark. It is just another ticker.
    bars = _series("XBI", 90.0, 5, seed=3)
    upsert_bars(db, "XBI", bars, source="fixture")
    got = _readback(db, "XBI")
    assert len(got) == 5


def test_delisted_bar_is_stored_and_retrievable(db):
    # survivorship-free: a delisted name's price history stays queryable.
    bars = _series("DEAD", 5.0, 3, seed=4)
    upsert_bars(db, "DEAD", bars, delisted=True)
    got = _readback(db, "DEAD")
    assert len(got) == 3
    assert all(b["delisted"] is True for b in got)


# --- Task 2: point-in-time bars_asof (no look-ahead) -----------------------------------------


def test_bars_asof_never_returns_a_future_bar(db):
    # THE look-ahead gate. Insert 8 weekly bars from 2024-01-01; the 5th week_end is 2024-01-29.
    bars = _series("MREV", 10.0, 8, seed=5)
    upsert_bars(db, "MREV", bars)
    as_of = "2024-01-29"  # week_end of the 5th bar
    got = bars_asof(db, "MREV", as_of)
    assert [b["week_end"] for b in got] == [b["week_end"] for b in bars[:5]]
    assert all(b["week_end"] <= as_of for b in got), "bars_asof must NEVER leak a bar after as_of"
    # chronological
    weeks = [b["week_end"] for b in got]
    assert weeks == sorted(weeks)


def test_bars_asof_between_weeks_excludes_the_future(db):
    bars = _series("MREV", 10.0, 8, seed=6)
    upsert_bars(db, "MREV", bars)
    # an as_of that falls between bar 3 (2024-01-15) and bar 4 (2024-01-22)
    got = bars_asof(db, "MREV", "2024-01-18")
    assert len(got) == 3
    assert got[-1]["week_end"] == "2024-01-15"


def test_bars_asof_returns_delisted_history(db):
    # survivorship-free at the point-in-time read too.
    bars = _series("DEAD", 5.0, 5, seed=7)
    upsert_bars(db, "DEAD", bars, delisted=True)
    got = bars_asof(db, "DEAD", "2099-01-01")
    assert len(got) == 5
    assert all(b["delisted"] is True for b in got)


def test_bars_asof_lookback_weeks_returns_most_recent_n(db):
    bars = _series("MREV", 10.0, 10, seed=8)
    upsert_bars(db, "MREV", bars)
    got = bars_asof(db, "MREV", "2099-01-01", lookback_weeks=3)
    assert len(got) == 3
    # the most recent 3, still chronological, still <= as_of
    assert [b["week_end"] for b in got] == [b["week_end"] for b in bars[-3:]]


def test_synthetic_seeded_series_is_deterministic_and_round_trips(db):
    # the deterministic fixture Wave-2 base-rate tests rely on: same seed -> same series.
    a = _series("XBI", 90.0, 6, seed=9)
    b = _series("XBI", 90.0, 6, seed=9)
    assert a == b, "seeded synthetic series must be reproducible for Wave-2 base rates"
    upsert_bars(db, "XBI", a)
    got = bars_asof(db, "XBI", "2099-01-01")
    assert [x["close"] for x in got] == [x["close"] for x in a]
