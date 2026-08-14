"""T-2 trigger seam + 48h near-event staleness exclusion — all time logic frozen.

freezegun pins ``now`` so the T-2 boundary and the 48h freshness window are tested
deterministically. Workflow 1 does NOT exist — these tests only exercise the seam
(a recorded trigger row + a pluggable callback).
"""

from datetime import datetime, timezone

import pytest
from freezegun import freeze_time

from catalyst_trader import store
from catalyst_trader.calendar import triggers
from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    CatalystType,
    DatePrecision,
    SourceOrigin,
    SourceType,
    Status,
    Uncertainty,
)


@pytest.fixture(autouse=True)
def _clear_callbacks():
    """Each test starts with an empty registry (module-level state)."""
    triggers._callbacks.clear()
    yield
    triggers._callbacks.clear()


def _make(db, event_date, status, last_verified_at=None, precision=DatePrecision.day, ticker="VRTX"):
    c = Catalyst(
        ticker=ticker,
        catalyst_type=CatalystType.pdufa,
        event_date=event_date,
        date_precision=precision,
        uncertainty_type=Uncertainty.firm,
        source_origin=SourceOrigin.curated_pdufa,
        sources=[
            CatalystSource(
                source_name="FDA",
                source_url="https://www.fda.gov/x",
                source_type=SourceType.primary,
                reported_date=event_date,
                retrieved_at="2026-08-14T00:00:00Z",
            )
        ],
    )
    cid = store.insert_catalyst(db, c)
    db.execute(
        "UPDATE catalyst SET status=?, last_verified_at=? WHERE id=?",
        (status.value, last_verified_at, cid),
    )
    db.commit()
    return cid


# --- T-2 trigger seam --------------------------------------------------------


def test_t2_trigger_fires_for_1_and_2_days_out_only(db):
    with freeze_time("2026-11-28T12:00:00Z"):
        one = _make(db, "2026-11-29", Status.verified, ticker="AAA")   # 1 day out
        two = _make(db, "2026-11-30", Status.verified, ticker="BBB")   # 2 days out
        _make(db, "2026-12-03", Status.verified, ticker="CCC")         # 5 days out
        _make(db, "2026-11-29", Status.unverified, ticker="DDD")       # unverified 1 day out

        seen = []
        triggers.register_callback(lambda row: seen.append(row["id"]))
        fired = triggers.detect_and_fire(db, now=datetime.now(timezone.utc))

    assert sorted(fired) == sorted([one, two])
    assert sorted(seen) == sorted([one, two])


def test_default_callback_does_not_crash_without_registration(db):
    with freeze_time("2026-11-28T12:00:00Z"):
        cid = _make(db, "2026-11-29", Status.verified)
        fired = triggers.detect_and_fire(db, now=datetime.now(timezone.utc))
    assert fired == [cid]  # logged via the default callback, no exception


def test_detect_and_fire_is_idempotent_no_double_fire(db):
    with freeze_time("2026-11-28T12:00:00Z"):
        cid = _make(db, "2026-11-29", Status.verified)
        seen = []
        triggers.register_callback(lambda row: seen.append(row["id"]))
        first = triggers.detect_and_fire(db, now=datetime.now(timezone.utc))
        second = triggers.detect_and_fire(db, now=datetime.now(timezone.utc))
    assert first == [cid]
    assert second == []          # already recorded -> not re-fired
    assert seen == [cid]         # callback invoked exactly once


def test_partial_month_date_does_not_spuriously_fire(db):
    # window start of "2026-12" is 2026-12-01 => 2 days from now, but precision is
    # a month (too wide to pin a T-2 day) so it must NOT fire.
    with freeze_time("2026-11-29T12:00:00Z"):
        _make(db, "2026-12", Status.verified, precision=DatePrecision.month)
        fired = triggers.detect_and_fire(db, now=datetime.now(timezone.utc))
    assert fired == []


# --- 48h near-event re-verification / staleness ------------------------------


def test_48h_reverify_excludes_stale_keeps_fresh(db):
    with freeze_time("2026-11-28T12:00:00Z"):
        stale = _make(db, "2026-11-29", Status.verified, last_verified_at="2026-11-20T00:00:00Z", ticker="STL")
        fresh = _make(db, "2026-11-29", Status.verified, last_verified_at="2026-11-28T00:00:00Z", ticker="FRS")
        far = _make(db, "2026-12-20", Status.verified, last_verified_at="2026-11-01T00:00:00Z", ticker="FAR")
        never = _make(db, "2026-11-29", Status.verified, last_verified_at=None, ticker="NVR")

        excluded = triggers.exclude_stale(db, now=datetime.now(timezone.utc))

    assert sorted(excluded) == sorted([stale, never])
    assert store.get_catalyst(db, fresh).status is Status.verified   # re-verified in-window
    assert store.get_catalyst(db, far).status is Status.verified     # not near the event
    assert store.get_catalyst(db, stale).status is Status.excluded


def test_exclude_never_deletes(db):
    with freeze_time("2026-11-28T12:00:00Z"):
        cid = _make(db, "2026-11-29", Status.verified, last_verified_at="2026-11-01T00:00:00Z")
        triggers.exclude_stale(db, now=datetime.now(timezone.utc))
    # row still exists (excluded, never deleted) — audit/backtest need the history
    assert store.get_catalyst(db, cid) is not None
    assert store.get_catalyst(db, cid).status is Status.excluded
