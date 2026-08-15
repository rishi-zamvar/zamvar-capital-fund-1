"""RED-first exhaustive suite for the catalyst-event quant tools (QUANT-02/03, PORT-02/03).

`catalyst_move_estimate` turns historical analog gaps into the signed expected move plus the
SEPARATE up/down magnitudes every downstream tool consumes; it works offline from analogs
alone and treats `implied_move` as a MAGNITUDE prior/clamp only, never a directional signal.
`expected_log_growth` / `hold_vs_exit` implement the Kelly-consistent hold-through-vs-exit
decision the LOCKED <model_forms> mandate — expected-LOG-growth at the survival-constrained f,
NOT raw EV, so a positive-EV hold with a fat down-tail is provably rejected (BLOCKER-2).

Every threshold is read from a params dict — a missing key RAISES; no numeric literal fallback
in any tool body. Same params + inputs in → identical frozen ToolResult out (deterministic,
offline, no DB). Written before the logic exists (module absent = RED).
"""

import math

import pytest

from catalyst_trader.quant.result import ToolResult

# --------------------------------------------------------------- catalyst_move_estimate

# A fully-specified estimator params block; tests remove keys to prove missing-key raises.
PARAMS = {"estimator": {"method": "median", "min_analogs": 4, "implied_blend": 0.5}}


def _estimate(**kw):
    from catalyst_trader.quant.events import catalyst_move_estimate

    return catalyst_move_estimate(**kw)


def test_estimate_signed_ev_from_both_branches_hand_computed():
    # median(up)=0.20, median(down)=0.25; EV = 0.6*0.20 - 0.4*0.25 = 0.02
    res = _estimate(
        p_positive=0.6,
        up_moves=[0.10, 0.20, 0.30],
        down_moves=[0.15, 0.25, 0.35],
        params=PARAMS,
    )
    assert isinstance(res, ToolResult)
    assert res.value == pytest.approx(0.02)
    assert res.detail["up_move"] == pytest.approx(0.20)
    assert res.detail["down_move"] == pytest.approx(0.25)
    assert res.detail["source"] == "analogs"
    assert res.detail["n_up"] == 3
    assert res.detail["n_down"] == 3


def test_estimate_median_is_the_robust_central_estimate():
    # a single outlier must not swing the estimate (median, not mean)
    res = _estimate(
        p_positive=0.5,
        up_moves=[0.10, 0.20, 5.0],  # mean would be 1.77; median is 0.20
        down_moves=[0.10, 0.20, 0.30],
        params=PARAMS,
    )
    assert res.detail["up_move"] == pytest.approx(0.20)


def test_estimate_works_offline_with_no_options_data():
    # NO implied_move supplied — analogs alone are the always-available core
    res = _estimate(
        p_positive=0.55, up_moves=[0.3], down_moves=[0.2], params=PARAMS
    )
    assert res.detail["source"] == "analogs"
    assert res.detail["implied_move"] is None


def test_estimate_implied_move_is_magnitude_prior_blend_not_direction():
    # both branches present + implied prior → blended magnitude (never flips the sign).
    # up = 0.5*0.20 + 0.5*0.40 = 0.30 ; down = 0.5*0.10 + 0.5*0.40 = 0.25
    res = _estimate(
        p_positive=0.6,
        up_moves=[0.20],
        down_moves=[0.10],
        params=PARAMS,
        implied_move=0.40,
    )
    assert res.detail["up_move"] == pytest.approx(0.30)
    assert res.detail["down_move"] == pytest.approx(0.25)
    # EV = 0.6*0.30 - 0.4*0.25 = 0.08
    assert res.value == pytest.approx(0.08)


def test_estimate_implied_prior_never_flips_sign():
    # a huge implied magnitude with a bearish mixture stays negative — prior is magnitude-only
    res = _estimate(
        p_positive=0.2,
        up_moves=[0.10],
        down_moves=[0.10],
        params=PARAMS,
        implied_move=10.0,
    )
    assert res.value < 0  # 0.2*up - 0.8*down with symmetric magnitudes → negative


def test_estimate_empty_branch_falls_back_to_implied_magnitude():
    # up branch empty → up_move = |implied| (fallback); source reflects implied reliance
    res = _estimate(
        p_positive=0.6,
        up_moves=[],
        down_moves=[0.20],
        params=PARAMS,
        implied_move=0.35,
    )
    assert res.detail["up_move"] == pytest.approx(0.35)
    assert res.detail["source"] == "implied_fallback"


def test_estimate_empty_branch_no_implied_raises():
    # no analogs on a side AND no prior → NO silent default
    with pytest.raises(ValueError):
        _estimate(p_positive=0.6, up_moves=[], down_moves=[0.2], params=PARAMS)


def test_estimate_both_empty_no_implied_raises():
    with pytest.raises(ValueError):
        _estimate(p_positive=0.6, up_moves=[], down_moves=[], params=PARAMS)


@pytest.mark.parametrize("bad_p", [float("nan"), -0.1, 1.1, 2.0])
def test_estimate_bad_p_positive_raises(bad_p):
    with pytest.raises(ValueError):
        _estimate(p_positive=bad_p, up_moves=[0.2], down_moves=[0.2], params=PARAMS)


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_estimate_nonfinite_analog_move_raises(bad):
    with pytest.raises(ValueError):
        _estimate(p_positive=0.6, up_moves=[0.2, bad], down_moves=[0.2], params=PARAMS)


def test_estimate_missing_params_min_analogs_key_raises_no_magic_number():
    # a missing threshold must RAISE — never a numeric literal fallback in the body
    bad = {"estimator": {"method": "median"}}  # no min_analogs
    with pytest.raises((KeyError, ValueError)):
        _estimate(p_positive=0.6, up_moves=[0.2], down_moves=[0.2], params=bad)


def test_estimate_missing_params_method_key_raises_no_magic_number():
    bad = {"estimator": {"min_analogs": 4}}  # no method
    with pytest.raises((KeyError, ValueError)):
        _estimate(p_positive=0.6, up_moves=[0.2], down_moves=[0.2], params=bad)


def test_estimate_unknown_method_raises():
    bad = {"estimator": {"method": "mean", "min_analogs": 4}}
    with pytest.raises(ValueError):
        _estimate(p_positive=0.6, up_moves=[0.2], down_moves=[0.2], params=bad)


def test_estimate_missing_implied_blend_when_prior_used_raises():
    # supplying an implied prior requires the blend weight — no literal default
    bad = {"estimator": {"method": "median", "min_analogs": 4}}  # no implied_blend
    with pytest.raises((KeyError, ValueError)):
        _estimate(
            p_positive=0.6,
            up_moves=[0.2],
            down_moves=[0.2],
            params=bad,
            implied_move=0.3,
        )


def test_estimate_cold_start_flag_when_below_min_analogs():
    # n_up + n_down = 2 < min_analogs (4) → cold_start True (gate widens uncertainty)
    res = _estimate(
        p_positive=0.6, up_moves=[0.2], down_moves=[0.2], params=PARAMS
    )
    assert res.detail["cold_start"] is True


def test_estimate_not_cold_start_when_enough_analogs():
    res = _estimate(
        p_positive=0.6,
        up_moves=[0.2, 0.3],
        down_moves=[0.2, 0.3],
        params=PARAMS,
    )
    assert res.detail["cold_start"] is False


def test_estimate_deterministic_same_inputs_same_result():
    a = _estimate(p_positive=0.6, up_moves=[0.2, 0.3], down_moves=[0.1], params=PARAMS)
    b = _estimate(p_positive=0.6, up_moves=[0.2, 0.3], down_moves=[0.1], params=PARAMS)
    assert a.value == b.value
    assert a.detail == b.detail


def test_estimate_inputs_snapshot_is_verbatim():  # QUANT-03
    res = _estimate(
        p_positive=0.6, up_moves=[0.2], down_moves=[0.1], params=PARAMS, implied_move=0.3
    )
    assert res.inputs["p_positive"] == 0.6
    assert res.inputs["up_moves"] == [0.2]
    assert res.inputs["down_moves"] == [0.1]
    assert res.inputs["implied_move"] == 0.3
    assert res.inputs["params"] == PARAMS
