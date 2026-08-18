"""BACK-04: pessimistic gap-open fill model + the data-latency `effective_asof` transform.

Two money-critical, deterministic knobs the backtest engine reads (both tunable, both sitting
in config beside each other):

- `fill_price` — a held-through binary fills at the GAP-OPEN far side, NEVER the stop level:
  a stop is jumped by the event gap and cannot fill inside it (filling at the SL is the classic
  optimistic-backtest lie). Slippage is a tunable far-side haircut. An event is skipped ONLY if
  halted / delisted / zero-volume / zero-quote — volume caps are ignored by design.

- `effective_asof` — subtracts a per-data-class publication lag from the decision date so a datum
  that would only have been available AFTER the decision is never read; ALL reads for that class
  go through `bars_asof(..., effective_asof(class, D, cfg))`. This reuses the shipped `<= as_of`
  guard — it just shifts the argument back. events.py threads it into the catalyst-verification
  filter too.
"""

from __future__ import annotations

from datetime import date, timedelta


def _skip(bar: dict) -> bool:
    """True iff the bar is untradeable: halted / delisted / zero-volume / zero-quote.

    A falsy volume (0 or None) == no trading == halted-or-illiquid. A falsy quote (0/None on any
    of O/H/L/C) == no real price. Volume CAPS are deliberately NOT a skip cause (Decision 2).
    """
    if bar.get("delisted") or bar.get("halted"):
        return True
    if not bar.get("volume"):
        return True
    return any(not bar.get(q) for q in ("open", "high", "low", "close"))


def _worsen(price: float, side: str, slippage: float) -> float:
    """Apply the slippage haircut on the FAR side — always against the position."""
    return price * (1 - slippage) if side == "long" else price * (1 + slippage)


# E8: Robinhood is commission-free, so the round-trip cost is the bid/ask HALF-SPREAD, paid on both
# entry and exit. We have no stored historical quotes, so estimate the half-spread from price — a
# proxy for liquidity (thin, low-priced biotech names quote much wider than large-caps).
# ponytail: price-tiered heuristic, known ceiling — real spreads need quote/price-book data.
# Upgrade path: capture RH get_equity_price_book depth and replace this with the measured half-spread.
def half_spread_pct(price: float) -> float:
    """Estimated one-side (half) bid/ask spread as a fraction of price, by price tier."""
    if price is None or price <= 0:
        return 0.010
    if price < 1:    return 0.010    # sub-$1: ~2% spread
    if price < 5:    return 0.005
    if price < 20:   return 0.0025
    if price < 100:  return 0.0012
    return 0.0006                    # large-cap: ~0.12% spread


def fill_price(
    bars: list[dict],
    *,
    side: str,
    held_through: bool,
    slippage: float,
    sl_level: float | None = None,
) -> float | None:
    """The pessimistic fill for a leg's exit; None if the action bar is untradeable.

    Args:
        bars: chronological weekly OHLCV; bars[-1] is the ACTION bar (the week we fill into).
        side: "long" | "short".
        held_through: the position was held ACROSS the binary event. Then the fill is the
            hold-week OPEN (the gap the market jumped to) worsened by slippage — a stop at
            `sl_level` is jumped and can NEVER fill there. If False, the position was exited
            before the event and fills at the action bar's far-side extreme (low for a long,
            high for a short) plus the haircut.
        slippage: far-side haircut fraction (tunable knob).
        sl_level: the (advisory) stop; accepted for interface completeness and to make the
            money invariant explicit — the held-through fill is deliberately independent of it.

    ponytail: WEEKLY-granularity ceiling. We model enter@prior-close, gap@hold-week-open,
    exit@hold-week action bar — the gap is the only intra-event resolution a weekly store has.
    Upgrade path: feed DAILY bars and fill at the event-day open/next-tick when sub-weekly data
    lands (the store's `week_end` becomes a trade date; this signature is unchanged).
    """
    if not bars:
        raise ValueError("fill_price requires at least one bar")
    if side not in ("long", "short"):
        raise ValueError(f"side must be long|short, got {side!r}")

    bar = bars[-1]
    if _skip(bar):
        return None

    if held_through:
        base = bar["open"]  # the gap open — a stop cannot fill inside the gap
    else:
        base = bar["low"] if side == "long" else bar["high"]  # far side of the action bar

    return _worsen(base, side, slippage)


def effective_asof(data_class: str, decision_date: str, latency_cfg: dict) -> str:
    """Shift `decision_date` back by the per-class publication lag (in DAYS).

    A read for a lagged class at decision date D must go through
    `bars_asof(..., effective_asof(class, D, cfg))` so a datum published only after D is
    never seen. A missing class RAISES — never a silent 0-lag (that would reopen look-ahead).
    """
    if data_class not in latency_cfg:
        raise KeyError(f"no latency configured for data class {data_class!r} (no silent 0-lag)")
    lag_days = latency_cfg[data_class]
    return (date.fromisoformat(decision_date) - timedelta(days=lag_days)).isoformat()
