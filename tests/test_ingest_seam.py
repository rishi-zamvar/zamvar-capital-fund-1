"""Plan 06.9-07 Task 1 — assemble_raw() the ONE provider->build_card injection seam (INGEST-03).

Offline: stubbed providers + the conftest in-memory `db`. Proves assemble_raw builds the exact
`raw` dict desk.company_scan.build_card consumes, INJECTS catalyst_date into the CBOE 7-market-key
options_quote so options_liquid sees the complete 8-key dict (no KeyError), degrades a None quote
cleanly, and that ingested store rows read identically to fixtures (zero downstream contract change).
"""

from types import SimpleNamespace

from catalyst_trader import ingest, store
from catalyst_trader.desk import company_scan
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

# The REAL CBOE 7-market-key options_quote (options_cboe.fetch shape) — NO catalyst_date; that is
# the ticker's next-catalyst date the provider cannot know, which assemble_raw injects downstream.
_CBOE_LIVE = {
    "options_quote": {
        "call_bid": 1.0, "call_ask": 1.2, "put_bid": 1.0, "put_ask": 1.2,
        "call_oi": 300, "put_oi": 300, "expiry": "2026-12-31",
    },
    "underlying_quote": {"bid": 10.0, "volume": 50_000, "oi": 600},
    "iv30": 0.85, "term_spread": 0.02, "straddle_move_pct": 0.18,
    "straddle_median": None, "underlying_price": 10.0,
}

_CBOE_NO_PAIR = {  # no live ATM pair -> options_quote=None + iv30=None (Pitfall 2)
    "options_quote": None, "iv30": None, "term_spread": None,
    "straddle_move_pct": None, "straddle_median": None,
    "underlying_price": 10.0,
    "underlying_quote": {"bid": 0.0, "volume": 0.0, "oi": 0},
}


def _providers(cboe, *, catalysts=(), finra=None, edgar=None):
    """A small provider struct of callables assemble_raw drives (tests inject stubs)."""
    return {
        "options": lambda tk: cboe,
        "finra": (lambda tk: finra) if finra is not None else None,
        "edgar": (lambda tk: edgar) if edgar is not None else None,
        "catalysts": lambda tk: list(catalysts),
    }


def _cat(event_date):
    return SimpleNamespace(event_date=event_date)


def test_assemble_raw_injects_catalyst_date_and_build_card_accepts(db):
    store.upsert_bars(db, "ABCD", [
        {"week_end": "2026-01-02", "close": 100.0, "volume": 1_000},
        {"week_end": "2026-01-09", "close": 110.0, "volume": 1_100},
    ])
    providers = _providers(_CBOE_LIVE, catalysts=[_cat("2026-03-15")])

    raw = ingest.assemble_raw(providers, "ABCD", "2026-01-09")

    # The seam fix: the 7-key CBOE quote becomes the COMPLETE 8-key options_liquid shape.
    assert raw["options_quote"]["catalyst_date"] == "2026-03-15"
    assert raw["next_catalyst"] == "2026-03-15"
    assert set(raw["options_quote"]) == {
        "call_bid", "call_ask", "put_bid", "put_ask", "call_oi", "put_oi", "expiry", "catalyst_date",
    }

    card = company_scan.build_card(db, "ABCD", "2026-01-09", raw, thesis_row={})
    assert card["options"]["options_liquid"] is True  # options_liquid ran, no KeyError


def test_assemble_raw_none_quote_degrades_cleanly(db):
    store.upsert_bars(db, "ABCD", [{"week_end": "2026-01-09", "close": 110.0, "volume": 1_100}])
    providers = _providers(_CBOE_NO_PAIR, catalysts=[_cat("2026-03-15")])

    raw = ingest.assemble_raw(providers, "ABCD", "2026-01-09")

    assert raw["options_quote"] is None  # never a partial dict
    card = company_scan.build_card(db, "ABCD", "2026-01-09", raw, thesis_row={})
    assert card["options"]["options_liquid"] is None  # build_card degrades to the in-house path


def test_assemble_raw_no_upcoming_catalyst_drops_quote(db):
    """No catalyst to gate options against -> options_quote degrades to None (never catalyst_date=None
    which would crash options_liquid's expiry compare)."""
    store.upsert_bars(db, "ABCD", [{"week_end": "2026-01-09", "close": 110.0, "volume": 1_100}])
    providers = _providers(_CBOE_LIVE, catalysts=[])  # no upcoming catalyst

    raw = ingest.assemble_raw(providers, "ABCD", "2026-01-09")

    assert raw["next_catalyst"] is None
    assert raw["options_quote"] is None
    card = company_scan.build_card(db, "ABCD", "2026-01-09", raw, thesis_row={})
    assert card["options"]["options_liquid"] is None


def test_zero_liquidity_reads_real_underlying_quote_shape(db):
    """The {bid,volume,oi} underlying_quote assemble_raw emits is consumed by zero_liquidity
    without KeyError (real-shape guard)."""
    store.upsert_bars(db, "ABCD", [{"week_end": "2026-01-09", "close": 110.0, "volume": 1_100}])
    providers = _providers(_CBOE_NO_PAIR, catalysts=[_cat("2026-03-15")])

    raw = ingest.assemble_raw(providers, "ABCD", "2026-01-09")
    card = company_scan.build_card(db, "ABCD", "2026-01-09", raw, thesis_row={})

    # underlying_quote had bid=0/volume=0/oi=0 -> zero_liquidity fires True, no KeyError.
    assert card["options"]["zero_liquidity"] is True


def test_ingested_bars_read_pointintime_unchanged(db):
    """Bars written with the multi-source cross-check provenance (source_grade/agreeing_sources)
    read back through bars_asof BYTE-IDENTICALLY to plain fixture bars — zero downstream contract
    change; the store IS the seam, no live-boolean anywhere."""
    ingested = [
        {"week_end": "2026-01-02", "open": 9.0, "high": 11.0, "low": 8.5, "close": 10.0, "volume": 1_000},
        {"week_end": "2026-01-09", "open": 10.0, "high": 12.0, "low": 9.5, "close": 11.0, "volume": 1_100},
    ]
    store.upsert_bars(db, "GRN", ingested, source="alpha_vantage", source_grade="green",
                      agreeing_sources="alpha_vantage,yfinance")
    store.upsert_bars(db, "FIX", ingested)  # default fixture source

    green = store.bars_asof(db, "GRN", "2026-01-09")
    fixture = store.bars_asof(db, "FIX", "2026-01-09")
    assert green == fixture  # provenance never leaks into the read contract


# --- pdufa_edgar daemon-path verify-synergy (PDUFA-EDGAR-04) ----------------------------------
# The chain the debug exposed: our OWN SEC-EDGAR PDUFA source, run on the daemon path
# (ingest_history -> _fetch_catalysts -> insert -> verify -> _pit_stamp), must reach verified +
# tradeable with a POINT-IN-TIME last_verified_at == the 8-K filing_date (never now/event_date).


def _seed_csv(tmp_path):
    """A tiny seed_universe.csv (one active name, # comment skipped) -> its path."""
    path = tmp_path / "seed.csv"
    path.write_text("ticker,company_name,market_cap,adv_usd,therapeutic_area,delisted\n"
                    "# comment line to skip\n"
                    "ABCD,Alpha Bio,1,1,x,false\n")
    return str(path)


def _edgar_pdufa_catalyst(ticker, event_date, *, filing_date):
    """Mirror pdufa_edgar._to_catalyst: a SINGLE 'SEC EDGAR' primary Catalyst carrying the 8-K
    filing_date as published_date. Under DATA-03 this single authoritative source self-verifies;
    the loop stamps last_verified_at from published_date (the 8-K filing_date, point-in-time)."""
    return Catalyst(
        ticker=ticker, catalyst_type=CatalystType.pdufa, event_date=event_date,
        date_precision=DatePrecision.day, uncertainty_type=Uncertainty.window,
        source_origin=SourceOrigin.curated_pdufa,
        external_ref=f"pdufa_edgar:{ticker}:0000000000-26-000001",
        status=Status.unverified,
        sources=[CatalystSource(
            source_name="SEC EDGAR", source_url="https://www.sec.gov/Archives/edgar/data/0/x-8k.htm",
            source_type=SourceType.primary, reported_date=event_date, date_type=DateType.estimated,
            published_date=filing_date, retrieved_at="2026-08-11T00:00:00Z")],
    )


def test_pdufa_edgar_single_source_verifies_and_stamps(db, tmp_path):
    """A pdufa_edgar 'SEC EDGAR' primary flows insert->verify->_pit_stamp on the daemon path to
    Status.verified AND last_verified_at == the 8-K filing_date AND appears in tradeable_catalysts —
    the DATA-03 self-verify synergy end-to-end, against the REAL verify pipeline (verify.py unchanged)."""
    csv_path = _seed_csv(tmp_path)
    providers = {
        "prices": lambda tk, s, e: [],  # no bars needed for the catalyst chain
        "options": lambda tk: None, "finra": lambda tk: None, "edgar": lambda tk: None,
        "pdufa_edgar": lambda tks, s, e, company_map=None: [
            _edgar_pdufa_catalyst("ABCD", "2026-10-01", filing_date="2026-08-11")],
    }
    ingest.ingest_history(db, start="2026-01-02", end="2026-01-09", providers=providers,
                          universe_csv=csv_path)
    cat = store.tradeable_catalysts(db)
    assert len(cat) == 1
    assert cat[0].status == Status.verified                 # single 'SEC EDGAR' primary self-verifies
    assert cat[0].last_verified_at == "2026-08-11"          # the 8-K filing_date — NOT now, NOT event_date


def test_pdufa_edgar_degrades_when_slot_missing(db, tmp_path):
    """No pdufa_edgar slot in the providers dict -> ingest_history runs clean (no raise), zero
    pdufa_edgar catalysts (the slot degrades to [] via _safe)."""
    csv_path = _seed_csv(tmp_path)
    providers = {"prices": lambda tk, s, e: [], "options": lambda tk: None,
                 "finra": lambda tk: None, "edgar": lambda tk: None}
    ingest.ingest_history(db, start="2026-01-02", end="2026-01-09", providers=providers,
                          universe_csv=csv_path)
    assert store.tradeable_catalysts(db) == []
