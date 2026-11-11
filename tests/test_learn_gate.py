"""Phase 10 LEARN-02: the promotion gate — frozen holdout, training-only proposals, golden-set regression
replay + guardrail + walk-forward evals, and the single promotion path into kb.load_params.

Offline: the gate logic runs against a deterministic STUB replay (a pure function of the params), and one
integration test runs the REAL Layer-A replay (run_layer_a) over tests/synth_history.
The bypass attempts live in tests/test_learn_gate_adversarial.py.
"""

import copy
import hashlib
from datetime import date, timedelta

import pytest

from catalyst_trader import db as _db
from catalyst_trader import kb
from catalyst_trader.learn import gate as lg
from catalyst_trader.store import upsert_bars

from tests.synth_history import seed_history, week_ends

WEEKS = week_ends(60)
H_START, H_END = WEEKS[40], WEEKS[59]          # 20-week frozen holdout
GOLDEN = [{"id": "g1", "start": WEEKS[10], "end": WEEKS[20], "note": "test window"}]


def _noise(tag: str, w: str, scale=0.01) -> float:
    h = int(hashlib.sha256(f"{tag}{w}".encode()).hexdigest()[:8], 16)
    return (h / 0xFFFFFFFF - 0.5) * 2 * scale


def stub_replay(calls=None):
    """Week book returns = noise + 0.002 * (shortlist_k - 4) + 0.002 * (cost_mult - 2): raising either
    knob helps in every week (a pure function of the params — the gate logic is what's under test)."""
    def fn(params, start, end):
        if calls is not None:
            calls.append((start, end))
        k, c = params["weekly"]["shortlist_k"], params["weekly"]["cost_mult"]
        return [(w, 0.002 + _noise("r", w) + 0.002 * (k - 4) + 0.002 * (c - 2))
                for w in WEEKS if start <= w <= end]
    return fn


def stub_bench(weeks):
    return [_noise("x", w, 0.02) for w in weeks]


def _conn():
    conn = _db.connect(":memory:")
    _db.migrate(conn)
    seed_history(conn, tickers=["XBI", "AAAA"], weeks=60)
    return conn


def _frozen():
    conn = _conn()
    hid = lg.freeze_holdout(conn, start=H_START, end=H_END, embargo_days=7, name="test")
    return conn, hid


def _diff(patch=None, **kw):
    d = {"target": "fitted_params:weekly", "patch": patch or {"weekly.shortlist_k": 6},
         "rationale": "in-sample improvement", "evidence": [f"train_replay:{WEEKS[0]}..{WEEKS[30]}"],
         "trained_through": WEEKS[30]}
    d.update(kw)
    return d


def _evaluate(conn, pid, **kw):
    kw.setdefault("replay", stub_replay())
    kw.setdefault("golden", GOLDEN)
    kw.setdefault("benchmark", stub_bench)
    return lg.evaluate(conn, pid, **kw)


def passed_proposal(conn=None, patch=None):
    if conn is None:
        conn, _ = _frozen()
    pid = lg.submit_proposal(conn, _diff(patch))
    rep = _evaluate(conn, pid)
    assert rep["passed"], rep["reasons"]
    return conn, pid


# ====================================================================== patch + bounds


def test_given_patch_when_applied_then_deep_copy_with_dotted_paths_set():
    base = copy.deepcopy(kb.BOOTSTRAP_DEFAULT)
    out = lg.apply_patch(base, {"weekly.shortlist_k": 5})
    assert out["weekly"]["shortlist_k"] == 5 and base["weekly"]["shortlist_k"] == 4


def test_given_unknown_path_when_applied_then_raises():
    with pytest.raises(KeyError):
        lg.apply_patch(kb.BOOTSTRAP_DEFAULT, {"weekly.nope": 1})


@pytest.mark.parametrize("patch,needle", [
    ({"weekly.hard_veto_drop": -0.30}, "not tunable"),        # safety knob
    ({"weekly.binary_gap_default": 0.1}, "not tunable"),
    ({"weekly.edge_min_pts": 0.01}, "out of bounds"),          # loosening the tradeability bar
    ({"weekly.min_effective_n": 10}, "out of bounds"),
    ({"weekly.shortlist_k": 4.5}, "type"),                     # int knob must stay int
    ({"weekly.shrink_prior_weight": float("nan")}, "finite"),
    ({}, "empty"),
])
def test_given_bad_patch_when_checked_then_named(patch, needle):
    reasons = lg.check_patch("fitted_params:weekly", patch, kb.BOOTSTRAP_DEFAULT)
    assert any(needle in r for r in reasons), reasons


def test_given_patch_equal_to_current_when_checked_then_no_op_named():
    assert any("no-op" in r for r in lg.check_patch(
        "fitted_params:weekly", {"weekly.shortlist_k": 4}, kb.BOOTSTRAP_DEFAULT))


def test_tunable_surface_only_tightens_the_tradeability_bar():
    w = kb.BOOTSTRAP_DEFAULT["weekly"]
    for key in ("edge_min_pts", "min_effective_n", "cost_mult"):
        assert lg.TUNABLE[f"weekly.{key}"][0] == w[key]
    for safety in ("hard_veto_drop", "binary_gap_default", "binary_gap_percentile", "roundtrip_cost",
                   "defensive_max_frac", "anchor", "beta_window_weeks"):
        assert f"weekly.{safety}" not in lg.TUNABLE


def test_trigger_seed_tier_matches_kb_seed_confidence():
    assert lg.SEED_CONFIDENCE == kb._SEED_CONFIDENCE == 0.3


# ====================================================================== frozen holdout


def test_given_holdout_when_frozen_then_manifest_covers_window_weeks():
    conn, hid = _frozen()
    h = lg.active_holdout(conn)
    assert h["id"] == hid and h["manifest"]["weeks"] == WEEKS[40:60]
    assert lg.holdout_sha(conn, h) == h["manifest_sha"]


def test_given_inverted_or_empty_window_when_frozen_then_refused():
    conn = _conn()
    with pytest.raises(ValueError):
        lg.freeze_holdout(conn, start=H_END, end=H_START)
    with pytest.raises(ValueError):
        lg.freeze_holdout(conn, start="2030-01-01", end="2030-06-01")  # no bars in window


def test_given_frozen_holdout_when_a_bar_in_window_is_revised_then_sha_drifts():
    conn, _ = _frozen()
    h = lg.active_holdout(conn)
    upsert_bars(conn, "AAAA", [{"week_end": WEEKS[45], "open": 1, "high": 1, "low": 1, "close": 1,
                               "volume": 1}])
    assert lg.holdout_sha(conn, h) != h["manifest_sha"]


def test_training_cutoff_clears_the_hold_week_and_embargo():
    conn, _ = _frozen()
    cut = lg.training_cutoff(lg.active_holdout(conn))
    assert cut == (date.fromisoformat(H_START) - timedelta(days=14)).isoformat()


def test_given_training_replay_when_window_ends_inside_embargo_or_holdout_then_leak_raised():
    conn, _ = _frozen()
    cut = lg.training_cutoff(lg.active_holdout(conn))
    tr = lg.TrainingReplay(stub_replay(), cut)
    assert tr(kb.BOOTSTRAP_DEFAULT, WEEKS[0], cut)  # ok up to the cutoff
    for end in ((date.fromisoformat(cut) + timedelta(days=1)).isoformat(), H_START, H_END):
        with pytest.raises(lg.HoldoutLeak):
            tr(kb.BOOTSTRAP_DEFAULT, WEEKS[0], end)


# ====================================================================== proposals


def test_given_valid_diff_when_submitted_then_stored_proposed_with_shas():
    conn, hid = _frozen()
    pid = lg.submit_proposal(conn, _diff())
    row = conn.execute("SELECT * FROM learn_proposal WHERE id=?", (pid,)).fetchone()
    assert row["status"] == "proposed" and row["holdout_id"] == hid
    assert row["base_sha"] == lg.sha(kb.load_params(conn, "weekly"))
    assert row["content_sha"] == lg.proposal_sha(row)


def test_given_no_frozen_holdout_when_submitted_then_refused():
    conn = _conn()
    with pytest.raises(lg.GateRefused):
        lg.submit_proposal(conn, _diff())


def test_given_trained_through_after_cutoff_when_submitted_then_leak():
    conn, _ = _frozen()
    with pytest.raises(lg.HoldoutLeak):
        lg.submit_proposal(conn, _diff(trained_through=WEEKS[39]))


def test_given_out_of_bounds_diff_when_submitted_then_rejected():
    conn, _ = _frozen()
    with pytest.raises(ValueError, match="out of bounds"):
        lg.submit_proposal(conn, _diff({"weekly.shortlist_k": 60}))


# ====================================================================== evaluate


def test_given_dominating_diff_when_evaluated_then_passes_every_check_and_records_run():
    conn, hid = _frozen()
    pid = lg.submit_proposal(conn, _diff())
    rep = _evaluate(conn, pid)
    assert rep["passed"] and rep["reasons"] == []
    for section in ("golden", "walk_forward", "guardrails"):
        assert section in rep
    assert rep["walk_forward"]["folds_won"] == 3 and rep["walk_forward"]["n_trials"] == 1
    run = conn.execute("SELECT * FROM learn_gate_run WHERE proposal_id=?", (pid,)).fetchone()
    assert run["passed"] == 1 and run["holdout_id"] == hid
    assert run["golden_sha"] == lg.sha(GOLDEN)
    assert conn.execute("SELECT status FROM learn_proposal WHERE id=?", (pid,)).fetchone()[0] == "passed"


def test_given_harmful_diff_when_evaluated_then_fails_naming_folds_alpha_and_golden():
    conn, _ = _frozen()
    pid = lg.submit_proposal(conn, _diff({"weekly.shortlist_k": 1}))
    rep = _evaluate(conn, pid)
    assert not rep["passed"]
    joined = " | ".join(rep["reasons"])
    assert "folds" in joined and "alpha" in joined and "golden regression g1" in joined
    assert conn.execute("SELECT status FROM learn_proposal WHERE id=?", (pid,)).fetchone()[0] == "failed"


def test_given_empty_golden_set_when_evaluated_then_fails_closed():
    conn, _ = _frozen()
    rep = _evaluate(conn, lg.submit_proposal(conn, _diff()), golden=[])
    assert not rep["passed"] and any("golden set is empty" in r for r in rep["reasons"])


def test_given_non_replayable_target_when_evaluated_then_fails_closed_without_replaying():
    conn, _ = _frozen()
    calls = []
    pid = lg.submit_proposal(conn, _diff({"estimator.min_analogs": 7}, target="fitted_params:pdufa"))
    rep = _evaluate(conn, pid, replay=stub_replay(calls))
    assert not rep["passed"] and any("no deterministic replay" in r for r in rep["reasons"])
    assert calls == []


def test_given_short_holdout_when_evaluated_then_fails_on_weeks():
    conn = _conn()
    lg.freeze_holdout(conn, start=WEEKS[50], end=WEEKS[59])  # 10 weeks < 12
    rep = _evaluate(conn, lg.submit_proposal(conn, _diff()))
    assert any("holdout weeks" in r for r in rep["reasons"])


def test_given_deeper_drawdown_when_evaluated_then_guardrail_fails():
    conn, _ = _frozen()

    def crashy(params, start, end):
        k = params["weekly"]["shortlist_k"]
        out = stub_replay()(params, start, end)
        if k == 6:  # patched: wins most weeks but takes a -30% hit once
            out = [(w, r + 0.01) for w, r in out]
            out[len(out) // 2] = (out[len(out) // 2][0], -0.30)
        return out
    rep = _evaluate(conn, lg.submit_proposal(conn, _diff()), replay=crashy)
    assert not rep["passed"] and any("max_drawdown" in r for r in rep["reasons"])


def test_given_unavailable_benchmark_when_evaluated_then_alpha_fails_named():
    conn, _ = _frozen()
    rep = _evaluate(conn, lg.submit_proposal(conn, _diff()), benchmark=lambda weeks: None)
    assert not rep["passed"] and any("benchmark unavailable" in r for r in rep["reasons"])


def test_given_repeated_gate_runs_when_evaluated_then_n_trials_deflates_and_budget_caps():
    conn, _ = _frozen()
    th = dict(lg.GATE_THRESHOLDS, max_gate_runs=3)
    for i in range(3):
        rep = _evaluate(conn, lg.submit_proposal(conn, _diff({"weekly.shortlist_k": 5 + i % 2})),
                        thresholds=th)
        assert rep["walk_forward"]["n_trials"] == i + 1
    with pytest.raises(lg.GateRefused, match="budget"):
        _evaluate(conn, lg.submit_proposal(conn, _diff()), thresholds=th)


def test_given_money_path_moved_since_proposal_when_evaluated_then_stale():
    conn, _ = _frozen()
    pid = lg.submit_proposal(conn, _diff())
    _c2, other = passed_proposal(conn, {"weekly.cost_mult": 3})
    lg.promote(conn, other)
    rep = _evaluate(conn, pid)
    assert not rep["passed"] and any("stale" in r for r in rep["reasons"])


# ====================================================================== promote


def test_given_passed_proposal_when_promoted_then_load_params_returns_patched():
    conn, pid = passed_proposal()
    before = kb.load_params(conn, "weekly")
    nid = lg.promote(conn, pid)
    after = kb.load_params(conn, "weekly")
    assert after["weekly"]["shortlist_k"] == 6 and before["weekly"]["shortlist_k"] == 4
    assert {k: v for k, v in after["weekly"].items() if k != "shortlist_k"} == \
           {k: v for k, v in before["weekly"].items() if k != "shortlist_k"}
    node = kb.get_node(conn, nid)
    assert node["confidence"] == pytest.approx(0.3 + 0.7 / 10)
    assert node["attrs"]["learn_promotion_id"]
    promo = conn.execute("SELECT * FROM learn_promotion").fetchone()
    assert promo["status"] == "applied" and promo["playbook_node_id"] == nid
    assert conn.execute("SELECT status FROM learn_proposal WHERE id=?", (pid,)).fetchone()[0] == "promoted"
    cites = conn.execute("SELECT COUNT(*) FROM kb_edge WHERE src_id=? AND rel='CITES'", (nid,)).fetchone()[0]
    assert cites == 1  # cite-or-drop: it cites its gate run


def test_given_two_promotions_when_promoted_then_confidence_strictly_increases_below_one():
    conn, p1 = passed_proposal()
    n1 = lg.promote(conn, p1)
    _, p2 = passed_proposal(conn, {"weekly.cost_mult": 3})
    n2 = lg.promote(conn, p2)
    c1, c2 = kb.get_node(conn, n1)["confidence"], kb.get_node(conn, n2)["confidence"]
    assert c1 < c2 < 1.0
    assert kb.load_params(conn, "weekly")["weekly"]["cost_mult"] == 3


def test_query_playbooks_breaks_confidence_ties_by_first_written():
    conn = _conn()
    ev = [kb.EvidenceSource(url="https://x", retrieved_at="2026-01-01", snippet_hash="a")]
    kb.insert_playbook(conn, "fitted_params:pdufa", "first", {"v": 1}, 0.3, ev)
    kb.insert_playbook(conn, "fitted_params:pdufa", "second", {"v": 2}, 0.3, ev)
    assert kb.load_params(conn, "pdufa") == {"v": 1}


# ====================================================================== real Layer-A plumbing


def test_given_real_layer_a_replay_when_evaluated_then_report_is_complete_and_leak_free():
    conn = _db.connect(":memory:")
    _db.migrate(conn)
    weeks = week_ends(40)
    seed_history(conn, tickers=["XBI", "AAAA", "BBBB", "CAT"], weeks=40,
                 catalysts=[{"ticker": "CAT", "event_date": weeks[32]}])
    lg.freeze_holdout(conn, start=weeks[25], end=weeks[39])
    pid = lg.submit_proposal(conn, {
        "target": "fitted_params:weekly", "patch": {"weekly.shortlist_k": 2}, "rationale": "r",
        "evidence": ["train"], "trained_through": weeks[20]})
    replay = lg.layer_a_replay(conn)
    rets = replay(kb.load_params(conn, "weekly"), weeks[25], weeks[39])
    assert rets and all(w >= weeks[25] for w, _ in rets)
    rep = lg.evaluate(conn, pid, replay=replay, golden=[{"id": "g", "start": weeks[5], "end": weeks[10]}],
                      benchmark=lg.xbi_benchmark(conn))
    assert isinstance(rep["passed"], bool)
    assert rep["walk_forward"]["n_weeks"] == len(rets)
    assert conn.execute("SELECT COUNT(*) FROM learn_gate_run").fetchone()[0] == 1


def test_given_xbi_bars_when_benchmark_then_one_return_per_week_or_none():
    conn = _conn()
    bench = lg.xbi_benchmark(conn)
    out = bench(WEEKS[10:13])
    assert len(out) == 3 and all(isinstance(x, float) for x in out)
    assert bench(["2031-01-06"]) is None
