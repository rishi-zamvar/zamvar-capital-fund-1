"""Quick-260819-p1x: the cache-first, as-of-scoped PRODUCTION daily-bars provider.

Task A built the intraweek reflex + latency-honest backtest driven by an INJECTED
`daily_bars_provider` seam `(ticker, as_of, exit_by) -> list[bar]` (synthetic bars in tests). This
wires the REAL feed WITHOUT changing that seam: a closure over the daily_bar cache that reads the
window point-in-time and (only when explicitly allowed) back-fills a gap via the free-unlimited
get_daily_bars. Populating the cache is the vetted job of scripts/cache_daily_bars.py — the backtest
itself defaults `allow_fetch=False` (cache-only, frugal: it can never spray live calls mid-run).

The window this returns is the crux (BLOCKER-1 / CONCERN-2 from plan-check):

  as_of  <  week_end  <=  exit_by + max_delay_bars trading bars

  * STRICT lower bound (as_of < week_end): the ENTRY fills at the NEXT bar after the as_of-close
    signal, never a same-as_of-dated bar (no same-bar entry look-ahead).
  * BUFFERED upper bound (max_delay_bars trading bars PAST exit_by): the exit/entry DECISION is
    still governed by the reflex (time_barrier=exit_by, signal-bar-onward) — these post-exit_by bars
    are the DELAYED-FILL execution supply for the T+1/T+2 latency sweep, NOT decision inputs. Without
    them a time-barrier leg has no bar to fill into at T+1/T+2 and the sweep is inert (T+0==T+1==T+2).
    The buffer is a modelled delayed fill, NOT look-ahead. It also resolves the holiday-`exit_by`
    abstain: the next trading bar past a holiday `exit_by` is now inside the window, so the time leg
    fires instead of abstaining.

max_delay_bars derives from the caller's latency sweep `delays` (default 2 = max((0,1,2))); it is
NOT a fresh magic literal — thread it from the caller.
"""

from __future__ import annotations

from datetime import date, timedelta

from .. import store
from ..providers import prices


def _window(bars: list[dict], as_of: str, exit_by: str, max_delay_bars: int) -> list[dict]:
    """Trim cache bars to `as_of < week_end <= exit_by + max_delay_bars trading bars`.

    Stepping the buffer over the AVAILABLE cache bars (not a calendar) is what makes the buffer a
    real trading-bar count regardless of weekends/holidays. Returns [] when no bar sits at/after
    `exit_by` — the reflex time leg then cannot fire, so the ticker is NOT covered (abstains).
    """
    fwd = [b for b in bars if b["week_end"] > as_of]  # STRICT lower bound (next bar after signal)
    idx = next((i for i, b in enumerate(fwd) if b["week_end"] >= exit_by), None)
    if idx is None:
        return []  # no bar at/after exit_by -> the time barrier can't fire -> not covered
    return fwd[: idx + max_delay_bars + 1]  # + max_delay_bars trading bars of delayed-fill supply


def make_daily_bars_provider(conn, *, allow_fetch: bool = False, max_delay_bars: int = 2):
    """Return `provider(ticker, as_of, exit_by) -> list[dict]` satisfying the engine's daily seam.

    Cache-first: reads daily_bars_asof and trims to the buffered no-look-ahead window. If the window
    is covered (a bar at/after exit_by exists) it is returned — 0 network calls (the frugality
    guarantee). Only if NOT covered AND `allow_fetch` does it call the free-unlimited get_daily_bars
    once, upsert the result to daily_bar, and re-read. `allow_fetch` defaults False so the backtest
    is cache-only: an un-populated ticker simply abstains ([] -> the leg is dropped gracefully).
    Never raises — any miss/degrade returns [].

    # ponytail: a closure over conn, not a class — one seam, no abstraction. The DB read is bounded
    #   by a generous calendar cap (a week per buffered bar always covers weekends+holidays); the
    #   trading-bar count in _window is the real trim, so the cap is never a magic money literal.
    """
    def provider(ticker: str, as_of: str, exit_by: str) -> list[dict]:
        cal_hi = (date.fromisoformat(exit_by) + timedelta(weeks=max(max_delay_bars, 1))).isoformat()
        try:
            bars = store.daily_bars_asof(conn, ticker, as_of, cal_hi)
            window = _window(bars, as_of, exit_by, max_delay_bars)
            if window:
                return window
            if not allow_fetch:
                return []  # cache-only + not covered -> abstain (no live call, frugal default)
            fetched = prices.get_daily_bars(ticker, as_of, cal_hi)  # free-unlimited DAILY_PROVIDERS
            if not fetched:
                return []
            store.upsert_daily_bars(conn, ticker, fetched)
            bars = store.daily_bars_asof(conn, ticker, as_of, cal_hi)
            return _window(bars, as_of, exit_by, max_delay_bars)
        except Exception:
            return []  # abstain, never sink the run

    return provider
