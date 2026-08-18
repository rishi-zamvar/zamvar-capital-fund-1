"""Serving gateway mechanism (DBOOK-03/04): deny-by-default + cutoff injection + ingestion lag.

serving.asof(conn, cutoff) is the single access seam; every accessor injects a knowable<=cutoff
transaction-time filter on top of the shipped valid-time reads. An unregistered table or a NULL
knowable stamp RAISES LookAheadDenied (never a silent []). price_bar is the one wired accessor here
(Plan 02); Plan 03 populates the rest.
"""

import pytest

from catalyst_trader import db as _db
from catalyst_trader import store
from catalyst_trader import serving
from catalyst_trader.serving import LookAheadDenied, StampSpec


@pytest.fixture
def conn():
    c = _db.connect(":memory:")
    _db.migrate(c)
    yield c
    c.close()


def _seed_bars(conn, ticker="ABCD"):
    store.upsert_bars(conn, ticker, [
        {"week_end": "2026-01-03", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100},
        {"week_end": "2026-01-10", "open": 10, "high": 12, "low": 10, "close": 11, "volume": 100},
        {"week_end": "2026-01-17", "open": 11, "high": 13, "low": 10, "close": 12, "volume": 100},
    ])


# --- Task 1: deny-by-default + factory + effective cutoff -------------------------------------

def test_unregistered_table_denied(conn):
    book = serving.asof(conn, "2026-01-31")
    with pytest.raises(LookAheadDenied):
        book._require("playbook")


def test_asof_defaults_to_now(conn):
    book = serving.asof(conn)
    assert book.cutoff.startswith("20")  # a real ISO timestamp (live cutoff=now)
    assert "T" in book.cutoff


def test_effective_cutoff_no_lag_is_identity(conn):
    book = serving.asof(conn, "2026-01-31")
    spec = StampSpec(valid_col="week_end", knowable_expr="week_end", data_class=None)
    assert book._effective_cutoff(spec) == "2026-01-31"


def test_effective_cutoff_uses_effective_asof(conn):
    book = serving.asof(conn, "2026-01-31", latency_cfg={"price": 2})
    spec = StampSpec(valid_col="week_end", knowable_expr="week_end", data_class="price")
    assert book._effective_cutoff(spec) == "2026-01-29"  # shifted back 2 days


def test_effective_cutoff_unconfigured_class_raises(conn):
    book = serving.asof(conn, "2026-01-31", latency_cfg={"other": 1})
    spec = StampSpec(valid_col="week_end", knowable_expr="week_end", data_class="price")
    with pytest.raises(KeyError):  # effective_asof raises — no silent 0-lag
        book._effective_cutoff(spec)


# --- Task 2: price_bar accessor end-to-end ---------------------------------------------------

def test_bars_behaviour_preserved(conn):
    _seed_bars(conn)
    book = serving.asof(conn, "2026-01-31")  # cutoff >= as_of, no lag
    assert book.bars("ABCD", "2026-01-17") == store.bars_asof(conn, "ABCD", "2026-01-17")


def test_bars_denies_post_cutoff(conn):
    _seed_bars(conn)
    # cutoff before the last bar's week_end -> that bar is denied even though valid-time passes
    book = serving.asof(conn, "2026-01-12")
    weeks = [b["week_end"] for b in book.bars("ABCD", "2026-01-31")]
    assert weeks == ["2026-01-03", "2026-01-10"]
    # cutoff at/after the bar -> present
    book2 = serving.asof(conn, "2026-01-17")
    weeks2 = [b["week_end"] for b in book2.bars("ABCD", "2026-01-31")]
    assert "2026-01-17" in weeks2


def test_bars_lag_shifts_cutoff(conn):
    _seed_bars(conn)
    # cutoff exactly on the last bar, but a 2-day lag pushes the effective cutoff before it
    book = serving.asof(conn, "2026-01-17", latency_cfg={"price": 2})
    weeks = [b["week_end"] for b in book.bars("ABCD", "2026-01-31")]
    assert "2026-01-17" not in weeks
    assert weeks == ["2026-01-03", "2026-01-10"]


def test_null_stamp_denied(conn):
    with pytest.raises(LookAheadDenied):
        serving._guard_not_null(None, "some_table")
    # a non-null value passes through unchanged
    assert serving._guard_not_null("2026-01-10", "some_table") == "2026-01-10"


def test_serving_imports_cleanly():
    from catalyst_trader.serving import asof, LookAheadDenied  # noqa: F401


# --- resolved-status catalysts surface in the backward/backtest walk (knowability via recorded_at) ---

def _seed_resolved_catalyst(conn, cid=1, ticker="ZZZZ", event_date="2026-06-01", recorded_at="2026-01-15"):
    conn.execute(
        "INSERT INTO catalyst (id,ticker,catalyst_type,event_date,date_precision,uncertainty_type,"
        "status,source_origin,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (cid, ticker, "pdufa", event_date, "day", "firm", "resolved", "curated_pdufa",
         recorded_at, recorded_at),
    )
    conn.execute(
        "INSERT INTO catalyst_version (catalyst_id,event_date,recorded_at) VALUES (?,?,?)",
        (cid, event_date, recorded_at),
    )
    conn.commit()


def test_catalysts_surface_resolved_status_when_knowable(conn):
    # A historical catalyst is stored status='resolved' (it has occurred). At a cutoff on/after its
    # version recorded_at it WAS a real known-upcoming event -> the gateway MUST surface it, so the
    # backward/backtest walk is not silently vacuous.
    _seed_resolved_catalyst(conn, recorded_at="2026-01-15")
    got = serving.asof(conn, "2026-02-01").catalysts()
    assert any(c.ticker == "ZZZZ" for c in got)


def test_catalysts_resolved_denied_before_recorded_at(conn):
    # No look-ahead: the same resolved catalyst is NOT knowable before its version recorded_at.
    _seed_resolved_catalyst(conn, recorded_at="2026-01-15")
    got = serving.asof(conn, "2026-01-01").catalysts()
    assert not any(c.ticker == "ZZZZ" for c in got)
