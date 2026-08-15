"""Phase 6.8 Stage-1 scanner (SCAN-02/03): the deterministic, $0-LLM trigger layer.

`build_card` assembles the write-once company vetting card from point-in-time price bars
(store.bars_asof) + injected raw provider values + the EMBEDDED weekly thesis_scan row — it
RECOMPUTES NO quant number (agents-never-do-arithmetic extended to modules: one computation
site per number, consumed here verbatim). `delta_card` is the pure, reproducible week-over-week
flag engine (F1-F13) that fires on band/sign/set TRANSITIONS with latching, hysteresis, and
cadence honesty; `_wakes` is the PRINCIPAL/CORROBORATOR tier gate that decides who earns a
Stage-2 Haiku pass — monitor-by-exception. No LLM, no network anywhere in this module.

# ponytail: one params dict + build_card + delta_card + _wakes + the 13 rule branches. The
#           "LLM cannot touch the trigger" law is the DETERMINISTIC-GATE principle copied from
#           synthesize_verdict — the discipline is shared, the code is not.
"""

import statistics
from datetime import date, timedelta

from ..store import bars_asof, card_asof
from .diligence import DILIGENCE_PARAMS, options_liquid, zero_liquidity

# The SINGLE source of scan thresholds (SCAN-03 no-silent-fallback). Module-level + always
# present, read via direct subscript (missing-key-raises), NEVER `.get`. DELIBERATELY DECOUPLED
# from the KB fitted-params seam (mirrors diligence.py DILIGENCE_PARAMS L31-35): the fitted
# strategy dict has NO "scan" key, so it can never become the threshold source. Do NOT add a
# scan block to the KB bootstrap default or its CSV. The PM retunes these post-paper-month.
SCAN_PARAMS = {"scan": {
    "iv_spike_pts": 5.0, "straddle_median_mult": 1.5, "term_kink_pts": 5.0,
    "si_rel_step": 0.20, "dtc_abs_step": 2.0, "vol_regime_ratio": 2.0,
    "volume_anomaly_mult": 3.0, "runway_bands": [18, 12, 6],
    "catalyst_bands_days": [14, 7], "competitor_days": 7,
    "big_move_pct": 0.10, "hysteresis_rearm_frac": 0.5,
    "max_stage2_wakes": 8, "escalate_conf_floor": 0.4,
    "offering_s3_ret": 0.20,  # a bare S-3 is material only while the stock is already up
}}

# The flag grammar is FROZEN for the phase (research §1.1). Tiers gate the wake decision: a
# PRINCIPAL is material alone; a CORROBORATOR only in company (>=2). FUTURE feeds
# (analyst-rating / 13F / intraday halt) are deliberately ABSENT — marked, not invented.
_TIER = {
    "F1": "PRINCIPAL", "F2": "PRINCIPAL", "F3": "PRINCIPAL", "F4": "PRINCIPAL",
    "F5": "PRINCIPAL", "F6": "PRINCIPAL", "F7": "CORROBORATOR", "F8": "PRINCIPAL",
    "F9": "PRINCIPAL", "F10": "CORROBORATOR", "F11": "CORROBORATOR",
    "F12": "PRINCIPAL", "F13": "PRINCIPAL",
}

_OFFERING_FORMS = frozenset({"424B5", "FWP"})   # always-material dilution filings
_S3_FORM = "S-3"                                  # shelf: material only while the stock is up


def _prior_week(week_end):
    """The ISO date one week before `week_end`. ponytail: naive 7-day subtraction — the caller's
    anchor spine owns real dates; upgrade if the anchor ever becomes non-weekly."""
    return (date.fromisoformat(week_end) - timedelta(days=7)).isoformat()


def _returns(closes):
    """Weekly simple returns from a chronological close series (skips zero-denominator weeks)."""
    return [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes)) if closes[i - 1]]


def _sigma(returns, n):
    """Population stdev of the last n weekly returns, or None if <2 observations."""
    window = returns[-n:]
    return statistics.pstdev(window) if len(window) >= 2 else None


def _runway_band(months, edges):
    """Band index from the runway_bands edges (higher = safer). None months -> None.
    edges [18,12,6] -> <6:0, >=6:1, >=12:2, >=18:3."""
    if months is None:
        return None
    return sum(1 for edge in sorted(edges) if months >= edge)


def build_card(conn, ticker, week_end, raw, thesis_row, *, params=SCAN_PARAMS):
    """Assemble the §2.2 company vetting card deterministically — point-in-time, no recompute.

    Price/vol fields come from store.bars_asof (week_end <= as_of, no look-ahead). Options /
    positioning / balance-sheet fields come from the injected `raw` provider dict (CBOE / FINRA /
    EDGAR / FMP are mocked seams this phase — build_card CONSUMES raw[...], it never fetches).
    The `thesis_row` is embedded VERBATIM (build_card calls no classify_drop / weekly_base_rate /
    thesis_scan — one computation site per number). The prior card's `fired` latch dict is carried
    forward; delta_card mutates it next.
    """
    p = params["scan"]
    bars = bars_asof(conn, ticker, week_end)               # point-in-time: week_end <= as_of only
    closes = [b["close"] for b in bars if b.get("close") is not None]
    volumes = [b["volume"] for b in bars if b.get("volume") is not None]
    rets = _returns(closes)

    def _ma(n):
        return statistics.fmean(closes[-n:]) if len(closes) >= n else None

    ma4, ma12 = _ma(4), _ma(12)
    prior_vol_median = statistics.median(volumes[:-1]) if len(volumes) >= 2 else None

    quote = raw.get("options_quote")
    underlying_q = raw.get("underlying_quote")

    card = {
        "ticker": ticker,
        "week_end": week_end,
        "catalyst": {
            "days_to_catalyst": raw.get("days_to_catalyst"),
            "next_catalyst": raw.get("next_catalyst"),
            "catalysts_4w": raw.get("catalysts_4w"),
            "competitor_next_7d": raw.get("competitor_next_7d"),
            "nct_snapshots": raw.get("nct_snapshots"),
        },
        "options": {
            "iv30": raw.get("iv30"),
            "term_spread": raw.get("term_spread"),
            "straddle_move_pct": raw.get("straddle_move_pct"),
            "straddle_median": raw.get("straddle_median"),   # caller-supplied trailing median (F4)
            "options_liquid": options_liquid(quote, params=DILIGENCE_PARAMS) if quote else None,
            "zero_liquidity": zero_liquidity(underlying_q) if underlying_q else None,
            "underlying_price": raw.get("underlying_price"),
        },
        "positioning": {
            "short_interest": raw.get("short_interest"),
            "days_to_cover": raw.get("days_to_cover"),
            "si_settlement_date": raw.get("si_settlement_date"),
        },
        "price_vol": {
            "ret_1w": rets[-1] if rets else None,
            "ret_4w": closes[-1] / closes[-5] - 1 if len(closes) >= 5 and closes[-5] else None,
            "px_vs_ma4": closes[-1] / ma4 - 1 if ma4 else None,
            "px_vs_ma12": closes[-1] / ma12 - 1 if ma12 else None,
            "sigma5": _sigma(rets, 5),
            "sigma20": _sigma(rets, 20),
            "turnover_flag": bool(prior_vol_median and volumes[-1] > prior_vol_median),
            "vol_vs_median": volumes[-1] / prior_vol_median if prior_vol_median else None,
        },
        "balance_sheet": {
            "cash_runway_months": raw.get("cash_runway_months"),
            "runway_band": _runway_band(raw.get("cash_runway_months"), p["runway_bands"]),
            "seen_accessions": raw.get("seen_accessions", []),
            "live_shelf": raw.get("live_shelf"),
        },
        "thesis_row": thesis_row,                             # EMBEDDED VERBATIM — never recomputed
        "thesis_ref": thesis_row.get("tool_ref") if isinstance(thesis_row, dict) else None,
        "card_version": "1",
    }

    prev = card_asof(conn, ticker, _prior_week(week_end))     # carry the prior latch state forward
    card["fired"] = dict(prev["fired"]) if prev and prev.get("fired") else {}
    return card
