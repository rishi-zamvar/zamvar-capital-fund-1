"""Plan 06.9-07 Task 2 — the historical ingestion loop (INGEST-04).

Offline: stub providers + the conftest in-memory `db` + a tiny seed CSV in tmp_path. Proves the
loop funnels provider output through the EXISTING idempotent write-paths — insert_catalyst THEN
verify_catalyst with a POINT-IN-TIME last_verified_at stamped from the FR primary source's
in-memory published_date (anti-look-ahead, BACK-01) — is idempotent (double-run = identical row
counts), survivorship-aware (delisted retained), and degrades per-datum without crashing.
"""

from catalyst_trader import ingest, store
from catalyst_trader.backtest.events import build_event_set
from catalyst_trader.models import (
    Catalyst,
    CatalystSource,
    CatalystType,
    DatePrecision,
    DateType,
    SourceOrigin,
    SourceType,
    Status,
    Uncertainty,
)


def _seed(tmp_path, rows):
    """Write a tiny seed_universe.csv (with a # comment line to skip) and return its path."""
    path = tmp_path / "seed.csv"
    lines = ["ticker,company_name,market_cap,adv_usd,therapeutic_area,delisted",
             "# comment line to skip"]
    lines += [f"{tk},{name},1,1,x,{'true' if dl else 'false'}" for tk, name, dl in rows]
    path.write_text("\n".join(lines))
    return str(path)


def _bars(ticker):
    return [
        {"week_end": "2026-01-02", "open": 9.0, "high": 11.0, "low": 8.5, "close": 10.0,
         "volume": 1_000, "source": "alpha_vantage", "source_grade": "green",
         "agreeing_sources": {"alpha_vantage", "yfinance"}},
        {"week_end": "2026-01-09", "open": 10.0, "high": 12.0, "low": 9.5, "close": 11.0,
         "volume": 1_100, "source": "alpha_vantage", "source_grade": "green",
         "agreeing_sources": {"alpha_vantage", "yfinance"}},
    ]


def _catalyst(ticker, event_date, *, two_source, fr_published):
    """A PDUFA catalyst mirroring pdufa.fetch output: FR primary (carries published_date) + optional
    RTTNews secondary. Two agreeing + a primary -> verify_catalyst returns verified."""
    sources = [CatalystSource(
        source_name="Federal Register", source_url="https://fr", source_type=SourceType.primary,
        reported_date=event_date, date_type=DateType.estimated, published_date=fr_published,
        retrieved_at="2026-01-01T00:00:00Z",
    )]
    if two_source:
        sources.append(CatalystSource(
            source_name="RTTNews", source_url="https://rtt", source_type=SourceType.secondary,
            reported_date=event_date, date_type=DateType.estimated,
            retrieved_at="2026-01-01T00:00:00Z",
        ))
    return Catalyst(
        ticker=ticker, catalyst_type=CatalystType.pdufa, event_date=event_date,
        date_precision=DatePrecision.day, uncertainty_type=Uncertainty.firm,
        source_origin=SourceOrigin.curated_pdufa, external_ref=f"pdufa:{ticker}:{event_date}",
        status=Status.unverified, sources=sources,
    )


def _ctgov_catalyst(ticker, event_date, *, posted):
    """A single-source CT.gov trial readout mirroring the clinicaltrials provider: ONE primary
    ClinicalTrials.gov source carrying published_date=lastUpdatePostDate. Under the DATA-03
    amendment this single authoritative source VERIFIES on its own."""
    source = CatalystSource(
        source_name="ClinicalTrials.gov", source_url="https://clinicaltrials.gov/study/NCT9",
        source_type=SourceType.primary, reported_date=event_date, date_type=DateType.estimated,
        published_date=posted, retrieved_at="2026-01-01T00:00:00Z",
    )
    return Catalyst(
        ticker=ticker, catalyst_type=CatalystType.trial_readout, event_date=event_date,
        date_precision=DatePrecision.day, uncertainty_type=Uncertainty.window,
        source_origin=SourceOrigin.clinicaltrials_gov, external_ref=f"NCT:{ticker}:{event_date}",
        status=Status.unverified, sources=[source],
    )


def _providers(*, prices=None, pdufa=None, clinicaltrials=None):
    """A provider struct the loop drives; unset providers default absent (degrade)."""
    return {
        "prices": prices if prices is not None else (lambda tk, s, e: _bars(tk)),
        "options": lambda tk: None,
        "finra": lambda tk: None,
        "edgar": lambda tk: None,
        "pdufa": pdufa,
        "clinicaltrials": clinicaltrials,
    }


def _counts(db):
    return {
        "bars": db.execute("SELECT COUNT(*) c FROM price_bar").fetchone()["c"],
        "catalysts": db.execute("SELECT COUNT(*) c FROM catalyst").fetchone()["c"],
        "cards": db.execute("SELECT COUNT(*) c FROM company_card").fetchone()["c"],
    }


def test_ingest_populates_bars_catalysts_cards(db, tmp_path):
    csv_path = _seed(tmp_path, [("ABCD", "Alpha Bio", False)])
    providers = _providers(
        pdufa=lambda tks, s, e, company_map=None: [
            _catalyst("ABCD", "2026-02-06", two_source=True, fr_published="2026-01-15")],
    )
    ingest.ingest_history(db, start="2026-01-02", end="2026-01-09", providers=providers,
                          universe_csv=csv_path)
    c = _counts(db)
    assert c["bars"] > 0 and c["catalysts"] == 1 and c["cards"] > 0


def test_ingest_two_source_catalyst_verified_and_pit_stamped(db, tmp_path):
    csv_path = _seed(tmp_path, [("ABCD", "Alpha Bio", False)])
    providers = _providers(
        pdufa=lambda tks, s, e, company_map=None: [
            _catalyst("ABCD", "2026-02-06", two_source=True, fr_published="2026-01-15")],
    )
    ingest.ingest_history(db, start="2026-01-02", end="2026-01-09", providers=providers,
                          universe_csv=csv_path)
    cat = store.tradeable_catalysts(db)
    assert len(cat) == 1
    assert cat[0].status == Status.verified
    assert cat[0].last_verified_at == "2026-01-15"  # the FR publication_date — NOT now, NOT event_date


def _tracker_only_catalyst(ticker, event_date):
    """A single NON-authoritative tracker (RTTNews secondary) — must stay untradeable (2-source
    rule preserved for scraped feeds; DATA-03 amendment does NOT touch trackers)."""
    return Catalyst(
        ticker=ticker, catalyst_type=CatalystType.pdufa, event_date=event_date,
        date_precision=DatePrecision.day, uncertainty_type=Uncertainty.soft,
        source_origin=SourceOrigin.curated_pdufa, external_ref=f"rtt:{ticker}:{event_date}",
        status=Status.unverified, sources=[CatalystSource(
            source_name="RTTNews", source_url="https://rtt", source_type=SourceType.secondary,
            reported_date=event_date, date_type=DateType.estimated,
            retrieved_at="2026-01-01T00:00:00Z")],
    )


def test_ingest_single_tracker_source_stays_untradeable(db, tmp_path):
    csv_path = _seed(tmp_path, [("ABCD", "Alpha Bio", False)])
    providers = _providers(
        pdufa=lambda tks, s, e, company_map=None: [
            _tracker_only_catalyst("ABCD", "2026-02-06")],
    )
    ingest.ingest_history(db, start="2026-01-02", end="2026-01-09", providers=providers,
                          universe_csv=csv_path)
    assert store.tradeable_catalysts(db) == []
    row = db.execute("SELECT status FROM catalyst").fetchone()
    assert row["status"] == Status.unverified.value


def test_ingest_verified_null_published_date_stays_unstamped(db, tmp_path):
    """HARDENING: a VERIFIED catalyst whose primary source has published_date=None must NOT be
    stamped — no fallback to now()/event_date. It stays unstamped (excluded by build_event_set),
    surfaced only in the tradeable count."""
    csv_path = _seed(tmp_path, [("ABCD", "Alpha Bio", False)])
    providers = _providers(
        pdufa=lambda tks, s, e, company_map=None: [
            _catalyst("ABCD", "2026-02-06", two_source=True, fr_published=None)],
    )
    ingest.ingest_history(db, start="2026-01-02", end="2026-01-09", providers=providers,
                          universe_csv=csv_path)
    cat = store.tradeable_catalysts(db)
    assert len(cat) == 1 and cat[0].status == Status.verified
    assert cat[0].last_verified_at is None  # never now(), never event_date
    # excluded from every event window (the last_verified_at guard)
    events = build_event_set(db, start="2026-01-16", end="2026-01-30", hold_days=30)
    assert all(not rec["catalysts"] for rec in events)


def test_ingest_last_verified_at_no_lookahead(db, tmp_path):
    """The D-stamped catalyst is INCLUDED in event windows with as_of >= D and EXCLUDED before D."""
    csv_path = _seed(tmp_path, [("ABCD", "Alpha Bio", False)])
    providers = _providers(
        pdufa=lambda tks, s, e, company_map=None: [
            _catalyst("ABCD", "2026-02-06", two_source=True, fr_published="2026-01-15")],
    )
    ingest.ingest_history(db, start="2026-01-02", end="2026-01-09", providers=providers,
                          universe_csv=csv_path)
    events = build_event_set(db, start="2026-01-09", end="2026-01-23", hold_days=30)
    by_as_of = {rec["as_of"]: rec["catalysts"] for rec in events}
    assert by_as_of["2026-01-09"] == []                 # as_of < D=2026-01-15 -> excluded
    assert len(by_as_of["2026-01-16"]) == 1             # as_of >= D -> included
    assert by_as_of["2026-01-16"][0]["ticker"] == "ABCD"


def test_ingest_single_ctgov_readout_verifies_and_pit_stamped(db, tmp_path):
    """DATA-03 amendment end-to-end: a SINGLE CT.gov readout now flows insert->verify->tradeable
    with a POINT-IN-TIME last_verified_at (the record's lastUpdatePostDate, NOT now/event_date).
    Anti-look-ahead: excluded before D, included at as_of >= D."""
    csv_path = _seed(tmp_path, [("ABCD", "Alpha Bio", False)])
    providers = _providers(clinicaltrials=lambda tks, s, e: [
        _ctgov_catalyst("ABCD", "2026-02-06", posted="2026-01-15")])
    ingest.ingest_history(db, start="2026-01-02", end="2026-01-09", providers=providers,
                          universe_csv=csv_path)
    cat = store.tradeable_catalysts(db)
    assert len(cat) == 1 and cat[0].status == Status.verified          # single source now tradeable
    assert cat[0].last_verified_at == "2026-01-15"                     # CT.gov post date, not now/event
    events = build_event_set(db, start="2026-01-09", end="2026-01-23", hold_days=30)
    by = {r["as_of"]: r["catalysts"] for r in events}
    assert by["2026-01-09"] == []                                     # as_of < D -> excluded
    assert len(by["2026-01-16"]) == 1 and by["2026-01-16"][0]["ticker"] == "ABCD"  # as_of >= D


def test_ingest_idempotent_double_run(db, tmp_path):
    csv_path = _seed(tmp_path, [("ABCD", "Alpha Bio", False), ("WXYZ", "Omega Tx", False)])
    providers = _providers(
        pdufa=lambda tks, s, e, company_map=None: [
            _catalyst("ABCD", "2026-02-06", two_source=True, fr_published="2026-01-15")],
    )
    kw = {"start": "2026-01-02", "end": "2026-01-09", "providers": providers,
          "universe_csv": csv_path}
    ingest.ingest_history(db, **kw)
    first = _counts(db)
    ingest.ingest_history(db, **kw)
    assert _counts(db) == first  # UPSERT on natural keys -> no duplication


def test_ingest_retains_delisted(db, tmp_path):
    csv_path = _seed(tmp_path, [("DEAD", "Defunct Bio", True)])
    ingest.ingest_history(db, start="2026-01-02", end="2026-01-09", providers=_providers(),
                          universe_csv=csv_path)
    rows = db.execute("SELECT delisted FROM price_bar WHERE ticker='DEAD'").fetchall()
    assert rows and all(r["delisted"] == 1 for r in rows)  # survivorship-free: retained + tagged


def test_ingest_persists_source_grade_agreeing(db, tmp_path):
    csv_path = _seed(tmp_path, [("ABCD", "Alpha Bio", False)])
    ingest.ingest_history(db, start="2026-01-02", end="2026-01-09", providers=_providers(),
                          universe_csv=csv_path)
    row = db.execute(
        "SELECT source_grade, agreeing_sources FROM price_bar WHERE ticker='ABCD' LIMIT 1"
    ).fetchone()
    assert row["source_grade"] == "green"
    assert set(row["agreeing_sources"].split(",")) == {"alpha_vantage", "yfinance"}


def test_ingest_provider_degrade_continues(db, tmp_path):
    """A provider returning [] for one name -> the loop still ingests the others (no crash)."""
    csv_path = _seed(tmp_path, [("GOOD", "Good Bio", False), ("EMPTY", "Empty Bio", False)])
    providers = _providers(prices=lambda tk, s, e: [] if tk == "EMPTY" else _bars(tk))
    ingest.ingest_history(db, start="2026-01-02", end="2026-01-09", providers=providers,
                          universe_csv=csv_path)
    assert db.execute("SELECT COUNT(*) c FROM price_bar WHERE ticker='GOOD'").fetchone()["c"] > 0
    assert db.execute("SELECT COUNT(*) c FROM price_bar WHERE ticker='EMPTY'").fetchone()["c"] == 0
