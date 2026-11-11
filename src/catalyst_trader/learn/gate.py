"""learn/gate.py (Phase 10, LEARN-02) — the ONLY way a config/playbook diff reaches the money path.

The money path reads every tunable number through kb.load_params (the top-confidence fitted_params:<type>
playbook). A diff is a dotted-path patch over that strategy dict. Its life:

    freeze_holdout  ->  submit_proposal (training-only, whitelisted, bounded)  ->  evaluate (the gate)
                    ->  promote (re-verifies everything, writes the new fitted_params version)

The gate (``evaluate``) names every miss; empty reasons == pass:
  integrity    holdout present + undrifted, proposal content intact, money path unchanged since proposed,
               target replayable, per-holdout run budget (runs beyond it refuse outright).
  guardrails   patch inside TUNABLE bounds (safety knobs are not tunable at all); patched holdout max
               drawdown >= the Phase-7 floor and not worse than baseline by more than dd_tolerance.
  golden       every golden case window replayed under baseline + patched: patched >= baseline - tol.
  walk-forward on the FROZEN holdout: enough weeks; patched wins a majority of chronological folds;
               deflated Sharpe with n_trials = gate runs already spent on this holdout + 1 (the
               multiple-testing / adaptive-overfit deflation); XBI-relative alpha >= baseline.

Structural enforcement lives in migration 020 (triggers) — this module is the only code that arms a
promotion and writes a learn version, and tests/test_learn_gate_adversarial.py tries to go around it.
No look-ahead at application: proposers only get a TrainingReplay that refuses any window whose
one-week exit could touch the embargo before the holdout.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt

from catalyst_trader import kb
from catalyst_trader.backtest.gate import THRESHOLDS, _below_floor
from catalyst_trader.dates import now_iso

SEED_CONFIDENCE = kb._SEED_CONFIDENCE   # migration 020 hardcodes 0.3 — a test pins them equal
HOLD_DAYS = 7                           # the one-week hold: a training as_of's exit bar is as_of + 7
REPLAYABLE = {"fitted_params:weekly"}   # targets Layer A can replay with no LLM (CONTEXT A1)
GOLDEN_PATH = Path(__file__).resolve().parents[3] / "data" / "learn" / "golden_set.json"

# dotted path -> (lo, hi). The bounds ARE a guardrail. Lower bounds of the tradeability bar equal today's
# values (the loop can only tighten it). Safety knobs (hard_veto_drop, binary_gap_*, defensive_*, anchor,
# beta_window_weeks, roundtrip_cost) are deliberately absent — never tunable by the loop (CONTEXT A2).
TUNABLE: dict[str, tuple[float, float]] = {
    "weekly.shrink_prior_weight": (20, 50),
    "weekly.edge_min_pts": (0.02, 0.06),
    "weekly.min_effective_n": (30, 100),
    "weekly.shortlist_k": (1, 6),
    "weekly.statistical_sleeve_cap": (0.0, 0.5),
    "weekly.sector_frac_cut": (0.3, 0.7),
    "weekly.cost_mult": (2, 4),
}

# Documented defaults the CEO retunes (CONTEXT D3).
GATE_THRESHOLDS = {
    "min_holdout_weeks": 12,
    "folds": 3,
    "min_dsr": 0.90,
    "dd_tolerance": 0.02,
    "max_drawdown": THRESHOLDS["max_drawdown"],
    "max_gate_runs": 20,
    "golden_tolerance": 0.0,
}


class HoldoutLeak(ValueError):
    """Proposal generation touched data inside (or too close to) the frozen holdout."""


class GateRefused(RuntimeError):
    """The gate (or promotion) refused outright — nothing was evaluated or written."""


class ProposedDiff(BaseModel):
    """A diff as the loop hands it over. extra=forbid: a diff cannot carry its own verdict/status/strategy."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    target: str
    patch: dict[str, StrictInt | StrictFloat]
    rationale: str = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)
    trained_through: str


# --------------------------------------------------------------------------- pure helpers


def sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def apply_patch(base: dict, patch: dict) -> dict:
    """Deep copy of `base` with each dotted path set. An unknown path raises KeyError (never invents keys)."""
    out = copy.deepcopy(base)
    for path, value in patch.items():
        *parents, leaf = path.split(".")
        node = out
        for p in parents:
            node = node[p]
        if leaf not in node:
            raise KeyError(path)
        node[leaf] = value
    return out


def check_patch(target: str, patch: dict, base: dict) -> list[str]:
    """Named reasons the patch is not admissible (empty == admissible)."""
    if not patch:
        return ["patch is empty"]
    if target not in REPLAYABLE:
        return []  # not tunable here; evaluate fails it closed ("no deterministic replay")
    reasons = []
    for path, v in patch.items():
        if path not in TUNABLE:
            reasons.append(f"{path} is not tunable")
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            reasons.append(f"{path}={v!r} is not a finite number")
            continue
        cur = apply_patch(base, {})
        for p in path.split("."):
            cur = cur[p]
        if isinstance(cur, int) and not isinstance(v, int):
            reasons.append(f"{path}={v!r} changes type (int knob)")
            continue
        lo, hi = TUNABLE[path]
        if not lo <= v <= hi:
            reasons.append(f"{path}={v!r} out of bounds [{lo}, {hi}]")
        elif v == cur:
            reasons.append(f"{path}={v!r} is a no-op")
    return reasons


def _scenario_ctype(target: str) -> str:
    if not target.startswith("fitted_params:"):
        raise ValueError(f"target {target!r} is not a fitted_params:<type> money-path config")
    return target.split(":", 1)[1]


# --------------------------------------------------------------------------- frozen holdout


def _manifest(conn, start: str, end: str) -> dict:
    bars = conn.execute(
        "SELECT ticker, week_end, open, high, low, close, volume FROM price_bar "
        "WHERE week_end >= ? AND week_end <= ? ORDER BY ticker, week_end", (start, end)).fetchall()
    cats = conn.execute(
        "SELECT id, ticker, event_date, status FROM catalyst WHERE event_date >= ? AND event_date <= ? "
        "ORDER BY id", (start, end)).fetchall()
    return {"weeks": sorted({b["week_end"] for b in bars}),
            "catalysts": [list(c) for c in cats],
            "bars_sha": sha([list(b) for b in bars])}


def freeze_holdout(conn, *, start: str, end: str, embargo_days: int = 7, name: str = "") -> int:
    """Freeze [start, end] as THE evaluation holdout (the latest frozen row is the active one)."""
    if start > end:
        raise ValueError(f"holdout start {start} after end {end}")
    m = _manifest(conn, start, end)
    if not m["weeks"]:
        raise ValueError(f"no price bars in holdout window {start}..{end}")
    hid = conn.execute(
        'INSERT INTO learn_holdout (name, start, "end", embargo_days, manifest, manifest_sha, frozen_at)'
        " VALUES (?,?,?,?,?,?,?)",
        (name, start, end, embargo_days, json.dumps(m), sha(m), now_iso())).lastrowid
    conn.commit()
    return hid


def active_holdout(conn) -> dict | None:
    row = conn.execute("SELECT * FROM learn_holdout ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return None
    h = dict(row)
    h["manifest"] = json.loads(h["manifest"])
    return h


def holdout_sha(conn, h: dict) -> str:
    """Recompute the holdout manifest sha from the CURRENT data (drift == a different sha)."""
    return sha(_manifest(conn, h["start"], h["end"]))


def training_cutoff(h: dict) -> str:
    """Last admissible training as_of: its one-week exit still lands >= embargo before the holdout."""
    d = date.fromisoformat(h["start"]) - timedelta(days=h["embargo_days"] + HOLD_DAYS)
    return d.isoformat()


class TrainingReplay:
    """The ONLY replay a proposer is handed: refuses any window ending after the training cutoff."""

    def __init__(self, replay, cutoff: str):
        self._replay, self.cutoff = replay, cutoff

    def __call__(self, params: dict, start: str, end: str):
        if end > self.cutoff or start > self.cutoff:
            raise HoldoutLeak(f"replay window {start}..{end} crosses the training cutoff {self.cutoff}")
        return self._replay(params, start, end)


# --------------------------------------------------------------------------- proposals


def proposal_sha(row) -> str:
    return sha({"target": row["target"], "patch": json.loads(row["patch_json"]),
                "trained_through": row["trained_through"], "holdout_id": row["holdout_id"],
                "base_sha": row["base_sha"]})


def submit_proposal(conn, diff) -> int:
    """Validate + store a diff as 'proposed'. Refuses forged fields, inadmissible patches and leaks."""
    d = diff if isinstance(diff, ProposedDiff) else ProposedDiff.model_validate(diff)
    h = active_holdout(conn)
    if h is None:
        raise GateRefused("no frozen holdout — freeze one before proposing")
    if d.trained_through > training_cutoff(h):
        raise HoldoutLeak(f"trained_through {d.trained_through} is after the training cutoff "
                          f"{training_cutoff(h)}")
    base = kb.load_params(conn, _scenario_ctype(d.target))
    if d.target in REPLAYABLE or not d.patch:
        reasons = check_patch(d.target, d.patch, base)
        if reasons:
            raise ValueError("; ".join(reasons))
    row = {"target": d.target, "patch_json": json.dumps(d.patch), "trained_through": d.trained_through,
           "holdout_id": h["id"], "base_sha": sha(base)}
    pid = conn.execute(
        "INSERT INTO learn_proposal (target, patch_json, rationale, evidence_json, trained_through,"
        " holdout_id, base_sha, content_sha, status, created_at) VALUES (?,?,?,?,?,?,?,?,'proposed',?)",
        (d.target, row["patch_json"], d.rationale, json.dumps(d.evidence), d.trained_through,
         h["id"], row["base_sha"], proposal_sha(row), now_iso())).lastrowid
    conn.commit()
    return pid


# --------------------------------------------------------------------------- the gate


def load_golden(path: str | Path | None = None) -> list[dict]:
    return json.loads(Path(path or GOLDEN_PATH).read_text())["cases"]


def _integrity(conn, prop, h_active) -> list[str]:
    reasons = []
    if h_active is None or h_active["id"] != prop["holdout_id"]:
        reasons.append("proposal is bound to a retired holdout (re-propose against the active one)")
    elif holdout_sha(conn, h_active) != h_active["manifest_sha"]:
        reasons.append("holdout drift: data in the frozen window changed since it was frozen")
    if proposal_sha(prop) != prop["content_sha"]:
        reasons.append("proposal content does not match its content sha (tampered)")
    if sha(kb.load_params(conn, _scenario_ctype(prop["target"]))) != prop["base_sha"]:
        reasons.append("stale: the money path moved since this proposal was made")
    return reasons


def _folds(xs: list, k: int) -> list[list]:
    n = len(xs)
    return [xs[i * n // k:(i + 1) * n // k] for i in range(k)]


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _walk_forward(base_r, pat_r, weeks, base_weeks, *, n_trials, benchmark, th) -> tuple[dict, list[str]]:
    from catalyst_trader.quant.performance import benchmark_relative, deflated_sharpe, max_drawdown

    reasons, out = [], {"n_weeks": len(pat_r), "n_trials": n_trials}
    if len(pat_r) < th["min_holdout_weeks"] or len(base_r) < th["min_holdout_weeks"]:
        reasons.append(f"holdout weeks={len(pat_r)} below min {th['min_holdout_weeks']}")
        return out, reasons
    won = sum(_mean(p) > _mean(b) for p, b in zip(_folds(pat_r, th["folds"]), _folds(base_r, th["folds"])))
    out["folds_won"] = won
    if won * 2 <= th["folds"]:
        reasons.append(f"walk-forward folds won {won}/{th['folds']} (need a majority)")
    try:
        out["dsr"] = deflated_sharpe(pat_r, n_trials=n_trials, periods_per_year=52).value
    except ValueError:
        out["dsr"] = None
    miss = _below_floor("dsr", out["dsr"], th["min_dsr"])
    if miss:
        reasons.append(miss)
    out["mdd_base"], out["mdd_patched"] = max_drawdown(base_r).value, max_drawdown(pat_r).value
    if out["mdd_patched"] < th["max_drawdown"]:
        reasons.append(f"guardrail: max_drawdown={out['mdd_patched']:.3f} below floor {th['max_drawdown']}")
    elif out["mdd_patched"] < out["mdd_base"] - th["dd_tolerance"]:
        reasons.append(f"guardrail: max_drawdown={out['mdd_patched']:.3f} worse than baseline "
                       f"{out['mdd_base']:.3f} by more than {th['dd_tolerance']}")
    bp, bb = benchmark(weeks), benchmark(base_weeks)
    if not bp or not bb or len(bp) != len(pat_r) or len(bb) != len(base_r):
        reasons.append("XBI benchmark unavailable for the holdout weeks — alpha cannot be certified")
        return out, reasons
    try:
        out["alpha_patched"] = benchmark_relative(pat_r, bp, periods_per_year=52).value
        out["alpha_base"] = benchmark_relative(base_r, bb, periods_per_year=52).value
    except ValueError as exc:
        reasons.append(f"alpha undefined ({exc})")
        return out, reasons
    if out["alpha_patched"] < out["alpha_base"]:
        reasons.append(f"XBI alpha {out['alpha_patched']:.4f} below baseline {out['alpha_base']:.4f}")
    return out, reasons


def evaluate(conn, proposal_id: int, *, replay, golden: list[dict], benchmark,
             thresholds: dict = GATE_THRESHOLDS) -> dict:
    """Run the gate on one proposal; record an immutable learn_gate_run; set status passed/failed.

    replay(params, start, end) -> [(week, book_return)]; benchmark(weeks) -> [xbi_return] | None.
    Raises GateRefused (recording nothing) when the proposal is not 'proposed' or the holdout's run
    budget is spent.
    """
    th = thresholds
    prop = conn.execute("SELECT * FROM learn_proposal WHERE id=?", (proposal_id,)).fetchone()
    if prop is None or prop["status"] != "proposed":
        raise GateRefused(f"proposal {proposal_id} is not awaiting evaluation")
    h = active_holdout(conn)
    spent = conn.execute("SELECT COUNT(*) FROM learn_gate_run WHERE holdout_id=?",
                         (prop["holdout_id"],)).fetchone()[0]
    if spent >= th["max_gate_runs"]:
        raise GateRefused(f"gate-run budget spent on holdout {prop['holdout_id']} "
                          f"({spent}/{th['max_gate_runs']}) — freeze a new holdout")

    patch = json.loads(prop["patch_json"])
    report: dict = {"proposal_id": proposal_id, "target": prop["target"], "patch": patch}
    reasons = _integrity(conn, prop, h)
    if prop["target"] not in REPLAYABLE:
        reasons.append(f"no deterministic replay for target {prop['target']} — fails closed")
    base = kb.load_params(conn, _scenario_ctype(prop["target"]))
    guard = check_patch(prop["target"], patch, base)
    report["guardrails"] = {"patch": guard}
    reasons += [f"guardrail: {r}" for r in guard]
    if not golden:
        reasons.append("golden set is empty — cannot certify (fails closed)")

    if not reasons:  # only spend replay on an admissible, intact proposal
        patched = apply_patch(base, patch)
        tol = th["golden_tolerance"]
        report["golden"] = []
        for case in golden:
            b = sum(r for _, r in replay(base, case["start"], case["end"]))
            p = sum(r for _, r in replay(patched, case["start"], case["end"]))
            report["golden"].append({"id": case["id"], "base": b, "patched": p})
            if p < b - tol:
                reasons.append(f"golden regression {case['id']}: patched {p:.4f} < baseline {b:.4f}")
        bw = replay(base, h["start"], h["end"])
        pw = replay(patched, h["start"], h["end"])
        wf, wf_reasons = _walk_forward([r for _, r in bw], [r for _, r in pw], [w for w, _ in pw],
                                       [w for w, _ in bw], n_trials=spent + 1, benchmark=benchmark, th=th)
        report["walk_forward"] = wf
        reasons += wf_reasons
    else:
        report.setdefault("golden", None)
        report["walk_forward"] = {"n_trials": spent + 1, "skipped": "integrity/guardrail failure"}

    report["reasons"], report["passed"] = reasons, not reasons
    conn.execute(
        "INSERT INTO learn_gate_run (proposal_id, holdout_id, content_sha, holdout_sha, golden_sha,"
        " n_trials, report, passed, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (proposal_id, prop["holdout_id"], prop["content_sha"],
         h["manifest_sha"] if h else "", sha(golden), spent + 1, json.dumps(report, default=str),
         int(not reasons), now_iso()))
    conn.execute("UPDATE learn_proposal SET status=? WHERE id=?",
                 ("passed" if not reasons else "failed", proposal_id))
    conn.commit()
    return report


# --------------------------------------------------------------------------- promotion (sole writer)


def promote(conn, proposal_id: int) -> int:
    """Apply a PASSED proposal to the money path: re-verify, arm a one-shot promotion, append the new
    fitted_params version (citing its gate run). Returns the new playbook node id. Never chained
    automatically after evaluate (CONTEXT D1)."""
    prop = conn.execute("SELECT * FROM learn_proposal WHERE id=?", (proposal_id,)).fetchone()
    if prop is None or prop["status"] != "passed":
        raise GateRefused(f"proposal {proposal_id} has not passed the gate")
    run = conn.execute("SELECT * FROM learn_gate_run WHERE proposal_id=? ORDER BY id DESC LIMIT 1",
                       (proposal_id,)).fetchone()
    if run is None or not run["passed"]:
        raise GateRefused(f"proposal {proposal_id} has no passed gate run")
    if proposal_sha(prop) != prop["content_sha"] or run["content_sha"] != prop["content_sha"]:
        raise GateRefused("proposal content changed after the gate run")
    h = active_holdout(conn)
    if (h is None or h["id"] != run["holdout_id"] or run["holdout_sha"] != h["manifest_sha"]
            or holdout_sha(conn, h) != h["manifest_sha"]):
        raise GateRefused("holdout changed (re-frozen or drifted) since the gate run")
    ctype = _scenario_ctype(prop["target"])
    base = kb.load_params(conn, ctype)
    if sha(base) != prop["base_sha"]:
        raise GateRefused("stale: the money path moved since this proposal was evaluated")

    strategy = apply_patch(base, json.loads(prop["patch_json"]))
    scenario_type = prop["target"]
    top = conn.execute(
        "SELECT MAX(confidence) FROM kb_node WHERE kind='playbook' "
        "AND json_extract(attrs_json,'$.scenario_type')=?", (scenario_type,)).fetchone()[0]
    top = SEED_CONFIDENCE if top is None else top
    confidence = top + (1.0 - top) / 10.0       # strictly above, never reaching 1
    promo_id = conn.execute(
        "INSERT INTO learn_promotion (proposal_id, gate_run_id, scenario_type, strategy_json, confidence,"
        " status, created_at) VALUES (?,?,?,?,?,'armed',?)",
        (proposal_id, run["id"], scenario_type, json.dumps(strategy), confidence, now_iso())).lastrowid
    node = kb.KBNode(kind="playbook", confidence=confidence, attrs={
        "scenario_type": scenario_type, "scenario": f"LEARN promotion of proposal {proposal_id}",
        "strategy": strategy, "learn_promotion_id": promo_id})
    ev = kb.EvidenceSource(url=f"learn://gate_run/{run['id']}", retrieved_at=now_iso(),
                           snippet_hash=run["content_sha"],
                           quote=f"gate run {run['id']} passed: {prop['patch_json']}")
    nid = kb.insert_claim(conn, node, [ev])   # one transaction with the armed promotion; rolls back both
    conn.execute("UPDATE learn_proposal SET status='promoted' WHERE id=?", (proposal_id,))
    conn.commit()
    return nid


# --------------------------------------------------------------------------- default replay + benchmark


def layer_a_replay(conn, embed=None):
    """replay(params, start, end) -> [(week, book_return)] via the Phase-7 Layer-A backtest (NO LLM).
    Book return = the size-weighted leg sum, the same weekly return baseline_distribution uses."""
    from catalyst_trader.backtest.engine import run_layer_a

    def fn(params, start, end):
        try:
            results, _dist = run_layer_a(conn, embed, start=start, end=end, params=params)
        except ValueError:  # no weeks in window -> baseline_distribution refuses an empty baseline
            return []
        return [(r.week, sum(l.size_pct * l.realized_ret for l in r.legs)) for r in results]
    return fn


def xbi_benchmark(conn):
    """benchmark(weeks) -> XBI one-week returns over the SAME entry/exit bars the backtest uses
    (engine._fill_leg, no costs), or None if any week is unmeasurable."""
    from catalyst_trader.backtest.engine import _fill_leg

    def fn(weeks):
        out = []
        for w in weeks:
            exit_by = (date.fromisoformat(w) + timedelta(days=HOLD_DAYS)).isoformat()
            leg = _fill_leg(conn, "XBI", w, exit_by, held_through=False, slippage=0.0, apply_costs=False)
            if leg is None:
                return None
            out.append(leg[2])
        return out
    return fn
