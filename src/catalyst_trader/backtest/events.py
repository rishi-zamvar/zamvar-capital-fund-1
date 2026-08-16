"""BACK-01: the point-in-time, survivorship-free event-set builder.

`build_event_set` walks a weekly `as_of` cursor across the backtest window and, at each
week, assembles a `(as_of, universe, catalysts, has_bars)` record read STRICTLY through
the shipped no-look-ahead guards:

- universe  -> universe.build.universe_as_of (latest cohort <= as_of, delisted retained)
- bars      -> store.bars_asof (week_end <= as_of, delisted retained)
- catalysts -> store.tradeable_catalysts THEN a MANDATORY post-filter on
               `last_verified_at <= effective_asof`. tradeable_catalysts is status-only
               (no date guard, store.py L166), so on a historical replay it returns
               catalysts verified AFTER the simulated week; the post-filter is the
               money-honesty fix that closes that verification look-ahead.

The result is survivorship-free (delisted cohort names appear) and look-ahead-impossible
on BOTH the event date (coming hold window) and the verification date.

ponytail: tests run on synthetic fixtures (tests/synth_history.py). Wiring the REAL ~1yr
earnings/PDUFA calendar into the store is a documented carry-forward, not this module's job.
"""

from __future__ import annotations

from datetime import date, timedelta

from ..store import bars_asof, tradeable_catalysts_light
from ..universe.build import universe_as_of


def build_event_set(
    conn,
    *,
    start: str,
    end: str,
    anchor: str = "MON",
    hold_days: int = 7,
    latency_cfg: dict | None = None,
) -> list[dict]:
    """Assemble chronological weekly event records over [start, end].

    Args:
        start/end: ISO week_end bounds; the cursor steps 7 days.
        anchor: the reference day (MON_OPEN / FRI_CLOSE) the engine enters/exits on — carried
            on each record; the same single anchor thesis_scan measures on (measurement==execution).
        hold_days: the upcoming-catalyst horizon. Default 7 = the one-week hold (a catalyst
            appears only in the week whose (as_of, as_of+7d] window contains its event_date).
            Widen it to list catalysts across the weeks leading up to the event.
        latency_cfg: per-data-class lag knob (fill.effective_asof). None => the catalyst
            verification filter compares against `as_of` directly (no data-latency shift).

    Each record: {as_of, anchor, universe: [ticker], catalysts: [{ticker, catalyst_type,
    event_date, last_verified_at}], has_bars: {ticker: bool}}.
    """
    records: list[dict] = []
    cursor = date.fromisoformat(start)
    end_d = date.fromisoformat(end)

    # status='verified' is week-invariant, so read the whole verified set ONCE; the per-week
    # date/verification guards below still filter it against each as_of (no look-ahead change).
    verified = tradeable_catalysts_light(conn)

    while cursor <= end_d:
        as_of = cursor.isoformat()
        hold_end = (cursor + timedelta(days=hold_days)).isoformat()

        # effective_asof lives in fill.py; import lazily so events tests (latency_cfg=None)
        # never require it, and the two modules can ship in either order within this plan.
        if latency_cfg:
            from .fill import effective_asof
            eff = effective_asof("catalyst", as_of, latency_cfg)
        else:
            eff = as_of

        universe = [u.ticker for u in universe_as_of(conn, as_of)]

        catalysts = [
            {
                "ticker": c.ticker,
                "catalyst_type": c.catalyst_type.value,
                "event_date": c.event_date,
                "last_verified_at": c.last_verified_at,
            }
            for c in verified
            # event is in the coming hold window (no past/too-far-future event) ...
            if as_of < c.event_date <= hold_end
            # ... AND we could actually have known it was verified by the effective as_of.
            # tradeable_catalysts_light has NO date guard, so this filter is mandatory (BACK-01).
            and c.last_verified_at is not None
            and c.last_verified_at <= eff
        ]

        has_bars = {tk: bool(bars_asof(conn, tk, as_of)) for tk in universe}

        records.append({
            "as_of": as_of,
            "anchor": anchor,
            "universe": universe,
            "catalysts": catalysts,
            "has_bars": has_bars,
        })
        cursor += timedelta(days=7)

    return records
