"""Cascade + cross-check engine (prices.get_weekly_bars) — pure stubbed providers, ZERO HTTP.

The single most correctness-critical unit in the phase. A "provider" is just a
`fetch(ticker, start, end) -> list[bar]` function; here every provider is a stub returning
canned Friday-anchored bars (each tagged _source/_grade like the real Wave-2 fetchers), so the
whole suite runs offline. We prove: ranked cascade + fall-through, >=2-source cross-check within
0.5% tolerance (agree -> high-confidence agreeing set), divergence beyond tolerance (structured
warning + keep highest-grade + agreeing_sources narrows to one), all-sources-miss -> ABSENT
(never imputed), no-keys degrades to the always-on pair, and comparison keyed on the shared
Friday week_end (mis-anchored weeks never falsely "agree").
"""

import logging

from catalyst_trader.providers import prices

TICKER, START, END = "IONS", "2026-08-01", "2026-08-31"
W1 = "2026-08-07"  # Friday
W2 = "2026-08-14"  # the next Friday


def _bar(week_end, close, source, grade):
    return {
        "week_end": week_end,
        "open": close - 0.10,
        "high": close + 0.20,
        "low": close - 0.20,
        "close": close,
        "volume": 1000.0,
        "_source": source,
        "_grade": grade,
    }


def _stub(*bars):
    """A provider stub: ignores (ticker, start, end), returns the canned bars."""
    return lambda ticker, start, end: list(bars)


def _empty():
    """A no-key / degraded provider: always returns []."""
    return lambda ticker, start, end: []


# ---- cross-check: agreement -------------------------------------------------------------


def test_two_sources_agree_high_confidence():
    green = _stub(_bar(W1, 10.00, "alpha_vantage", "green"))
    yellow = _stub(_bar(W1, 10.02, "yfinance", "yellow"))  # 0.2% off -> within 0.5% tol
    out = prices.get_weekly_bars(TICKER, START, END, providers=[green, yellow])
    assert len(out) == 1
    b = out[0]
    assert b["agreeing_sources"] == {"alpha_vantage", "yfinance"}  # both agree
    assert b["source"] == "alpha_vantage" and b["source_grade"] == "green"  # best grade kept
    assert b["close"] == 10.00  # highest-grade source's bar is the one kept


# ---- cross-check: divergence ------------------------------------------------------------


def test_divergence_logged_keeps_highest_grade(caplog):
    green = _stub(_bar(W1, 10.00, "alpha_vantage", "green"))
    yellow = _stub(_bar(W1, 12.00, "yfinance", "yellow"))  # 20% off -> beyond 0.5% tol
    with caplog.at_level(logging.WARNING):
        out = prices.get_weekly_bars(TICKER, START, END, providers=[green, yellow])
    assert len(out) == 1
    b = out[0]
    assert b["source"] == "alpha_vantage" and b["source_grade"] == "green"  # highest grade kept
    assert b["close"] == 10.00
    assert b["agreeing_sources"] == {"alpha_vantage"}  # narrows to one (unconfirmed)
    # structured warning names ticker, week_end, per-source closes, and the delta
    text = caplog.text
    assert TICKER in text and W1 in text
    assert "10.0" in text and "12.0" in text  # per-source closes surfaced
    assert "diverg" in text.lower()


# ---- ranked fall-through ----------------------------------------------------------------


def test_fallthrough_fills_gap():
    # provider 1 only has W1; provider 2 fills the W2 gap.
    p1 = _stub(_bar(W1, 10.00, "alpha_vantage", "green"))
    p2 = _stub(_bar(W1, 10.01, "yfinance", "yellow"), _bar(W2, 11.00, "yfinance", "yellow"))
    out = prices.get_weekly_bars(TICKER, START, END, providers=[p1, p2])
    weeks = {b["week_end"] for b in out}
    assert weeks == {W1, W2}
    w2 = next(b for b in out if b["week_end"] == W2)
    assert w2["source"] == "yfinance"  # filled from the fall-through provider
    assert w2["agreeing_sources"] == {"yfinance"}  # single-source, unconfirmed


# ---- never impute ----------------------------------------------------------------------


def test_all_sources_miss_week_is_absent():
    # No source carries W2 -> it must simply not exist in the output (no interpolation/ffill).
    p1 = _stub(_bar(W1, 10.00, "yfinance", "yellow"))
    p2 = _stub(_bar(W1, 10.00, "nasdaq", "yellow"))
    out = prices.get_weekly_bars(TICKER, START, END, providers=[p1, p2])
    assert {b["week_end"] for b in out} == {W1}  # W2 absent, not fabricated
    assert all(b["close"] is not None for b in out)  # no null/synthetic bar snuck in


def test_no_available_source_returns_empty():
    out = prices.get_weekly_bars(TICKER, START, END, providers=[_empty(), _empty()])
    assert out == []  # degrade, never a fabricated series


# ---- null-close bars are a degrade, never data (live-shakedown regression) --------------


def test_null_close_bar_dropped_not_emitted(caplog):
    # The highest-RANKED available source returns close=None (Yahoo NaN); a lower-ranked source
    # has the real close. The null-close bar must be DROPPED — never emitted (would crash
    # upsert_bars NOT NULL) and never counted as a cross-source divergence against the real close.
    yf_null = _stub({**_bar(W1, 99.0, "yfinance", "yellow"), "close": None})
    nasdaq = _stub(_bar(W1, 25.0, "nasdaq", "yellow"))
    with caplog.at_level(logging.WARNING):
        out = prices.get_weekly_bars(TICKER, START, END, providers=[yf_null, nasdaq])
    assert len(out) == 1
    b = out[0]
    assert b["close"] == 25.0 and b["source"] == "nasdaq"  # the real observation wins
    assert b["agreeing_sources"] == {"nasdaq"}             # single real source, unconfirmed
    assert "diverg" not in caplog.text.lower()             # null-vs-real is not a divergence


def test_all_bars_null_close_week_is_absent():
    # Every source returns close=None for the week -> no usable observation -> the week is ABSENT
    # (degrade), never a fabricated/null bar in the output.
    p1 = _stub({**_bar(W1, 10.0, "yfinance", "yellow"), "close": None})
    p2 = _stub({**_bar(W1, 10.0, "nasdaq", "yellow"), "close": None})
    out = prices.get_weekly_bars(TICKER, START, END, providers=[p1, p2])
    assert out == []


# ---- no keys -> degrade to always-on ----------------------------------------------------


def test_no_keys_degrades_to_always_on():
    av = _empty()       # keyed GREEN, no key -> []
    tiingo = _empty()   # keyed GREEN, no key -> []
    yf = _stub(_bar(W1, 10.00, "yfinance", "yellow"))
    nasdaq = _stub(_bar(W1, 10.00, "nasdaq", "yellow"))
    out = prices.get_weekly_bars(TICKER, START, END, providers=[av, tiingo, yf, nasdaq])
    assert len(out) == 1
    b = out[0]
    assert b["agreeing_sources"] == {"yfinance", "nasdaq"}  # always-on pair still cross-checks
    assert b["source_grade"] == "yellow"


# ---- compare only within the same Friday week_end --------------------------------------


def test_compare_by_aligned_week_end():
    # Same close, but the two bars sit on DIFFERENT Fridays -> they must NOT cross-check into
    # one high-confidence bar; each stays a single-source bar on its own week.
    a = _stub(_bar(W1, 10.00, "alpha_vantage", "green"))
    b = _stub(_bar(W2, 10.00, "yfinance", "yellow"))
    out = prices.get_weekly_bars(TICKER, START, END, providers=[a, b])
    assert {x["week_end"] for x in out} == {W1, W2}
    for x in out:
        assert len(x["agreeing_sources"]) == 1  # different weeks never falsely "agree"


def test_same_week_end_cross_checks():
    # Same Friday week_end + within tol -> the aligned compare DOES fire.
    a = _stub(_bar(W1, 10.00, "alpha_vantage", "green"))
    b = _stub(_bar(W1, 10.00, "yfinance", "yellow"))
    out = prices.get_weekly_bars(TICKER, START, END, providers=[a, b])
    assert len(out) == 1
    assert out[0]["agreeing_sources"] == {"alpha_vantage", "yfinance"}


# ---- output ordering + provenance envelope ---------------------------------------------


def test_output_is_chronological_and_carries_provenance():
    p = _stub(_bar(W2, 11.00, "yfinance", "yellow"), _bar(W1, 10.00, "yfinance", "yellow"))
    out = prices.get_weekly_bars(TICKER, START, END, providers=[p])
    assert [b["week_end"] for b in out] == [W1, W2]  # sorted by week_end
    for b in out:
        assert "source" in b and "source_grade" in b and "agreeing_sources" in b


# ---- N-source median triangulation (Plan 06.10-04, research §2.3) -----------------------


def test_median_keeps_majority_flags_outlier(caplog):
    # The OUTLIER is the HIGHEST-GRADE source (12.00) — this is exactly where 2-source pairwise
    # (which anchors on the highest grade) would keep the wrong value. N-source median must pick
    # the majority cluster (10.00/10.02), keep the highest-grade AGREEING source, and flag the
    # outlier as a divergence excluded from agreeing_sources — never averaged in.
    green = _stub(_bar(W1, 12.00, "alpha_vantage", "green"))   # highest grade, but the outlier
    yellow1 = _stub(_bar(W1, 10.00, "yfinance", "yellow"))     # majority
    yellow2 = _stub(_bar(W1, 10.02, "nasdaq", "yellow"))       # majority (0.2% off -> in tol)
    with caplog.at_level(logging.WARNING):
        out = prices.get_weekly_bars(TICKER, START, END, providers=[green, yellow1, yellow2])
    assert len(out) == 1
    b = out[0]
    assert b["close"] == 10.00                                  # a REAL majority bar, not 12.00
    assert b["source"] == "yfinance"                            # highest-grade AGREEING source
    assert b["agreeing_sources"] == {"yfinance", "nasdaq"}      # outlier excluded
    assert "alpha_vantage" not in b["agreeing_sources"]
    assert "diverg" in caplog.text.lower() and "12.0" in caplog.text


def test_even_split_degrades_to_unconfirmed(caplog):
    # 4 sources in a balanced 2-2 split (10.00/10.01 vs 12.00/12.01). The median lands BETWEEN the
    # clusters (11.005) -> the in-tolerance set is EMPTY. This MUST degrade to the highest-grade
    # source as unconfirmed: a REAL bar is still emitted, agreeing_sources = {that one source},
    # divergence logged — never no bar, never a crash, never the between-clusters median.
    av = _stub(_bar(W1, 10.00, "alpha_vantage", "green"))       # highest grade
    tiingo = _stub(_bar(W1, 10.01, "tiingo", "green"))
    yf = _stub(_bar(W1, 12.00, "yfinance", "yellow"))
    nasdaq = _stub(_bar(W1, 12.01, "nasdaq", "yellow"))
    with caplog.at_level(logging.WARNING):
        out = prices.get_weekly_bars(TICKER, START, END, providers=[av, tiingo, yf, nasdaq])
    assert len(out) == 1                                        # a bar IS emitted (never no-bar)
    b = out[0]
    assert b["close"] == 10.00                                  # highest-grade REAL bar kept
    assert b["source"] == "alpha_vantage"
    assert b["agreeing_sources"] == {"alpha_vantage"}           # unconfirmed single
    assert b["close"] != 11.005                                 # never the between-clusters median
    assert "diverg" in caplog.text.lower()


def test_two_source_pairwise_unchanged():
    # Regression guard: the 2-source case behaves exactly as the shipped 6.9 pairwise logic.
    green = _stub(_bar(W1, 10.00, "alpha_vantage", "green"))
    yellow = _stub(_bar(W1, 10.02, "yfinance", "yellow"))       # within 0.5% tol
    out = prices.get_weekly_bars(TICKER, START, END, providers=[green, yellow])
    assert len(out) == 1
    b = out[0]
    assert b["agreeing_sources"] == {"alpha_vantage", "yfinance"}
    assert b["source"] == "alpha_vantage" and b["close"] == 10.00


def test_single_source_unconfirmed():
    only = _stub(_bar(W1, 10.00, "yfinance", "yellow"))
    out = prices.get_weekly_bars(TICKER, START, END, providers=[only])
    assert len(out) == 1
    assert out[0]["agreeing_sources"] == {"yfinance"}           # unconfirmed


def test_all_miss_no_imputation():
    # >=3 providers but none carries W2 -> W2 must be ABSENT (no synthesized/median-filled bar).
    p1 = _stub(_bar(W1, 10.00, "alpha_vantage", "green"))
    p2 = _stub(_bar(W1, 10.01, "yfinance", "yellow"))
    p3 = _stub(_bar(W1, 10.02, "nasdaq", "yellow"))
    out = prices.get_weekly_bars(TICKER, START, END, providers=[p1, p2, p3])
    assert {b["week_end"] for b in out} == {W1}                 # W2 never fabricated
    assert all(b["close"] is not None for b in out)


def test_divergence_record_shape(caplog):
    # The divergence log carries ticker, week_end, per-source closes, and a max delta — the shape
    # the health JSON counts in Plan 06.
    green = _stub(_bar(W1, 10.00, "alpha_vantage", "green"))
    yellow1 = _stub(_bar(W1, 10.02, "yfinance", "yellow"))
    yellow2 = _stub(_bar(W1, 12.00, "nasdaq", "yellow"))        # the outlier
    with caplog.at_level(logging.WARNING):
        prices.get_weekly_bars(TICKER, START, END, providers=[green, yellow1, yellow2])
    text = caplog.text
    assert TICKER in text and W1 in text                        # ticker + week_end
    assert "10.0" in text and "12.0" in text                    # per-source closes
    assert "delta" in text.lower()                              # a max-delta field


# ---- split / bad-tick / stale detectors (Plan 06.10-04 Task 2) --------------------------


def _series(*closes, volumes=None):
    """Chronological bar series over consecutive Fridays (offline, for the detectors)."""
    fridays = ["2026-08-07", "2026-08-14", "2026-08-21", "2026-08-28", "2026-09-04", "2026-09-11"]
    vols = volumes or [1000.0] * len(closes)
    return [{**_bar(fridays[i], c, "yfinance", "yellow"), "volume": vols[i]}
            for i, c in enumerate(closes)]


def test_split_candidate_flagged_not_adjusted():
    # A ~2x raw-close jump with FLAT volume (no news spike) -> flagged as a corporate-action
    # candidate; the RAW closes are NEVER mutated (RAW is locked).
    bars = _series(10.0, 20.0, 20.1)          # 2x jump at week 2, flat volume
    before = [b["close"] for b in bars]
    flags = prices.flag_split_candidates(bars, ticker=TICKER)
    assert len(flags) == 1
    assert flags[0]["week_end"] == "2026-08-14" and abs(flags[0]["ratio"] - 2.0) < 0.01
    assert [b["close"] for b in bars] == before   # RAW unchanged, no auto-adjust


def test_bad_tick_dropped():
    # A single reverting >N-sigma spike (30.0 between ~10 neighbours) is dropped; the rest stay.
    bars = _series(10.0, 10.1, 9.9, 30.0, 10.05, 9.95)
    out = prices.drop_bad_ticks(bars)
    closes = [b["close"] for b in out]
    assert 30.0 not in closes                       # the spike is gone
    assert len(out) == len(bars) - 1                # exactly one bar dropped
    assert closes == [10.0, 10.1, 9.9, 10.05, 9.95] # adjacent bars intact, order preserved


def test_stale_helper():
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)
    cadence_s = 24 * 3600                            # daily
    fresh = (now - timedelta(hours=12)).isoformat()
    old = (now - timedelta(days=3)).isoformat()      # > 2x cadence
    assert prices.is_stale(old, cadence_s, now=now) is True
    assert prices.is_stale(fresh, cadence_s, now=now) is False
    assert prices.is_stale(None, cadence_s, now=now) is True   # never fetched -> stale
