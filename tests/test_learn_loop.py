"""Phase 10: the weekly learning loop — resolved trade -> judge -> proposals (TRAINING window only) ->
gate. The loop never promotes; promotion stays an explicit step (CONTEXT D1). Fully offline (stub replay
+ stub judge from the gate/judge test modules)."""

import inspect
from datetime import date

import pytest

from catalyst_trader import kb
from catalyst_trader.learn import gate as lg
from catalyst_trader.learn import loop as ll

from tests.test_learn_gate import GOLDEN, _conn, _frozen, stub_bench, stub_replay
from tests.test_learn_judge import _resolved, _verdict


def _train(calls=None):
    conn, _ = _frozen()
    cut = lg.training_cutoff(lg.active_holdout(conn))
    return conn, cut, lg.TrainingReplay(stub_replay(calls), cut)


def test_given_spy_replay_when_grid_proposes_then_every_window_ends_by_the_cutoff():
    calls = []
    conn, cut, tr = _train(calls)
    ll.grid_proposer(tr, kb.load_params(conn, "weekly"), cutoff=cut, lookback_weeks=30)
    assert calls and all(end <= cut and start <= cut for start, end in calls)


def test_given_improvable_knobs_when_grid_proposes_then_whitelisted_in_bounds_improvements():
    conn, cut, tr = _train()
    base = kb.load_params(conn, "weekly")
    diffs = ll.grid_proposer(tr, base, cutoff=cut, lookback_weeks=30)
    assert diffs
    keys = set()
    for d in diffs:
        assert d["target"] == "fitted_params:weekly" and d["trained_through"] == cut
        assert lg.check_patch(d["target"], d["patch"], base) == []
        keys |= set(d["patch"])
    assert keys <= {"weekly.shortlist_k", "weekly.cost_mult"}  # only knobs the stub rewards
    assert {"weekly.shortlist_k": 6} in [d["patch"] for d in diffs]


def test_given_no_knob_helps_when_grid_proposes_then_nothing():
    conn, cut, _ = _train()
    flat = lg.TrainingReplay(lambda p, s, e: [("w1", 0.01), ("w2", -0.01), ("w3", 0.0)], cut)
    assert ll.grid_proposer(flat, kb.load_params(conn, "weekly"), cutoff=cut) == []


def test_given_frozen_holdout_when_cycle_runs_then_judges_proposes_evaluates_and_never_promotes():
    conn, _ = _frozen()
    _resolved(conn)
    before = kb.load_params(conn, "weekly")
    rep = ll.run_learn_cycle(conn, replay=stub_replay(), golden=GOLDEN, benchmark=stub_bench,
                             judge_fn=lambda p: _verdict(), judge_model="stub", lookback_weeks=30)
    assert rep["judge"]["judged"] == 1
    assert rep["proposals"] and len(rep["reports"]) == len(rep["proposals"])
    assert any(r["passed"] for r in rep["reports"])            # a proposal PASSED the gate ...
    assert conn.execute("SELECT COUNT(*) FROM learn_promotion").fetchone()[0] == 0
    assert kb.load_params(conn, "weekly") == before            # ... and still did NOT reach the money path


def test_given_no_holdout_when_cycle_runs_then_refused_and_nothing_proposed():
    conn = _conn()
    with pytest.raises(lg.GateRefused):
        ll.run_learn_cycle(conn, replay=stub_replay(), golden=GOLDEN, benchmark=stub_bench)
    assert conn.execute("SELECT COUNT(*) FROM learn_proposal").fetchone()[0] == 0


def test_given_budget_exhausted_mid_cycle_when_cycle_runs_then_stops_cleanly():
    conn, _ = _frozen()
    th = dict(lg.GATE_THRESHOLDS, max_gate_runs=1)
    rep = ll.run_learn_cycle(conn, replay=stub_replay(), golden=GOLDEN, benchmark=stub_bench,
                             thresholds=th, lookback_weeks=30)
    assert len(rep["reports"]) == 1 and rep["stopped"] and "budget" in rep["stopped"]


def test_loop_module_never_promotes():
    assert "promote(" not in inspect.getsource(ll)


@pytest.mark.xfail(strict=True, reason="DEFERRED: LLM proposer (reads judge rationales + post-mortems "
                   "from the TRAINING window only, emits ProposedDiff). Deferred wiring ships as xfail.")
def test_given_judged_training_cases_when_llm_proposer_runs_then_diffs_are_proposed():
    assert hasattr(ll, "llm_proposer")
