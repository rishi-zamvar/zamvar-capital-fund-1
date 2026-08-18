"""Adversarial temporal non-interference suite (DBOOK-07).

The gateway (Plans 02-03) is only trustworthy if an ADVERSARY cannot pull post-cutoff data through
it. This suite IS that adversary: it sweeps cutoffs across a known bitemporal timeline and asserts,
at every step, that the served set equals EXACTLY the facts knowable by that cutoff (property-shaped,
not one hand-picked case). Grounded in the availability-gate / non-interference framing (arXiv
2608.09988 / 2607.04958). Every assertion reads through serving.asof — never a raw store read.
"""

import pytest

from catalyst_trader import db as _db
from catalyst_trader import serving
from catalyst_trader.serving import LookAheadDenied
from tests import leak_fixtures as L

# Cutoffs swept across the timeline: before everything, between each transaction time, after all.
CUTOFFS = ["2026-01-01", "2026-01-07", "2026-01-13", "2026-01-15", "2026-01-20", "2026-12-31"]
AS_OF = "2026-06-01"  # far-future valid-time bound so knowable-time is the binding constraint


@pytest.fixture
def conn():
    c = _db.connect(":memory:")
    _db.migrate(c)
    yield c
    c.close()


@pytest.fixture
def tl(conn):
    return conn, L.seed_leak_timeline(conn)


# --- Task 1: core non-interference sweep ----------------------------------------------------

@pytest.mark.parametrize("cutoff", CUTOFFS)
def test_no_post_cutoff_fact_served(tl, cutoff):
    conn, t = tl
    book = serving.asof(conn, cutoff)

    # bars: knowable = week_end. served == the week_ends <= cutoff (identical string compare).
    got = {b["week_end"] for b in book.bars(t.ticker, AS_OF)}
    assert got == {w for w in t.week_ends if w <= cutoff}

    # card at W2: present iff W2 <= cutoff
    assert (book.card(t.ticker, AS_OF) is not None) == (t.week_ends[1] <= cutoff)

    # scan_flag: knowable = recorded_at (R2), NOT its week_end
    assert (len(book.scan_flags(t.ticker, AS_OF)) == 1) == (t.scan_recorded_at <= cutoff)

    # universe cohort: knowable = recorded_at (RU)
    assert (len(book.universe(AS_OF)) == 1) == (t.universe_recorded_at <= cutoff)

    # catalyst_move: knowable = knowable_asof (KM)
    assert (len(book.catalyst_moves(t.catalyst_id)) == 1) == (t.move_knowable_asof <= cutoff)

    # catalyst: never gates on event_date; the version's recorded_at is the gate
    cats = book.catalysts()
    assert (len(cats) == 1) == (t.cat_v1_at <= cutoff)


def test_unstamped_table_denied(tl):
    conn, _ = tl
    # the playbook table exists (raw) but is NOT in STAMP_REGISTRY -> deny-by-default
    with pytest.raises(LookAheadDenied):
        serving.asof(conn, "2026-12-31")._require("playbook")


def test_live_cutoff_now_sees_all(tl):
    conn, t = tl
    book = serving.asof(conn)  # cutoff = now -> the full current view
    assert {b["week_end"] for b in book.bars(t.ticker, AS_OF)} == set(t.week_ends)
    assert book.card(t.ticker, AS_OF) is not None
    assert len(book.scan_flags(t.ticker, AS_OF)) == 1
    assert len(book.universe(AS_OF)) == 1
    assert len(book.catalyst_moves(t.catalyst_id)) == 1
    assert len(book.catalysts()) == 1


# --- Task 2: as-of-then revision replay + no-whole-table-stat-leak ---------------------------

def test_amended_catalyst_returns_asof_then_version(tl):
    conn, t = tl
    # before T1: neither version knowable
    assert serving.asof(conn, "2026-01-01").catalysts() == []
    # between T1 and T2: the OLD version (D1)
    mid = serving.asof(conn, "2026-01-10").catalysts()
    assert [c.event_date for c in mid] == [t.event_date_v1]
    # after T2: the NEW version (D2)
    after = serving.asof(conn, "2026-12-31").catalysts()
    assert [c.event_date for c in after] == [t.event_date_v2]


def test_derived_stat_uses_only_pre_cutoff_rows(tl):
    conn, t = tl
    # naive leaking stat: mean close over the WHOLE raw table (sees post-cutoff bars)
    naive = conn.execute("SELECT AVG(close) FROM price_bar WHERE ticker=?", (t.ticker,)).fetchone()[0]
    # correct: mean over ONLY the rows the gateway serves at a mid cutoff
    mid_cutoff = "2026-01-13"  # W1,W2 knowable; W3 (2026-01-19) is not
    served = serving.asof(conn, mid_cutoff).bars(t.ticker, AS_OF)
    pre_only = sum(b["close"] for b in served) / len(served)
    expected_pre = (10 + 12) / 2  # W1,W2 closes; W3 close (14) excluded
    assert pre_only == expected_pre
    assert pre_only != naive  # the guard blocks the future row from the aggregate
    # at cutoff=now the two converge (all rows knowable)
    live = serving.asof(conn).bars(t.ticker, AS_OF)
    assert sum(b["close"] for b in live) / len(live) == naive


def test_lag_closes_borderline_leak(tl):
    conn, t = tl
    # W3 is knowable at its week_end 2026-01-19; a 3-day price lag pushes the effective cutoff back
    # so a cutoff ON 2026-01-19 no longer serves it (lag is part of the non-interference guarantee).
    no_lag = serving.asof(conn, "2026-01-19").bars(t.ticker, AS_OF)
    assert t.week_ends[2] in {b["week_end"] for b in no_lag}
    lagged = serving.asof(conn, "2026-01-19", latency_cfg={"price": 3}).bars(t.ticker, AS_OF)
    assert t.week_ends[2] not in {b["week_end"] for b in lagged}
