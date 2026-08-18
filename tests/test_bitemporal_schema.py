"""Migration 011 — bitemporal schema tests (DBOOK-01).

Asserts the additive migration adds the two genuinely-MISSING transaction-time stamps
(scan_flag.recorded_at, universe_snapshot.recorded_at) + the append-only catalyst_version
history table, and that the backfill is non-destructive + idempotent (re-runnable, never
double-seeds). See 07.6-CONTEXT stamp_audit for why these three are the only stamps added.
"""

from catalyst_trader import db as _db


def _cols(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _migrate_upto(conn, n):
    """Apply migrations 001..n via the shipped runner's file list (simulate a pre-011 db)."""
    _db._current_version(conn)  # creates schema_version if absent
    for version, path in _db._pending():
        if version > n:
            continue
        conn.executescript(path.read_text())
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    conn.commit()


def _seed_pre011(conn):
    """Insert one catalyst + scan_flag + universe_snapshot row using the pre-011 schema."""
    conn.execute(
        "INSERT INTO catalyst (ticker, catalyst_type, event_date, date_precision, "
        "uncertainty_type, status, source_origin, created_at, updated_at) "
        "VALUES ('ABCD','pdufa','2026-11-14','day','firm','verified','curated_pdufa',"
        "'2026-08-01T00:00:00+00:00','2026-08-01T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO scan_flag (ticker, week_end, payload, routed) "
        "VALUES ('ABCD','2026-08-08','{}',0)"
    )
    conn.execute(
        "INSERT INTO universe_snapshot (as_of_date, ticker, included, delisted) "
        "VALUES ('2026-08-01','ABCD',1,0)"
    )
    conn.commit()


def test_migration_adds_recorded_at_and_catalyst_version():
    conn = _db.connect(":memory:")
    _db.migrate(conn)
    assert "recorded_at" in _cols(conn, "scan_flag")
    assert "recorded_at" in _cols(conn, "universe_snapshot")
    assert _cols(conn, "catalyst_version") == {
        "id",
        "catalyst_id",
        "event_date",
        "event_date_end",
        "recorded_at",
    }
    conn.close()


def test_backfill_is_nondestructive():
    conn = _db.connect(":memory:")
    _migrate_upto(conn, 10)  # pre-011 state
    _seed_pre011(conn)
    _db.migrate(conn)  # applies 011 (the only pending) + backfills

    # scan_flag.recorded_at <- week_end; universe_snapshot.recorded_at <- as_of_date
    assert conn.execute("SELECT recorded_at FROM scan_flag").fetchone()[0] == "2026-08-08"
    assert conn.execute("SELECT recorded_at FROM universe_snapshot").fetchone()[0] == "2026-08-01"

    # catalyst_version seeded with one version-1 row per existing catalyst, recorded_at=created_at
    rows = conn.execute("SELECT * FROM catalyst_version").fetchall()
    assert len(rows) == 1
    assert rows[0]["event_date"] == "2026-11-14"
    assert rows[0]["recorded_at"] == "2026-08-01T00:00:00+00:00"
    conn.close()


def test_backfill_is_idempotent():
    conn = _db.connect(":memory:")
    _migrate_upto(conn, 10)
    _seed_pre011(conn)
    _db.migrate(conn)

    # migrate() again is a no-op (version already recorded) — no duplicate versions
    _db.migrate(conn)
    assert conn.execute("SELECT COUNT(*) FROM catalyst_version").fetchone()[0] == 1

    # re-running the guarded backfill DML must also be safe (WHERE NOT EXISTS / recorded_at IS NULL)
    conn.executescript(
        "INSERT INTO catalyst_version (catalyst_id, event_date, event_date_end, recorded_at) "
        "SELECT c.id, c.event_date, c.event_date_end, c.created_at FROM catalyst c "
        "WHERE NOT EXISTS (SELECT 1 FROM catalyst_version v WHERE v.catalyst_id = c.id);"
        "UPDATE scan_flag SET recorded_at = week_end WHERE recorded_at IS NULL;"
        "UPDATE universe_snapshot SET recorded_at = as_of_date WHERE recorded_at IS NULL;"
    )
    assert conn.execute("SELECT COUNT(*) FROM catalyst_version").fetchone()[0] == 1
    assert conn.execute("SELECT recorded_at FROM scan_flag").fetchone()[0] == "2026-08-08"
    conn.close()
