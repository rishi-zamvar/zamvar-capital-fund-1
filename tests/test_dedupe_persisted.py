"""E7 — cross-source persisted catalyst dedupe (the gap _dedup_catalysts can't cover)."""
from catalyst_trader import db as _db
from catalyst_trader.universe.discover import dedupe_persisted_catalysts


def _cat(conn, cid, ticker, ev, ct, created):
    conn.execute(
        "INSERT INTO catalyst (id,ticker,catalyst_type,event_date,date_precision,uncertainty_type,"
        "status,source_origin,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (cid, ticker, ct, ev, "day", "firm", "resolved", "curated_pdufa", created, created))
    conn.execute("INSERT INTO catalyst_version (catalyst_id,event_date,recorded_at) VALUES (?,?,?)",
                 (cid, ev, created))


def test_dedupe_collapses_cross_source_dupes_keeping_earliest():
    c = _db.connect(":memory:"); _db.migrate(c)
    # same (ticker,event_date,type) from two sources -> one earnings event
    _cat(c, 1, "BBIO", "2026-08-10", "earnings", "2026-08-16T09:00:00Z")  # nasdaq seed (earliest)
    _cat(c, 2, "BBIO", "2026-08-10", "earnings", "2026-08-18T03:00:00Z")  # reclassified 8-K
    _cat(c, 3, "IONS", "2026-07-29", "earnings", "2026-08-01T00:00:00Z")  # unique, keep
    c.commit()
    deleted = dedupe_persisted_catalysts(c)
    assert deleted == 1
    remaining = {r["id"] for r in c.execute("SELECT id FROM catalyst")}
    assert remaining == {1, 3}                       # kept earliest (id 1) + the unique (id 3)
    # cascade cleaned the dropped id's version
    assert c.execute("SELECT COUNT(*) FROM catalyst_version WHERE catalyst_id=2").fetchone()[0] == 0


def test_dedupe_idempotent():
    c = _db.connect(":memory:"); _db.migrate(c)
    _cat(c, 1, "BBIO", "2026-08-10", "earnings", "2026-08-16T09:00:00Z")
    _cat(c, 2, "BBIO", "2026-08-10", "earnings", "2026-08-18T03:00:00Z")
    c.commit()
    assert dedupe_persisted_catalysts(c) == 1
    assert dedupe_persisted_catalysts(c) == 0        # nothing left to collapse
