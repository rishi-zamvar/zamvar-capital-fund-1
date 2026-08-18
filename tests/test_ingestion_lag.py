"""Per-data-class ingestion lag through the gateway (DBOOK-06).

The idealized public date overstates what we'd actually have had, so each lagged data class routes
its cutoff through the REUSED fill.effective_asof (no new lag mechanism). A borderline fact is
denied under a configured lag and served without it; an unconfigured class RAISES (no silent 0-lag);
latency_cfg=None is the honest raw-cutoff opt-out (production paths pass a real cfg).
"""

import pytest

from catalyst_trader import db as _db
from catalyst_trader import store


@pytest.fixture
def conn():
    c = _db.connect(":memory:")
    _db.migrate(c)
    yield c
    c.close()


def _seed_bar(conn, week_end="2026-01-17"):
    store.upsert_bars(conn, "ABCD", [
        {"week_end": week_end, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100},
    ])


def test_lag_denies_borderline_fact(conn):
    from catalyst_trader import serving
    _seed_bar(conn, "2026-01-17")
    # cutoff exactly on the bar's week_end: a 2-day price lag pushes the effective cutoff before it.
    denied = serving.asof(conn, "2026-01-17", latency_cfg={"price": 2}).bars("ABCD", "2026-01-31")
    assert denied == []
    served = serving.asof(conn, "2026-01-17", latency_cfg=None).bars("ABCD", "2026-01-31")
    assert [b["week_end"] for b in served] == ["2026-01-17"]


def test_unconfigured_lag_class_raises(conn):
    from catalyst_trader import serving
    _seed_bar(conn)
    with pytest.raises(KeyError):  # effective_asof raises on a class not in the cfg
        serving.asof(conn, "2026-01-17", latency_cfg={"other": 1}).bars("ABCD", "2026-01-31")


def test_no_lag_default_is_raw_cutoff(conn):
    from catalyst_trader import serving
    _seed_bar(conn, "2026-01-17")
    # latency_cfg=None => raw cutoff for every class (no lag applied)
    served = serving.asof(conn, "2026-01-17").bars("ABCD", "2026-01-31")
    assert [b["week_end"] for b in served] == ["2026-01-17"]
