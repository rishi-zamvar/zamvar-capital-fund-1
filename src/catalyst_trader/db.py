"""Single-file SQLite store: connection + numbered-migration runner with schema_version tracking."""

import re
import sqlite3
from pathlib import Path

from catalyst_trader.config import settings

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_MIGRATION_RE = re.compile(r"^(\d+)_.*\.sql$")


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path if path is not None else settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _current_version(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT max(version) AS v FROM schema_version").fetchone()
    return row["v"] or 0


def _pending() -> list[tuple[int, Path]]:
    found = []
    for path in MIGRATIONS_DIR.glob("*.sql"):
        m = _MIGRATION_RE.match(path.name)
        if m:
            found.append((int(m.group(1)), path))
    return sorted(found)


def migrate(conn: sqlite3.Connection) -> None:
    """Apply every migrations/NNN_*.sql with NNN > current version, in order. Idempotent."""
    current = _current_version(conn)
    for version, path in _pending():
        if version <= current:
            continue
        conn.executescript(path.read_text())
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
        conn.commit()
