"""Quick-260819-p1x Task 2 — the vetted, --dry-run-able wide daily-bars populate step.

THE ONE LIVE STEP of this plan — frugality is money-adjacent here (CLAUDE.md). Mirrors
scripts/price_backfill_free.py: FREE-UNLIMITED DAILY_PROVIDERS only (yfinance daily + Nasdaq daily
cross-check — NEVER Tiingo/AV), ONE wide get_daily_bars call per DISTINCT ticker (deduped across all
its events, NOT one call per event), upsert to the isolated daily_bar table, idempotent, skip-on-miss.

--dry-run is DEFAULT-SAFE: it prints the exact call plan (distinct tickers, call count, source, budget)
and EXITS WITHOUT NETWORK — this IS the CLAUDE.md pre-pull vet. The live pull runs ONLY with
--no-dry-run (an explicit operator step, after the dry-run plan has been reviewed).

Offline self-check (--self-check): asserts dedupe (one window per ticker spanning its events) and
one-wide-call-per-ticker on a tmp DB with a monkeypatched get_daily_bars — ZERO live network.
"""

import argparse
import os
import sqlite3
import sys
from datetime import date, timedelta

from catalyst_trader import store
from catalyst_trader.providers import prices

DEFAULT_START = "2025-08-17"   # warm-playbook window (see gen_overnight_report.py)
DEFAULT_END = "2026-08-10"
DEFAULT_DB = "catalyst.db"

# Per-ticker window pad each side of its event dates. Must cover: the entry lookback (build_event_set
# lists a catalyst in the week whose (as_of, as_of+7d] contains event_date, so as_of can be up to ~7d
# pre-event) + the one-week hold to exit_by + the max_delay_bars delayed-fill supply past exit_by.
# 21 calendar days each side is a safe margin over that ~9-trading-bar span (weekends/holidays incl.).
BUFFER_DAYS = 21


def distinct_ticker_windows(conn, start, end):
    """{ticker: (win_start, win_end)}: ONE wide window per DISTINCT ticker spanning ALL its events in
    [start, end], each padded by BUFFER_DAYS. The dedupe is the whole point — one call per ticker."""
    rows = conn.execute(
        "SELECT ticker, event_date FROM catalyst "
        "WHERE event_date IS NOT NULL AND event_date >= ? AND event_date <= ? "
        "ORDER BY ticker, event_date",
        (start, end),
    ).fetchall()
    events: dict[str, list[str]] = {}
    for r in rows:
        events.setdefault(r["ticker"], []).append(r["event_date"])
    windows = {}
    for tk, dates in events.items():
        lo = (date.fromisoformat(min(dates)) - timedelta(days=BUFFER_DAYS)).isoformat()
        hi = (date.fromisoformat(max(dates)) + timedelta(days=BUFFER_DAYS)).isoformat()
        windows[tk] = (lo, hi)
    return windows


def print_plan(windows, start, end):
    """The CLAUDE.md pre-pull vet: distinct tickers, call count, source, budget — zero network."""
    n = len(windows)
    print(f"=== cache_daily_bars VET (dry-run) — warm-playbook window {start}..{end} ===")
    print(f"distinct tickers : {n}")
    print(f"get_daily_bars calls : {n}  (ONE wide call per DISTINCT ticker, deduped across events)")
    print("source : yfinance daily (free-unlimited) + Nasdaq daily cross-check  [DAILY_PROVIDERS]")
    print("budget : yfinance effectively unlimited; Nasdaq is the free cross-check — 0 paid quota spent")
    for tk, (lo, hi) in sorted(windows.items()):
        print(f"  {tk:8s} {lo} .. {hi}")


def live_pull(conn, windows):
    """Free-unlimited wide pull per ticker -> upsert to daily_bar. Idempotent; skip (never error) on
    a free-source miss. Called ONLY without --dry-run (the operator step)."""
    done, skipped = [], []
    total = len(windows)
    for i, (tk, (lo, hi)) in enumerate(sorted(windows.items()), 1):
        try:
            bars = prices.get_daily_bars(tk, lo, hi) or []  # DAILY_PROVIDERS = free-unlimited only
        except Exception as exc:
            bars = []
            print(f"[{i}/{total}] {tk}: ERROR {exc} — SKIP", flush=True)
        if not bars:
            skipped.append(tk)
            print(f"[{i}/{total}] {tk}: no free-source daily bars — SKIP (no quota spent)", flush=True)
            continue
        store.upsert_daily_bars(conn, tk, bars, source="cascade")
        done.append(tk)
        print(f"[{i}/{total}] {tk}: {len(bars)} daily bars upserted", flush=True)
    print(f"\n=== DONE === upserted:{len(done)}  skipped(free-miss):{len(skipped)}", flush=True)
    print("skipped:", skipped, flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=os.environ.get("CATALYST_DB", DEFAULT_DB))
    ap.add_argument("--start", default=os.environ.get("BACKTEST_START", DEFAULT_START))
    ap.add_argument("--end", default=os.environ.get("BACKTEST_END", DEFAULT_END))
    ap.add_argument("--dry-run", action="store_true", default=True,
                    help="(default) print the vetted plan and EXIT — zero network")
    ap.add_argument("--no-dry-run", dest="dry_run", action="store_false",
                    help="ACTUALLY pull (operator step, after vetting the dry-run plan)")
    ap.add_argument("--self-check", action="store_true",
                    help="offline assert-based self-check (no network)")
    args = ap.parse_args(argv)

    if args.self_check:
        return _self_check()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row  # store.upsert_daily_bars reads existing["id"]
    windows = distinct_ticker_windows(conn, args.start, args.end)
    print_plan(windows, args.start, args.end)
    if args.dry_run:
        print("\nDRY RUN — no network calls made. Re-run with --no-dry-run to pull (operator step).")
        return 0
    live_pull(conn, windows)
    return 0


def _self_check():
    """Offline: dedupe (one window/ticker spanning its events) + one-wide-call-per-ticker. No network."""
    from datetime import timedelta as _td

    from catalyst_trader import db as _db
    from catalyst_trader.models import (
        Catalyst, CatalystSource, CatalystType, DatePrecision, SourceOrigin,
        SourceType, Status, Uncertainty,
    )

    def _cat(ticker, event_date):
        return Catalyst(
            ticker=ticker, company_name=ticker, catalyst_type=CatalystType.pdufa,
            event_date=event_date, date_precision=DatePrecision.day,
            uncertainty_type=Uncertainty.firm, status=Status.verified,
            source_origin=SourceOrigin.curated_pdufa, last_verified_at=f"{event_date}T00:00:00Z",
            external_ref=f"{ticker}:{event_date}",
            sources=[CatalystSource(source_name="FDA", source_url="https://www.fda.gov/x",
                                    source_type=SourceType.primary, reported_date=event_date,
                                    date_type="actual", retrieved_at=f"{event_date}T00:00:00Z")],
        )

    conn = _db.connect(":memory:")
    _db.migrate(conn)
    # two events for AAAA (must dedupe to ONE window spanning both), one for BBBB, one OUT of window.
    store.insert_catalyst(conn, _cat("AAAA", "2025-09-01"))
    store.insert_catalyst(conn, _cat("AAAA", "2025-11-01"))
    store.insert_catalyst(conn, _cat("BBBB", "2025-10-01"))
    store.insert_catalyst(conn, _cat("ZZZZ", "2030-01-01"))  # outside the window -> excluded

    windows = distinct_ticker_windows(conn, DEFAULT_START, DEFAULT_END)
    assert set(windows) == {"AAAA", "BBBB"}, windows  # dedupe + window filter
    lo, hi = windows["AAAA"]
    assert lo == (date.fromisoformat("2025-09-01") - _td(days=BUFFER_DAYS)).isoformat()
    assert hi == (date.fromisoformat("2025-11-01") + _td(days=BUFFER_DAYS)).isoformat()

    # one-wide-call-per-ticker: monkeypatch get_daily_bars via the module reference (no network).
    calls = []
    orig = prices.get_daily_bars
    prices.get_daily_bars = lambda tk, s, e: calls.append((tk, s, e)) or [
        {"week_end": s, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}]
    try:
        live_pull(conn, windows)
    finally:
        prices.get_daily_bars = orig
    assert len(calls) == len(windows) == 2, calls  # exactly ONE call per DISTINCT ticker
    assert {c[0] for c in calls} == {"AAAA", "BBBB"}
    n = conn.execute("SELECT count(*) c FROM daily_bar").fetchone()["c"]
    assert n == 2, n
    conn.close()
    print("cache_daily_bars self-check: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
