"""KB schema smoke tests: sqlite-vec loaded, migration 003 tables present + coexisting, vec roundtrip."""

import pytest
from sqlite_vec import serialize_float32


def test_sqlite_vec_extension_loaded(db):
    ver = db.execute("SELECT vec_version()").fetchone()[0]
    assert isinstance(ver, str) and ver
