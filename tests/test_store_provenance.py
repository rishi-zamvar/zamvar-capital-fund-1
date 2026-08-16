"""Migration 007 + upsert_bars provenance kwargs (source_grade / agreeing_sources).

Offline-only: exercises the migrated in-memory `db` fixture. Proves the two new
columns exist, persist behind two OPTIONAL backward-compatible kwargs, and that the
(ticker, week_end) natural key + idempotency are untouched.
"""

from catalyst_trader import store


def _bar(week_end="2026-01-02", close=10.0):
    return {"week_end": week_end, "open": 9.0, "high": 11.0, "low": 8.5,
            "close": close, "volume": 1000.0}


def test_migration_007_adds_columns(db):
    cols = {r["name"] for r in db.execute("PRAGMA table_info(price_bar)").fetchall()}
    assert "source_grade" in cols
    assert "agreeing_sources" in cols


def test_upsert_persists_grade_and_agreeing(db):
    store.upsert_bars(db, "ACME", [_bar()], source="yfinance",
                      source_grade="green", agreeing_sources="yfinance,nasdaq")
    row = db.execute(
        "SELECT source_grade, agreeing_sources FROM price_bar WHERE ticker=?", ("ACME",)
    ).fetchone()
    assert row["source_grade"] == "green"
    assert row["agreeing_sources"] == "yfinance,nasdaq"


def test_upsert_backward_compatible_default_none(db):
    # old-style call with NO grade kwargs — must still work, columns NULL
    n = store.upsert_bars(db, "ACME", [_bar()], source="fixture")
    assert n == 1
    row = db.execute(
        "SELECT source_grade, agreeing_sources FROM price_bar WHERE ticker=?", ("ACME",)
    ).fetchone()
    assert row["source_grade"] is None
    assert row["agreeing_sources"] is None


def test_upsert_idempotent_with_grade(db):
    store.upsert_bars(db, "ACME", [_bar(close=10.0)], source="yfinance",
                      source_grade="green", agreeing_sources="yfinance")
    store.upsert_bars(db, "ACME", [_bar(close=12.0)], source="yfinance",
                      source_grade="yellow", agreeing_sources="yfinance,tiingo")
    rows = db.execute("SELECT close, source_grade, agreeing_sources FROM price_bar "
                      "WHERE ticker=?", ("ACME",)).fetchall()
    assert len(rows) == 1  # updated in place, no duplicate
    assert rows[0]["close"] == 12.0
    assert rows[0]["source_grade"] == "yellow"
    assert rows[0]["agreeing_sources"] == "yfinance,tiingo"
