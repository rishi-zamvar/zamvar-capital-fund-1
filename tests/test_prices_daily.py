"""Daily event-window accessor + migration 010 (Phase 6.12 Plan 06, Task 1) — offline.

get_daily_bars gives the T-1..T+2 daily close-to-close granularity that weekly bars cannot,
reusing the shared per-provider daily fetch + cross-check. It runs ONLY the daily-capable subset
(DAILY_PROVIDERS = Tiingo/Nasdaq); it must NOT route through PRICE_PROVIDERS whose rank-0 sources
are weekly-native (that would silently compute the move off WEEKLY closes). The weekly path is a
parity guard: the refactor must not change get_weekly_bars output. ZERO live API.
"""

import json
from pathlib import Path

from catalyst_trader import db as _db
from catalyst_trader.providers import prices

FIXTURES = Path(__file__).parent / "fixtures"


def _nasdaq_window():
    return json.loads((FIXTURES / "nasdaq_daily_event_window.json").read_text())


def _stub_yfinance(monkeypatch):
    """Offline: no live yfinance. The provider lists capture the functions at import time, so
    patching the module attribute alone misses them — swap the yfinance entries in each
    function's default `providers` list."""
    yf = (prices._yf_weekly, prices._yf_daily)
    for fn in (prices.get_weekly_bars, prices.get_daily_bars):
        stubbed = [(lambda *a, **k: []) if p in yf else p for p in fn.__kwdefaults__["providers"]]
        monkeypatch.setitem(fn.__kwdefaults__, "providers", stubbed)


def _wire_nasdaq_only(monkeypatch):
    """Nasdaq returns the daily fixture; the keyed GREEN sources (AV/Tiingo) have no key -> skip."""
    monkeypatch.setattr(prices.settings, "tiingo_api_key", None)
    monkeypatch.setattr(prices.settings, "alpha_vantage_api_key", None)
    monkeypatch.setattr(prices, "get_json", lambda *a, **k: _nasdaq_window())
    _stub_yfinance(monkeypatch)


# ── migration 010 ────────────────────────────────────────────────────────────────────────────


def test_migration_010_creates_catalyst_move():
    conn = _db.connect(":memory:")
    _db.migrate(conn)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(catalyst_move)").fetchall()}
    assert {"id", "catalyst_id", "realized_move", "move_window", "knowable_asof",
            "source_grade", "computed_at"} <= cols
    # FK to catalyst
    fks = conn.execute("PRAGMA foreign_key_list(catalyst_move)").fetchall()
    assert any(fk["table"] == "catalyst" for fk in fks)
    # UNIQUE(catalyst_id, move_window)
    idxs = conn.execute("PRAGMA index_list(catalyst_move)").fetchall()
    uniq_cols = []
    for idx in idxs:
        if idx["unique"]:
            uniq_cols.append({r["name"] for r in conn.execute(f"PRAGMA index_info('{idx['name']}')").fetchall()})
    assert {"catalyst_id", "move_window"} in uniq_cols
    conn.close()


# ── get_daily_bars ───────────────────────────────────────────────────────────────────────────


def test_get_daily_bars_returns_daily_not_weekly(monkeypatch):
    _wire_nasdaq_only(monkeypatch)
    bars = prices.get_daily_bars("TEST", "2026-09-28", "2026-10-09")
    dates = [b["week_end"] for b in bars]
    assert len(bars) == 10  # DAILY, not one weekly bar per Friday
    assert len(set(dates)) == 10  # distinct trade dates
    assert dates == sorted(dates)  # chronological
    # both the T-1 (10/01=99.0) and T+2 (10/06=107.0) daily closes exist for a 10/02 event
    by_date = {b["week_end"]: b["close"] for b in bars}
    assert by_date["2026-10-01"] == 99.0 and by_date["2026-10-06"] == 107.0


def test_get_daily_bars_degrades_to_empty(monkeypatch):
    monkeypatch.setattr(prices.settings, "tiingo_api_key", None)
    monkeypatch.setattr(prices.settings, "alpha_vantage_api_key", None)
    monkeypatch.setattr(prices, "get_json", lambda *a, **k: None)  # every source degrades
    _stub_yfinance(monkeypatch)  # yfinance degrades too
    assert prices.get_daily_bars("TEST", "2026-09-28", "2026-10-09") == []


def test_get_daily_bars_uses_daily_subset_not_price_providers():
    # DAILY_PROVIDERS must exclude the WEEKLY-native sources (_av_weekly / _yf_weekly)...
    assert prices._av_weekly not in prices.DAILY_PROVIDERS
    assert prices._yf_weekly not in prices.DAILY_PROVIDERS
    # ...and be FREE-UNLIMITED ONLY (frugality): yfinance daily + Nasdaq daily. The quota-limited
    # Tiingo daily is a FALLBACK, never in the routine bulk set.
    assert prices._yf_daily in prices.DAILY_PROVIDERS  # reliable multi-year daily source
    assert set(prices.DAILY_PROVIDERS) == {prices._yf_daily, prices._nasdaq_daily_bars}
    assert prices._tiingo_daily_bars not in prices.DAILY_PROVIDERS  # quota source is fallback-only
    assert prices._tiingo_daily_bars in prices.FALLBACK_DAILY_PROVIDERS


def test_get_daily_bars_cross_check_grade(monkeypatch):
    # Two daily providers agree on a date -> highest-grade (green tiingo) wins, both agree.
    def tiingo(t, s, e):
        return [{"week_end": "2026-10-01", "open": 99.0, "high": 100.0, "low": 98.0,
                 "close": 99.0, "volume": 1000, "_source": "tiingo", "_grade": "green"}]

    def nasdaq(t, s, e):
        return [{"week_end": "2026-10-01", "open": 99.0, "high": 100.0, "low": 98.0,
                 "close": 99.1, "volume": 1000, "_source": "nasdaq", "_grade": "yellow"}]

    bars = prices.get_daily_bars("TEST", "2026-09-28", "2026-10-09", providers=[tiingo, nasdaq])
    assert len(bars) == 1
    assert bars[0]["source"] == "tiingo" and bars[0]["source_grade"] == "green"
    assert bars[0]["agreeing_sources"] == {"tiingo", "nasdaq"}


# ── parity guard: the weekly path must be unchanged by the refactor ───────────────────────────


def test_get_weekly_bars_unchanged(monkeypatch):
    _wire_nasdaq_only(monkeypatch)
    bars = prices.get_weekly_bars("TEST", "2026-09-28", "2026-10-09")
    # Nasdaq daily -> resampled to Friday weeks: the 10-day window spans 2 calendar weeks.
    fridays = [b["week_end"] for b in bars]
    assert fridays == ["2026-10-02", "2026-10-09"]
    # each is a real Friday anchor with a weekly close (last day's close of that week)
    by = {b["week_end"]: b for b in bars}
    assert by["2026-10-02"]["close"] == 100.0  # 10/02 is the last trade day of that Mon-Fri week
    assert by["2026-10-09"]["close"] == 118.0  # last of the next week
    for b in bars:
        assert b["source"] == "nasdaq" and b["source_grade"] == "yellow"
