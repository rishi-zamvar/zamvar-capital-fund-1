"""Plan 06.9-07 Task 1 — assemble_raw() the ONE provider->build_card injection seam (INGEST-03).

Offline: stubbed providers + the conftest in-memory `db`. Proves assemble_raw builds the exact
`raw` dict desk.company_scan.build_card consumes, INJECTS catalyst_date into the CBOE 7-market-key
options_quote so options_liquid sees the complete 8-key dict (no KeyError), degrades a None quote
cleanly, and that ingested store rows read identically to fixtures (zero downstream contract change).
"""

from types import SimpleNamespace

from catalyst_trader import ingest, store
from catalyst_trader.desk import company_scan

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
