"""db.connect concurrency settings: WAL + busy_timeout (playbook fan-out write contention)."""
from catalyst_trader import db as _db


def test_file_db_uses_wal_and_busy_timeout(tmp_path):
    p = str(tmp_path / "t.db")
    c = _db.connect(p)
    assert c.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert c.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
    c.close()


def test_memory_db_skips_wal_but_sets_timeout():
    c = _db.connect(":memory:")
    # in-memory can't be WAL; must not error, and busy_timeout still applies
    assert c.execute("PRAGMA journal_mode").fetchone()[0].lower() in ("memory", "delete")
    assert c.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
    c.close()
