"""Smoke tests for the shared conftest fixtures + the captured Wave-0 data fixtures."""

from datetime import datetime, timezone


def test_db_fixture_is_migrated(db):
    tables = {
        r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"catalyst", "catalyst_source", "universe_snapshot", "schema_version"} <= tables


def test_ctgov_partial_fixture_has_month_only_date(load_fixture):
    d = load_fixture("ctgov_partial_date")
    struct = d["protocolSection"]["statusModule"]["primaryCompletionDateStruct"]
    assert len(struct["date"]) == 7  # YYYY-MM, not coerced to a day
    assert struct["type"] == "ESTIMATED"


def test_ctgov_full_fixture_has_full_date(load_fixture):
    struct = load_fixture("ctgov_full_date")["protocolSection"]["statusModule"][
        "primaryCompletionDateStruct"
    ]
    assert len(struct["date"]) == 10  # YYYY-MM-DD


def test_ctgov_collaborator_fixture_lead_is_not_the_company(load_fixture):
    lead = load_fixture("ctgov_collaborator")["protocolSection"][
        "sponsorCollaboratorsModule"
    ]["leadSponsor"]["name"]
    assert "vertex" not in lead.lower()  # the sponsor-fuzziness gotcha


def test_fmp_calendar_fixture_shape(load_fixture):
    rows = load_fixture("fmp_earnings_calendar")
    assert rows and {"date", "symbol", "epsEstimated"} <= set(rows[0])


def test_frozen_now_pins_the_clock(frozen_now):
    with frozen_now("2026-11-28T12:00:00Z"):
        assert datetime.now(timezone.utc).date().isoformat() == "2026-11-28"
