"""Quick-260819-p1x Task 1 — the cache-first PRODUCTION daily-bars provider (TDD, fully offline).

Money-critical invariants under test (monkeypatch get_daily_bars / seed daily_bar directly — ZERO
live network, ZERO live catalyst.db):
  - Cache HIT: a covered window returns from cache with get_daily_bars NOT called (frugality).
  - STRICT lower bound (as_of < week_end): entry never fills on a same-as_of-dated bar.
  - BLOCKER-1 buffered upper bound: the window carries bars PAST exit_by so a time-barrier leg fills
    at a bar dated AFTER exit_by at T+1/T+2 — proving the latency sweep actually bites time exits.
  - allow_fetch gating: cache-only default abstains; allow_fetch=True back-fills once + upserts.
  - Graceful degrade: an empty/raising get_daily_bars returns [] (leg abstains), never raises.
  - price_bar ISOLATION: writing daily_bar leaves the weekly price_bar substrate byte-for-byte.
  - Idempotent upsert; migration 014 applies cleanly.
"""

from catalyst_trader import store
from catalyst_trader.backtest.daily_provider import make_daily_bars_provider
from catalyst_trader.backtest.fill import reflex_exit
from catalyst_trader.desk.exit_plan import EXIT_PARAMS

AS_OF = "2025-01-06"     # Monday (the decision-week close / signal bar)
EXIT_BY = "2025-01-13"   # as_of + 7d (the reflex time barrier)
_MULT = EXIT_PARAMS["off_map_mult"]


def _bar(day, close=100.0, o=None, h=None, lo=None, vol=1_000_000.0):
    """A flat-ish daily bar inside a wide (90,110) band so nothing triggers before the time leg."""
    return {"week_end": day, "open": o if o is not None else close,
            "high": h if h is not None else close + 1, "low": lo if lo is not None else close - 1,
            "close": close, "volume": vol}


# trade dates: 01-06 (==as_of, must be EXCLUDED), the intraweek bars, 01-13 (==exit_by), then buffer.
_DATES = ["2025-01-06", "2025-01-07", "2025-01-08", "2025-01-09", "2025-01-10",
          "2025-01-13", "2025-01-14", "2025-01-15"]


def _seed_covered(db, ticker="AAAA"):
    store.upsert_daily_bars(db, ticker, [_bar(d) for d in _DATES])


def _no_call_guard(monkeypatch):
    """Monkeypatch prices.get_daily_bars to a counter that also flags any call."""
    calls = []
    monkeypatch.setattr(
        "catalyst_trader.backtest.daily_provider.prices.get_daily_bars",
        lambda *a, **k: calls.append((a, k)) or [],
    )
    return calls


# ============================== cache-first + no-look-ahead ==============================


def test_cache_hit_returns_from_cache_with_zero_fetches(db, monkeypatch):
    _seed_covered(db)
    calls = _no_call_guard(monkeypatch)
    provider = make_daily_bars_provider(db)  # allow_fetch=False (default)
    bars = provider("AAAA", AS_OF, EXIT_BY)
    assert bars, "a covered window must return bars"
    assert calls == [], "cache hit must NOT call get_daily_bars (frugality guarantee)"


def test_strict_lower_bound_entry_bar_dated_after_as_of(db):
    _seed_covered(db)
    provider = make_daily_bars_provider(db)
    bars = provider("AAAA", AS_OF, EXIT_BY)
    assert all(b["week_end"] > AS_OF for b in bars), "STRICT lower bound: no same-as_of bar"
    assert bars[0]["week_end"] == "2025-01-07", "entry fills at the NEXT bar after the signal"


def test_no_bar_returned_beyond_the_buffer(db):
    _seed_covered(db)  # buffer = max_delay_bars(2) trading bars past exit_by -> last kept is 01-15
    provider = make_daily_bars_provider(db)
    bars = provider("AAAA", AS_OF, EXIT_BY)
    assert bars[-1]["week_end"] == "2025-01-15", "upper bound = exit_by + 2 trading bars"


def test_blocker1_time_barrier_leg_fills_after_exit_by_at_latency(db):
    """The exact gap plan-check flagged: the buffered window must let a time-barrier leg fill at a
    bar dated AFTER exit_by at T+1/T+2, so T+0 != T+1 != T+2 and the sweep is NOT inert."""
    _seed_covered(db)
    window = make_daily_bars_provider(db)("AAAA", AS_OF, EXIT_BY)
    assert any(b["week_end"] > EXIT_BY for b in window), "delayed-fill supply past exit_by is present"

    entry = window[0]["open"]
    common = dict(entry=entry, side="long", band=(90.0, 110.0), stop=80.0, target=130.0,
                  time_barrier=EXIT_BY, slippage=0.0, off_map_mult=_MULT)
    t0 = reflex_exit(window, exit_latency_bars=0, **common)
    t1 = reflex_exit(window, exit_latency_bars=1, **common)
    t2 = reflex_exit(window, exit_latency_bars=2, **common)
    assert t0["reason"] == "time" and t0["exit"] == EXIT_BY
    assert t1["exit"] == "2025-01-14" > EXIT_BY, "T+1 fills at a bar AFTER exit_by"
    assert t2["exit"] == "2025-01-15", "T+2 steps one further"
    assert t0["exit"] != t1["exit"] != t2["exit"], "the latency sweep actually bites time exits"


def test_out_of_window_cache_bars_never_leak(db):
    # cache holds bars well before as_of and far past the buffer; neither may appear in the window.
    store.upsert_daily_bars(db, "AAAA",
                            [_bar("2024-12-30"), _bar("2024-12-31")] +
                            [_bar(d) for d in _DATES] +
                            [_bar("2025-02-01"), _bar("2025-02-02")])
    bars = make_daily_bars_provider(db)("AAAA", AS_OF, EXIT_BY)
    assert all(AS_OF < b["week_end"] <= "2025-01-15" for b in bars)


# ============================== allow_fetch gating ==============================


def test_cache_only_default_abstains_without_fetch(db, monkeypatch):
    calls = _no_call_guard(monkeypatch)
    provider = make_daily_bars_provider(db)  # empty cache + allow_fetch=False
    assert provider("NONE", AS_OF, EXIT_BY) == []
    assert calls == [], "the cache-only default must never issue a live call"


def test_allow_fetch_true_gap_fetches_once_and_upserts(db, monkeypatch):
    fetched = [dict(_bar(d), source="yfinance", source_grade="yellow",
                    agreeing_sources={"yfinance", "nasdaq"}) for d in _DATES]
    calls = []
    monkeypatch.setattr(
        "catalyst_trader.backtest.daily_provider.prices.get_daily_bars",
        lambda ticker, start, end, **k: calls.append((ticker, start, end)) or fetched,
    )
    provider = make_daily_bars_provider(db, allow_fetch=True)
    bars = provider("BBBB", AS_OF, EXIT_BY)
    assert bars, "the back-filled window is returned"
    assert len(calls) == 1, "exactly ONE wide fetch on a cache miss"
    assert calls[0][0] == "BBBB" and calls[0][1] == AS_OF, "fetch is scoped from as_of"
    # upserted to daily_bar (and re-read on the next call with ZERO further fetches)
    n = db.execute("SELECT count(*) c FROM daily_bar WHERE ticker='BBBB'").fetchone()["c"]
    assert n == len(_DATES)
    provider("BBBB", AS_OF, EXIT_BY)
    assert len(calls) == 1, "a now-covered ticker must not re-fetch"


# ============================== graceful degrade ==============================


def test_empty_fetch_degrades_to_empty(db, monkeypatch):
    monkeypatch.setattr(
        "catalyst_trader.backtest.daily_provider.prices.get_daily_bars", lambda *a, **k: [])
    assert make_daily_bars_provider(db, allow_fetch=True)("X", AS_OF, EXIT_BY) == []


def test_raising_fetch_degrades_to_empty_never_raises(db, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("provider down")
    monkeypatch.setattr(
        "catalyst_trader.backtest.daily_provider.prices.get_daily_bars", _boom)
    assert make_daily_bars_provider(db, allow_fetch=True)("X", AS_OF, EXIT_BY) == []


def test_uncovered_cache_abstains_when_no_bar_at_or_after_exit_by(db, monkeypatch):
    # cache has only pre-exit_by bars -> the time leg can't fire -> not covered -> abstain (no fetch)
    store.upsert_daily_bars(db, "AAAA", [_bar("2025-01-07"), _bar("2025-01-08")])
    calls = _no_call_guard(monkeypatch)
    assert make_daily_bars_provider(db)("AAAA", AS_OF, EXIT_BY) == []
    assert calls == []


# ============================== price_bar isolation + idempotence + migration ==========


def test_writing_daily_bar_leaves_price_bar_untouched(db):
    # a weekly Friday bar in the weekly substrate...
    store.upsert_bars(db, "ISO", [{"week_end": "2025-01-10", "open": 50.0, "high": 51.0,
                                   "low": 49.0, "close": 50.0, "volume": 2_000_000.0}])
    # ...must NOT be overwritten by a same-DATE daily bar written to the separate daily_bar table.
    store.upsert_daily_bars(db, "ISO", [_bar("2025-01-10", close=999.0)])
    wk = db.execute("SELECT close FROM price_bar WHERE ticker='ISO' AND week_end='2025-01-10'").fetchone()
    assert wk["close"] == 50.0, "the weekly price_bar Friday close is byte-for-byte unchanged"
    assert db.execute("SELECT count(*) c FROM price_bar").fetchone()["c"] == 1
    dl = db.execute("SELECT close FROM daily_bar WHERE ticker='ISO' AND trade_date='2025-01-10'").fetchone()
    assert dl["close"] == 999.0, "the daily bar lives in its own isolated table"


def test_upsert_daily_bars_idempotent_updates_in_place(db):
    store.upsert_daily_bars(db, "AAAA", [_bar("2025-01-07", close=100.0)])
    store.upsert_daily_bars(db, "AAAA", [_bar("2025-01-07", close=123.0)])
    rows = db.execute("SELECT close FROM daily_bar WHERE ticker='AAAA' AND trade_date='2025-01-07'").fetchall()
    assert len(rows) == 1, "same (ticker, trade_date) updates in place, no dupes"
    assert rows[0]["close"] == 123.0


def test_migration_014_applies(db):
    tbl = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_bar'").fetchone()
    idx = db.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_daily_bar_ticker_date'"
    ).fetchone()
    assert tbl is not None and idx is not None
    cols = {r["name"] for r in db.execute("PRAGMA table_info(daily_bar)")}
    assert {"ticker", "trade_date", "open", "high", "low", "close", "volume",
            "source", "source_grade", "agreeing_sources", "retrieved_at"} <= cols
