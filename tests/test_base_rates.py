"""RED-first suite for the clinical base-rate loader (FRAME-03, OPS-04).

The anti-hallucination invariant: no number without a source. base_rate() must return the
value WITH its citation (source_name/source_url/quote), and must RAISE on an unknown key
rather than return a silent None an agent could cite as fact. Reads the real
data/base_rates.csv shipped in Task 1. Written before base_rates.py exists (module absent = RED).
"""

import pytest

from catalyst_trader.quant.base_rates import base_rate, load_base_rates

# --------------------------------------------------------------------- load_base_rates


def test_load_base_rates_returns_typed_rows():
    rows = load_base_rates()
    assert isinstance(rows, list) and len(rows) >= 12
    # value is float-typed (not the raw CSV string)
    assert all(isinstance(r["value"], float) for r in rows)
    # every row carries its citation columns
    assert all(r["source_name"] and r["source_url"] and r["quote"] for r in rows)


# --------------------------------------------------------------------- base_rate


def test_base_rate_loads_value_with_citation():
    # FRAME-03: value AND citation come back together.
    row = base_rate("loa", phase="I", indication="all")
    assert row["value"] == pytest.approx(0.079)
    assert row["source_name"]
    assert row["source_url"].startswith("http")
    assert row["quote"]


def test_base_rate_oncology_row():
    assert base_rate("loa", phase="I", indication="oncology")["value"] == pytest.approx(0.034)


def test_base_rate_crl_penalty_is_negative():
    assert base_rate("crl_penalty", indication="all")["value"] == pytest.approx(-0.28)


def test_base_rate_adcom_followthrough():
    assert base_rate("adcom_followthrough", indication="all")["value"] == pytest.approx(0.90)


def test_base_rate_unknown_key_raises():
    # no silent None — an agent must never cite a number that isn't in the table.
    with pytest.raises(ValueError):
        base_rate("does_not_exist")


def test_base_rate_unknown_phase_raises():
    with pytest.raises(ValueError):
        base_rate("loa", phase="IV", indication="all")
