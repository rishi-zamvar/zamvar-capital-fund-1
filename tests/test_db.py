"""Schema + migration-runner tests (money-critical: the store must enforce constraints)."""

import sqlite3

import pytest

from catalyst_trader import db


def _fresh():
    conn = db.connect(":memory:")
    db.migrate(conn)
    return conn


def test_migrate_creates_all_four_tables():
    conn = _fresh()
    names = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"catalyst", "catalyst_source", "universe_snapshot", "schema_version"} <= names


def test_migrate_records_latest_version():
    conn = _fresh()
    latest = db._pending()[-1][0]  # highest numbered migration on disk
    assert conn.execute("SELECT max(version) AS v FROM schema_version").fetchone()["v"] == latest


def test_migrate_is_idempotent():
    conn = _fresh()
    latest = db._pending()[-1][0]
    db.migrate(conn)  # second run must not error or re-apply
    db.migrate(conn)
    assert conn.execute("SELECT max(version) AS v FROM schema_version").fetchone()["v"] == latest


def test_catalyst_type_check_constraint():
    conn = _fresh()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO catalyst "
            "(ticker, catalyst_type, event_date, date_precision, uncertainty_type, "
            " source_origin, created_at, updated_at) "
            "VALUES ('X','bogus','2026-11-30','day','soft','ad_hoc_user','t','t')"
        )


def test_catalyst_source_date_type_check_constraint():
    conn = _fresh()
    conn.execute(
        "INSERT INTO catalyst "
        "(ticker, catalyst_type, event_date, date_precision, uncertainty_type, "
        " source_origin, created_at, updated_at) "
        "VALUES ('X','pdufa','2026-11-30','day','soft','ad_hoc_user','t','t')"
    )
    cid = conn.execute("SELECT id FROM catalyst").fetchone()["id"]
    # valid values insert cleanly
    for dt in ("estimated", "actual"):
        conn.execute(
            "INSERT INTO catalyst_source "
            "(catalyst_id, source_name, source_type, reported_date, date_type, retrieved_at) "
            "VALUES (?, 'FDA', 'primary', '2026-11-30', ?, 't')",
            (cid, dt),
        )
    # bogus value rejected
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO catalyst_source "
            "(catalyst_id, source_name, source_type, reported_date, date_type, retrieved_at) "
            "VALUES (?, 'FDA', 'primary', '2026-11-30', 'bogus', 't')",
            (cid,),
        )


def test_foreign_keys_enforced():
    conn = _fresh()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO catalyst_source "
            "(catalyst_id, source_name, source_type, reported_date, retrieved_at) "
            "VALUES (999, 'FDA', 'primary', '2026-11-30', 't')"
        )
