"""A small bitemporal fixture timeline for the leak-property suite (DBOOK-07).

Seeds a known timeline through the SHIPPED writers (catalyst_move + the unstamped playbook table
are the only raw INSERTs — they have no writer) and returns the known knowable dates so the
adversarial tests can assert the temporal non-interference invariant (served == knowable-by-cutoff)
at every cutoff step. freezegun pins each write's transaction time (recorded_at).
"""

from __future__ import annotations

from dataclasses import dataclass

from freezegun import freeze_time

from catalyst_trader import store
from catalyst_trader.universe import build
from catalyst_trader.models import (
    Catalyst, CatalystSource, CatalystType, DatePrecision, DateType,
    SourceOrigin, SourceType, Status, Uncertainty,
)

TICKER = "ABCD"
W1, W2, W3 = "2026-01-05", "2026-01-12", "2026-01-19"   # price-bar week_ends (knowable=week_end)
RU = "2026-01-02T00:00:00+00:00"                         # universe cohort recorded_at
R2 = "2026-01-14T00:00:00+00:00"                         # scan_flag recorded_at
KM = "2026-01-13"                                        # catalyst_move knowable_asof
T1 = "2026-01-06T00:00:00+00:00"                         # catalyst v1 recorded_at (event_date D1)
T2 = "2026-01-16T00:00:00+00:00"                         # catalyst v2 recorded_at (amended -> D2)
D1, D2 = "2026-03-01", "2026-03-15"


@dataclass(frozen=True)
class LeakTimeline:
    ticker: str
    week_ends: tuple
    universe_recorded_at: str
    scan_recorded_at: str
    move_knowable_asof: str
    cat_v1_at: str
    cat_v2_at: str
    event_date_v1: str
    event_date_v2: str
    catalyst_id: int


def _source(**over):
    base = dict(
        source_name="ClinicalTrials.gov", source_url="https://clinicaltrials.gov/study/NCT1",
        source_type=SourceType.primary, reported_date=D1, date_type=DateType.estimated,
        retrieved_at="2026-01-06T00:00:00Z",
    )
    base.update(over)
    return CatalystSource(**base)


def _catalyst(event_date):
    return Catalyst(
        ticker=TICKER, company_name="Abcd", catalyst_type=CatalystType.pdufa,
        event_date=event_date, date_precision=DatePrecision.day,
        uncertainty_type=Uncertainty.window, status=Status.verified,
        source_origin=SourceOrigin.curated_pdufa, external_ref="NCT1", sources=[_source()],
    )


def seed_leak_timeline(conn) -> LeakTimeline:
    # price bars — knowable = week_end (no separate transaction time)
    store.upsert_bars(conn, TICKER, [
        {"week_end": W1, "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100},
        {"week_end": W2, "open": 10, "high": 12, "low": 10, "close": 12, "volume": 100},
        {"week_end": W3, "open": 12, "high": 14, "low": 11, "close": 14, "volume": 100},
    ])
    # company_card at W2 (knowable = week_end)
    store.write_card(conn, TICKER, W2, {"x": 1})
    # scan_flag recorded at R2 (knowable = recorded_at, distinct from its week_end)
    with freeze_time(R2):
        store.write_scan_flag(conn, TICKER, W2, {"flag": 1})
    # universe cohort recorded at RU
    with freeze_time(RU):
        build.build_snapshot(conn, "2026-01-01", seed_rows=[{"ticker": TICKER}])
    # catalyst: inserted at T1 (D1), amended at T2 (D2) -> two versions
    with freeze_time(T1):
        cid = store.insert_catalyst(conn, _catalyst(D1))
    with freeze_time(T2):
        store.insert_catalyst(conn, _catalyst(D2))
    # catalyst_move (no shipped writer) — knowable_asof = KM
    conn.execute(
        "INSERT INTO catalyst_move (catalyst_id, realized_move, move_window, knowable_asof, computed_at) "
        "VALUES (?,?,?,?,?)",
        (cid, 0.2, "(-1,2)", KM, "2026-01-13T00:00:00+00:00"),
    )
    # a deliberately-UNSTAMPED table (stands in for the 7.5 playbook) — must be deny-by-default
    conn.execute("CREATE TABLE playbook (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO playbook (name) VALUES ('scenario-1')")
    conn.commit()
    return LeakTimeline(
        ticker=TICKER, week_ends=(W1, W2, W3), universe_recorded_at=RU, scan_recorded_at=R2,
        move_knowable_asof=KM, cat_v1_at=T1, cat_v2_at=T2, event_date_v1=D1, event_date_v2=D2,
        catalyst_id=cid,
    )
