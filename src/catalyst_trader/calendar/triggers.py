"""T-2 trigger seam + 48h near-event staleness exclusion (DATA-05, DATA-03).

Workflow 1 does NOT exist in Phase 1 — this module is only the pluggable seam.
``detect_and_fire`` records a ``trigger_event`` row and calls the registered
callback (default: log; a notification hook is left as a comment). Phases 4+
register the real Workflow-1 launcher via ``register_callback``. Do NOT build
Workflow 1 here.

All time logic is timezone-naive US calendar-date arithmetic (per 01-RESEARCH):
day-deltas are computed on the date; the 48h freshness window is computed in hours
against ``last_verified_at``. Only day-precision catalysts can pin a T-2 day — a
month/quarter/year window is too wide to identify the T-2 boundary, so it never
fires (documented rule below).
"""

import logging
import sqlite3
from collections.abc import Callable
from datetime import date, datetime, time, timedelta, timezone

from catalyst_trader.config import settings
from catalyst_trader.dates import parse_precision
from catalyst_trader.models import DatePrecision, Status

logger = logging.getLogger(__name__)

# T-2 window: a verified catalyst 1 or 2 calendar days out.
T2_MIN_DAYS = 1
T2_MAX_DAYS = 2

# Module-level callback registry. Empty -> the default log callback is used.
_callbacks: list[Callable[[sqlite3.Row], None]] = []


def register_callback(fn: Callable[[sqlite3.Row], None]) -> None:
    """Register a callback invoked with the catalyst row when it is T-2.

    Phases 4+ register the real Workflow-1 launcher here. Workflow 1 is NOT built
    in this phase — with nothing registered, firing only logs.
    """
    _callbacks.append(fn)


def _default_callback(row: sqlite3.Row) -> None:
    # ponytail: log-only seam. A notification hook (ZeeChat/ntfy) plugs in here
    # by calling register_callback — no notification dependency in Phase 1.
    logger.info(
        "T-2 trigger: catalyst id=%s %s %s event=%s",
        row["id"],
        row["ticker"],
        row["catalyst_type"],
        row["event_date"],
    )


def _fire(row: sqlite3.Row) -> None:
    for fn in (_callbacks or [_default_callback]):
        fn(row)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _window_start(event_date: str) -> date:
    """The earliest day the event could fall on, given the source's precision."""
    p = parse_precision(event_date)
    if p is DatePrecision.day:
        return date.fromisoformat(event_date)
    if p is DatePrecision.month:
        y, m = event_date.split("-")
        return date(int(y), int(m), 1)
    return date(int(event_date), 1, 1)  # year-only window start


def exclude_stale(conn: sqlite3.Connection, now: datetime | None = None) -> list[int]:
    """Exclude near-event catalysts that could not be re-verified in time (DATA-03).

    A catalyst within ``freshness_near_event_hours`` of its event whose
    ``last_verified_at`` is older than that window (or missing) is set
    status='excluded' — never traded on a stale date, never deleted. Returns the
    affected ids. A catalyst re-verified inside the window (fresh stamp) is kept.
    """
    now = _aware(now or datetime.now(timezone.utc))
    near = timedelta(hours=settings.freshness_near_event_hours)
    excluded: list[int] = []

    rows = conn.execute(
        "SELECT * FROM catalyst WHERE status IN (?, ?)",
        (Status.unverified.value, Status.verified.value),
    ).fetchall()
    for row in rows:
        event_dt = _aware(datetime.combine(_window_start(row["event_date"]), time.min))
        to_event = event_dt - now
        if not (timedelta(0) <= to_event <= near):
            continue  # not near the event — freshness rule does not bite yet
        lv = row["last_verified_at"]
        stale = lv is None or (now - _aware(datetime.fromisoformat(lv))) > near
        if stale:
            conn.execute(
                "UPDATE catalyst SET status=?, updated_at=? WHERE id=?",
                (Status.excluded.value, now.isoformat(), row["id"]),
            )
            excluded.append(row["id"])
    conn.commit()
    return excluded


def detect_and_fire(conn: sqlite3.Connection, now: datetime | None = None) -> list[int]:
    """Fire the trigger seam for verified catalysts 1-2 days out (DATA-05).

    Only day-precision catalysts fire: a month/quarter/year date is a window too
    wide to pin the T-2 boundary, so it is skipped. Firing is idempotent — a
    ``trigger_event`` row (unique per catalyst+event_date) dedups repeat runs, so
    a second run the same day (or the next day when T-2 becomes T-1) does not
    re-fire. Returns the ids fired on this run.
    """
    now = _aware(now or datetime.now(timezone.utc))
    today = now.date()
    fired: list[int] = []

    rows = conn.execute(
        "SELECT * FROM catalyst WHERE status=?", (Status.verified.value,)
    ).fetchall()
    for row in rows:
        if parse_precision(row["event_date"]) is not DatePrecision.day:
            continue  # window too wide to pin T-2 — do not spuriously fire
        days = (date.fromisoformat(row["event_date"]) - today).days
        if not (T2_MIN_DAYS <= days <= T2_MAX_DAYS):
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO trigger_event (catalyst_id, event_date, fired_at) "
            "VALUES (?, ?, ?)",
            (row["id"], row["event_date"], now.isoformat()),
        )
        if cur.rowcount:  # a new trigger row was recorded -> fire exactly once
            _fire(row)
            fired.append(row["id"])
    conn.commit()
    return fired
