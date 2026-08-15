"""Weekly universe-wide thesis engine (WEEK-02).

Three deterministic, frozen-ToolResult tools — NO LLM inside (agents interpret + veto downstream;
these only compute, agents-never-do-arithmetic):

  classify_drop    — split a weekly move into sector-beta vs idiosyncratic (via correlation_beta)
                     + a deterministic catalyst news gate (busted / positive) + a turnover flag.
  weekly_base_rate — beta-binomial-shrunk conditional P(next-week-up): a thin per-name sample is
                     pulled toward the parent cohort (mirrors the estimator cold-start seam in
                     events.py), quoted with a return CI. The measurement anchor == the execution
                     anchor (one params["weekly"]["anchor"] — the trap that evaporates the edge).
  thesis_scan      — the weekly driver: a row for EVERY universe name (a "no measured edge" row is
                     itself a valid, data-backed read), a 4-part tradeability bar, and the -15%
                     falling-knife HARD VETO enforced regardless of class.

Every threshold is read from params["weekly"] (Plan 01) — a missing key raises (no literal in a
tool body). All data via the point-in-time bars store (bars_asof, no look-ahead). Fully offline.
"""

import math

import numpy as np

from .pairs import correlation_beta
from .result import ToolResult

_VERSION = "1.0.0"
_XBI = "XBI"

# FIXED trigger grammar (research §2.4) — no free-form. trigger -> (op, threshold on the weekly ret).
_TRIGGERS = {
    "drop_le_-0.05": ("le", -0.05),
    "drop_le_-0.10": ("le", -0.10),
    "drop_le_-0.15": ("le", -0.15),
    "up_ge_0.05": ("ge", 0.05),
    "up_ge_0.10": ("ge", 0.10),
}


# --- shared low-level helpers ----------------------------------------------------------------


def _weekly_returns(bars):
    """Close-to-close weekly returns; returns[i] is the return of the week ending at bars[i+1]."""
    c = [b["close"] for b in bars]
    return [c[i] / c[i - 1] - 1.0 for i in range(1, len(c))]


def _trigger_hit(ret, op, thr):
    return ret <= thr if op == "le" else ret >= thr


def _turnover_flag(bars, lookback):
    """"high"/"low": the latest bar's volume vs the trailing-median volume over `lookback` weeks."""
    vols = [b["volume"] for b in bars if b.get("volume") is not None]
    if len(vols) < 2:
        return "low"
    cur = vols[-1]
    trailing = vols[-(lookback + 1):-1]
    med = float(np.median(trailing)) if trailing else cur
    return "high" if cur > med else "low"


# --- Task 1: classify_drop -------------------------------------------------------------------


def classify_drop(ticker, week_end, store, kb_conn, *, params):
    """Split this week's move into sector-beta vs idiosyncratic and gate it on catalyst news.

    Money-safety: the sector/idio split (via correlation_beta vs XBI) + the news gate is how a
    busted-catalyst drop is kept OUT of the mean-reversion bucket downstream (Savor 2012: info
    moves drift, no-info moves reverse). Returns a frozen ToolResult; NO LLM inside.
    """
    w = params["weekly"]  # missing "weekly" group -> KeyError
    beta_window = w["beta_window_weeks"]
    sector_cut = w["sector_frac_cut"]
    turnover_lb = w["turnover_lookback"]

    bars = store.bars_asof(kb_conn, ticker, week_end, lookback_weeks=beta_window + 1)
    xbi = store.bars_asof(kb_conn, _XBI, week_end, lookback_weeks=beta_window + 1)
    if len(bars) < 2 or len(xbi) < 2:
        raise ValueError(f"need >= 2 bars for {ticker} and XBI at {week_end}")

    a_ret = _weekly_returns(bars)
    m_ret = _weekly_returns(xbi)
    n = min(len(a_ret), len(m_ret))
    a_ret, m_ret = a_ret[-n:], m_ret[-n:]

    beta = correlation_beta(a_ret, m_ret).detail["beta"]  # REUSE — do not reimplement OLS beta
    ret = a_ret[-1]
    xbi_ret = m_ret[-1]
    idio_ret = ret - beta * xbi_ret
    sector_frac = abs(beta * xbi_ret) / abs(ret) if ret != 0 else 0.0

    news_hits = _news_in_drop_week(store, kb_conn, ticker, bars, week_end)

    if abs(idio_ret) < sector_cut * abs(ret):
        drop_class = "sector_beta"
    elif news_hits:
        drop_class = "busted_catalyst" if ret < 0 else "positive_catalyst"
    else:
        # ponytail: an SEC S-1/424B dilution flag is a future feed; with no news the honest
        # default is idio_no_news (upgrade to a dilution class when the filings feed lands).
        drop_class = "idio_no_news"

    return ToolResult(
        tool="classify_drop",
        tool_version=_VERSION,
        inputs={"ticker": ticker, "week_end": week_end, "params": params},
        value=None,
        detail={
            "ret": ret,
            "beta": beta,
            "idio_ret": idio_ret,
            "sector_frac": sector_frac,
            "drop_class": drop_class,
            "turnover_flag": _turnover_flag(bars, turnover_lb),
            "news_hits": news_hits,
        },
    )


def _news_in_drop_week(store, kb_conn, ticker, bars, week_end):
    """Verified catalysts for `ticker` landing in the drop week (prev_week_end, week_end]."""
    prev = bars[-2]["week_end"]
    hits = []
    for c in store.tradeable_catalysts(kb_conn):
        if c.ticker == ticker and prev < c.event_date <= week_end:
            hits.append({"catalyst_type": c.catalyst_type.value, "event_date": c.event_date})
    return hits
