"""RED-first exhaustive spec for the football-field aggregator (FF-02/FF-03, QUANT-03).

`expected_move_field` combines already-normalized per-method move MAGNITUDES into the
convergence point estimate = confidence-weighted trimmed MEDIAN, plus a dispersion/agreement
score. Money-critical: RAISES on out-of-domain input (never a misleading NaN), drops abstaining
methods (the caller omits them — never entered as 0), and refuses a one-method 'field' (no false
precision). Every threshold is read from params["field"] by direct subscript — a missing key
RAISES; there is no numeric literal fallback in the tool body. Written before the logic exists.
"""

import math

import pytest

from catalyst_trader.quant.result import ToolResult


def _field(*args, **kwargs):
    # import inside the helper so collection does not crash before GREEN (field.py absent)
    from catalyst_trader.quant.field import expected_move_field

    return expected_move_field(*args, **kwargs)


def _method(method, magnitude, weight, ref="tool:x#0"):
    return {"method": method, "magnitude": magnitude, "weight": weight, "ref": ref}


_PARAMS = {"field": {"min_methods": 2, "trim_frac": 0.0, "dispersion_wide": 0.5}}


# --------------------------------------------------------- convergence point estimate


def test_given_two_methods_when_equal_weight_then_value_is_weighted_median():
    # weighted median of [0.10, 0.20] w=[1,1]: cumulative crosses half exactly -> average = 0.15
    methods = [_method("analog", 0.10, 1.0), _method("implied", 0.20, 1.0)]
    res = _field(methods, _PARAMS)
    assert isinstance(res, ToolResult)
    assert res.value == pytest.approx(0.15)
    assert res.detail["point_estimate"] == pytest.approx(0.15)


def test_given_low_weight_outlier_when_aggregated_then_it_does_not_drag_the_estimate():
    # cluster {0.10,0.12} heavy, 0.90 light -> weighted median stays in the cluster (0.12),
    # far below the weighted MEAN (~0.268) a naive average would produce.
    methods = [
        _method("analog", 0.10, 2.0),
        _method("base_rate", 0.12, 2.0),
        _method("implied", 0.90, 1.0),
    ]
    res = _field(methods, _PARAMS)
    weighted_mean = (0.10 * 2 + 0.12 * 2 + 0.90 * 1) / 5.0
    assert res.value == pytest.approx(0.12)
    assert res.value < weighted_mean


def test_given_fewer_methods_than_min_when_aggregated_then_raises():
    methods = [_method("analog", 0.10, 1.0)]  # one method < min_methods=2
    with pytest.raises(ValueError):
        _field(methods, _PARAMS)


def test_given_missing_field_params_key_when_aggregated_then_raises_keyerror():
    methods = [_method("analog", 0.10, 1.0), _method("implied", 0.20, 1.0)]
    with pytest.raises(KeyError):
        _field(methods, {})  # no "field" block -> KeyError, no literal fallback


@pytest.mark.parametrize("bad", [-0.01, math.nan, math.inf, -math.inf])
def test_given_bad_magnitude_when_aggregated_then_raises(bad):
    methods = [_method("analog", bad, 1.0), _method("implied", 0.20, 1.0)]
    with pytest.raises(ValueError):
        _field(methods, _PARAMS)


@pytest.mark.parametrize("bad_w", [0.0, -1.0, math.nan, math.inf])
def test_given_bad_weight_when_aggregated_then_raises(bad_w):
    methods = [_method("analog", 0.10, bad_w), _method("implied", 0.20, 1.0)]
    with pytest.raises(ValueError):
        _field(methods, _PARAMS)


def test_value_is_always_a_nonnegative_magnitude():
    methods = [_method("analog", 0.05, 1.0), _method("implied", 0.30, 1.0)]
    res = _field(methods, _PARAMS)
    assert res.value >= 0.0


# --------------------------------------------------------------- dispersion / agreement


def test_detail_carries_full_convergence_contract():
    methods = [
        _method("analog", 0.10, 1.0, ref="tool:catalyst#a"),
        _method("implied", 0.20, 1.0, ref="tool:implied#b"),
    ]
    res = _field(methods, _PARAMS)
    d = res.detail
    for key in (
        "contributions",
        "point_estimate",
        "low",
        "high",
        "dispersion",
        "agreement",
        "n_methods",
        "method_labels",
        "refs",
    ):
        assert key in d, f"missing detail key {key!r}"
    assert d["n_methods"] == 2
    assert d["method_labels"] == ["analog", "implied"]
    assert d["refs"] == ["tool:catalyst#a", "tool:implied#b"]
    assert d["low"] == pytest.approx(0.10)
    assert d["high"] == pytest.approx(0.20)


def test_wide_dispersion_when_methods_disagree_is_flagged_wide():
    # big spread -> CV >= dispersion_wide -> "wide"
    methods = [
        _method("analog", 0.05, 1.0),
        _method("implied", 0.10, 1.0),
        _method("base_rate", 0.80, 1.0),
    ]
    res = _field(methods, _PARAMS)
    assert res.detail["agreement"] == "wide"
    assert res.detail["dispersion"] >= _PARAMS["field"]["dispersion_wide"]


def test_tight_dispersion_when_methods_agree_is_flagged_tight():
    methods = [
        _method("analog", 0.20, 1.0),
        _method("implied", 0.21, 1.0),
        _method("base_rate", 0.22, 1.0),
    ]
    res = _field(methods, _PARAMS)
    assert res.detail["agreement"] == "tight"
    assert res.detail["dispersion"] < _PARAMS["field"]["dispersion_wide"]


# ------------------------------------------------------------------------------- trim


def test_positive_trim_frac_drops_the_symmetric_extremes_before_dispersion():
    # [0.10, 0.12, 0.14, 0.16, 2.0] w=1 each. trim_frac=0.2 removes 0.2*5=1.0 weight per tail
    # -> drops 0.10 (low) and 2.0 (high); survivors {0.12,0.14,0.16}. Median stays robust (0.14)
    # either way, but the surviving-magnitude dispersion collapses once the outlier is trimmed.
    methods = [
        _method("m1", 0.10, 1.0),
        _method("m2", 0.12, 1.0),
        _method("m3", 0.14, 1.0),
        _method("m4", 0.16, 1.0),
        _method("m5", 2.0, 1.0),
    ]
    no_trim = _field(methods, {"field": {"min_methods": 2, "trim_frac": 0.0, "dispersion_wide": 0.5}})
    trimmed = _field(methods, {"field": {"min_methods": 2, "trim_frac": 0.2, "dispersion_wide": 0.5}})
    assert no_trim.value == pytest.approx(0.14)
    assert trimmed.value == pytest.approx(0.14)
    # the outlier is gone from the trimmed convergence zone
    assert trimmed.detail["high"] == pytest.approx(0.16)
    assert trimmed.detail["low"] == pytest.approx(0.12)
    # and the spread collapses because 2.0 no longer counts
    assert trimmed.detail["dispersion"] < no_trim.detail["dispersion"]


# ---------------------------------------------------------------- ToolResult contract


def test_result_is_frozen_toolresult_with_verbatim_inputs():
    methods = [_method("analog", 0.10, 1.0), _method("implied", 0.20, 1.0)]
    res = _field(methods, _PARAMS)
    assert res.tool == "expected_move_field"
    assert res.tool_version == "1.0.0"
    assert res.inputs["methods"] == methods
    assert res.inputs["params"] == _PARAMS
    with pytest.raises(Exception):
        res.value = 0.99  # frozen contract
