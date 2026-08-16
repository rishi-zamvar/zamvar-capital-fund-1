"""Friday week_end anchor + daily->weekly resampler (providers/_weekly.py).

The ONE non-obvious correctness requirement of the multi-source design (RESEARCH §4):
every price source MUST emit `week_end` on the SAME Friday anchor before cross-check and
before upsert, or UNIQUE(ticker, week_end) mis-aligns and cross-check silently compares
different real weeks. Pure offline unit tests, no network.

Calendar refs (2026): 2026-01-05 Mon, 2026-01-07 Wed, 2026-01-09 Fri, 2026-01-11 Sun.
"""

from datetime import date, datetime

from catalyst_trader.providers._weekly import friday_week_end, resample_daily_to_weekly


def test_friday_week_end_from_monday():
    assert friday_week_end("2026-01-05") == "2026-01-09"


def test_friday_week_end_from_friday_is_identity():
    assert friday_week_end("2026-01-09") == "2026-01-09"


def test_friday_week_end_from_midweek():
    assert friday_week_end("2026-01-07") == "2026-01-09"


def test_friday_week_end_accepts_date_and_datetime():
    assert friday_week_end(date(2026, 1, 5)) == "2026-01-09"
    assert friday_week_end(datetime(2026, 1, 7, 16, 0)) == "2026-01-09"


def test_resample_empty_in_empty_out():
    assert resample_daily_to_weekly([]) == []


def test_resample_groups_daily_into_weekly():
    daily = [
        {"week_end": "2026-01-05", "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 100.0},
        {"week_end": "2026-01-06", "open": 10.5, "high": 12.0, "low": 10.0, "close": 11.5, "volume": 200.0},
        {"week_end": "2026-01-07", "open": 11.5, "high": 11.8, "low": 10.8, "close": 11.0, "volume": 150.0},
        {"week_end": "2026-01-08", "open": 11.0, "high": 13.0, "low": 10.5, "close": 12.5, "volume": 300.0},
        {"week_end": "2026-01-09", "open": 12.5, "high": 12.9, "low": 12.0, "close": 12.8, "volume": 250.0},
    ]
    weekly = resample_daily_to_weekly(daily)
    assert len(weekly) == 1
    bar = weekly[0]
    assert bar["week_end"] == "2026-01-09"
    assert bar["open"] == 10.0       # first day's open
    assert bar["high"] == 13.0       # max
    assert bar["low"] == 9.5         # min
    assert bar["close"] == 12.8      # last day's close
    assert bar["volume"] == 1000.0   # sum


def test_resample_partial_week():
    # holiday-shortened week (4 days), still one bar on the Friday
    daily = [
        {"week_end": "2026-01-06", "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5, "volume": 100.0},
        {"week_end": "2026-01-07", "open": 10.5, "high": 11.5, "low": 10.0, "close": 11.0, "volume": 120.0},
        {"week_end": "2026-01-08", "open": 11.0, "high": 12.0, "low": 10.8, "close": 11.8, "volume": 130.0},
        {"week_end": "2026-01-09", "open": 11.8, "high": 12.2, "low": 11.5, "close": 12.0, "volume": 140.0},
    ]
    weekly = resample_daily_to_weekly(daily)
    assert len(weekly) == 1
    bar = weekly[0]
    assert bar["week_end"] == "2026-01-09"
    assert bar["open"] == 10.0
    assert bar["high"] == 12.2
    assert bar["low"] == 9.0
    assert bar["close"] == 12.0
    assert bar["volume"] == 490.0


def test_all_sources_agree_on_anchor():
    # yfinance 1wk indexes the week by its MONDAY; a daily series is per-day.
    # Both must land on the identical Friday week_end for the SAME real week.
    yf_weekly_point_monday = "2026-01-05"
    daily_series = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]
    anchor_from_yf = friday_week_end(yf_weekly_point_monday)
    anchors_from_daily = {friday_week_end(d) for d in daily_series}
    assert anchors_from_daily == {anchor_from_yf} == {"2026-01-09"}
