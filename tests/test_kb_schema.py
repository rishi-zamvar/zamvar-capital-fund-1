"""KB schema smoke tests: sqlite-vec loaded, migration 003 tables present + coexisting, vec roundtrip."""

import pytest
from sqlite_vec import serialize_float32


def test_sqlite_vec_extension_loaded(db):
    ver = db.execute("SELECT vec_version()").fetchone()[0]
    assert isinstance(ver, str) and ver


def test_003_tables_exist(db):
    names = {
        r["name"]
        for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('kb_node','kb_edge')"
        )
    }
    assert {"kb_node", "kb_edge"} <= names
    # vec0 shadow table: confirm it is queryable
    assert db.execute("SELECT count(*) FROM kb_vec").fetchone()[0] == 0
    # Phase-1 table still present (migrations coexist)
    db.execute("SELECT * FROM catalyst")


def test_003_check_enums_reject_bad_values(db):
    db.execute(
        "INSERT INTO kb_node (kind, created_at) VALUES ('company', '2026-08-14')"
    )
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO kb_node (kind, created_at) VALUES ('bogus_kind', '2026-08-14')"
        )
    with pytest.raises(Exception):
        db.execute(
            "INSERT INTO kb_edge (src_id, rel, dst_id) VALUES (1, 'BOGUS_REL', 1)"
        )


def test_vec_roundtrip(db):
    from catalyst_trader import kb
    vec = [0.1] * kb.EMBED_DIM  # tracks the kb_vec dimension (migration 004: 1024)
    db.execute(
        "INSERT INTO kb_vec (node_id, embedding) VALUES (?, ?)",
        (1, serialize_float32(vec)),
    )
    row = db.execute(
        "SELECT node_id, distance FROM kb_vec WHERE embedding MATCH ? ORDER BY distance LIMIT 1",
        (serialize_float32(vec),),
    ).fetchone()
    assert row["node_id"] == 1
    assert abs(row["distance"]) < 1e-5
