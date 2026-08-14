"""Point-in-time universe builder (DATA-06).

Survivorship-free by construction: append-only as_of_date cohorts, delisted names
retained, inclusion driven by explicit criteria (catalyst density, market cap,
liquidity), and an as-of query that never returns a future cohort.
"""

import json

from catalyst_trader import store
from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    CatalystType,
    DatePrecision,
    SourceOrigin,
    SourceType,
    Uncertainty,
)
from catalyst_trader.universe.build import build_snapshot, universe_as_of


def _seed_catalyst(db, ticker, event_date):
    """Insert one upcoming catalyst for `ticker` so density can be counted from the DB."""
    c = Catalyst(
        ticker=ticker,
        catalyst_type=CatalystType.trial_readout,
        event_date=event_date,
        date_precision=DatePrecision.day,
        uncertainty_type=Uncertainty.window,
        source_origin=SourceOrigin.clinicaltrials_gov,
        external_ref=f"NCT-{ticker}-{event_date}",
        sources=[
            CatalystSource(
                source_name="ClinicalTrials.gov",
                source_url="https://clinicaltrials.gov/study/x",
                source_type=SourceType.primary,
                reported_date=event_date,
                retrieved_at="2026-08-14T00:00:00Z",
            )
        ],
    )
    return store.insert_catalyst(db, c)


# ~healthy seed rows above every threshold
def _rows():
    return [
        dict(ticker="VRTX", company_name="Vertex", market_cap="120000000000",
             adv_usd="500000000", therapeutic_area="Cystic Fibrosis", delisted="0"),
        dict(ticker="REGN", company_name="Regeneron", market_cap="70000000000",
             adv_usd="400000000", therapeutic_area="Immunology", delisted="0"),
    ]


def test_build_snapshot_scores_and_includes(db):
    _seed_catalyst(db, "VRTX", "2026-10-01")
    _seed_catalyst(db, "REGN", "2026-11-15")

    n = build_snapshot(db, "2026-08-14", _rows())
    assert n == 2

    rows = db.execute(
        "SELECT * FROM universe_snapshot WHERE as_of_date='2026-08-14' ORDER BY ticker"
    ).fetchall()
    assert {r["ticker"] for r in rows} == {"VRTX", "REGN"}
    for r in rows:
        c = json.loads(r["criteria_json"])
        assert set(c) == {"catalyst_density", "market_cap", "adv_usd", "therapeutic_area"}
        assert c["catalyst_density"] == 1
        assert r["included"] == 1


def test_catalyst_density_counts_only_upcoming_in_window(db):
    _seed_catalyst(db, "VRTX", "2026-10-01")  # in 6mo window
    _seed_catalyst(db, "VRTX", "2026-12-20")  # in 6mo window
    _seed_catalyst(db, "VRTX", "2027-06-01")  # outside 6mo window
    _seed_catalyst(db, "VRTX", "2026-01-01")  # in the past

    build_snapshot(db, "2026-08-14", [_rows()[0]])
    row = db.execute("SELECT criteria_json FROM universe_snapshot WHERE ticker='VRTX'").fetchone()
    assert json.loads(row["criteria_json"])["catalyst_density"] == 2


def test_below_liquidity_floor_excluded_with_reason(db):
    _seed_catalyst(db, "TINY", "2026-10-01")
    rows = [dict(ticker="TINY", company_name="Tiny", market_cap="120000000000",
                 adv_usd="1000", therapeutic_area="Oncology", delisted="0")]

    n = build_snapshot(db, "2026-08-14", rows)
    assert n == 0
    r = db.execute("SELECT * FROM universe_snapshot WHERE ticker='TINY'").fetchone()
    assert r is not None  # written, not silently dropped
    assert r["included"] == 0
    assert "adv_usd" in r["reason"]


def test_zero_density_excluded_with_reason(db):
    # no catalysts seeded for this ticker
    rows = [dict(ticker="NOCAT", company_name="NoCat", market_cap="120000000000",
                 adv_usd="500000000", therapeutic_area="Oncology", delisted="0")]
    n = build_snapshot(db, "2026-08-14", rows)
    assert n == 0
    r = db.execute("SELECT * FROM universe_snapshot WHERE ticker='NOCAT'").fetchone()
    assert r["included"] == 0
    assert "catalyst" in r["reason"].lower()


def test_delisted_retained_in_snapshot(db):
    rows = [dict(ticker="DEAD", company_name="Delisted Co", market_cap="120000000000",
                 adv_usd="500000000", therapeutic_area="Oncology", delisted="1")]
    build_snapshot(db, "2026-08-14", rows)
    r = db.execute("SELECT * FROM universe_snapshot WHERE ticker='DEAD'").fetchone()
    assert r is not None  # retained (not filtered out) — survivorship-free
    assert r["delisted"] == 1


def test_append_only_two_cohorts_earlier_unchanged(db):
    _seed_catalyst(db, "VRTX", "2026-10-01")
    _seed_catalyst(db, "REGN", "2026-11-15")

    build_snapshot(db, "2026-06-01", _rows())
    first = db.execute(
        "SELECT COUNT(*) AS n FROM universe_snapshot WHERE as_of_date='2026-06-01'"
    ).fetchone()["n"]

    build_snapshot(db, "2026-08-14", _rows())

    # both cohorts exist; the earlier one is untouched
    assert db.execute(
        "SELECT COUNT(*) AS n FROM universe_snapshot WHERE as_of_date='2026-06-01'"
    ).fetchone()["n"] == first
    assert db.execute(
        "SELECT COUNT(DISTINCT as_of_date) AS n FROM universe_snapshot"
    ).fetchone()["n"] == 2


def test_universe_as_of_returns_latest_not_future(db):
    _seed_catalyst(db, "VRTX", "2026-10-01")
    _seed_catalyst(db, "REGN", "2026-11-15")
    build_snapshot(db, "2026-06-01", _rows())
    build_snapshot(db, "2026-09-01", _rows())

    mid = universe_as_of(db, "2026-07-15")
    assert {s.as_of_date for s in mid} == {"2026-06-01"}  # not the future 2026-09-01 cohort

    late = universe_as_of(db, "2026-09-15")
    assert {s.as_of_date for s in late} == {"2026-09-01"}

    assert universe_as_of(db, "2025-01-01") == []  # nothing before the first cohort


def test_build_snapshot_loads_seed_csv_when_rows_omitted(db):
    # the shipped template must be loadable end-to-end (density-gated, so may include 0)
    n = build_snapshot(db, "2026-08-14")
    assert isinstance(n, int)
    written = db.execute(
        "SELECT COUNT(*) AS n FROM universe_snapshot WHERE as_of_date='2026-08-14'"
    ).fetchone()["n"]
    assert written >= 1  # template ships at least the VRTX/REGN example rows
