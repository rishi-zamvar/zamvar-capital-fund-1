"""Shared pytest fixtures: migrated in-memory DB, fixture loader, frozen-clock helper."""

import json
from pathlib import Path

import pytest
from freezegun import freeze_time

from catalyst_trader import db as _db
from catalyst_trader import kb as _kb

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def db():
    """In-memory SQLite connection with the schema already migrated. Closes on teardown."""
    conn = _db.connect(":memory:")
    _db.migrate(conn)
    yield conn
    conn.close()


@pytest.fixture
def load_fixture():
    """Return a helper: load_fixture('ctgov_partial_date') -> dict from tests/fixtures/<name>.json."""

    def _load(name: str):
        path = FIXTURES / (name if name.endswith(".json") else f"{name}.json")
        return json.loads(path.read_text())

    return _load


@pytest.fixture
def load_text_fixture():
    """Return a helper: load_text_fixture('rttnews.html') -> raw str from tests/fixtures/<name>."""

    def _load(name: str):
        return (FIXTURES / name).read_text()

    return _load


@pytest.fixture
def embed():
    """Return the deterministic offline hash embedder shared across KB tests."""
    return _kb.hash_embed


@pytest.fixture
def frozen_now():
    """Return freezegun's freeze_time so time-dependent tests (Plan 05) can pin `now()`.

    Usage:
        with frozen_now("2026-11-28T12:00:00Z"):
            ...
    """
    return freeze_time
