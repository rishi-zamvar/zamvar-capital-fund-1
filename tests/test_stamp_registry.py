"""Full STAMP_REGISTRY + per-table accessors (DBOOK-05).

The registry encodes the audited knowable stamp for every served table. Key fixes proven here:
the catalyst event_date bug (resolve via catalyst_version_asof, NEVER gate on event_date), the
price_bar/company_card backfill trap (week_end, never retrieved_at), and scan_flag/universe gating
on recorded_at. Every accessor is behaviour-preserving on correct data + leak-denying post-cutoff.
"""

import pytest
from freezegun import freeze_time

from catalyst_trader import db as _db
from catalyst_trader import store
from catalyst_trader import serving
from catalyst_trader.serving import LookAheadDenied
from catalyst_trader.universe import build
from catalyst_trader.models import (
    Catalyst, CatalystSource, CatalystType, DatePrecision, DateType,
    SourceOrigin, SourceType, Status, Uncertainty,
)


@pytest.fixture
def conn():
    c = _db.connect(":memory:")
    _db.migrate(c)
    yield c
    c.close()


def _source(**over):
    base = dict(
        source_name="ClinicalTrials.gov", source_url="https://clinicaltrials.gov/study/NCT1",
        source_type=SourceType.primary, reported_date="2027-06-01",
        date_type=DateType.estimated, retrieved_at="2026-08-01T00:00:00Z",
    )
    base.update(over)
    return CatalystSource(**base)


def _catalyst(**over):
    base = dict(
        ticker="ABCD", company_name="Abcd", catalyst_type=CatalystType.pdufa,
        event_date="2027-06-01", date_precision=DatePrecision.day,
        uncertainty_type=Uncertainty.window, status=Status.verified,
        source_origin=SourceOrigin.curated_pdufa, external_ref="NCT1", sources=[_source()],
    )
    base.update(over)
    return Catalyst(**base)


# --- registry coverage ----------------------------------------------------------------------

def test_registry_covers_all_served_tables():
    assert set(serving.STAMP_REGISTRY) == {
        "catalyst", "catalyst_move", "trigger_event", "kb_node", "kb_edge",
        "price_bar", "company_card", "universe_snapshot", "scan_flag",
    }


def test_retrieved_at_only_in_comments_never_in_where():
    """The backfill trap: price_bar/company_card must gate on week_end, never retrieved_at."""
    import pathlib
    src = pathlib.Path(serving.__file__).read_text()
    for line in src.splitlines():
        stripped = line.strip()
        if "retrieved_at" in stripped and not stripped.startswith("#"):
            pytest.fail(f"retrieved_at outside a comment (backfill trap): {line!r}")


# --- catalyst accessor: the event_date bug fix ----------------------------------------------

def test_catalyst_never_gates_on_event_date(conn):
    # A: future event_date but recorded (knowable) in the PAST -> served at a later cutoff.
    with freeze_time("2026-08-01T00:00:00+00:00"):
        store.insert_catalyst(conn, _catalyst(ticker="AAAA", external_ref="A", event_date="2027-06-01"))
    # B: recorded only in the FUTURE relative to the cutoff -> excluded (gate is recorded_at).
    with freeze_time("2026-09-01T00:00:00+00:00"):
        store.insert_catalyst(conn, _catalyst(ticker="BBBB", external_ref="B", event_date="2027-01-01"))

    book = serving.asof(conn, "2026-08-15T00:00:00+00:00")
    tickers = {c.ticker for c in book.catalysts()}
    assert "AAAA" in tickers  # future event_date is NOT a knowability gate
    assert "BBBB" not in tickers  # its only version was recorded after the cutoff


def test_catalyst_amended_date_asof(conn):
    with freeze_time("2026-08-01T00:00:00+00:00"):
        store.insert_catalyst(conn, _catalyst(event_date="2027-06-01"))
    with freeze_time("2026-09-01T00:00:00+00:00"):
        store.insert_catalyst(conn, _catalyst(event_date="2027-07-15"))  # amended

    old = serving.asof(conn, "2026-08-15T00:00:00+00:00").catalysts()
    new = serving.asof(conn, "2026-09-15T00:00:00+00:00").catalysts()
    assert [c.event_date for c in old] == ["2027-06-01"]
    assert [c.event_date for c in new] == ["2027-07-15"]


def test_catalyst_gate_uses_recorded_at_not_last_verified_at(conn):
    """Plan-check nit #1: the gate is the version's recorded_at (transaction time), NOT
    last_verified_at (a later re-verification stamp). A catalyst last-verified AFTER the cutoff
    but whose version was recorded BEFORE it is still served — proving the gate semantics."""
    with freeze_time("2026-08-01T00:00:00+00:00"):
        cid = store.insert_catalyst(conn, _catalyst(event_date="2027-06-01"))
    # last_verified_at is a much later re-verification (post-cutoff); recorded_at stays 2026-08-01.
    conn.execute("UPDATE catalyst SET last_verified_at=? WHERE id=?", ("2026-12-31T00:00:00+00:00", cid))
    conn.commit()
    assert conn.execute("SELECT last_verified_at FROM catalyst WHERE id=?", (cid,)).fetchone()[0] \
        != conn.execute("SELECT recorded_at FROM catalyst_version WHERE catalyst_id=?", (cid,)).fetchone()[0]

    book = serving.asof(conn, "2026-08-15T00:00:00+00:00")  # after recorded_at, before last_verified_at
    assert {c.ticker for c in book.catalysts()} == {"ABCD"}  # gated on recorded_at, not last_verified_at


# --- card / scan_flag / universe accessors --------------------------------------------------

def test_card_behaviour_preserved(conn):
    store.write_card(conn, "ABCD", "2026-01-10", {"x": 1})
    book = serving.asof(conn, "2026-01-31")
    assert book.card("ABCD", "2026-01-31") == store.card_asof(conn, "ABCD", "2026-01-31")


def test_card_denies_post_cutoff(conn):
    store.write_card(conn, "ABCD", "2026-01-20", {"x": 1})
    assert serving.asof(conn, "2026-01-10").card("ABCD", "2026-01-31") is None
    assert serving.asof(conn, "2026-01-31").card("ABCD", "2026-01-31") == {"x": 1}


def test_scan_flag_gates_on_recorded_at_not_week_end(conn):
    # week_end is in-window but the flag was RECORDED after the cutoff -> denied (gate=recorded_at).
    with freeze_time("2026-03-01T00:00:00+00:00"):
        store.write_scan_flag(conn, "ABCD", "2026-01-10", {"flag": 1})
    book = serving.asof(conn, "2026-02-01T00:00:00+00:00")  # after week_end, before recorded_at
    assert book.scan_flags("ABCD", "2026-01-31") == []
    book2 = serving.asof(conn, "2026-03-15T00:00:00+00:00")
    assert book2.scan_flags("ABCD", "2026-01-31") == [{"flag": 1}]


def test_scan_flag_null_recorded_at_denied(conn):
    conn.execute("INSERT INTO scan_flag (ticker, week_end, payload, routed) VALUES (?,?,?,?)",
                 ("ABCD", "2026-01-10", "{}", 0))  # recorded_at defaults NULL
    conn.commit()
    with pytest.raises(LookAheadDenied):
        serving.asof(conn, "2026-12-31T00:00:00+00:00").scan_flags("ABCD", "2026-01-31")


def test_universe_gates_on_recorded_at(conn):
    with freeze_time("2026-03-01T00:00:00+00:00"):
        build.build_snapshot(conn, "2026-01-01", seed_rows=[{"ticker": "ABCD"}])
    # cohort recorded 2026-03-01; a cutoff before that sees no cohort even though as_of_date passes
    assert serving.asof(conn, "2026-02-01T00:00:00+00:00").universe("2026-06-01") == []
    served = serving.asof(conn, "2026-03-15T00:00:00+00:00").universe("2026-06-01")
    assert [u.ticker for u in served] == ["ABCD"]


def test_universe_null_recorded_at_denied(conn):
    conn.execute("INSERT INTO universe_snapshot (as_of_date, ticker, included, delisted) "
                 "VALUES (?,?,?,?)", ("2026-01-01", "ABCD", 1, 0))  # recorded_at NULL
    conn.commit()
    with pytest.raises(LookAheadDenied):
        serving.asof(conn, "2026-12-31T00:00:00+00:00").universe("2026-06-01")


# --- Task 2: catalyst_move + kb accessors + behaviour-preservation sweep ---------------------

def _seed_move(conn, knowable_asof="2026-02-15", window="(-1,2)"):
    with freeze_time("2026-08-01T00:00:00+00:00"):
        cid = store.insert_catalyst(conn, _catalyst())
    conn.execute(
        "INSERT INTO catalyst_move (catalyst_id, realized_move, move_window, knowable_asof, computed_at) "
        "VALUES (?,?,?,?,?)",
        (cid, 0.12, window, knowable_asof, "2026-02-15T00:00:00+00:00"),
    )
    conn.commit()
    return cid


def test_catalyst_move_gates_on_knowable_asof(conn):
    cid = _seed_move(conn, knowable_asof="2026-02-15")
    assert serving.asof(conn, "2026-02-01").catalyst_moves(cid) == []  # not yet knowable
    served = serving.asof(conn, "2026-03-01").catalyst_moves(cid)
    assert len(served) == 1 and served[0]["realized_move"] == 0.12


def test_catalyst_move_guards_null_stamp(conn):
    # catalyst_move.knowable_asof is NOT NULL by schema, so the deny is structural; the accessor
    # still routes every row through the shared _guard_not_null defensive guard.
    with pytest.raises(LookAheadDenied):
        serving._guard_not_null(None, "catalyst_move")


def test_kb_nodes_gate_on_created_at(conn):
    conn.execute("INSERT INTO kb_node (kind, created_at) VALUES ('playbook','2026-02-10')")
    conn.execute("INSERT INTO kb_node (kind, created_at) VALUES ('outcome','2026-05-10')")
    conn.commit()
    served = serving.asof(conn, "2026-03-01").kb_nodes()
    dates = [n["created_at"] for n in served]
    assert dates == ["2026-02-10"]  # the 2026-05-10 node is post-cutoff -> denied


def test_all_accessors_behaviour_preserved(conn):
    # At cutoff=now / no-lag the gateway is transparent: each accessor == the shipped raw read.
    with freeze_time("2026-01-05T00:00:00+00:00"):
        store.upsert_bars(conn, "ABCD", [
            {"week_end": "2026-01-03", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100}])
        store.write_card(conn, "ABCD", "2026-01-03", {"x": 1})
        store.write_scan_flag(conn, "ABCD", "2026-01-03", {"flag": 1})
        build.build_snapshot(conn, "2026-01-01", seed_rows=[{"ticker": "ABCD"}])
        store.insert_catalyst(conn, _catalyst())

    book = serving.asof(conn)  # cutoff=now, no lag
    assert book.bars("ABCD", "2026-06-01") == store.bars_asof(conn, "ABCD", "2026-06-01")
    assert book.card("ABCD", "2026-06-01") == store.card_asof(conn, "ABCD", "2026-06-01")
    assert book.scan_flags("ABCD", "2026-06-01") == store.scan_flags_asof(conn, "ABCD", "2026-06-01")
    assert [u.ticker for u in book.universe("2026-06-01")] == \
        [u.ticker for u in build.universe_as_of(conn, "2026-06-01")]
    assert [(c.ticker, c.event_date) for c in book.catalysts()] == \
        [(c.ticker, c.event_date) for c in store.tradeable_catalysts_light(conn)]
