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
from datetime import date, timedelta

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


# --- Task 2: weekly_base_rate ----------------------------------------------------------------


def weekly_base_rate(ticker, trigger, drop_class, turnover, as_of, store, kb_conn, *,
                     params, window_years=None):
    """Beta-binomial-shrunk conditional P(next-week-up) for a (trigger, drop_class, turnover) cell.

    The thin-per-name trap: a name with 4 historical bounces is NOT a 100% edge. We shrink the raw
    per-name rate toward the parent cohort with a beta-binomial prior (mirrors the estimator
    cold-start seam in events.py): p_shrunk = (n_name*p_name + k_prior*p_cohort)/(n_name+k_prior).
    Thin n is pulled to the cohort; ample n washes the prior out (p_shrunk -> p_raw). The
    measurement window is anchored on the SAME params["weekly"]["anchor"] the runner executes on
    (measurement window == execution window). Frozen ToolResult; NO LLM inside.
    """
    w = params["weekly"]  # missing "weekly" group -> KeyError
    if trigger not in _TRIGGERS:
        raise ValueError(f"unknown trigger {trigger!r}; use one of {sorted(_TRIGGERS)}")
    op, thr = _TRIGGERS[trigger]
    anchor = w["anchor"]
    min_n = w["min_effective_n"]
    k_prior = w["shrink_prior_weight"]
    turnover_lb = w["turnover_lookback"]
    years = window_years if window_years is not None else w["window_years"]
    lookback = years * 52

    n_up, nexts, dates = _trigger_events(store, kb_conn, ticker, as_of, lookback, op, thr,
                                         turnover, turnover_lb)
    n_name = len(nexts)
    p_raw = n_up / n_name if n_name else 0.0

    # parent cohort: SAME-trigger events pooled over every OTHER ticker (universe level).
    # ponytail: therapeutic-area sub-cohort is a future feed; the universe pool is the widest
    # cohort available offline (ladder collapses to it), with a 0.5 uninformative prior when empty.
    c_up, c_n = _cohort_events(store, kb_conn, ticker, as_of, lookback, op, thr)
    if c_n:
        p_cohort, cohort_level = c_up / c_n, "universe"
    else:
        p_cohort, cohort_level = 0.5, "prior"

    p_shrunk = (n_name * p_raw + k_prior * p_cohort) / (n_name + k_prior)
    shrunk = n_name < min_n  # cold-start flag (mirrors events.py) — thin n is being propped up

    arr = np.asarray(nexts, dtype=float)
    mean_next = float(arr.mean()) if n_name else 0.0
    median_next = float(np.median(arr)) if n_name else 0.0
    ci_low, ci_high = _mean_ci(arr)
    win_loss_ratio = _win_loss(arr)

    return ToolResult(
        tool="weekly_base_rate",
        tool_version=_VERSION,
        inputs={
            "ticker": ticker, "trigger": trigger, "drop_class": drop_class,
            "turnover": turnover, "as_of": as_of, "params": params,
            "window_years": window_years,
        },
        value=p_shrunk,
        detail={
            "n_name": n_name,
            "n_effective": n_name,  # ponytail: cluster-discounted effective-n < n; naive for now
            "n_cohort": c_n,
            "cohort_level": cohort_level,
            "p_cohort": p_cohort,
            "p_raw": p_raw,
            "p_shrunk": p_shrunk,
            "shrunk": shrunk,
            "shrink_prior_weight": k_prior,
            "mean_next": mean_next,
            "median_next": median_next,
            "win_loss_ratio": win_loss_ratio,
            "ci_low": ci_low,
            "ci_high": ci_high,
            "anchor": anchor,
            "events": dates,
        },
    )


def _trigger_events(store, kb_conn, ticker, as_of, lookback, op, thr, turnover, turnover_lb):
    """Historical (trigger[, turnover])-matching weeks and their NEXT-week return. Never a look-ahead."""
    bars = store.bars_asof(kb_conn, ticker, as_of, lookback_weeks=lookback)
    rets = _weekly_returns(bars)  # rets[i] ends at bars[i+1]
    n_up = 0
    nexts, dates = [], []
    for i in range(len(rets) - 1):  # need a next week to score the outcome
        if not _trigger_hit(rets[i], op, thr):
            continue
        if turnover is not None and _turnover_flag(bars[: i + 2], turnover_lb) != turnover:
            continue
        nxt = rets[i + 1]
        nexts.append(nxt)
        dates.append(bars[i + 1]["week_end"])
        if nxt > 0:
            n_up += 1
    return n_up, nexts, dates


def _cohort_events(store, kb_conn, target, as_of, lookback, op, thr):
    """Same-trigger next-week-up counts pooled over every ticker except `target` (parent cohort)."""
    rows = kb_conn.execute(
        "SELECT DISTINCT ticker FROM price_bar WHERE ticker != ?", (target,)
    ).fetchall()
    up = n = 0
    for r in rows:
        tk = r[0]
        rets = _weekly_returns(store.bars_asof(kb_conn, tk, as_of, lookback_weeks=lookback))
        for i in range(len(rets) - 1):
            if _trigger_hit(rets[i], op, thr):
                n += 1
                if rets[i + 1] > 0:
                    up += 1
    return up, n


def _mean_ci(arr):
    """Naive iid 95% normal CI on the mean next-week return.

    ponytail: biotech weekly moves are cross-correlated, so the effective sample size is below the
    printed n and this CI is optimistically tight — widen with a cluster-robust SE if it matters.
    """
    n = len(arr)
    if n == 0:
        return 0.0, 0.0
    m = float(arr.mean())
    if n == 1:
        return m, m
    se = float(arr.std(ddof=1)) / math.sqrt(n)
    return m - 1.96 * se, m + 1.96 * se


def _win_loss(arr):
    """Average win magnitude / average loss magnitude over the next-week returns."""
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    if wins.size == 0:
        return 0.0
    if losses.size == 0:
        return float("inf")
    return float(wins.mean() / abs(losses.mean()))


# --- Task 3: thesis_scan ---------------------------------------------------------------------


def _match_trigger(ret):
    """Map a weekly return to its FIXED trigger cell (most extreme first); None = no measured cell."""
    if ret <= -0.15:
        return "drop_le_-0.15"
    if ret <= -0.10:
        return "drop_le_-0.10"
    if ret <= -0.05:
        return "drop_le_-0.05"
    if ret >= 0.10:
        return "up_ge_0.10"
    if ret >= 0.05:
        return "up_ge_0.05"
    return None


def _thesis_type(drop_class):
    """Class -> intended thesis (research §2.4). busted_catalyst is NEVER a bounce (no thesis)."""
    if drop_class in ("sector_beta", "idio_no_news"):
        return "mean_reversion"
    if drop_class == "positive_catalyst":
        return "continuation"
    if drop_class == "dilution":
        return "excluded"
    return "none"  # busted_catalyst + anything unmapped: no statistical thesis


def _catalyst_in_hold_window(store, kb_conn, ticker, week_end):
    """A verified catalyst in the upcoming hold week (week_end, week_end + 7 days]."""
    end = (date.fromisoformat(week_end) + timedelta(days=7)).isoformat()
    return any(
        c.ticker == ticker and week_end < c.event_date <= end
        for c in store.tradeable_catalysts(kb_conn)
    )


def thesis_scan(universe, week_end, store, kb_conn, *, params):
    """The weekly driver — a thesis row for EVERY universe name (WEEK-02).

    Every name gets a data-backed read, including a "no measured edge" row (a valid answer). A row
    is eligible ONLY if ALL four gates hold — edge >= edge_min_pts, n_effective >= min_effective_n,
    mean_next > cost_mult*roundtrip_cost, ci_low > 0 — AND it is not a -15% falling-knife (HARD VETO,
    any class) and not a busted catalyst. A name with a catalyst inside the hold window is handed to
    Workflow-1 (catalyst precedence). Frozen ToolResult; NO LLM inside.
    """
    w = params["weekly"]
    edge_min = w["edge_min_pts"]
    min_n = w["min_effective_n"]
    cost_floor = w["cost_mult"] * w["roundtrip_cost"]
    hard_veto = w["hard_veto_drop"]

    tickers = [getattr(item, "ticker", item) for item in universe]
    rows = [
        _thesis_row(tk, week_end, store, kb_conn, params, edge_min, min_n, cost_floor, hard_veto)
        for tk in tickers
    ]

    return ToolResult(
        tool="thesis_scan",
        tool_version=_VERSION,
        inputs={"universe": tickers, "week_end": week_end, "params": params},
        value=None,
        detail={"rows": rows},
    )


def _thesis_row(ticker, week_end, store, kb_conn, params, edge_min, min_n, cost_floor, hard_veto):
    cd = classify_drop(ticker, week_end, store, kb_conn, params=params).detail
    ret, drop_class, turnover = cd["ret"], cd["drop_class"], cd["turnover_flag"]

    # catalyst precedence: Workflow-1 owns any name with a tradeable catalyst in the hold window.
    if _catalyst_in_hold_window(store, kb_conn, ticker, week_end):
        return {"ticker": ticker, "thesis_type": "catalyst", "trigger": None, "p": None,
                "mean_next": None, "n_effective": 0, "eligible": False,
                "veto_reasons": ["catalyst_precedence"]}

    trigger = _match_trigger(ret)
    if trigger is None:  # no measured cell — a valid "no edge" read (still a row)
        return {"ticker": ticker, "thesis_type": _thesis_type(drop_class), "trigger": None,
                "p": None, "mean_next": None, "n_effective": 0, "eligible": False,
                "veto_reasons": ["no_trigger"]}

    br = weekly_base_rate(ticker, trigger, drop_class, turnover, week_end, store, kb_conn,
                          params=params).detail
    p, mean_next, ci_low = br["p_shrunk"], br["mean_next"], br["ci_low"]
    n_eff = br["n_effective"]
    edge = p - br["p_cohort"]

    veto = []
    if ret <= hard_veto:
        veto.append("hard_veto_drop")       # -15% falling knife: ANY class, overrides every edge
    if drop_class == "busted_catalyst":
        veto.append("busted_catalyst")      # a busted catalyst is NEVER a bounce candidate
    if edge < edge_min:
        veto.append("edge_below_min")
    if n_eff < min_n:
        veto.append("thin_n")
    if mean_next <= cost_floor:
        veto.append("below_cost")
    if ci_low <= 0:
        veto.append("ci_touches_zero")

    return {"ticker": ticker, "thesis_type": _thesis_type(drop_class), "trigger": trigger,
            "p": p, "mean_next": mean_next, "n_effective": n_eff,
            "eligible": not veto, "veto_reasons": veto}
