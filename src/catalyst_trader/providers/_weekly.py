"""Shared Friday week_end anchor + daily->weekly resampler for the multi-source price cascade.

RESEARCH §4 — the ONE non-obvious correctness requirement of the multi-source design. Price
sources disagree on how they index a week: yfinance `1wk` indexes by the week's MONDAY;
Nasdaq/Tiingo/AV-daily are per-day. If they upsert on different anchors, UNIQUE(ticker,
week_end) mis-aligns and cross-check silently compares different real weeks. Every source MUST
route through friday_week_end() BEFORE cross-check and BEFORE upsert so the same calendar week
maps to ONE identical week_end. Pure Python — no pandas.
"""

from datetime import date, datetime
from itertools import groupby


def friday_week_end(d) -> str:
    """ISO date of THAT week's Friday (the shared anchor).

    Accepts an ISO string, date, or datetime. The week is Mon..Sun (ISO); the Friday within it
    is the anchor. A Monday-indexed weekly bar (yfinance) and any weekday of the same real week
    all map to the identical Friday.
    """
    if isinstance(d, str):
        d = date.fromisoformat(d)
    elif isinstance(d, datetime):
        d = d.date()
    # weekday(): Mon=0 .. Sun=6; Friday=4. Shift to this Mon-Sun week's Friday.
    return d.fromordinal(d.toordinal() + (4 - d.weekday())).isoformat()


def resample_daily_to_weekly(daily_bars: list[dict]) -> list[dict]:
    """Bucket daily OHLCV bar dicts into one weekly bar per Friday week_end.

    open=first day's open, high=max, low=min, close=last day's close, volume=sum. Output bars
    carry week_end=the Friday. Total + deterministic: empty in -> empty out; a holiday-shortened
    week still yields one bar keyed on that week's Friday. Days are ordered by their raw week_end
    before aggregation so first/last are the true chronological open/close.
    """
    if not daily_bars:
        return []
    ordered = sorted(daily_bars, key=lambda b: b["week_end"])
    weekly = []
    for friday, group in groupby(ordered, key=lambda b: friday_week_end(b["week_end"])):
        days = list(group)
        highs = [b["high"] for b in days if b.get("high") is not None]
        lows = [b["low"] for b in days if b.get("low") is not None]
        volumes = [b["volume"] for b in days if b.get("volume") is not None]
        weekly.append({
            "week_end": friday,
            "open": days[0].get("open"),
            "high": max(highs) if highs else None,
            "low": min(lows) if lows else None,
            "close": days[-1]["close"],
            "volume": sum(volumes) if volumes else None,
        })
    return weekly
