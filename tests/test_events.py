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


# ------------------------------------------------------------------ expected_log_growth


def _elg(**kw):
    from catalyst_trader.quant.events import expected_log_growth

    return expected_log_growth(**kw)


def _hve(**kw):
    from catalyst_trader.quant.events import hold_vs_exit

    return hold_vs_exit(**kw)


def test_log_growth_hand_computed():
    # 0.5*log(1+1*1.0) + 0.5*log(1+1*0.0) = 0.5*log(2) + 0 = 0.34657
    res = _elg(f=1.0, outcomes=[(0.5, 1.0), (0.5, 0.0)])
    assert isinstance(res, ToolResult)
    assert res.value == pytest.approx(0.5 * math.log(2.0))


def test_log_growth_fair_bet_is_zero_growth():
    # 0.5*log(2) + 0.5*log(0.5) = 0 — the classic no-growth double-or-halve
    res = _elg(f=1.0, outcomes=[(0.5, 1.0), (0.5, -0.5)])
    assert res.value == pytest.approx(0.0, abs=1e-12)


def test_log_growth_f_nonpositive_raises():
    for bad_f in (0.0, -0.5):
        with pytest.raises(ValueError):
            _elg(f=bad_f, outcomes=[(0.5, 1.0), (0.5, -0.5)])


def test_log_growth_probs_must_sum_to_one():
    with pytest.raises(ValueError):
        _elg(f=1.0, outcomes=[(0.5, 0.1), (0.4, 0.1)])  # sums to 0.9


def test_log_growth_nonsurvivable_size_raises_never_silent_neg_inf():
    # 1 + f*ret <= 0 is a sizing bug — must RAISE, never return a silent -inf
    with pytest.raises(ValueError):
        _elg(f=2.0, outcomes=[(0.6, 1.0), (0.4, -0.7)])  # 1 + 2*(-0.7) = -0.4


@pytest.mark.parametrize("bad_p", [float("nan"), -0.1, 1.1])
def test_log_growth_bad_prob_raises(bad_p):
    with pytest.raises(ValueError):
        _elg(f=1.0, outcomes=[(bad_p, 0.1), (1.0 - bad_p, 0.1)])


def test_log_growth_deterministic():
    a = _elg(f=0.5, outcomes=[(0.6, 0.2), (0.4, -0.1)])
    b = _elg(f=0.5, outcomes=[(0.6, 0.2), (0.4, -0.1)])
    assert a.value == b.value


# ---------------------------------------------------------------------- hold_vs_exit


def test_hold_vs_exit_positive_ev_but_tail_favors_exit():
    # THE CRUX (BLOCKER-2): hold has POSITIVE raw EV that EXCEEDS the run-up EV, yet the
    # fat -70% down-tail makes expected-LOG-growth favor EXIT → decision must be 0.0.
    f = 1.0
    hold = [(0.6, 1.0), (0.4, -0.7)]  # raw EV = 0.6 - 0.28 = +0.32
    exit_ = [(0.6, 0.05), (0.4, -0.02)]  # raw EV = 0.03 - 0.008 = +0.022
    raw_ev_hold = sum(p * r for p, r in hold)
    raw_ev_exit = sum(p * r for p, r in exit_)
    assert raw_ev_hold > 0 and raw_ev_hold > raw_ev_exit  # raw EV would say HOLD

    res = _hve(f=f, hold_outcomes=hold, exit_outcomes=exit_)
    assert res.value == 0.0  # log-growth says EXIT — the tail penalty fired
    assert res.detail["decision"] == "exit"
    assert res.detail["g_hold"] < res.detail["g_exit"]


def test_hold_vs_exit_confident_asymmetric_payoff_holds():
    # a confident, asymmetric-in-our-favor payoff → HOLD wins on log-growth too
    res = _hve(
        f=0.5,
        hold_outcomes=[(0.8, 0.5), (0.2, -0.2)],
        exit_outcomes=[(0.6, 0.03), (0.4, -0.01)],
    )
    assert res.value == 1.0
    assert res.detail["decision"] == "hold"
    assert res.detail["g_hold"] > res.detail["g_exit"]


def test_hold_vs_exit_margin_requires_a_clear_edge_to_hold():
    # a positive but tiny hold edge is suppressed once a margin is demanded
    hold = [(0.55, 0.10), (0.45, -0.08)]
    exit_ = [(0.55, 0.09), (0.45, -0.08)]
    base = _hve(f=0.5, hold_outcomes=hold, exit_outcomes=exit_)
    gated = _hve(f=0.5, hold_outcomes=hold, exit_outcomes=exit_, margin=1.0)
    assert base.value == 1.0  # hold marginally better with no margin
    assert gated.value == 0.0  # a large required margin flips it to exit


def test_hold_vs_exit_nonsurvivable_size_raises():
    with pytest.raises(ValueError):
        _hve(
            f=2.0,
            hold_outcomes=[(0.6, 1.0), (0.4, -0.7)],  # 1 + 2*(-0.7) < 0
            exit_outcomes=[(0.6, 0.05), (0.4, -0.02)],
        )


def test_hold_vs_exit_deterministic():
    kw = dict(
        f=0.5,
        hold_outcomes=[(0.6, 0.3), (0.4, -0.2)],
        exit_outcomes=[(0.6, 0.05), (0.4, -0.02)],
    )
    assert _hve(**kw).value == _hve(**kw).value


def test_hold_vs_exit_inputs_snapshot():  # QUANT-03
    res = _hve(
        f=0.5,
        hold_outcomes=[(0.6, 0.3), (0.4, -0.2)],
        exit_outcomes=[(0.6, 0.05), (0.4, -0.02)],
        margin=0.01,
    )
    assert res.inputs["f"] == 0.5
    assert res.inputs["margin"] == 0.01
    assert res.inputs["hold_outcomes"] == [(0.6, 0.3), (0.4, -0.2)]
