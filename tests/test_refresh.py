"""Idempotent daily refresh orchestrator — providers -> store -> verify -> freshness -> triggers.

Providers are injected (stub fns) for the deterministic idempotency/degrade cases and
exercised for real via pytest-httpx for the wiring case. freezegun pins ``now`` so the
verify/exclude/trigger time logic is deterministic.
"""

from datetime import datetime, timezone

import pytest
from freezegun import freeze_time

from catalyst_trader import store
from catalyst_trader.calendar import refresh, triggers
from catalyst_trader.config import settings
from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    CatalystType,
    DatePrecision,
    SourceOrigin,
    SourceType,
    Status,
    Uncertainty,
)


@pytest.fixture(autouse=True)
def _clear_callbacks():
    triggers._callbacks.clear()
    yield
    triggers._callbacks.clear()


def _ct_catalyst(event_date="2027-06-15", ext="NCT1"):
    return Catalyst(
        ticker="VRTX",
        catalyst_type=CatalystType.trial_readout,
        event_date=event_date,
        date_precision=DatePrecision.day,
        uncertainty_type=Uncertainty.soft,
        source_origin=SourceOrigin.clinicaltrials_gov,
        external_ref=ext,
        sources=[
            CatalystSource(
                source_name="ClinicalTrials.gov",
                source_url="https://clinicaltrials.gov/study/NCT1",
                source_type=SourceType.primary,
                reported_date=event_date,
                retrieved_at="2026-08-14T00:00:00Z",
            )
        ],
    )


def _fmp_catalyst(event_date="2027-02-04", ext="VRTX"):
    return Catalyst(
        ticker="VRTX",
        catalyst_type=CatalystType.earnings,
        event_date=event_date,
        date_precision=DatePrecision.day,
        uncertainty_type=Uncertainty.window,
        source_origin=SourceOrigin.fmp_earnings,
        external_ref=ext,
        sources=[
            CatalystSource(
                source_name="FMP",
                source_url="https://financialmodelingprep.com/stable/earnings-calendar",
                source_type=SourceType.secondary,
                reported_date=event_date,
                retrieved_at="2026-08-14T00:00:00Z",
            )
        ],
    )


def _count(db):
    return db.execute("SELECT count(*) AS n FROM catalyst").fetchone()["n"]


def _curated_csv(tmp_path):
    p = tmp_path / "pdufa.csv"
    p.write_text(
        "ticker,catalyst_type,event_date,source_name,source_url,source_type\n"
        "SRPT,pdufa,2027-03-30,FDA,https://www.fda.gov/x,primary\n"
    )
    return str(p)


# --- idempotency -------------------------------------------------------------


def test_refresh_is_idempotent(db, tmp_path):
    ct = lambda *a, **k: [_ct_catalyst()]
    fm = lambda *a, **k: [_fmp_catalyst()]
    csv = _curated_csv(tmp_path)
    with freeze_time("2026-08-14T12:00:00Z"):
        now = datetime.now(timezone.utc)
        refresh.refresh(db, ["VRTX", "SRPT"], now=now, ct_fetch=ct, fmp_fetch=fm,
                        pdufa_csv=csv, fmp_enabled=True)
        first = _count(db)
        refresh.refresh(db, ["VRTX", "SRPT"], now=now, ct_fetch=ct, fmp_fetch=fm,
                        pdufa_csv=csv, fmp_enabled=True)
        second = _count(db)
    assert first == 3  # 1 CT + 1 FMP + 1 curated
    assert second == first  # re-run produces no duplicate rows


# --- graceful degrade without the FMP key ------------------------------------


def test_refresh_degrades_without_fmp_key(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "fmp_api_key", None)
    ct = lambda *a, **k: [_ct_catalyst()]

    def fm(*a, **k):
        raise RuntimeError("FMP_API_KEY not set")

    csv = _curated_csv(tmp_path)
    with freeze_time("2026-08-14T12:00:00Z"):
        summary = refresh.refresh(
            db, ["VRTX", "SRPT"], now=datetime.now(timezone.utc),
            ct_fetch=ct, fmp_fetch=fm, pdufa_csv=csv,
        )
    # CT.gov + curated present, FMP skipped, no crash
    assert _count(db) == 2
    assert summary["fetched"] == 1  # only the CT.gov catalyst was fetched


def test_refresh_fmp_runtimeerror_is_swallowed(db, monkeypatch):
    monkeypatch.setattr(settings, "fmp_api_key", "SET")
    ct = lambda *a, **k: [_ct_catalyst()]

    def fm(*a, **k):
        raise RuntimeError("FMP down")

    with freeze_time("2026-08-14T12:00:00Z"):
        summary = refresh.refresh(
            db, ["VRTX"], now=datetime.now(timezone.utc), ct_fetch=ct, fmp_fetch=fm
        )
    assert _count(db) == 1  # degraded to CT.gov only, did not crash
    assert summary["fetched"] == 1


# --- verify + exclude + trigger are wired ------------------------------------


def test_refresh_fires_t2_trigger(db):
    # A pre-seeded 2-source verified catalyst 2 days out re-verifies (stays fresh)
    # and fires the seam.
    c = Catalyst(
        ticker="VRTX",
        catalyst_type=CatalystType.pdufa,
        event_date="2026-11-30",
        date_precision=DatePrecision.day,
        uncertainty_type=Uncertainty.firm,
        source_origin=SourceOrigin.curated_pdufa,
        external_ref="seed1",
        sources=[
            CatalystSource(source_name="FDA", source_url="https://fda.gov/a",
                           source_type=SourceType.primary, reported_date="2026-11-30",
                           retrieved_at="2026-08-14T00:00:00Z"),
            CatalystSource(source_name="Company IR", source_url="https://ir.example.com/b",
                           source_type=SourceType.secondary, reported_date="2026-11-30",
                           retrieved_at="2026-08-14T00:00:00Z"),
        ],
    )
    cid = store.insert_catalyst(db, c)
    seen = []
    triggers.register_callback(lambda row: seen.append(row["id"]))
    with freeze_time("2026-11-28T12:00:00Z"):
        summary = refresh.refresh(
            db, ["VRTX"], now=datetime.now(timezone.utc),
            ct_fetch=lambda *a, **k: [], fmp_fetch=lambda *a, **k: [], fmp_enabled=False,
        )
    assert seen == [cid]
    assert summary["fired"] == 1
    assert store.get_catalyst(db, cid).status is Status.verified


def test_refresh_excludes_stale_near_event(db):
    # Near-event catalyst that can no longer re-verify (single source) is excluded.
    c = Catalyst(
        ticker="VRTX",
        catalyst_type=CatalystType.pdufa,
        event_date="2026-11-29",
        date_precision=DatePrecision.day,
        uncertainty_type=Uncertainty.soft,
        source_origin=SourceOrigin.curated_pdufa,
        external_ref="seed2",
        sources=[
            CatalystSource(source_name="FDA", source_url="https://fda.gov/a",
                           source_type=SourceType.primary, reported_date="2026-11-29",
                           retrieved_at="2026-08-14T00:00:00Z"),
        ],
    )
    cid = store.insert_catalyst(db, c)
    db.execute(
        "UPDATE catalyst SET status='verified', last_verified_at='2026-11-01T00:00:00Z' WHERE id=?",
        (cid,),
    )
    db.commit()
    with freeze_time("2026-11-28T12:00:00Z"):
        summary = refresh.refresh(
            db, ["VRTX"], now=datetime.now(timezone.utc),
            ct_fetch=lambda *a, **k: [], fmp_fetch=lambda *a, **k: [], fmp_enabled=False,
        )
    assert store.get_catalyst(db, cid).status is Status.excluded
    assert summary["excluded"] == 1


# --- real providers wire in (pytest-httpx) -----------------------------------


def test_refresh_full_pipeline_httpx(db, httpx_mock, load_fixture, monkeypatch):
    monkeypatch.setattr(settings, "fmp_api_key", "TESTKEY")
    monkeypatch.setattr(settings, "ctgov_request_spacing_s", 0)
    # FIFO: CT.gov /studies, then FMP calendar, then FMP confirmed.
    httpx_mock.add_response(
        json={"studies": [load_fixture("ctgov_full_date")], "totalCount": 1}
    )
    httpx_mock.add_response(json=load_fixture("fmp_earnings_calendar"))
    httpx_mock.add_response(json=load_fixture("fmp_earnings_confirmed"))
    with freeze_time("2024-06-10T12:00:00Z"):
        summary = refresh.refresh(db, ["VRTX"], now=datetime.now(timezone.utc))
    # CT.gov VRTX trial + FMP VRTX earnings persisted through the real providers
    tickers = {r["ticker"] for r in db.execute("SELECT ticker FROM catalyst").fetchall()}
    assert "VRTX" in tickers
    assert summary["fetched"] >= 2


def test_main_entrypoint_exists():
    assert callable(refresh.main)
