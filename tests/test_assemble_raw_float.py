"""Plan 06.11-03 Task 2 — assemble_raw's ADDITIVE float/shares_outstanding wiring.

The RH `float` slot (get_equity_fundamentals) gives the card pipeline a clean float source where
there was none. assemble_raw surfaces it additively: raw["float"] from RH, raw["shares_outstanding"]
from RH degrading to the existing edgar `financials` shares. ADDITIVE keys only — build_card's
consumed contract is unchanged (a guard test proves the existing raw key set is preserved).
"""

from catalyst_trader import ingest

# The existing full raw key set — build_card's consumed contract. The new float/shares_outstanding
# keys are ADDITIVE: this set must remain a subset of assemble_raw's output regardless of RH slots.
_BASE_KEYS = {
    "options_quote", "underlying_quote", "iv30", "term_spread", "straddle_move_pct",
    "straddle_median", "underlying_price", "short_interest", "days_to_cover",
    "si_settlement_date", "cash_runway_months", "seen_accessions", "live_shelf",
    "days_to_catalyst", "next_catalyst", "catalysts_4w", "competitor_next_7d", "nct_snapshots",
}


def _providers(*, float_slot=None, financials=None):
    p = {
        "options": lambda tk: {},
        "finra": None,
        "edgar": None,
        "catalysts": lambda tk: [],
    }
    if float_slot is not None:
        p["float"] = lambda tk: float_slot
    if financials is not None:
        p["financials"] = lambda tk: financials
    return p


def test_assemble_raw_adds_float_from_rh():
    providers = _providers(float_slot={"float": 162910507.568, "shares_outstanding": 166184322.999})
    raw = ingest.assemble_raw(providers, "IONS", "2026-08-14")
    assert raw["float"] == 162910507.568
    assert raw["shares_outstanding"] == 166184322.999


def test_assemble_raw_float_degrades_to_financials_shares():
    # No RH float slot, but edgar financials has shares_outstanding -> degrade to edgar.
    providers = _providers(financials={"shares_outstanding": 999.0})
    raw = ingest.assemble_raw(providers, "IONS", "2026-08-14")
    assert raw["float"] is None
    assert raw["shares_outstanding"] == 999.0

    # Neither RH nor edgar -> both None (never fabricated).
    raw2 = ingest.assemble_raw(_providers(), "IONS", "2026-08-14")
    assert raw2["float"] is None
    assert raw2["shares_outstanding"] is None


def test_rh_float_wins_over_financials():
    providers = _providers(
        float_slot={"float": 100.0, "shares_outstanding": 200.0},
        financials={"shares_outstanding": 999.0},
    )
    raw = ingest.assemble_raw(providers, "IONS", "2026-08-14")
    assert raw["shares_outstanding"] == 200.0  # RH primary


def test_build_card_contract_unchanged():
    """No RH slots at all -> assemble_raw still returns the full existing key set; the additive
    float/shares_outstanding keys never remove or rename anything build_card consumes."""
    raw = ingest.assemble_raw(_providers(), "IONS", "2026-08-14")
    assert _BASE_KEYS.issubset(set(raw))
    # the only new keys are the two additive ones
    assert set(raw) - _BASE_KEYS == {"float", "shares_outstanding"}
