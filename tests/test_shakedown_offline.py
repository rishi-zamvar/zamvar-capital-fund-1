"""Plan 06.9-08 Task 1 — the OFFLINE wiring gate for the live shakedown (INGEST-05).

Zero live API. This proves the SAME orchestration the live `scripts/shakedown.py::main` runs —
ingest the seed universe -> run_layer_a + thesis_scan on the ingested data -> a structured
edge-case report incl. the first-class `tradeable_catalyst_count` — completes end-to-end against
FIXTURE/stub providers + the conftest in-memory `db`. The live network run is NEVER a pytest test
(project rule); it is `python -m scripts.shakedown` at the operator checkpoint.
"""

from catalyst_trader import db as _db
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
from scripts import shakedown as sd

# Fridays (the shared price anchor) so as_of/week_end line up with the bars. A multi-week series
# so thesis_scan/classify_drop have enough observations for the sector-beta correlation.
_WEEKS = ["2026-01-02", "2026-01-09", "2026-01-16", "2026-01-23", "2026-01-30", "2026-02-06"]
_W1, _W2 = _WEEKS[0], _WEEKS[-1]
_PIT = "2026-01-30"  # a catalyst PIT-stamp date INSIDE [_W1, _W2]


def _seed(tmp_path, rows):
    path = tmp_path / "seed.csv"
    lines = ["ticker,company_name,market_cap,adv_usd,therapeutic_area,delisted",
             "# comment line to skip"]
    lines += [f"{tk},{name},1,1,x,{'true' if dl else 'false'}" for tk, name, dl in rows]
    path.write_text("\n".join(lines))
    return str(path)


def _bars(tk):
    """A deterministic weekly OHLCV walk across _WEEKS (distinct per ticker so beta is defined)."""
    step = (sum(ord(c) for c in tk) % 5) / 100.0 + 0.01  # a stable per-ticker drift
    close = 10.0
    out = []
    for i, wk in enumerate(_WEEKS):
        prev = close
        close = round(close * (1 + step * (1 if i % 2 else -1)), 4)
        out.append({"week_end": wk, "open": prev, "high": max(prev, close) * 1.02,
                    "low": min(prev, close) * 0.98, "close": close, "volume": 1_000 + i,
                    "source": "alpha_vantage", "source_grade": "green",
                    "agreeing_sources": {"alpha_vantage", "yfinance"}})
    return out


def _catalyst(ticker, event_date, *, two_source, fr_published):
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


def _providers(*, prices=None, pdufa=None):
    return {
        "prices": prices if prices is not None else (lambda tk, s, e: _bars(tk)),
        "options": lambda tk: None,
        "finra": lambda tk: None,
        "edgar": lambda tk: None,
        "financials": lambda tk: None,
        "clinicaltrials": lambda tks, s, e: [],
        "earnings": lambda tks, s, e: [],
        "pdufa": pdufa if pdufa is not None else (lambda tks, s, e, company_map=None: []),
    }


_KW = {"start": _W1, "end": _W2}


def test_shakedown_wiring_end_to_end(db, tmp_path):
    """The full path completes with no exception: ingest populates the store, run_layer_a returns a
    result + baseline distribution, thesis_scan returns a row per universe name."""
    # XBI is the sector reference thesis_scan/classify_drop need — the real seed always carries it.
    csv_path = _seed(tmp_path, [("ABCD", "Alpha Bio", False), ("WXYZ", "Omega Tx", False),
                                ("XBI", "SPDR Biotech ETF", False)])
    report = sd.run_shakedown(db, None, _providers(), universe_csv=csv_path, **_KW)

    # ingest happened
    assert db.execute("SELECT COUNT(*) c FROM price_bar").fetchone()["c"] > 0
    # run_layer_a produced a real baseline distribution over ingested data
    assert "distribution" in report["backtest"]
    assert report["backtest"]["distribution"]["n_weeks"] >= 1
    # thesis_scan ran and returned a row per universe name (incl. XBI's own row)
    assert report["thesis_scan"]["n_rows"] == 3


def test_shakedown_produces_edge_case_report(db, tmp_path):
    """The report carries every edge-case category key the operator triages."""
    csv_path = _seed(tmp_path, [("ABCD", "Alpha Bio", False)])
    report = sd.run_shakedown(db, None, _providers(), universe_csv=csv_path, **_KW)
    for key in ("illiquid", "missing_bars", "divergence_count", "stale", "delisting",
                "ticker_mismatch", "gaps", "rate_limit", "tradeable_catalyst_count"):
        assert key in report, f"missing edge-case key: {key}"
    assert "coverage" in report


def _tracker_only(ticker, event_date):
    """A single NON-authoritative tracker (RTTNews secondary): stays untradeable under DATA-03
    (a lone Federal Register/CT.gov source WOULD now single-verify — the amendment)."""
    return Catalyst(
        ticker=ticker, catalyst_type=CatalystType.pdufa, event_date=event_date,
        date_precision=DatePrecision.day, uncertainty_type=Uncertainty.soft,
        source_origin=SourceOrigin.curated_pdufa, external_ref=f"rtt:{ticker}:{event_date}",
        status=Status.unverified, sources=[CatalystSource(
            source_name="RTTNews", source_url="https://rtt", source_type=SourceType.secondary,
            reported_date=event_date, date_type=DateType.estimated,
            retrieved_at="2026-01-01T00:00:00Z")],
    )


def test_shakedown_reports_tradeable_catalyst_count(db, tmp_path):
    """The honesty line: a 2-source verified catalyst PIT-stamped in-window is counted; a lone
    NON-authoritative tracker feed yields 0 (a vacuous backtest is SURFACED, not hidden)."""
    csv_path = _seed(tmp_path, [("ABCD", "Alpha Bio", False)])

    two = _providers(pdufa=lambda tks, s, e, company_map=None: [
        _catalyst("ABCD", "2026-03-06", two_source=True, fr_published=_PIT)])
    r_two = sd.run_shakedown(db, None, two, universe_csv=csv_path, **_KW)
    assert r_two["tradeable_catalyst_count"] == 1

    one = _providers(pdufa=lambda tks, s, e, company_map=None: [
        _tracker_only("SNGL", "2026-03-06")])
    csv2 = _seed(tmp_path, [("SNGL", "Single Bio", False)])
    conn2 = _db.connect(":memory:")
    _db.migrate(conn2)
    try:
        r_one = sd.run_shakedown(conn2, None, one, universe_csv=csv2, **_KW)
        assert r_one["tradeable_catalyst_count"] == 0
    finally:
        conn2.close()


def test_shakedown_degrade_is_logged_not_fabricated(db, tmp_path):
    """A provider that degrades (raises / empty) for one name -> that name has NO fabricated bar; it
    surfaces in the report (ticker_mismatch), never as an invented value."""
    csv_path = _seed(tmp_path, [("GOOD", "Good Bio", False), ("DEAD", "No Data", False)])

    def _prices(tk, s, e):
        if tk == "DEAD":
            raise RuntimeError("simulated source outage")
        return _bars(tk)

    report = sd.run_shakedown(db, None, _providers(prices=_prices), universe_csv=csv_path, **_KW)
    assert db.execute("SELECT COUNT(*) c FROM price_bar WHERE ticker='DEAD'").fetchone()["c"] == 0
    assert "DEAD" in report["ticker_mismatch"]
    assert "GOOD" not in report["ticker_mismatch"]
