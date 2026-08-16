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
