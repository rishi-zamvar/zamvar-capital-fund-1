"""Offline math tests for the before/after retrieval stress harness (quick-260818-l64 Task 3).

Only the two PURE helpers are the tested surface — the live wiring (connect, analog_query) lives in
main() and is the Task-4 operator step. No DB here.
"""

from scripts.retrieval_stress import _aggregate, _overlap


def test_overlap_disjoint_partial_identical():
    assert _overlap(["a", "b"], ["c", "d"]) == 0
    assert _overlap(["a", "b"], ["a", "c"]) == 1
    assert _overlap(["a", "b"], ["a", "b"]) == 2
    assert _overlap([], ["a"]) == 0  # empty query -> no overlap


def test_aggregate_after_beats_before_when_sibling_added():
    # one cid: query = {A,B}. BEFORE retrieves {A} and {C} -> overlaps [1,0] mean 0.5.
    # AFTER retrieves {A,B} and {C} -> overlaps [2,0] mean 1.0. after > before, n=1.
    per_cid = [{
        "cid": 221,
        "query_setups": ["A", "B"],
        "before": [{"setups": ["A"]}, {"setups": ["C"]}],
        "after": [{"setups": ["A", "B"]}, {"setups": ["C"]}],
    }]
    agg = _aggregate(per_cid)
    assert agg["n"] == 1
    assert agg["mean_overlap_before"] == 0.5
    assert agg["mean_overlap_after"] == 1.0
    assert agg["mean_overlap_after"] > agg["mean_overlap_before"]


def test_aggregate_averages_across_cids_and_handles_empty_results():
    per_cid = [
        {"cid": 1, "query_setups": ["A"], "before": [{"setups": ["A"]}], "after": [{"setups": ["A"]}]},
        {"cid": 2, "query_setups": ["A"], "before": [], "after": [{"setups": ["A"]}]},
    ]
    agg = _aggregate(per_cid)
    assert agg["n"] == 2
    assert agg["mean_overlap_before"] == 0.5   # (1.0 + 0.0) / 2
    assert agg["mean_overlap_after"] == 1.0     # (1.0 + 1.0) / 2
