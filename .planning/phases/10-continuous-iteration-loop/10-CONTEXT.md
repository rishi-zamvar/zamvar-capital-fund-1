# Phase 10: Continuous-Iteration Loop - Context

**Gathered:** 2026-11-11
**Status:** Ready for planning
**Source:** discuss-phase --auto (autonomous run; every gray area resolved at the recommended default,
each recorded below as an ASSUMPTION). Requirements LEARN-01, LEARN-02.

<domain>
## Phase Boundary

Predict -> realize -> score -> propose-diff -> GATE -> (explicit) promote.

1. LEARN-01: after a paper trade resolves (closed + Phase-8 attributed), an LLM judge grades the desk's
   prediction against the realized outcome. A calibration harness measures judge-vs-human agreement on
   hand-graded labels; a judge is only "calibrated" when it clears the agreement floors on REAL
   (non-synthetic) labels.
2. LEARN-02: the loop proposes config/playbook diffs; a diff can reach the money path only by passing a
   golden-set regression replay + guardrail evals + a walk-forward eval on a FROZEN holdout.
3. Structural: no diff can auto-apply to the paper/live money path without passing the gate. Enforced
   in the DB (triggers) and in code (single promotion path), with an adversarial test suite.

Out of scope: LEARN-03 (Phase 8 owns it), an LLM proposer (deferred, xfail), re-running the LLM desk
(Layer B) inside the gate, live execution (Phase 11).
</domain>

<decisions>
## Implementation Decisions

### What is "the money path" (the thing a diff could change)
- The deterministic money path reads every tunable number through ONE seam: `kb.load_params(conn, type)`
  = the top-confidence `fitted_params:<type>` playbook node, else `BOOTSTRAP_DEFAULT`. Desk weekly
  runner, Layer-A backtest, catalyst_context, builder, MD and paper attribution all read it. So a
  "config diff" = a dotted-path patch over a `fitted_params:<type>` strategy dict; "promoting" it =
  appending a new higher-confidence `fitted_params:<type>` playbook version (append-only versioning
  that already exists — no new read path).
- ASSUMPTION A1: the only REPLAYABLE target this phase is `fitted_params:weekly` (the `weekly` group),
  because Layer A (`run_layer_a(params=...)`) is fully parameterised by it and needs no LLM. Any other
  target (catalyst-type builder params, warm free-form playbooks read by the LLM desk) is accepted as a
  proposal but the gate FAILS CLOSED ("no deterministic replay for target") — it can never auto-apply.
- ASSUMPTION A2: tunable surface = a whitelist (`learn.gate.TUNABLE`) of weekly knobs with hard bounds
  taken from the research ranges already documented in BOOTSTRAP_DEFAULT comments:
  shrink_prior_weight [20,50], edge_min_pts [0.02,0.06], min_effective_n [30,100], shortlist_k [1,6],
  statistical_sleeve_cap [0,0.5], sector_frac_cut [0.3,0.7], cost_mult [2,4]. Lower bounds on
  edge_min_pts / min_effective_n / cost_mult equal today's values = the loop can only TIGHTEN the
  tradeability bar, never loosen it. SAFETY knobs (hard_veto_drop, binary_gap_*, binary_catalyst_types,
  defensive_*, anchor, beta_window_weeks, roundtrip_cost) are deliberately NOT tunable.

### LEARN-01 judge
- Judge = injected callable `judge_fn(prompt) -> dict | JudgeVerdict`; contract `JudgeVerdict`
  (extra=forbid): grade 1..5, direction_correct bool, rationale non-empty. Live binding
  `make_live_judge()` goes through the ONE SDK seam `desk.runtime.run_structured` with
  `allowed_tools=[]` (the judge cannot touch anything). Tests stub it; one opt-in live test runs only
  with `LEARN_LIVE_JUDGE=1`.
- ASSUMPTION A3 (rubric): 5 = right direction for the right reason (catalyst effect drove it);
  4 = right direction, reason mostly right; 3 = right direction for the wrong reason (tape/beta) OR right
  reason but badly sized; 2 = wrong direction but the kill criteria/pre-mortem named what happened;
  1 = wrong direction and the thesis missed it entirely. The judge is given the prediction (direction,
  thesis/kill criteria/pre-mortem from the Phase-9 review snapshot, size) AND the realized outcome (Phase-8
  attribution: verdict, gross move, catalyst_effect vs beta_drift). Grading is post-hoc by design (it is
  not a forecast, so it may see the outcome).
- ASSUMPTION A4 (calibration floors): calibrated iff >= 20 REAL labels AND quadratic-weighted kappa >= 0.6
  AND within-one agreement >= 0.8 (standard "substantial agreement" bands). Synthetic labels are scored
  and reported but NEVER count toward the verdict. A judgement row can be flagged calibrated=1 only if it
  references a PASSED calibration for the SAME judge model (DB trigger).
- Seed labels: `data/learn/judge_labels.json`, 10 cases spanning grades 1-5, ALL `synthetic: true,
  needs_ceo_grading: true, grader: "SYNTHETIC-PLACEHOLDER (claude)"`. Pydantic refuses a synthetic label
  that claims it needs no CEO grading. Until the CEO grades >= 20 real cases the judge is UNCALIBRATED and
  every judgement is stored calibrated=0 (scores are informational, never a gate input).
- ASSUMPTION A5: judge scores are NOT a gate input this phase (an uncalibrated judge must not steer
  money). They feed the post-mortem record and the CEO's calibration work.

### LEARN-02 gate
- Frozen holdout: `learn_holdout` row (start, end, embargo_days, manifest + sha). Manifest = holdout
  weeks + catalyst ids + a digest of every price bar in the window. DB triggers forbid UPDATE/DELETE.
  The gate recomputes the manifest at evaluate AND promote time; any drift (a bar revised, a catalyst
  added) refuses. ASSUMPTION A6: the active holdout = the latest frozen row; rolling it forward is an
  explicit operator action (CEO decision D2) — proposals bound to an older holdout go stale.
- No leak into proposal generation: training cutoff = holdout.start - embargo_days (default 7).
  Proposers only ever receive a `TrainingReplay` that raises `HoldoutLeak` for any window ending on/after
  the cutoff, and `submit_proposal` rejects `trained_through >= cutoff`. ASSUMPTION A7: walk-forward
  means train strictly BEFORE the holdout (no training on post-holdout data either — that would be
  look-ahead relative to the holdout weeks).
- Gate = all of (every miss named, empty reasons == pass):
  1. integrity: holdout present + undrifted; proposal content sha intact; money path unchanged since the
     proposal was made (base sha); target replayable; per-holdout gate-run budget not exhausted
     (ASSUMPTION A8: 20 runs, then re-freeze — bounds adaptive overfitting to the holdout).
  2. guardrails: patch inside TUNABLE + bounds + type-preserving; patched holdout max drawdown >= the
     Phase-7 floor (THRESHOLDS["max_drawdown"] = -0.25) and >= baseline - 0.02.
  3. golden-set regression replay: every golden case (a frozen date window) replayed under baseline and
     patched; patched week-sum return must be >= baseline - tolerance (0.0) on EVERY case. Empty golden
     set = fail closed. Golden set sha is recorded in the gate run.
  4. walk-forward on the frozen holdout: >= 12 holdout weeks; patched beats baseline in a majority of
     3 chronological folds; deflated Sharpe of the patched weekly returns with n_trials = (#gate runs
     already spent on this holdout + 1) >= 0.90 (ASSUMPTION A9; the multiple-testing deflation is the
     anti-overfit term); XBI-relative alpha (quant.performance.benchmark_relative, XBI legs via the
     backtest's own _fill_leg) patched >= baseline.
- Gate runs are immutable rows (`learn_gate_run`) binding content sha + holdout sha + golden sha.
- Promotion: `learn.gate.promote` is the ONLY writer. It re-verifies everything, arms a one-shot
  `learn_promotion` row, writes the new `fitted_params:<type>` version through `kb.insert_claim`
  (cite-or-drop: it cites the gate run), confidence = top + (1-top)/10 (strictly above, never reaching 1).
- ASSUMPTION A10 (CEO decision D1): promotion is an EXPLICIT step (`weekly_cycle.py --promote ID`),
  never chained automatically after a pass. The weekly `--learn` cycle judges, proposes and evaluates
  only. Flipping to auto-promote-on-pass is a one-line change the CEO can authorise.

### Structural enforcement (migration 020)
- kb_node BEFORE INSERT trigger: a playbook that carries `learn_promotion_id`, OR ANY
  `fitted_params:weekly` playbook (the replayable target has no seed tier at all), OR any other
  `fitted_params:*` playbook with confidence > 0.3 (above the bootstrap seed tier), must match an ARMED
  promotion whose gate run PASSED, for the same scenario_type, identical strategy JSON and confidence;
  else `RAISE(ABORT, 'LEARN gate: ...')`. An AFTER INSERT trigger consumes the promotion (one-shot).
- kb_node BEFORE UPDATE trigger: `fitted_params:*` playbook versions are append-only (no in-place edit
  of attrs/confidence).
- learn_promotion BEFORE INSERT: requires a passed gate run for the same proposal. learn_gate_run and
  learn_holdout: no UPDATE/DELETE. learn_proposal: target/patch/sha immutable.
- ASSUMPTION A11 (threat model): the adversary is a proposed diff and the loop code that handles it —
  forged fields, post-gate mutation, skipping the gate, out-of-bounds/safety-knob patches, holdout
  tampering, direct KB writes. A human with raw SQL on catalyst.db is out of scope (they can do anything);
  existing tests that inserted fitted_params at confidence 0.4-0.9 directly are re-pointed to the seed
  tier (<= 0.3) or now assert the refusal.
- `kb.query_playbooks` tie-break `id ASC` (plan-check B1): an equal-confidence late row can never
  silently displace the first seed. Residual (A11): a direct <= 0.3 insert for a CSV catalyst type is the
  operator bootstrap tier, outside the loop — covered by the grep invariant, not the trigger.
- learn_calibration: CHECK passed=0 OR n_real >= 20; no UPDATE/DELETE. Calibrations and judgements are
  bound to the judge model AND the rubric sha (a rubric change invalidates old calibrations).
- Leak boundary includes the exit fill: training cutoff = holdout.start - embargo_days - 7 (the one-week
  hold), i.e. the last training as_of's exit bar still lands >= embargo before the holdout.
- Code invariant (grep test): nothing under `src/catalyst_trader/learn/` except `gate.promote` writes a
  KB claim; `scripts/weekly_cycle.py` never calls insert_playbook/insert_claim.

### Golden set
- `data/learn/golden_set.json`: seeded with well-known market stress windows for small-cap biotech
  (2020-03 COVID crash, 2022-05 XBI capitulation, 2022-06 rebound) flagged `needs_ceo_review: true`.
  ASSUMPTION A12: these are reasonable regression windows, not CEO-curated cases.

### Deferred (xfail, shipped in the introducing plan)
- Headless resolution -> judge auto-fire: `paper_ledger.weekly_mark_pass` has no judge seam (the judge
  needs a CC session/LLM; `--mark` is launchd-headless). Strict xfail in 10-01.
- LLM proposer (reads judge rationales + post-mortems from the TRAINING window only). Strict xfail in 10-03.

### Claude's discretion
- File layout: one package `src/catalyst_trader/learn/` with `judge.py`, `gate.py`, `loop.py`.
- Migrations 019 (judge) + 020 (gate).
</decisions>

<ceo_actions>
## Needs the CEO
- C1: grade >= 20 REAL resolved cases (replace/extend data/learn/judge_labels.json; all 10 seeds are
  SYNTHETIC placeholders). Until then the judge is uncalibrated by construction.
- C2: confirm/curate the golden set windows (data/learn/golden_set.json, needs_ceo_review).
- C3: choose and freeze the first holdout window on the real DB (`weekly_cycle.py --freeze-holdout`).
- D1: auto-promote on gate pass, or keep the explicit `--promote` step (default: explicit).
- D2: holdout roll-forward cadence (default: manual re-freeze; 20 gate runs per holdout).
- D3: retune floors (min_dsr 0.90, kappa 0.6, within-one 0.8, 20 labels, 12 holdout weeks).
</ceo_actions>

<code_context>
## Reuse
- `kb.load_params` / `query_playbooks` / `insert_claim` / `_SEED_CONFIDENCE` (money-path seam, cite-or-drop).
- `backtest.engine.run_layer_a(params=...)`, `_fill_leg` (XBI legs), `backtest.gate.THRESHOLDS/_below_floor`.
- `quant.performance.deflated_sharpe`, `benchmark_relative`, `max_drawdown`.
- `paper_ledger` attribution JSON (Phase 8) + `paper_pending.review` (Phase 9) for the judge case.
- `desk.runtime.run_structured` (the one SDK seam) for the live judge.
- Precedents: strict xfail for deferred wiring (tests/test_backtest_latency_sweep.py); grep invariants
  (tests/test_weekly_cycle.py); DB-enforced gates (paper_ledger structural opener).
</code_context>
