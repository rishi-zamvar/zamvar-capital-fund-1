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
raises into the pipeline or fabricates a bar — miss/no-key/degrade all return [].
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

    The endpoint is asset-class-partitioned: an ETF (XBI, LABD, ...) returns NO rows under
    ``assetclass=stocks``, so we fall through to ``assetclass=etf``. Without this the sector
    reference XBI silently has zero bars and the whole beta/thesis_scan sleeve goes dark
    (live-shakedown finding).
    """
    url = f"https://api.nasdaq.com/api/quote/{ticker}/historical"
    rows = []
    for assetclass in ("stocks", "etf"):
        params = {"assetclass": assetclass, "fromdate": start, "todate": end, "limit": "9999"}
        data = get_json("nasdaq", url, params=params, ua="browser")
        rows = ((data or {}).get("data") or {}).get("tradesTable", {}).get("rows") or []
        if rows:
            break
    if not rows:
        return []
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


# ---- the cascade: ranked registry + cross-check/fallback ----------------------------------

# Grade rank: keyed GREEN first (Alpha Vantage, Tiingo — [] when unkeyed, so simply skipped),
# then always-on YELLOW (yfinance + Nasdaq = the zero-config default cross-check pair). Stooq is
# excluded (disabled). Order IS the grade rank: the first provider that has a given week_end is
# the highest-grade source for that week.
PRICE_PROVIDERS = [_av_weekly, _tiingo_eod, _yf_weekly, _nasdaq_daily]


def get_weekly_bars(ticker, start, end, *, providers=PRICE_PROVIDERS, tol_pct=0.5):
    """Cross-checked, provenance-tagged weekly bars for one ticker (the price substrate).

    Iterates the ranked `providers` (highest grade first), skipping any source that returns []
    (no key / degrade / miss). Bars are indexed by the shared Friday `week_end` (Plan 02 anchor)
    so only the SAME real week is ever compared. For each week_end:

      - >=2 sources agree within `tol_pct` (abs(a-b)/a on close) -> high-confidence: keep the
        highest-grade source's bar, `agreeing_sources` = every source within tolerance.
      - any source diverges beyond `tol_pct` -> log a structured warning (ticker, week_end,
        per-source closes, max delta), keep the highest-grade source's bar, and narrow
        `agreeing_sources` to just the sources that agreed with it (single -> unconfirmed).
      - one source only -> keep it, `agreeing_sources` = that one source (unconfirmed).
      - NO available source has the week -> the bar is ABSENT (not in the output). Never
        synthesized / fabricated / back-filled — a missing week is a degrade, not a guess.

    Returns a chronological list of bar dicts each carrying `source`, `source_grade`, and an
    `agreeing_sources` set, ready for upsert_bars(..., source_grade=, agreeing_sources=).
    """
    # week_end -> bars in provider-rank order (index 0 = highest-grade source for that week).
    by_week: dict[str, list[dict]] = {}
    for fetch in providers:
        try:
            bars = fetch(ticker, start, end)
        except Exception as exc:  # a source failing must not sink the cascade — skip + degrade
            logger.warning(
                "price source %s failed for %s: %s", getattr(fetch, "__name__", fetch), ticker, exc
            )
            continue
        for b in bars or []:
            # A bar without a close is not a usable price observation — a source returning
            # close=None (Yahoo NaN rows, an incomplete current week) is a DEGRADE, not data.
            # Drop it here so it can never (a) become the cross-check reference and be emitted with
            # close=None (NOT NULL crash in upsert_bars), (b) trip a None-arithmetic TypeError in
            # the divergence delta, or (c) masquerade as a genuine cross-source divergence.
            if b.get("close") is None:
                continue
            by_week.setdefault(b["week_end"], []).append(b)

    tol = tol_pct / 100.0
    out = []
    for week_end in sorted(by_week):
        candidates = by_week[week_end]  # already highest-grade first
        ref = candidates[0]
        ref_close = ref["close"]
        agreeing = [ref]  # the reference always agrees with itself
        divergent = []
        for b in candidates[1:]:
            if ref_close and abs(b["close"] - ref_close) / abs(ref_close) <= tol:
                agreeing.append(b)
            else:
                divergent.append(b)
        if divergent:
            deltas = [abs(b["close"] - ref_close) / abs(ref_close) for b in candidates] if ref_close else []
            logger.warning(
                "price cross-check divergence %s %s: closes=%s max_delta=%.4f%%",
                ticker,
                week_end,
                {b["_source"]: b["close"] for b in candidates},
                (max(deltas) * 100) if deltas else 0.0,
            )
        out.append({
            "week_end": week_end,
            "open": ref.get("open"),
            "high": ref.get("high"),
            "low": ref.get("low"),
            "close": ref["close"],
            "volume": ref.get("volume"),
            "source": ref["_source"],
            "source_grade": ref["_grade"],
            "agreeing_sources": {b["_source"] for b in agreeing},
        })
    return out
