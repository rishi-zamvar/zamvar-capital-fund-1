"""RED-first exhaustive edge-case suite for the portfolio tools (OPS-04, QUANT-02/03).

concentration (Herfindahl Σwᵢ² + max single-name weight) and exposure (gross Σ|wᵢ| + net Σwᵢ).
The honest long/long framing (PITFALLS #1): two longs are 2× gross long, NOT netted — gross
uses abs so real directional risk is surfaced to the PM/Risk agent. Both tools RAISE on an
empty book or any NaN/inf weight rather than emitting a misleading number (Pattern 2). Written
before the logic exists (module absent = RED).
"""

import math

import pytest

from catalyst_trader.quant.result import ToolResult
from catalyst_trader.quant.portfolio import concentration, exposure


# ------------------------------------------------------------------- concentration


def test_concentration_empty_raises():
    with pytest.raises(ValueError):
        concentration([])


def test_concentration_nan_raises():
    with pytest.raises(ValueError):
        concentration([0.5, math.nan, 0.2])


def test_concentration_single_name():
    # extreme: a one-name book is maximally concentrated
    r = concentration([1.0])
    assert r.value == pytest.approx(1.0)
    assert r.detail["max_weight"] == pytest.approx(1.0)
    assert isinstance(r, ToolResult)


def test_concentration_happy():
    r = concentration([0.5, 0.3, 0.2])
    assert r.value == pytest.approx(0.38)  # 0.25 + 0.09 + 0.04
    assert r.detail["max_weight"] == pytest.approx(0.5)


def test_concentration_max_weight_uses_abs():
    # max single-name magnitude ignores sign
    r = concentration([0.3, -0.6, 0.1])
    assert r.detail["max_weight"] == pytest.approx(0.6)


def test_concentration_inputs_snapshot():
    # QUANT-03: .inputs is the verbatim call args
    r = concentration([0.5, 0.3, 0.2])
    assert r.inputs == {"weights": [0.5, 0.3, 0.2]}


# ----------------------------------------------------------------------- exposure


def test_exposure_empty_raises():
    with pytest.raises(ValueError):
        exposure([])


def test_exposure_nan_raises():
    with pytest.raises(ValueError):
        exposure([0.6, math.nan])


def test_exposure_happy():
    r = exposure([0.5, 0.3, 0.2])
    assert r.value == pytest.approx(1.0)  # gross
    assert r.detail["net"] == pytest.approx(1.0)
    assert isinstance(r, ToolResult)


def test_exposure_two_longs_not_netted():
    # PITFALLS #1: two longs = 2× gross long, NOT netted
    r = exposure([0.6, 0.6])
    assert r.value == pytest.approx(1.2)
    assert r.detail["net"] == pytest.approx(1.2)


def test_exposure_negative_weight_gross_exceeds_abs_net():
    # a negative weight makes gross (abs sum) strictly larger than |net|
    r = exposure([0.6, -0.4])
    assert r.value == pytest.approx(1.0)  # gross |0.6| + |0.4|
    assert r.detail["net"] == pytest.approx(0.2)
    assert r.value > abs(r.detail["net"])


def test_exposure_inputs_snapshot():
    # QUANT-03: .inputs is the verbatim call args
    r = exposure([0.6, 0.6])
    assert r.inputs == {"weights": [0.6, 0.6]}
