"""RED-first suite for the tunable biotech rubric (FRAME-01/02, QUANT-03, OPS-04).

Weights are DATA (data/rubric_weights.json) the Phase-10 learning loop rewrites — so the
loader must reject a corrupt file (Σ≠1, missing key, negative/out-of-range weight) before it
can poison a score, and editing the file must change the composite with no code change.
Written before rubric.py exists (module absent = RED).
"""

import json

import pytest

from catalyst_trader.quant.result import ToolResult
from catalyst_trader.quant.rubric import load_weights, score_rubric

# The 8 factor keys (FRAME-01) — a full, valid factor_scores payload for happy-path tests.
_ALL_FACTORS = {
    "pos": 8.0,
    "cash_runway": 6.0,
    "trial_design": 7.0,
    "endpoint_credibility": 5.0,
    "regulatory_precedent": 9.0,
    "pipeline_concentration": 4.0,
    "management": 6.0,
    "commercial": 5.0,
}


def _write_weights(path, weights, version=1):
    path.write_text(json.dumps({"version": version, "weights": weights}))
    return path


# --------------------------------------------------------------------- load_weights


def test_load_weights_real_file_sums_to_one():
    w = load_weights()  # the shipped data/rubric_weights.json
    assert abs(sum(w["weights"].values()) - 1.0) < 1e-6
    assert len(w["weights"]) == 8


def test_load_weights_rejects_sum_not_one(tmp_path):
    bad = _write_weights(tmp_path / "w.json", {k: 0.9 / 8 for k in _ALL_FACTORS})
    with pytest.raises(ValueError):
        load_weights(bad)


def test_load_weights_rejects_missing_factor(tmp_path):
    weights = {k: v for k, v in {**{k: 0.125 for k in _ALL_FACTORS}}.items()}
    del weights["commercial"]  # 7 keys, would sum to 0.875 and be missing a factor
    bad = _write_weights(tmp_path / "w.json", weights)
    with pytest.raises(ValueError):
        load_weights(bad)


def test_load_weights_rejects_negative_weight(tmp_path):
    # plan-checker addendum: the learning loop rewrites this file; a negative weight would
    # produce a nonsensical score even if the row happens to sum to 1.0.
    weights = {k: v for k, v in zip(_ALL_FACTORS, [0.40, 0.30, 0.20, 0.15, 0.13, 0.12, -0.10, -0.20])}
    assert abs(sum(weights.values()) - 1.0) < 1e-6  # sums to 1.0 but has negatives
    bad = _write_weights(tmp_path / "w.json", weights)
    with pytest.raises(ValueError):
        load_weights(bad)


def test_load_weights_rejects_weight_above_one(tmp_path):
    weights = {k: v for k, v in zip(_ALL_FACTORS, [1.20, 0.10, 0.10, -0.10, -0.10, -0.10, -0.05, -0.05])}
    assert abs(sum(weights.values()) - 1.0) < 1e-6
    bad = _write_weights(tmp_path / "w.json", weights)
    with pytest.raises(ValueError):
        load_weights(bad)


# --------------------------------------------------------------------- score_rubric


def test_score_rubric_happy_composite_in_range():
    res = score_rubric(_ALL_FACTORS)
    assert isinstance(res, ToolResult)
    assert 0.0 <= res.value <= 100.0
    # detail surfaces the PoS factor separately (dominant driver of a binary)
    assert res.detail["pos_factor"] == _ALL_FACTORS["pos"]
    assert res.detail["weights_version"] == 1


def test_score_rubric_all_tens_is_one_hundred():
    res = score_rubric({k: 10.0 for k in _ALL_FACTORS})
    assert res.value == pytest.approx(100.0)


def test_score_rubric_all_zeros_is_zero():
    res = score_rubric({k: 0.0 for k in _ALL_FACTORS})
    assert res.value == pytest.approx(0.0)


def test_score_rubric_rejects_missing_factor():
    scores = {k: 5.0 for k in _ALL_FACTORS}
    del scores["pos"]
    with pytest.raises(ValueError):
        score_rubric(scores)


def test_score_rubric_rejects_unknown_factor():
    scores = {**{k: 5.0 for k in _ALL_FACTORS}, "extra_bogus": 5.0}
    with pytest.raises(ValueError):
        score_rubric(scores)


def test_score_rubric_rejects_score_above_ten():
    scores = {**{k: 5.0 for k in _ALL_FACTORS}, "pos": 11.0}
    with pytest.raises(ValueError):
        score_rubric(scores)


def test_score_rubric_rejects_negative_score():
    scores = {**{k: 5.0 for k in _ALL_FACTORS}, "pos": -1.0}
    with pytest.raises(ValueError):
        score_rubric(scores)


def test_score_rubric_records_inputs_snapshot():
    # QUANT-03: the emitted result carries the exact call args verbatim.
    res = score_rubric(_ALL_FACTORS)
    assert res.inputs["factor_scores"] == _ALL_FACTORS


def test_score_rubric_tunable_via_file(tmp_path):
    # FRAME-02: editing the weights file changes the score with NO code change.
    base = {k: v for k, v in zip(_ALL_FACTORS, [0.20, 0.15, 0.15, 0.12, 0.12, 0.10, 0.08, 0.08])}
    # bump pos, cut commercial by the same amount → still Σ=1.0
    bumped = {**base, "pos": 0.28, "commercial": 0.0}
    assert abs(sum(bumped.values()) - 1.0) < 1e-6

    w_base = load_weights(_write_weights(tmp_path / "base.json", base))
    w_bumped = load_weights(_write_weights(tmp_path / "bumped.json", bumped))

    scores = {**_ALL_FACTORS, "pos": 10.0, "commercial": 0.0}  # make the reweighting bite
    r1 = score_rubric(scores, weights=w_base)
    r2 = score_rubric(scores, weights=w_bumped)
    assert r1.value != r2.value  # weights are data — file edit moved the score
