"""learn/loop.py (Phase 10) — the weekly learning cycle: judge resolved trades -> propose diffs from the
TRAINING window only -> run each through the gate. It NEVER applies anything: promotion is the separate,
explicit learn.gate step (CONTEXT D1), so a passing diff still waits for the operator.

The shipped proposer is deterministic (grid_proposer): for each TUNABLE knob it tries the bound ends and
midpoint and keeps the best one if it beats the current config's in-sample Sharpe. It only ever sees a
learn.gate.TrainingReplay, so it cannot read a week inside (or embargo-adjacent to) the frozen holdout.
# ponytail: one-knob-at-a-time grid (no joint search) — joint moves multiply gate runs, and each gate
#           run deflates the holdout's DSR bar; upgrade to a joint search only with a bigger holdout.
"""

from __future__ import annotations

import statistics
from datetime import date, timedelta

from catalyst_trader import kb
from catalyst_trader.learn import gate as lg
from catalyst_trader.learn import judge as jd


def _score(rets: list[float]) -> float | None:
    """In-sample per-week Sharpe (mean/stdev); None when undefined."""
    if len(rets) < 2:
        return None
    sd = statistics.stdev(rets)
    return statistics.mean(rets) / sd if sd > 0 else None


def _candidates(key: str, current):
    lo, hi = lg.TUNABLE[key]
    mid = (lo + hi) / 2
    vals = {lo, hi, round(mid) if isinstance(current, int) else mid}
    return sorted(v for v in vals if v != current)


def grid_proposer(train_replay, base_params: dict, *, cutoff: str, lookback_weeks: int = 104,
                  keys=None, min_improvement: float = 0.0) -> list[dict]:
    """One ProposedDiff dict per knob whose best in-sample value beats the current config, best first."""
    start = (date.fromisoformat(cutoff) - timedelta(weeks=lookback_weeks)).isoformat()
    base_score = _score([r for _, r in train_replay(base_params, start, cutoff)])
    if base_score is None:
        return []
    out = []
    for key in keys or lg.TUNABLE:
        cur = base_params
        for p in key.split("."):
            cur = cur[p]
        best = None
        for v in _candidates(key, cur):
            s = _score([r for _, r in train_replay(lg.apply_patch(base_params, {key: v}), start, cutoff)])
            if s is not None and s > base_score + min_improvement and (best is None or s > best[1]):
                best = (v, s)
        if best is not None:
            out.append({"target": "fitted_params:weekly", "patch": {key: best[0]},
                        "rationale": f"in-sample Sharpe {best[1]:.3f} vs current {base_score:.3f} "
                                     f"over {start}..{cutoff}",
                        "evidence": [f"train_replay:{start}..{cutoff}"], "trained_through": cutoff,
                        "_gain": best[1] - base_score})
    out.sort(key=lambda d: d["_gain"], reverse=True)
    for d in out:
        d.pop("_gain")
    return out


def run_learn_cycle(conn, *, replay, golden, benchmark, judge_fn=None, judge_model: str | None = None,
                    proposer=grid_proposer, max_proposals: int = 3, lookback_weeks: int = 104,
                    thresholds: dict = lg.GATE_THRESHOLDS) -> dict:
    """judge -> propose -> evaluate. Returns {judge, proposals, reports, stopped}. Applies nothing."""
    h = lg.active_holdout(conn)
    if h is None:
        raise lg.GateRefused("no frozen holdout — freeze one before running the learning loop")
    judged = (jd.judge_resolved(conn, judge_fn=judge_fn, judge_model=judge_model)
              if judge_fn is not None else None)
    cutoff = lg.training_cutoff(h)
    diffs = proposer(lg.TrainingReplay(replay, cutoff), kb.load_params(conn, "weekly"),
                     cutoff=cutoff, lookback_weeks=lookback_weeks)[:max_proposals]
    report = {"judge": judged, "proposals": [], "reports": [], "stopped": None}
    for d in diffs:
        pid = lg.submit_proposal(conn, d)
        report["proposals"].append(pid)
        try:
            report["reports"].append(lg.evaluate(conn, pid, replay=replay, golden=golden,
                                                 benchmark=benchmark, thresholds=thresholds))
        except lg.GateRefused as exc:  # run budget spent: stop, leave the rest 'proposed'
            report["stopped"] = str(exc)
            break
    return report
