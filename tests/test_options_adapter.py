"""Options-IV adapter (FF-05): the ABSTAINING seam over quant.options.implied_move + the
options_snapshot cache read/write helpers.

Money-critical invariants under test:
  - a complete straddle dict -> a ToolResult carrying the model-free straddle move;
  - an iv+days_to_event dict -> a ToolResult via the IV method;
  - the provider ABSTAINS (returns None) on no data and on an incomplete/degraded snapshot —
    it NEVER fabricates a move and NEVER raises into the desk;
  - the options_snapshot table is provisioned by db.migrate() (migration 012, no inline DDL) and
    the write/read cache helpers round-trip in :memory().

Everything offline: providers are plain fakes, the cache uses the migrated in-memory db fixture.
"""

import pytest

from catalyst_trader.desk.options_adapter import (
    implied_move_from_provider,
    options_snapshot_provider,
    write_options_snapshot,
)


# --- implied_move_from_provider: straddle / iv / abstain --------------------


def test_straddle_provider_returns_toolresult():
    provider = lambda t, d: {"underlying_price": 100.0, "call_mid": 6.0, "put_mid": 4.0}
    res = implied_move_from_provider("ACME", "2026-11-15", provider)
    assert res is not None
    assert res.value == pytest.approx(0.10)          # (6+4)/100, model-free straddle
    assert res.detail["method"] == "straddle"


def test_iv_provider_returns_toolresult():
    provider = lambda t, d: {"underlying_price": 100.0, "iv": 0.80, "days_to_event": 365}
    res = implied_move_from_provider("ACME", "2026-11-15", provider)
    assert res is not None
    assert res.value == pytest.approx(0.80)          # iv * sqrt(365/365)
    assert res.detail["method"] == "iv"


def test_none_provider_abstains():
    assert implied_move_from_provider("ACME", "2026-11-15", lambda t, d: None) is None
    assert implied_move_from_provider("ACME", "2026-11-15", lambda t, d: {}) is None


def test_incomplete_dict_abstains_without_raising():
    # underlying only — no complete method -> ValueError inside implied_move -> ABSTAIN (None).
    assert implied_move_from_provider("ACME", "2026-11-15",
                                      lambda t, d: {"underlying_price": 100.0}) is None
    # missing underlying_price key entirely -> KeyError inside the adapter -> ABSTAIN.
    assert implied_move_from_provider("ACME", "2026-11-15",
                                      lambda t, d: {"call_mid": 6.0, "put_mid": 4.0}) is None
    # a degraded underlying (<= 0) -> ValueError -> ABSTAIN, never crash the desk.
    assert implied_move_from_provider("ACME", "2026-11-15",
                                      lambda t, d: {"underlying_price": 0.0, "call_mid": 6.0, "put_mid": 4.0}) is None


# --- options_snapshot cache round-trip (migration 012 via db.migrate) -------


def test_migration_012_creates_options_snapshot(db):
    """The db fixture is db.connect(':memory:') + db.migrate() — the table exists with no inline DDL."""
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='options_snapshot'"
    ).fetchone()
    assert row is not None


def test_cache_round_trip_straddle(db):
    write_options_snapshot(db, "ACME", "2026-11-15", underlying_price=100.0,
                           call_mid=6.0, put_mid=4.0, source="rh_expired")
    provider = options_snapshot_provider(db)
    got = provider("ACME", "2026-11-15")
    assert got == {"underlying_price": 100.0, "call_mid": 6.0, "put_mid": 4.0}
    # and the cached snapshot feeds the adapter end-to-end
    res = implied_move_from_provider("ACME", "2026-11-15", provider)
    assert res.value == pytest.approx(0.10)


def test_cache_round_trip_iv_drops_none_entries(db):
    write_options_snapshot(db, "ACME", "2026-11-15", underlying_price=100.0,
                           iv=0.8, days_to_event=30, source="rh_expired")
    got = options_snapshot_provider(db)("ACME", "2026-11-15")
    assert got == {"underlying_price": 100.0, "iv": 0.8, "days_to_event": 30}
    assert "call_mid" not in got  # None columns are dropped, not returned as None


def test_cache_miss_returns_none(db):
    assert options_snapshot_provider(db)("NOPE", "2026-11-15") is None


def test_cache_upsert_is_idempotent(db):
    write_options_snapshot(db, "ACME", "2026-11-15", underlying_price=100.0,
                           call_mid=6.0, put_mid=4.0, source="rh_expired")
    write_options_snapshot(db, "ACME", "2026-11-15", underlying_price=110.0,
                           call_mid=7.0, put_mid=5.0, source="rh_live")
    got = options_snapshot_provider(db)("ACME", "2026-11-15")
    assert got == {"underlying_price": 110.0, "call_mid": 7.0, "put_mid": 5.0}  # REPLACE on the PK
