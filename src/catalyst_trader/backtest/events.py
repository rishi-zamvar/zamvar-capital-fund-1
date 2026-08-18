"""BACK-01: the point-in-time, survivorship-free event-set builder.

`build_event_set` walks a weekly `as_of` cursor across the backtest window and, at each week,
assembles a `(as_of, universe, catalysts, has_bars)` record read STRICTLY through the MANDATORY
serving gateway (07.6, decision B) at cutoff=as_of — the SAME seam the live desk reads through at
cutoff=now, so backtest and live execute identical read code (no logic drift):

- universe  -> book.universe(as_of)   (latest cohort valid AND knowable by cutoff, delisted retained)
- bars      -> book.bars(ticker, as_of)  (week_end <= as_of; delisted retained)
- catalysts -> book.catalysts()  (the bitemporal recorded_at<=cutoff resolve). This REPLACES the old
               ad-hoc `tradeable_catalysts` + manual `last_verified_at`-post-filter: the gateway is
               now the SOLE catalyst-knowability gate, resolving each event_date from the append-only
               catalyst_version history so a catalyst recorded (verified) after the simulated week is
               never seen, and a pre-amendment replay returns the pre-amendment date.

The result is survivorship-free (delisted cohort names appear) and look-ahead-impossible on BOTH the
event date (coming hold window) and the knowable/transaction date. The per-class ingestion lag rides
the catalyst read (cat_book carries latency_cfg); bars/universe read a no-lag book (as before).

ponytail: tests run on synthetic fixtures (tests/synth_history.py). Wiring the REAL ~1yr
earnings/PDUFA calendar into the store is a documented carry-forward, not this module's job.
"""

from __future__ import annotations

from datetime import date, timedelta

from .. import serving


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

    while cursor <= end_d:
        as_of = cursor.isoformat()
        hold_end = (cursor + timedelta(days=hold_days)).isoformat()

        # ponytail: the serving gateway is now the SOLE catalyst-knowability gate — the old ad-hoc
        # last_verified_at<=eff post-filter is GONE, replaced by book.catalysts() (bitemporal
        # recorded_at<=cutoff resolve). Two books: bars/universe read with NO lag (as before);
        # catalysts read through cat_book which carries the per-class ingestion lag (latency_cfg),
        # exactly where the old code applied effective_asof("catalyst", ...). A single book can't
        # serve mixed classes when latency_cfg omits "price", so bars/universe use a no-lag book.
        book = serving.asof(conn, cutoff=as_of, latency_cfg=None)
        cat_book = serving.asof(conn, cutoff=as_of, latency_cfg=latency_cfg)

        universe = [u.ticker for u in book.universe(as_of)]

        catalysts = [
            {
                "ticker": c.ticker,
                "catalyst_type": c.catalyst_type.value,
                "event_date": c.event_date,
                "last_verified_at": c.last_verified_at,
            }
            for c in cat_book.catalysts()
            # the gateway already enforced knowability (recorded_at<=cutoff, +lag); here we keep only
            # the coming hold window (as_of < event_date <= hold_end) on the AS-OF-resolved event_date.
            if as_of < c.event_date <= hold_end
        ]

        has_bars = {tk: bool(book.bars(tk, as_of)) for tk in universe}

        records.append({
            "as_of": as_of,
            "anchor": anchor,
            "universe": universe,
            "catalysts": catalysts,
            "has_bars": has_bars,
        })
        cursor += timedelta(days=7)

    return records
