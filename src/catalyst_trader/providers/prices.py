"""Per-source RAW/unadjusted weekly price fetchers for the multi-source cascade.

The operator correction that shaped this file: prices are NOT yfinance-only. Each source is a
plain module-level `fetch_weekly_bars(ticker, start, end) -> list[dict]` returning RAW OHLCV
weekly bars anchored to the shared Friday week_end (providers/_weekly). RAW is the whole point:
adjusted prices bake FUTURE corporate-action knowledge (splits/dividends) into a historical bar
= look-ahead into the backtest. So yfinance runs with auto_adjust=False + raw Close; Alpha
Vantage uses TIME_SERIES_WEEKLY (never _ADJUSTED); Tiingo reads `close` (never `adjClose`).

Grades: always-on YELLOW = yfinance + Nasdaq (zero-config default). Keyed GREEN = Alpha Vantage
+ Tiingo, which return [] when their key is absent so the cascade simply skips them. Stooq is
registered-but-disabled (IP proof-of-work wall from this machine, RESEARCH §1). Nothing here
raises into the pipeline or imputes — miss/no-key/degrade all return [].
"""

import logging

import yfinance as yf

from catalyst_trader.config import settings
from catalyst_trader.providers._http import get_json
from catalyst_trader.providers._weekly import friday_week_end, resample_daily_to_weekly

logger = logging.getLogger(__name__)


def _f(x):
    """Parse a Nasdaq/AV price string ('$10.50', '1,000') or number to float; None on junk."""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).replace("$", "").replace(",", "").strip()
    if not s or s in ("--", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _yf_weekly(ticker, start, end, *, downloader=yf.download):
    """yfinance 1wk RAW bars (YELLOW, always-on). auto_adjust=False -> raw Close, not Adj Close.

    Monday-indexed weekly rows are re-anchored to that week's Friday. Empty/None frame -> [];
    a malformed row is skipped+logged, never crashes the fetch. downloader is injectable so the
    suite runs fully offline.
    """
    df = downloader(
        ticker, start=start, end=end, interval="1wk", auto_adjust=False, progress=False
    )
    if df is None or df.empty:
        return []
    bars = []
    for idx, row in df.iterrows():
        try:
            close = row["Close"]  # RAW — NOT "Adj Close" (that is the look-ahead trap)
            if close is None or (isinstance(close, float) and close != close):  # NaN guard
                continue
            bars.append({
                "week_end": friday_week_end(idx.date() if hasattr(idx, "date") else idx),
                "open": _f(row["Open"]),
                "high": _f(row["High"]),
                "low": _f(row["Low"]),
                "close": _f(close),
                "volume": _f(row["Volume"]),
                "_source": "yfinance",
                "_grade": "yellow",
            })
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("yfinance row skipped for %s (%s)", ticker, exc)
    return bars


def _nasdaq_daily(ticker, start, end):
    """Nasdaq historical JSON -> RAW daily bars resampled to Friday weeks (YELLOW, always-on).

    Prices are '$'-prefixed strings, unadjusted. Fetched via _http with a browser UA (the host
    403s non-browser agents); a degrade (None from _http) -> [].
    """
    url = f"https://api.nasdaq.com/api/quote/{ticker}/historical"
    params = {"assetclass": "stocks", "fromdate": start, "todate": end, "limit": "9999"}
    data = get_json("nasdaq", url, params=params, ua="browser")
    if not data:
        return []
    rows = (data.get("data") or {}).get("tradesTable", {}).get("rows") or []
    daily = []
    for r in rows:
        close = _f(r.get("close"))
        if close is None:
            continue
        # Nasdaq date is MM/DD/YYYY -> ISO for the anchor.
        m, d, y = r["date"].split("/")
        daily.append({
            "week_end": f"{y}-{m}-{d}",
            "open": _f(r.get("open")),
            "high": _f(r.get("high")),
            "low": _f(r.get("low")),
            "close": close,
            "volume": _f(r.get("volume")),
        })
    weekly = resample_daily_to_weekly(daily)
    for b in weekly:
        b["_source"] = "nasdaq"
        b["_grade"] = "yellow"
    return weekly


def _av_weekly(ticker, start, end):
    """Alpha Vantage TIME_SERIES_WEEKLY RAW bars (GREEN, keyed).

    Uses the NON-adjusted function on purpose (TIME_SERIES_WEEKLY, never ..._ADJUSTED) and reads
    "4. close" (never "5. adjusted close") — adjusted = look-ahead. [] when the key is absent so
    the cascade skips it, or on _http degrade. Native weekly series re-anchored to Friday and
    windowed to [start, end].
    """
    key = settings.alpha_vantage_api_key
    if key is None:
        return []
    url = "https://www.alphavantage.co/query"
    params = {"function": "TIME_SERIES_WEEKLY", "symbol": ticker, "apikey": key}
    data = get_json("alpha_vantage", url, params=params, ua="browser")
    if not data:
        return []
    series = data.get("Weekly Time Series") or {}
    bars = []
    for day, row in series.items():
        week_end = friday_week_end(day)
        if week_end < start or week_end > end:
            continue
        close = _f(row.get("4. close"))  # RAW close — NOT "5. adjusted close"
        if close is None:
            continue
        bars.append({
            "week_end": week_end,
            "open": _f(row.get("1. open")),
            "high": _f(row.get("2. high")),
            "low": _f(row.get("3. low")),
            "close": close,
            "volume": _f(row.get("6. volume")),
            "_source": "alpha_vantage",
            "_grade": "green",
        })
    bars.sort(key=lambda b: b["week_end"])
    return bars


def _tiingo_eod(ticker, start, end):
    """Tiingo EOD daily RAW bars resampled to Friday weeks (GREEN, keyed).

    Reads `close/open/high/low/volume` — NEVER `adjClose`/`adj*` (those bake in future
    corporate actions). [] when the key is absent or on _http degrade.
    """
    key = settings.tiingo_api_key
    if key is None:
        return []
    url = f"https://api.tiingo.com/tiingo/daily/{ticker}/prices"
    params = {"token": key, "startDate": start, "endDate": end}
    data = get_json("tiingo", url, params=params, ua="browser")
    if not data:
        return []
    daily = []
    for row in data:
        close = _f(row.get("close"))  # RAW close — NOT row["adjClose"]
        if close is None:
            continue
        daily.append({
            "week_end": str(row["date"])[:10],  # ISO datetime -> YYYY-MM-DD
            "open": _f(row.get("open")),
            "high": _f(row.get("high")),
            "low": _f(row.get("low")),
            "close": close,
            "volume": _f(row.get("volume")),
        })
    weekly = resample_daily_to_weekly(daily)
    for b in weekly:
        b["_source"] = "tiingo"
        b["_grade"] = "green"
    return weekly


def _stooq(ticker, start, end):
    # ponytail: registered-but-disabled; IP proof-of-work wall from this machine (RESEARCH §1);
    # re-enable if reachable from another egress (the shape would mirror _nasdaq_daily: CSV EOD
    # via _http, RAW OHLCV, resample_daily_to_weekly, _source="stooq"/_grade="yellow").
    return []
