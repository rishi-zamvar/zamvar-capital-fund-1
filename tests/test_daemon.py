"""Plan 06.10-06 Task 2 — the stateless run_cycle daemon + self-heal (detect_gaps/backfill) + the
data-health writer. Zero live API: FIXTURE providers + the conftest in-memory `db`. run_cycle is
IDEMPOTENT (double-run = identical counts, the crash-safety proxy) and never raises on a degraded
source (launchd is the supervisor, store idempotency is the resumability)."""

import json
import logging
from datetime import datetime, timezone

from catalyst_trader import pipeline, store
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
from scripts import daemon

# window_weeks=4 anchored at a fixed Monday -> Fridays 01-16, 01-23, 01-30, 02-06
_NOW = datetime(2026, 2, 9, 12, 0, tzinfo=timezone.utc)
_WEEKS = ["2026-01-16", "2026-01-23", "2026-01-30", "2026-02-06"]
_START, _END = _WEEKS[0], _WEEKS[-1]


def _seed(tmp_path, tickers):
    path = tmp_path / "seed.csv"
    lines = ["ticker,company_name,market_cap,adv_usd,therapeutic_area,delisted"]
    lines += [f"{tk},{tk} Bio,1,1,x,false" for tk in tickers]
    path.write_text("\n".join(lines))
    return str(path)


def _bars(tk, weeks=_WEEKS):
    step = (sum(ord(c) for c in tk) % 5) / 100.0 + 0.01
    close, out = 10.0, []
    for i, wk in enumerate(weeks):
        prev = close
        close = round(close * (1 + step * (1 if i % 2 else -1)), 4)
        out.append({"week_end": wk, "open": prev, "high": max(prev, close) * 1.02,
                    "low": min(prev, close) * 0.98, "close": close, "volume": 1_000 + i,
                    "source": "alpha_vantage", "source_grade": "green",
                    "agreeing_sources": {"alpha_vantage", "yfinance"}})
    return out


def _providers(*, prices=None):
    return {
        "prices": prices if prices is not None else (lambda tk, s, e: _bars(tk)),
        "options": lambda tk: None, "finra": lambda tk: None, "edgar": lambda tk: None,
        "financials": lambda tk: None, "macro": None,
        "clinicaltrials": lambda tks, s, e: [],
        "earnings": lambda tks, s, e: [],
        "pdufa": lambda tks, s, e, company_map=None: [],
    }


def _catalyst(ticker, event_date):
    src = CatalystSource(
        source_name="Federal Register", source_url="https://fr", source_type=SourceType.primary,
        reported_date=event_date, date_type=DateType.estimated, published_date=event_date,
        retrieved_at="2026-01-01T00:00:00Z")
    return Catalyst(
        ticker=ticker, catalyst_type=CatalystType.pdufa, event_date=event_date,
        date_precision=DatePrecision.day, uncertainty_type=Uncertainty.firm,
        source_origin=SourceOrigin.curated_pdufa, external_ref=f"pdufa:{ticker}:{event_date}",
        status=Status.unverified, sources=[src])


_CYCLE_KW = dict(window_weeks=4, now=_NOW)


def test_run_cycle_populates_store(db, tmp_path):
    csv_path = _seed(tmp_path, ["ABCD", "WXYZ", "XBI"])
    daemon.run_cycle(db, _providers(), universe_csv=csv_path,
                     health_path=str(tmp_path / "data_health.json"), **_CYCLE_KW)
    assert db.execute("SELECT COUNT(*) c FROM price_bar").fetchone()["c"] > 0
    assert db.execute("SELECT COUNT(*) c FROM company_card").fetchone()["c"] > 0


def test_run_cycle_idempotent(db, tmp_path):
    csv_path = _seed(tmp_path, ["ABCD", "WXYZ", "XBI"])
    hp = str(tmp_path / "data_health.json")
    daemon.run_cycle(db, _providers(), universe_csv=csv_path, health_path=hp, **_CYCLE_KW)
    n1 = db.execute("SELECT COUNT(*) c FROM price_bar").fetchone()["c"]
    c1 = db.execute("SELECT COUNT(*) c FROM company_card").fetchone()["c"]
    daemon.run_cycle(db, _providers(), universe_csv=csv_path, health_path=hp, **_CYCLE_KW)
    n2 = db.execute("SELECT COUNT(*) c FROM price_bar").fetchone()["c"]
    c2 = db.execute("SELECT COUNT(*) c FROM company_card").fetchone()["c"]
    assert (n1, c1) == (n2, c2), "double-run wrote duplicate rows — not idempotent"


def test_detect_gaps_finds_holes(db):
    universe = ["ABCD", "WXYZ", "NOCARD"]
    # ABCD complete (fresh); WXYZ partial + a STALE source; NOCARD has an upcoming catalyst, no card
    store.upsert_bars(db, "ABCD", _bars("ABCD"), source="alpha_vantage", source_grade="green",
                      agreeing_sources="alpha_vantage,yfinance")
    store.upsert_bars(db, "WXYZ", _bars("WXYZ", weeks=_WEEKS[:2]), source="stalesrc",
                      source_grade="green", agreeing_sources="stalesrc")
    db.execute("UPDATE price_bar SET retrieved_at='2020-01-01T00:00:00+00:00' WHERE source='stalesrc'")
    db.commit()
    cid = store.insert_catalyst(db, _catalyst("NOCARD", "2026-03-06"))
    assert cid

    gaps = pipeline.detect_gaps(db, universe, (_START, _END), pipeline.registry.CADENCE, now=_NOW)
    missing = set(gaps["price_weeks_missing"])
    assert "WXYZ@2026-01-30" in missing and "WXYZ@2026-02-06" in missing
    assert not any(g.startswith("ABCD@") for g in missing)
    assert "stalesrc" in gaps["stale_sources"]
    assert "NOCARD" in gaps["missing_cards"]


def test_backfill_fills_gaps(db, tmp_path):
    csv_path = _seed(tmp_path, ["ABCD", "WXYZ"])
    # seed WXYZ with only 2 of 4 weeks -> a real hole
    store.upsert_bars(db, "WXYZ", _bars("WXYZ", weeks=_WEEKS[:2]), source="alpha_vantage")
    gaps = pipeline.detect_gaps(db, ["ABCD", "WXYZ"], (_START, _END), pipeline.registry.CADENCE, now=_NOW)
    assert any(g.startswith("WXYZ@") for g in gaps["price_weeks_missing"])

    pipeline.backfill(db, _providers(), gaps, (_START, _END), universe_csv=csv_path)
    after = pipeline.detect_gaps(db, ["ABCD", "WXYZ"], (_START, _END), pipeline.registry.CADENCE, now=_NOW)
    assert not any(g.startswith("WXYZ@") for g in after["price_weeks_missing"]), "backfill left holes"


def test_degraded_source_no_raise(db, tmp_path):
    csv_path = _seed(tmp_path, ["ABCD"])
    # a pre-existing STALE source in the store (the degrade signal) + a provider that RAISES
    store.upsert_bars(db, "OLD", _bars("OLD"), source="deadsrc", source_grade="green",
                      agreeing_sources="deadsrc")
    db.execute("UPDATE price_bar SET retrieved_at='2020-01-01T00:00:00+00:00' WHERE source='deadsrc'")
    db.commit()

    def _boom(tk, s, e):
        raise RuntimeError("simulated source outage")

    hp = str(tmp_path / "data_health.json")
    # never raises — the degrade is caught by ingest._safe / the cascade, recorded, not fatal
    daemon.run_cycle(db, _providers(prices=_boom), universe_csv=csv_path, health_path=hp, **_CYCLE_KW)
    health = json.loads(open(hp).read())
    assert health["degraded"] is True
    assert health["sources"]["deadsrc"]["degraded"] is True


def test_data_health_divergences_this_cycle(db, tmp_path):
    """A cycle that logs K cross-check divergences -> data_health.divergences_this_cycle == K
    (a PER-CYCLE count via the log-tap, NOT a fabricated rolling window)."""
    csv_path = _seed(tmp_path, ["ABCD"])
    K = 3
    log = logging.getLogger("catalyst_trader.providers.prices")

    def _diverging(tk, s, e):
        for _ in range(K):
            log.warning("cross-check divergence for %s: sources disagree", tk)
        return _bars(tk)  # full coverage -> no gaps -> backfill is a no-op (no re-ingest double count)

    hp = str(tmp_path / "data_health.json")
    daemon.run_cycle(db, _providers(prices=_diverging), universe_csv=csv_path, health_path=hp, **_CYCLE_KW)
    health = json.loads(open(hp).read())
    assert health["divergences_this_cycle"] == K
