"""Append-never-overwrite catalyst revision semantics (DBOOK-02).

An amended event_date appends a NEW catalyst_version row (old retained); an unchanged re-fetch
appends NO version (idempotent). catalyst_version_asof resolves the event_date knowable at a
cutoff — the replay primitive the serving gateway (Plan 02+) builds on. Mirrors S&P Capital IQ
PIT: a period's value comes from the one applicable version whose transaction-time precedes as-of.
"""

from freezegun import freeze_time

from catalyst_trader import store
from catalyst_trader.universe import build
from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    CatalystType,
    DatePrecision,
    DateType,
    SourceOrigin,
    SourceType,
    Uncertainty,
)

T1 = "2026-08-01T00:00:00+00:00"
T2 = "2026-08-10T00:00:00+00:00"


def _source(**over):
    base = dict(
        source_name="ClinicalTrials.gov",
        source_url="https://clinicaltrials.gov/study/NCT1",
        source_type=SourceType.primary,
        reported_date="2026-11-30",
        date_type=DateType.estimated,
        retrieved_at="2026-08-01T00:00:00Z",
    )
    base.update(over)
    return CatalystSource(**base)


def _catalyst(**over):
    base = dict(
        ticker="VRTX",
        company_name="Vertex",
        catalyst_type=CatalystType.pdufa,
        event_date="2026-11-30",
        date_precision=DatePrecision.day,
        uncertainty_type=Uncertainty.window,
        source_origin=SourceOrigin.curated_pdufa,
        external_ref="NCT1",
        sources=[_source()],
    )
    base.update(over)
    return Catalyst(**base)


def test_amended_date_appends_version_and_asof_resolves(db):
    with freeze_time(T1):
        cid = store.insert_catalyst(db, _catalyst(event_date="2026-11-30"))
    with freeze_time(T2):
        cid2 = store.insert_catalyst(db, _catalyst(event_date="2026-12-15"))
    assert cid == cid2  # same (ticker, external_ref) -> same materialized row

    versions = db.execute(
        "SELECT event_date, recorded_at FROM catalyst_version WHERE catalyst_id=? ORDER BY recorded_at",
        (cid,),
    ).fetchall()
    assert [v["event_date"] for v in versions] == ["2026-11-30", "2026-12-15"]

    # main catalyst row = LATEST version (live-view cache)
    assert db.execute("SELECT event_date FROM catalyst WHERE id=?", (cid,)).fetchone()[0] == "2026-12-15"

    # bitemporal replay: OLD date before the amendment cutoff, NEW date after, None before either
    assert store.catalyst_version_asof(db, cid, T1)["event_date"] == "2026-11-30"
    assert store.catalyst_version_asof(db, cid, "2026-08-05T00:00:00+00:00")["event_date"] == "2026-11-30"
    assert store.catalyst_version_asof(db, cid, T2)["event_date"] == "2026-12-15"
    assert store.catalyst_version_asof(db, cid, "2026-07-01T00:00:00+00:00") is None


def test_unchanged_refetch_appends_no_version(db):
    with freeze_time(T1):
        cid = store.insert_catalyst(db, _catalyst(event_date="2026-11-30"))
    with freeze_time(T2):
        store.insert_catalyst(db, _catalyst(event_date="2026-11-30"))  # same date
    n = db.execute("SELECT COUNT(*) FROM catalyst_version WHERE catalyst_id=?", (cid,)).fetchone()[0]
    assert n == 1  # idempotent — no new version on unchanged re-fetch


def test_new_insert_writes_version1(db):
    with freeze_time(T1):
        cid = store.insert_catalyst(db, _catalyst())
    row = db.execute(
        "SELECT event_date, recorded_at FROM catalyst_version WHERE catalyst_id=?", (cid,)
    ).fetchone()
    assert row["event_date"] == "2026-11-30"
    assert row["recorded_at"] == T1


def test_write_scan_flag_stamps_recorded_at(db):
    with freeze_time(T1):
        store.write_scan_flag(db, "VRTX", "2026-08-08", {"flag": 1})
    assert db.execute("SELECT recorded_at FROM scan_flag").fetchone()[0] == T1


def test_build_snapshot_stamps_recorded_at(db):
    with freeze_time(T1):
        build.build_snapshot(db, "2026-08-01", seed_rows=[{"ticker": "VRTX"}])
    stamps = [r[0] for r in db.execute("SELECT recorded_at FROM universe_snapshot").fetchall()]
    assert stamps and all(s == T1 for s in stamps)
