# The 52-Week Sequential Walk-Forward Learning Harness — Design

**Researched / designed:** 2026-08-16
**Domain:** point-in-time walk-forward · sequential playbook accumulation · per-cohort config/param calibration · reuse of the Phase-7 backtest infra + the desk + the KB
**Confidence:** HIGH on reuse (every signature below confirmed against source via Graphify graph-first + direct read); MEDIUM on cost (order-of-magnitude, no full-chain run has been metered yet)

---

## Scope note (operator course-correction, 2026-08-16 — READ FIRST)

The operator refined the harness's PURPOSE mid-research. This design reflects the **simplified** scope, which **removes** work:

- **The walk-forward's job is NOT to prove decision quality.** It has exactly two deliverables: **(1) fine-tune the config/params** (financial-model + MCP-analysis-skill settings, per cohort/stock) and **(2) build the playbook**. **Bias is explicitly acceptable here.**
- **Decision-making capability is proven elsewhere** — in the **forward paper-trading month (Phase 8)**, which is leak-free by construction (it trades events that have not happened yet).
- Therefore the elaborate **outcome-blind / no-leak enforcement apparatus for the agentic desk is DROPPED** (`OutcomeBlindCatalyst` projection of the full chain, web-block re-assertion beyond the desk's own web-free default, and the shuffled-outcome leakage-control test). See "Why blinding is unnecessary here" below — this is a real simplification, leaned into, not a corner cut.

Two things that sound similar are **kept**, because they are correctness, not blinding:

1. **Point-in-time DATA correctness** on the pre-event setup features — a setup feature computed from prices *after* the event yields a *wrong* fitted parameter, independent of any agent. Keep the `<= pre_event_asof` guards.
2. **A permanent `biased_optimistic` label** on every result, so the walk-forward's win-rate is never mistaken for an edge proof.

---

## Summary

The harness is a **chronological, one-week-at-a-time walk over the historical event set**. It reuses the Phase-7 point-in-time event set (`build_event_set`) as the week cursor, runs the **full live desk chain** (`run_desk` → `run_portfolio` → `run_diligence` → `md.reconcile`) point-in-time at each `week_end`, records the **BEFORE** (setup + call + confidence + kill-criteria), advances time, **realizes the outcome deterministically from post-event bars** (`fill.py` — no LLM arithmetic), records the **AFTER** (move + surprise + which pre-signals were predictive + cited mechanism), and **writes the per-trade record into the KB** via the Phase-7.5 `insert_catalyst_record` helper. Because records are written **in chronological order as the walk proceeds**, week *N*'s `analog_query` / `load_params` reads see **only weeks 1..N-1** — the compounding playbook the operator asked for, for free, from write-order alone (no as-of filter apparatus needed).

The **primary deliverable is the calibrated config**: the walk fits `fitted_params:<type>` playbooks per cohort **from the realized price moves** (ground truth from bars), and — the key honesty point — **that fit does not depend on the desk's calls at all**, so the agentic desk being outcome-aware cannot corrupt it. The **secondary deliverable is the playbook / analog store** that makes `analog_query` return real analogs on every later live catalyst. A **per-trade before/after ledger** surfaces the ~52 trades one-by-one for operator review. A **rolling metrics panel** (win-rate / calibration / return-vs-1%) shows whether the loop improves — labelled biased-optimistic throughout.

**Primary recommendation:** Build **one thin orchestrator** (`backtest/walkforward.py`, ~180–250 lines) that threads the already-built full chain over `build_event_set`, realizes outcomes via `fill.py`, and writes records via the Phase-7.5 `insert_catalyst_record`; plus **one ledger/report generator**. Everything money-touching or analytical already exists. This is the Phase-7.5 historical backfill, run **sequentially instead of in bulk**, with the full agentic chain in the loop — which is exactly "the learning loop running on history."

---

## User Constraints (money-critical, from CLAUDE.md + operator course-correction)

### Locked (do not violate)
- **Point-in-time DATA correctness is money-critical** — setup features via the shipped `<= as_of` guards only; a feature unreadable as-of is **dropped, not imputed**. (Kept for *validity*, not leak-prevention.)
- **No-LLM-arithmetic on money numbers** — realized moves/surprise/predictive-match are Python-computed from bars via `fill.py`; agents only narrate the mechanism *with a citation*.
- **Provenance / cite-or-drop** — every KB node routes through `insert_claim` (rejects a claim with no `CITES` edge, atomically).
- **FREE data**; **`.venv/bin/python`**; **Graphify graph-first**; **reuse the Phase-7 backtest infra + the desk + the KB — minimal new surface.**
- **Human gate inviolable** everywhere downstream (not exercised by the historical walk, but the walk never places an order).

### Explicitly relaxed for THIS run (operator, 2026-08-16)
- **Agentic-desk outcome-awareness is acceptable.** Bias is fine. Drop `OutcomeBlindCatalyst` full-chain projection, web-block re-assertion, and the leakage-control test.
- **Token-heavy is fine.** Do **not** compromise full-workflow depth to save tokens. Cost is noted honestly (below) but not designed around.

### Deferred / out of scope
- The **honest, leak-free decision-quality proof** — that is the **forward paper month (Phase 8)**, not this walk.
- The **gated diff-merge machinery** (golden-set regression + walk-forward eval before a diff touches the money path) — that is **Phase 10 / LEARN-02**; this walk *produces* the calibrated params it will later gate, it does not build the gate.

---

## The two-stage honesty split (frame this so roles are never confused)

| | **Year walk-forward (this harness)** | **Forward paper month (Phase 8)** |
|---|---|---|
| **Question it answers** | "What are the right per-cohort params, and what does the playbook look like?" | "Does the desk actually make good decisions out-of-sample?" |
| **Leak-free?** | **No — and that's fine.** Biased-optimistic. | **Yes, by construction** — the events have not happened. |
| **What the number means** | calibration + a populated analog store | the honest edge / decision-quality proof |
| **Label** | `biased_optimistic=True` on every result | trustworthy |
| **Why bias doesn't poison the deliverable** | the config/param fit is computed from **realized price moves** (bars), not from the desk's calls | n/a |

Both are needed. The walk-forward *calibrates and stocks the playbook*; the paper month *proves the edge*. The walk-forward's win-rate is **never** the go-live evidence — `backtest/gate.py`'s sample-based gate already refuses to let a thin/flattering sample clear go-live.

---

## Why agentic blinding is unnecessary here (bake this reasoning into the plan)

The original ask included re-using Phase-7's `OutcomeBlindCatalyst` + web-block + a shuffled-outcome leakage test to keep the LLM desk from memorizing known outcomes. The operator dropped this. The reasoning, stated so a future reader doesn't "re-add safety":

1. **The parameter/playbook fit reads REALIZED MOVES, not the desk's calls.** `fitted_params:<type>` is fit on the outcome-node distribution (`realized_ret`, `surprise_vs_expected`, IV-crush, hedge-leg behavior) — all Python-computed from bars via `fill.py`. Even a desk that has perfectly memorized every outcome cannot change the realized bar prices. So agentic outcome-awareness **cannot corrupt the primary deliverable.**
2. **A playbook is inherently retrospective.** "What happened, and what pointed to it in hindsight" is *supposed* to be written with full knowledge of the outcome. Outcome-awareness is appropriate for the record itself.
3. **The one thing that *would* corrupt the fit is look-ahead in the DATA** — a setup feature computed from post-event bars. That is plain arithmetic wrongness, unrelated to the agent, and it is **kept** (next section).

The Phase-7 `OutcomeBlindCatalyst` / `_assert_web_free` machinery stays available in `backtest/layerb.py` for anyone who later wants a *blinded* replay — the walk-forward simply does not invoke it.

---

## 1. The walk-forward loop

### The cursor: reuse `build_event_set` unchanged
`backtest/events.py::build_event_set(conn, *, start, end, anchor='MON', hold_days=7, latency_cfg=None)` (confirmed against source, `events.py` L30) already walks a weekly `as_of` cursor and returns, per week, `{as_of, anchor, universe, catalysts:[{ticker, catalyst_type, event_date, last_verified_at}], has_bars}` — **point-in-time and survivorship-free**, with the mandatory `last_verified_at <= effective_asof` catalyst post-filter that closes the verification look-ahead (`events.py` L84-90). The window length is a knob (`start`/`end`); ~52 weekly steps is the target, not a constant.

### Per-week procedure (chronological)
For each `rec` in `build_event_set(conn, start, end)`, in order, for each catalyst in `rec["catalysts"]`:

**(a) Assemble the point-in-time setup** at `pre_event_asof` (= the last bar strictly before `event_date`, or `as_of`). Reuse the Phase-7.5 setup-feature assembler (§B.1 of `universe-expansion-and-playbook-dataset.md`): drop-regime (`quant.weekly.classify_drop`), base rates (`quant.base_rate`), short interest (`card_asof`), implied move / IV (`options_cboe`), runway/float (`edgartools`), and prior analogs (`kb.analog_query`). **Every read via a `<= pre_event_asof` guard** (§2 below).

**(b) Run the FULL workflow point-in-time** — the live desk chain, in order:
1. `verdict = await run_desk(conn, catalyst)` — 4 analysts → bull/bear debate → verifier-gated `DebateVerdict` (`orchestrator.py` L44).
2. `dossier = (await run_portfolio(conn, embed, [workitem], open_book, target_return=0.01, ...))[0]` — builder → risk (ruin-capped size + validated hedge) → select_book → memo/pre-mortem → PM (`orchestrator.py` L81). The `workitem` = `{verdict, catalyst, entry, risk_inputs}`; `entry`/`risk_inputs`/`market_data` come from step (a) (the same caller-supplied context seam `run_weekly`/`run_portfolio` already require — `weekly.py` L79-114, L84-85).
3. `dd = await run_diligence(conn, dd_input, market_data=market_data, embed=embed)` — the 8-dimension adversarial firewall → deterministic `synthesize_verdict` → opus narrative → cite-or-drop `DiligenceDossier` (`diligence.py` L495).
4. `decision = await md.reconcile(conn, embed, item={verdict, dossier, dd, catalyst, dd_input, market_data, open_book, incoming_flags:[]})` — the bounded MD/GP loop, the **one point that sees all three workflows**, emitting the terminal `MDDecision` (enter/pass/escalate) — the recommended trade (`md.py` L283). This is what the live desk does every week; the harness just feeds it historical inputs.

**(c) Record the BEFORE** — the `prediction`(setup) side of the record: the setup feature vector, the desk's call (`verdict.direction`, `verdict.confidence`, `verdict.kill_criteria`), the built trade (`dossier.trade` size/direction/hedge), the diligence verdict, and the MD decision. Stamped `as_of = pre_event_asof`.

**(d) Advance time, realize the outcome deterministically** — from post-event bars only, via the shipped pessimistic fill model: `fill.fill_price(bars_asof(conn, ticker, exit_by), side, held_through=True, slippage)` (`fill.py` L41). Held-through binaries fill at the **gap-open far side, never the stop** (the classic optimistic-backtest lie, guarded at `fill.py` L77-82). Compute realized 1-day and 1-week move, `surprise_vs_expected = realized − implied` (sign + magnitude, deterministic), IV-crush, and the hedge-leg's realized move — exactly the Phase-7.5 outcome spec (§B.1).

**(e) Record the AFTER + write the record** — the `outcome` node + `rationale` (mechanism cited from the resolving 8-K/PR; `surprise_vs_expected` and `predictive_signals.matched_realized` deterministic; an agent may only narrate, labelled `grounding:"inferred"`), then `kb.insert_catalyst_record(conn, catalyst, setup_attrs, outcome_attrs, rationale, evidence, embed=embed)` (the Phase-7.5 helper) — writing the `catalyst → prediction(setup) → outcome` graph atomically through `insert_claim` (cite-or-drop by construction).

**(f) Compound.** Because (e) has now committed weeks 1..N's records, week *N+1*'s step-(a) `analog_query` and step-(b) `load_params` **see them**. Optionally re-fit `fitted_params:<type>` every *K* weeks (below) so the desk's *parameters* also compound, not just its analogs.

### State that carries forward vs. resets

| Carries forward (the compounding) | Resets each week |
|---|---|
| **The KB**: every `catalyst/prediction/outcome/playbook` node written so far (→ `analog_query` grows) | The **open_book** — each trade is an independent one-week hold; there is no running portfolio to carry (the compounding is knowledge, not capital) |
| **`fitted_params:<type>`** playbooks (if incremental refit is on) — week N+1's `load_params` returns the updated cohort params | Per-week market context (entry/risk_inputs/market_data) — re-assembled point-in-time |
| The **rolling metrics series** (append-only, for the compounding panel) | — |

> Design decision — **incremental vs. terminal refit.** Two honest modes, both cheap:
> - **Terminal refit** (simplest): walk once writing records; refit `fitted_params:<type>` once at the end. The *analog store* compounds during the walk; the *params* are calibrated once. Matches Phase-7.5's bulk backfill exactly, just sequential.
> - **Incremental refit** (truer to "each trade informed by every prior lesson"): re-fit every *K* weeks (e.g. K=4) so `load_params` shadows the bootstrap partway through and later weeks trade on calibrated params. Costs only deterministic re-fits (no extra LLM). **Recommend incremental (K≈4)** — it is the operator's "compounds so each successive trade is informed by every prior lesson," and the extra cost is negligible (the LLM desk dominates spend, not the fit).

---

## 2. Point-in-time DATA correctness (KEPT — this is validity, not agentic blinding)

Distinct from the dropped outcome-blinding. A setup feature computed from a bar *after* the event produces a **wrong fitted parameter**, regardless of any agent — so this is plain arithmetic correctness and stays.

1. **The event set is already point-in-time** — `build_event_set` reads universe via `universe_as_of`, bars via `bars_asof`, catalysts via `tradeable_catalysts_light` **then** the mandatory `last_verified_at <= effective_asof` post-filter (`events.py` L60, L84-90). `tradeable_catalysts` is status-only (no date guard), so the post-filter is the money-honesty fix — the record builder must re-apply it (Pitfall #4 in the 7.5 doc; do not read catalysts raw).
2. **Every setup read goes through a `<= pre_event_asof` guard** — `bars_asof`, `card_asof`, `scan_flags_asof`. A feature unreadable as-of is **dropped, not imputed** (cite-or-drop; the daemon's degrade-to-None discipline).
3. **The setup and outcome are two disjoint as-ofs** — the setup pass is keyed to `pre_event_asof`; the outcome to post-event bars. They never share an as-of. (This is a data-timing invariant, not an agent firewall — it holds even though the desk is outcome-aware.)
4. **The KB read is naturally 1..N-1** — because records are written in chronological walk order (§1f), `analog_query` at week N cannot return week N's own outcome or any future analog; there is no data yet. **No as-of filter on the KB read is required** — do not build one. The only rule is: **do not pre-run the Phase-7.5 bulk backfill before the walk** (that would pre-load all outcomes and defeat the sequencing). The walk *is* the population path.
5. **Test-enforced (Wave 0):** extend the existing `bars_asof` no-look-ahead regression (`tests/test_backtest_events.py::test_event_set_no_future_bar`) to the record builder — poison the store with a future bar and assert the assembled setup still reads only `<= as_of`. This is the *data* test; the dropped leakage-control test was a different (agentic) thing.

---

## 3. The per-trade before/after examination artifact

Reuse the Phase-7.5 catalyst-outcome record schema verbatim (§B.1 of `universe-expansion-and-playbook-dataset.md`) — the graph is `company → catalyst → prediction(setup) / → outcome`, all `CITES → evidence_source`. Per trade the operator inspects:

**BEFORE (the `prediction`/setup node + the call):**
- setup feature vector at `pre_event_asof` (drop-class, base rates, short interest, implied move/IV, runway/float, prior analogs surfaced)
- the desk's **call**: `verdict.direction`, `verdict.confidence`, `verdict.thesis`
- the built **trade**: `dossier.trade` (direction, size_pct, hedge peer + mechanism), `dossier.decision`
- the **kill-criteria** (`verdict.kill_criteria`) and diligence `dd.verdict` + red_flags
- the **MD decision** (`decision.decision`, accepted_residuals, preserved dissent)

**AFTER (the `outcome` node + `rationale`):**
- realized **1d / 1wk move** + direction (deterministic, `fill.py`)
- **surprise_vs_expected** `{expected, realized, surprise, sign_flip}` (deterministic)
- **predictive_signals**: which pre-features pointed the right way (`matched_realized` per feature, deterministic) — "what before pointed to this"
- **hedge-leg behavior** (peer's realized move — validated/refuted the inverse-payoff claim)
- **mechanism** (`CRL | approval | hit_primary | missed_primary | mixed`) — **cited** to the resolving filing/PR
- the **playbook delta** it produced (which `fitted_params:<type>` cell moved, and by how much, at the next refit)

**How the ~52 are surfaced:** a **trade-by-trade ledger** the operator reviews one-by-one — a `docs/phase-reports/`-style HTML (reuse the terminal/brass design language mandated in CLAUDE.md, favicon 🧬, both themes), one expandable row per trade: BEFORE call | AFTER outcome | matched? | mechanism | playbook delta, plus a top-line `biased_optimistic` banner. Generated deterministically from the KB records — nothing in it that isn't a committed, cited node. (Backing store is the KB; the HTML is a read-only projection, same as the Phase-9 Historical Performance page will later consume.)

---

## 4. The compounding measurement (does it actually get better?)

Reuse `quant/performance.py` verbatim (all confirmed against source): `win_rate`, `avg_win_loss`, `sharpe`, `sortino`, `max_drawdown`, `hedge_effectiveness` — each RAISES on undefined rather than emitting a fake number, and `sharpe`/`sortino` **require** `periods_per_year` (the freq-footgun cure; pass 52). Reuse `backtest.engine.baseline_distribution(results, periods_per_year=52)` to roll per-leg outcomes into the frozen `BaselineDistribution`, and `backtest.gate.sample_based_gate(distribution, n_catalysts, thresholds)` for the explicit go/no-go (below `min_sample=30` it is a hard NO-GO regardless of metrics — it refuses to flatter a thin sample).

**The compounding view** (the "is it improving" question) — computed on a **rolling / expanding** window across the chronological trades:
- **rolling win-rate** (e.g. trailing-12-trade) — is the desk's directional hit-rate rising as the playbook fills?
- **calibration**: predicted `verdict.confidence` (or the base-rate `p`) vs realized win-frequency, bucketed — is the desk getting better-calibrated, not just luckier? (Reuse the predictive_signals match data; calibration = the Phase-9 "prediction-vs-realized calibration" surfaced early.)
- **return vs the 1%/week target** — the size-weighted weekly return series vs 0.01, cumulative and rolling.

**Honesty guard:** every one of these carries the `biased_optimistic` label. A rising rolling win-rate here is **consistent with** genuine calibration improvement **and** with the desk memorizing more outcomes as history accumulates — the walk **cannot distinguish them**, and does not try to. The distinguishing test is the forward paper month (Phase 8). What the walk *can* prove honestly: whether the **fitted params** improve the **Layer-A mechanical** backtest (which has no LLM and cannot memorize) — run `run_layer_a` before vs after the refit and compare `BaselineDistribution`. **That** delta is an honest measure of the calibration's value, because Layer A is deterministic. (Recommend surfacing both: the biased agentic rolling panel *and* the clean Layer-A before/after.)

---

## 5. Reuse vs. build + cost

### Reuse-vs-build verdict: **~90% reuse. One thin orchestrator + one report generator is the entire new surface.**

| Concern | Verdict | What (confirmed against source) |
|---|---|---|
| Week cursor / point-in-time event set | **REUSE** | `backtest.events.build_event_set` (`events.py` L30) |
| Deterministic outcome from bars | **REUSE** | `backtest.fill.fill_price` (`fill.py` L41), `store.bars_asof` |
| Catalyst call | **REUSE** | `desk.orchestrator.run_desk` (`orchestrator.py` L44) |
| Portfolio build | **REUSE** | `desk.orchestrator.run_portfolio` (`orchestrator.py` L81) |
| Independent diligence | **REUSE** | `desk.diligence.run_diligence` (`diligence.py` L495) |
| The full-chain integration (sees all 3 workflows → recommended trade) | **REUSE** | `desk.md.reconcile` (`md.py` L283) — already composes run_desk + run_portfolio + run_diligence |
| Per-trade record graph (setup→event→outcome→rationale) | **REUSE** (Phase-7.5) | `kb.insert_catalyst_record` (proposed in 7.5; the walk is its sequential caller) |
| Analog compounding | **REUSE** | `kb.analog_query` (`kb.py` L172) — grows automatically from write-order |
| Param compounding / the moat | **REUSE** | `kb.load_params` (`kb.py` L373) + `insert_playbook`/`seed_fitted_params` + the Phase-7.5 cohort-refit function |
| Metrics + go/no-go | **REUSE** | `quant.performance.*`, `backtest.engine.baseline_distribution`, `backtest.gate.sample_based_gate` |
| Forward-path record seam | **REUSE** | `desk.weekly.record_weekly_outcome` (`weekly.py` L159) — the same pattern, live |
| **The chronological loop** (thread the chain over the event set, realize outcomes, write records in order, incremental refit) | **BUILD** | `backtest/walkforward.py` (~180–250 lines) |
| **The trade-by-trade ledger HTML** + rolling/calibration panel | **BUILD** | one report generator (deterministic KB projection) |
| **The `biased_optimistic` label on the batch result** | **BUILD** (trivial) | mirror `LayerBResult.biased_optimistic` (`layerb.py` L65) on the walk's result contract |
| **DROPPED (vs original ask)** | **DROP** | `OutcomeBlindCatalyst` full-chain projection, web-block re-assertion, shuffled-outcome leakage-control test |

Relationship to `run_layer_b`: `layerb.run_layer_b` replays **only the catalyst layer** (`run_desk`) with sampling + the blinding guards (`layerb.py` L186-206). The walk-forward is the **full-chain, un-blinded, sequential** generalization: instead of `_replay_one → run_desk`, it does `run_desk → run_portfolio → run_diligence → md.reconcile → realize → insert_catalyst_record`, in chronological order, no sampling (or documented sampling for cost). It **reuses `build_event_set` the same way** and **reuses the `biased_optimistic` label** — but it does not reuse the `OutcomeBlind`/web-free guards (dropped per operator). Do not fork layerb.py; build a sibling `walkforward.py` that calls the full chain.

### Honest cost estimate (token-heavy is fine; noting, not designing around)

The dominant cost is the **full agentic chain per catalyst**, run ~52–104 times (≈1–2 tradeable catalysts/week × ~52 weeks). One full chain fires, per catalyst, roughly:
- `run_desk`: 4 analysts + bull/bear/moderator debate (`MAX_ROUNDS`) + verifier gate — order ~8–12 LLM calls
- `run_portfolio`: builder + risk + memo + pre-mortem + pm_decide — order ~5 LLM calls
- `run_diligence`: 8 dimension agents (sonnet) + opus narrative + opus cite-or-drop enforce — order ~10+ LLM calls
- `md.reconcile`: up to 3 rounds of opus review + terminal opus decision + possible cascade re-runs of desk/portfolio/diligence — order ~4–15 LLM calls, occasionally re-firing the whole chain

→ **order ~30–50 LLM calls per catalyst**, plausibly **~200k–600k tokens per full chain** (no full-chain run has been metered — the P2-P4 executor avg was ~90k, but a full desk is a different, heavier shape; treat this as an order-of-magnitude). Across 52–104 catalysts: **~10M–60M tokens** for the walk — i.e. low hundreds of dollars at API rates, comparable to a few of the larger build phases (6.10 alone was ~1.5M build tokens; the cumulative build is ~16.6M). **This is expected and acceptable** per the operator; do not thin the chain to cut it.

**Cost levers that do NOT touch money reasoning** (apply freely; the money decisions are already deterministic — `size_for_survival`, `synthesize_verdict`, `select_book`, the surprise/predictive-match — so cheapening the *narrative/analyst* layers cannot corrupt a money number):
- **Batch API (≈50% off)** — the walk is a fully offline historical run with **no latency requirement**, the ideal Batch workload. This is the single biggest lever and costs nothing in fidelity. **Strongly recommend.**
- **Haiku where the desk already tiers down** — diligence dimensions already default to sonnet (`diligence.py` L159); the Phase-6.8 Haiku DD-replica pattern (185k for a full once-over pass) shows Haiku is viable for the screening layers. Keep **judgment** calls (debate, MD decision, verifier, narrative) on opus.
- **Documented sampling** (like `layerb.sample_catalysts` — never a silent `[:N]`, always a logged drop-list) if the operator ever wants a cheaper partial walk. Default: **no sampling** (full walk), per "don't compromise depth."
- **Don't babysit the run** (TOKEN-NOTES 6.10 directive): the walk is multi-hour — launch in background, write a completion signal, return; the orchestrator owns the wait. A babysat long run tripled Plan-07's cost.

---

## Prerequisite ordering (what must exist before this can run)

1. **Phase 6.12 — Data-Driven Universe Expansion** (`universe-expansion...md` Part A): the ~80-name survivorship-free `universe_as_of` cohort **defines the ingest set**. Without it the catalyst feed is vacuous (19 unverified earnings-only catalysts today).
2. **Historical ingestion pass** (road-to-backtest **Stage 1**): one pass populates the store over a **3–5yr** survivorship-free window (prices via the built N-source cascade; trial readouts CT.gov; earnings Nasdaq; **PDUFA/AdCom via a past-dated EDGAR-8K efts pass** — `pdufa_edgar` found forward events, run the same phrase set over the past). `ingest_history` stamps `last_verified_at` point-in-time. **This is the raw material; without it `build_event_set` returns empty weeks.**
3. **Phase 7.5 — Catalyst-Outcome Playbook Dataset** (`universe-expansion...md` Part B/C): `kb.insert_catalyst_record` + the point-in-time **setup-feature assembler** + the **cohort-refit** function must exist. The walk-forward is the **sequential caller** of these — it does not re-implement them. (Critically: run the walk **instead of** 7.5's bulk backfill, or the sequencing is lost — §2.4.)
4. **Phase 7 backtest infra** — `build_event_set`, `fill.py`, `performance.py`, `gate.py`, `engine.baseline_distribution`. **DONE** (all read from source).
5. **The full desk chain** — `run_desk` (Phase 4), `run_portfolio`/`risk`/`builder` (Phase 5), `run_diligence` (Phase 6), `md.reconcile` (Phase 6.7). **Code exists on disk** (all read from source); confirm each phase is closed before the walk relies on it.

**Then** `backtest/walkforward.py` can run. Ordering: **6.12 → historical ingest (Stage 1) → 7.5 helpers → walk-forward.** The walk-forward is naturally a **late Phase-7.x / pre-Phase-8 step** (it needs the calibrated dataset machinery but produces the params Phase 8 will paper-trade on).

---

## How this refines the Phase 10 roadmap entry

Phase 10 (Continuous-Iteration Loop, LEARN-01/LEARN-02) is currently "predict → realize → score → propose-diff, gated behind golden-set regression + walk-forward evals." This harness **is the LEARN loop, run on history as a walk-forward** — it clarifies and de-risks Phase 10:

1. **The walk-forward is the *retrospective instantiation* of the same loop.** Phase 10 runs predict→realize→score→propose-diff forward, one catalyst at a time, gated. This harness runs the identical predict→realize→record→refit loop over history, one week at a time, sequentially. Same shape, historical inputs. Building it now **de-risks Phase 10** — the loop mechanics ship and are exercised on 52 trades before they gate real diffs.
2. **It supplies Phase 10's "walk-forward evals against a frozen holdout" primitive.** LEARN-02 requires a diff to pass a walk-forward eval before merging to the money path. This harness **is** that walk-forward evaluator — freeze a holdout window, run the walk with vs without the proposed diff, compare `BaselineDistribution` (honest, via the deterministic Layer-A before/after in §4). Phase 10's gate calls it.
3. **It draws the honesty boundary Phase 10 must respect.** The walk-forward's own agentic win-rate is `biased_optimistic` and **may not** be a merge criterion (it can reflect memorization). The **valid** merge signals are: (a) the deterministic Layer-A `BaselineDistribution` delta from the refit, and (b) the forward paper month. Phase 10's diff-gate should key on those, not the biased agentic number. **Recommend adding this caveat to the Phase-10 success criteria.**
4. **It separates "build the playbook" from "prove the edge."** Phase 10 as written blends learning with proving. This harness cleanly does the **calibration + playbook-building** half (biased-OK); **Phase 8's paper month** does the **decision-quality proof** half (leak-free). Phase 10's *gate* is what merges a validated diff — it consumes both, and this harness is the historical half of its evidence.

**Suggested ROADMAP refinement:** add a Phase (7.6 or a Phase-10 sub-item) "**Sequential walk-forward learning harness**" with the explicit note: *biased-optimistic by design; calibrates `fitted_params:<type>` from realized bars + stocks the analog store sequentially; its agentic win-rate is never a go-live or diff-merge criterion — the honest signals are the deterministic Layer-A refit delta and the Phase-8 forward paper month.*

---

## Open questions

1. **Incremental refit cadence K.** K=4 weeks recommended (params compound mid-walk, negligible extra cost). Could be K=1 (every trade) — more faithful to "each trade informed by every prior lesson," but re-fits cohorts with tiny n early on (label bootstrap-fallback, as `load_params` already does). **Recommend K=4, revisit once real cohort sizes are known.**
2. **Cohort granularity for the fit.** `fitted_params:<type>` is keyed by catalyst_type today. The 7.5 doc recommends cohort = catalyst_type × TA × drop_regime for statistical power over a thin 3–5yr window. Confirm the refit function's cohort key with Phase-7.5's design before the walk relies on it.
3. **Per-full-chain token cost is unmetered.** The ~200k–600k/chain estimate is order-of-magnitude. **Meter one full `md.reconcile` chain on real inputs** before committing to a 104-catalyst full walk, so the Batch-API budget is sized from data, not a guess. (Cheap: one metered run.)
4. **MD escalations during the historical walk.** `md.reconcile` writes `.monitor/blocker.json` on escalate (`md.py` L360-362) — for a headless historical walk, escalations should be **logged into the record** (an "escalate" outcome is a valid data point), not written to the live blocker file. Thread a no-op / walk-scoped `blocker_path` so a historical escalation doesn't raise a live operator banner.

---

## Sources

**Primary (HIGH — codebase, signatures confirmed via Graphify graph-first + direct read):**
- `src/catalyst_trader/backtest/events.py` — `build_event_set` (point-in-time cursor + `last_verified_at <= effective_asof` post-filter)
- `src/catalyst_trader/backtest/fill.py` — `fill_price` (gap-open far-side, never-fills-at-stop), `effective_asof`
- `src/catalyst_trader/backtest/layerb.py` — `run_layer_b`, `OutcomeBlindCatalyst`, `biased_optimistic` label, `sample_catalysts` drop-list (the pattern generalized; blinding guards dropped)
- `src/catalyst_trader/backtest/engine.py` — `run_layer_a`, `baseline_distribution`, `BaselineDistribution`
- `src/catalyst_trader/backtest/gate.py` — `sample_based_gate`, `THRESHOLDS` (min_sample=30 hard NO-GO)
- `src/catalyst_trader/desk/orchestrator.py` — `run_desk` (L44), `run_portfolio` (L81)
- `src/catalyst_trader/desk/diligence.py` — `run_diligence` (L495), deterministic `synthesize_verdict`
- `src/catalyst_trader/desk/md.py` — `reconcile` (L283, the 3-workflow integration → `MDDecision`), `cross_check`
- `src/catalyst_trader/desk/weekly.py` — `run_weekly` (L79), `record_weekly_outcome` (L159, the WEEK-05 forward seam)
- `src/catalyst_trader/kb.py` — `analog_query` (L172), `load_params` (L373), `insert_claim`/`insert_playbook`/`seed_fitted_params`, `BOOTSTRAP_DEFAULT`
- `src/catalyst_trader/quant/performance.py` — `sharpe`/`sortino`/`win_rate`/`max_drawdown`/`avg_win_loss`/`hedge_effectiveness` (periods_per_year required)
- Graphify graph (`graphify-out/graph.json`, indexed 2026-08-16) — `graphify explain` confirmed callers/callees of run_desk, run_portfolio, run_layer_b, analog_query, build_event_set, run_diligence

**Secondary (HIGH — project research, live-verified):**
- `.planning/research/universe-expansion-and-playbook-dataset.md` — the 5-stage plan, the catalyst-outcome record schema (§B.1), no-look-ahead data guards (§B.2), `insert_catalyst_record` design (§B.4), Phase 6.12 + 7.5 definitions
- `docs/road-to-backtest.html` — the five stages (Stage 1 ingest → Stage 5 Phase-10 gated learning loop); "the tools are commodities, the calibrated assumptions are the moat; a thin sample is a no-go, not a number to flatter"
- `.planning/ROADMAP.md` — Phase 8 (paper ledger, LEARN-03), Phase 10 (LEARN-01/02, gated diff-merge)
- `.planning/REQUIREMENTS.md` — LEARN-01/02/03 definitions
- `.planning/TOKEN-NOTES.md` — carried directives (Graphify-first, reuse-vs-new up front, don't-babysit-live-runs, Batch/Haiku right-sizing, plan-check ON for money phases)

**Operator input (authoritative — this session):**
- Course-correction 2026-08-16: drop agentic outcome-blinding + leakage test; keep point-in-time DATA correctness, sequential compounding, per-trade artifact, config-fit-from-realized-moves, and the `biased_optimistic` label; token-heavy is fine; frame the two-stage honesty split (walk = calibration/playbook; paper month = edge proof).

## Metadata

**Confidence breakdown:**
- Reuse map / signatures: **HIGH** — every function read from source + confirmed via Graphify
- Loop design / point-in-time data correctness: **HIGH** — reuses shipped guards (`build_event_set`, `bars_asof`, `fill.py`)
- Config-fit-doesn't-depend-on-desk-calls reasoning: **HIGH** — fit reads outcome nodes (bars), structurally independent of `run_desk`
- Cost: **MEDIUM** — order-of-magnitude; no full `md.reconcile` chain metered yet (Open Q3)

**Research date:** 2026-08-16 · **Valid until:** ~2026-09-15 (reuse targets stable; re-confirm `insert_catalyst_record` + cohort-refit signatures against Phase-7.5 once built)
