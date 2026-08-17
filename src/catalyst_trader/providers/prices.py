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
import statistics
from datetime import datetime, timezone

import pandas as pd
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
    # yfinance 1.6.0 returns MultiIndex (field, ticker) columns even for a single ticker, so
    # row["Close"] would be a Series (the ticker sub-level), not a scalar — the NaN guard never
    # fires and every bar comes back all-None. Flatten to the field level so row["Close"] is a
    # scalar again. Handle both MultiIndex (real) and flat (defensive) column shapes.
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(axis=1, level=1)
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


def _yf_daily(ticker, start, end, *, downloader=yf.download):
    """yfinance 1d RAW bars (YELLOW, always-on) for the event-window move computation.

    The reliable free multi-year DAILY source (Tiingo needs a key; Nasdaq's free daily doesn't
    serve historical windows — verified live 2026-08-17, both return [] for 2024 dates). auto_adjust
    =False -> raw Close (never Adj Close, the look-ahead trap). Each bar is keyed on its raw TRADE
    date in `week_end` (the daily fetchers' convention, so get_daily_bars' per-date cross-check
    applies unchanged). Empty/None frame -> []; a malformed row is skipped+logged. downloader is
    injectable so the suite runs fully offline.
    """
    df = downloader(
        ticker, start=start, end=end, interval="1d", auto_adjust=False, progress=False
    )
    if df is None or df.empty:
        return []
    if isinstance(df.columns, pd.MultiIndex):  # yfinance 1.6.0 MultiIndex, as in _yf_weekly
        df = df.droplevel(axis=1, level=1)
    bars = []
    for idx, row in df.iterrows():
        try:
            close = row["Close"]  # RAW — NOT "Adj Close"
            if close is None or (isinstance(close, float) and close != close):  # NaN guard
                continue
            d = idx.date() if hasattr(idx, "date") else idx
            bars.append({
                "week_end": d.isoformat() if hasattr(d, "isoformat") else str(d),  # raw trade date
                "open": _f(row["Open"]),
                "high": _f(row["High"]),
                "low": _f(row["Low"]),
                "close": _f(close),
                "volume": _f(row["Volume"]),
                "_source": "yfinance",
                "_grade": "yellow",
            })
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("yfinance daily row skipped for %s (%s)", ticker, exc)
    return bars


def _nasdaq_daily_bars(ticker, start, end):
    """Nasdaq historical JSON -> RAW *daily* bars (the pre-resample list), YELLOW, always-on.

    Prices are '$'-prefixed strings, unadjusted. Fetched via _http with a browser UA (the host
    403s non-browser agents); a degrade (None from _http) -> [].

    The endpoint is asset-class-partitioned: an ETF (XBI, LABD, ...) returns NO rows under
    ``assetclass=stocks``, so we fall through to ``assetclass=etf``. Without this the sector
    reference XBI silently has zero bars and the whole beta/thesis_scan sleeve goes dark
    (live-shakedown finding). Each bar's `week_end` is the raw TRADE date (ISO) — resampling to
    Friday weeks (get_weekly_bars) or keeping it daily (get_daily_bars) is the caller's choice.
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
        # Nasdaq date is MM/DD/YYYY -> ISO trade date.
        m, d, y = r["date"].split("/")
        daily.append({
            "week_end": f"{y}-{m}-{d}",
            "open": _f(r.get("open")),
            "high": _f(r.get("high")),
            "low": _f(r.get("low")),
            "close": close,
            "volume": _f(r.get("volume")),
            "_source": "nasdaq",
            "_grade": "yellow",
        })
    return daily


def _nasdaq_daily(ticker, start, end):
    """Nasdaq RAW daily bars resampled to Friday weeks (YELLOW). Weekly wrapper over the daily fetch."""
    weekly = resample_daily_to_weekly(_nasdaq_daily_bars(ticker, start, end))
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


def _tiingo_daily_bars(ticker, start, end):
    """Tiingo EOD RAW *daily* bars (the pre-resample list), GREEN, keyed.

    Reads `close/open/high/low/volume` — NEVER `adjClose`/`adj*` (those bake in future
    corporate actions). [] when the key is absent or on _http degrade. `week_end` is the raw
    trade date (ISO).
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
            "week_end": str(row["date"])[:10],  # ISO datetime -> YYYY-MM-DD trade date
            "open": _f(row.get("open")),
            "high": _f(row.get("high")),
            "low": _f(row.get("low")),
            "close": close,
            "volume": _f(row.get("volume")),
            "_source": "tiingo",
            "_grade": "green",
        })
    return daily


def _tiingo_eod(ticker, start, end):
    """Tiingo EOD daily RAW bars resampled to Friday weeks (GREEN). Weekly wrapper over the daily fetch."""
    weekly = resample_daily_to_weekly(_tiingo_daily_bars(ticker, start, end))
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

# The ONLY daily-capable providers (keyed GREEN Tiingo first, then always-on YELLOW Nasdaq). These
# return RAW DAILY bars (the pre-resample list) so a T-1->T+2 close-to-close event move is computed
# at daily granularity. CRITICAL: get_daily_bars must NOT route through PRICE_PROVIDERS — its rank-0
# `_av_weekly` returns Friday WEEKLY bars and `_yf_weekly` uses interval='1wk', so a move computed
# off those would be a SILENT weekly-close corruption of the screen's central metric.
# Daily-capable subset for get_daily_bars. yfinance daily is the reliable always-on multi-year
# source (Tiingo keyless-degrades; Nasdaq's free daily doesn't serve historical windows — verified
# live). Ranked GREEN-first: Tiingo (if keyed) -> yfinance daily -> Nasdaq daily.
DAILY_PROVIDERS = [_tiingo_daily_bars, _yf_daily, _nasdaq_daily_bars]


def get_weekly_bars(ticker, start, end, *, providers=PRICE_PROVIDERS, tol_pct=0.5):
    """Cross-checked, provenance-tagged weekly bars for one ticker (the price substrate).

    Iterates the ranked `providers` (highest grade first), skipping any source that returns []
    (no key / degrade / miss). Bars are indexed by the shared Friday `week_end` (Plan 02 anchor)
    so only the SAME real week is ever compared. For each week_end (research §2.3):

      - >=3 sources -> N-source median triangulation: the median close is the consensus PROBE;
        the in-tolerance set = sources within `tol_pct` of it; keep the HIGHEST-GRADE in-tolerance
        source's REAL bar, `agreeing_sources` = that in-tolerance set. Robust to one bad source
        (even when it is the highest grade). Out-of-tolerance sources are excluded + logged.
      - >=3 sources but an EVEN-N no-consensus split (e.g. 2-2) leaves the median BETWEEN clusters
        and the in-tolerance set EMPTY -> DEGRADE: keep the highest-grade source's bar,
        `agreeing_sources` = {that one source}, log unconfirmed. Never no-bar, never the median.
      - 2 sources -> unchanged pairwise: agree within tol -> both in `agreeing_sources`; diverge
        -> keep the highest-grade bar, narrow to one (unconfirmed).
      - 1 source -> keep it, `agreeing_sources` = that one (unconfirmed).
      - NO available source has the week -> the bar is ABSENT (not in the output). Never
        synthesized / fabricated / back-filled — a missing week is a degrade, not a guess.

    The median is used ONLY to SELECT the agreeing set; the emitted close is ALWAYS a real source
    bar, never the median (and never a between-clusters value). Returns a chronological list of
    bar dicts each carrying `source`, `source_grade`, and an `agreeing_sources` set, ready for
    upsert_bars(..., source_grade=, agreeing_sources=).
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
        candidates = by_week[week_end]  # already highest-grade first (provider rank)
        if len(candidates) >= 3:
            # N-source median triangulation. The median is only a SELECTION probe — the in-tol set
            # is every source within tol of it. `candidates` order is preserved so agreeing[0] is
            # the highest-grade in-tol source. An outlier (even the highest-grade one) falls out.
            med = statistics.median(b["close"] for b in candidates)
            agreeing = [b for b in candidates if med and abs(b["close"] - med) / abs(med) <= tol]
            if not agreeing:
                # even-N no-consensus split: median between clusters, in-tol set empty. Degrade to
                # the highest-grade source as unconfirmed — never no-bar, never the median value.
                agreeing = [candidates[0]]
        else:
            # <=2 sources: unchanged 6.9 pairwise vs the highest-grade reference.
            ref_close = candidates[0]["close"]
            agreeing = [candidates[0]]
            for b in candidates[1:]:
                if ref_close and abs(b["close"] - ref_close) / abs(ref_close) <= tol:
                    agreeing.append(b)
        ref = agreeing[0]  # highest-grade agreeing source's REAL bar (never a synthesized value)
        agreeing_srcs = {b["_source"] for b in agreeing}
        divergent = [b for b in candidates if b["_source"] not in agreeing_srcs]
        if divergent:
            closes = [b["close"] for b in candidates]
            lo, hi = min(closes), max(closes)
            max_delta = (hi - lo) / abs(lo) if lo else 0.0
            logger.warning(
                "price cross-check divergence %s %s: closes=%s max_delta=%.4f%%",
                ticker,
                week_end,
                {b["_source"]: b["close"] for b in candidates},
                max_delta * 100,
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
            "agreeing_sources": agreeing_srcs,
        })
    return out


def get_daily_bars(ticker, start, end, *, providers=DAILY_PROVIDERS, tol_pct=0.5):
    """Cross-checked DAILY close-to-close bars for the event window (T-1..T+2 granularity).

    Runs ONLY the daily-capable subset (Tiingo/Nasdaq raw daily) — NOT PRICE_PROVIDERS, whose
    weekly-native rank-0 sources would silently compute the move off WEEKLY closes. The daily
    fetchers key each bar on its raw TRADE date, so get_weekly_bars' cross-check/grade machinery
    (first provider with a given date wins, N-source median triangulation) applies unchanged —
    it simply groups by trade date instead of Friday week. [] on degrade.

    # ponytail: delegate to get_weekly_bars over the daily subset — the daily providers skip the
    # resample, so no weekly bucketing runs; do NOT re-fetch or add a source.
    """
    return get_weekly_bars(ticker, start, end, providers=providers, tol_pct=tol_pct)


# ---- quality detectors (research §2.3) — pure/log-only, consumed by the daemon (Plans 06/07)


def flag_split_candidates(bars, *, ticker=None, split_tol=0.1, vol_spike=1.5):
    """Flag ~2x / ~0.5x RAW-close jumps vs the ADJACENT week with no corroborating volume spike as
    candidate corporate actions (research §2.3). LOG + return the flags — NEVER auto-adjust; RAW is
    locked, the flag IS the signal. A genuine news move comes WITH a volume spike; a split moves
    price on ~flat volume, so we only flag when volume did NOT spike. Pure/offline.

    Returns a list of {ticker, week_end, prev_close, close, ratio} — the shape Plan 06 counts."""
    flags = []
    ordered = sorted(bars, key=lambda b: b["week_end"])
    for prev, cur in zip(ordered, ordered[1:]):
        pc, cc = prev.get("close"), cur.get("close")
        if not pc or not cc:
            continue
        ratio = cc / pc
        split_like = abs(ratio - 2.0) <= split_tol or abs(ratio - 0.5) <= split_tol / 2
        if not split_like:
            continue
        pv, cv = prev.get("volume") or 0.0, cur.get("volume") or 0.0
        vol_ratio = (cv / pv) if pv else 0.0
        if vol_ratio >= vol_spike:  # a real volume spike -> a news move, not a split
            continue
        flags.append({"ticker": ticker, "week_end": cur["week_end"],
                      "prev_close": pc, "close": cc, "ratio": ratio})
        logger.warning(
            "split/dividend candidate %s %s: %.4f->%.4f (%.2fx) volx=%.2f (RAW not adjusted)",
            ticker, cur["week_end"], pc, cc, ratio, vol_ratio,
        )
    return flags


def drop_bad_ticks(bars, *, n_sigma=4.0, revert_tol=0.1):
    """Drop a single-bar close that spikes > n_sigma over the local window AND reverts the next bar
    (a bad tick), returning a NEW list; adjacent bars are untouched. Needs >=3 bars. Pure/offline.

    The window centre/scale use the robust median + population stdev of the OTHER closes. When the
    window is perfectly flat (sigma==0) no tick can be scored, so it is left in place.
    # ponytail: median/stdev over the whole series, not a rolling window — fine at ~weekly bars.
    """
    ordered = sorted(bars, key=lambda b: b["week_end"])
    if len(ordered) < 3:
        return ordered
    closes = [b["close"] for b in ordered]
    drop = set()
    for i in range(1, len(ordered) - 1):
        prev, cur, nxt = closes[i - 1], closes[i], closes[i + 1]
        if not prev or abs(nxt - prev) / abs(prev) > revert_tol:
            continue  # does not revert -> a real move, not a bad tick
        window = [c for j, c in enumerate(closes) if j != i]
        center = statistics.median(window)
        sigma = statistics.pstdev(window)
        if sigma > 0 and abs(cur - center) > n_sigma * sigma:
            drop.add(i)
            logger.warning(
                "bad tick dropped %s %s: close=%.4f reverts to ~%.4f (%.1fσ over window median %.4f)",
                ordered[i].get("_source") or ordered[i].get("source"),
                ordered[i].get("week_end"), cur, prev, abs(cur - center) / sigma, center,
            )
    return [b for j, b in enumerate(ordered) if j not in drop]


def is_stale(fetch_ts, cadence_s, *, now=None):
    """True if the last successful fetch is older than 2x the source cadence — the daemon/health
    JSON degrade signal (Plans 06/07). `fetch_ts`: ISO-8601 string, datetime, or None (never
    fetched -> stale). `cadence_s`: expected seconds between fetches. Pure/offline."""
    if fetch_ts is None:
        return True
    if isinstance(fetch_ts, str):
        fetch_ts = datetime.fromisoformat(fetch_ts)
    now = now or datetime.now(timezone.utc)
    if fetch_ts.tzinfo is None:
        fetch_ts = fetch_ts.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - fetch_ts).total_seconds() > 2 * cadence_s
