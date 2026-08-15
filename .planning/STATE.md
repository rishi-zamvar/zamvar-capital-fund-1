---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: verifying
stopped_at: Completed 05-07-PLAN.md
last_updated: "2026-08-15T08:04:17.638Z"
last_activity: 2026-08-15
progress:
  total_phases: 11
  completed_phases: 5
  total_plans: 32
  completed_plans: 32
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-14)

**Core value:** Given an imminent biotech catalyst, produce a data-backed, portfolio-aware, hedged one-week trade recommendation the user can trust enough to approve — and get measurably better at it every week.
**Current focus:** Phase 05 — trade-builder-honest-hedge-ruin-avoidant-sizing-workflow-1b-2

## Current Position

Phase: 05 (trade-builder-honest-hedge-ruin-avoidant-sizing-workflow-1b-2) — EXECUTING
Plan: 7 of 7
Status: Phase complete — ready for verification
Last activity: 2026-08-15

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01 P01 | 5 | 3 tasks | 15 files |
| Phase 01 P02 | 5 | 2 tasks | 2 files |
| Phase 01-data-integrity-catalyst-feed P03 | 5min | 2 tasks | 7 files |
| Phase 01-data-integrity-catalyst-feed P04 | 10min | 3 tasks tasks | 8 files files |
| Phase 01-data-integrity-catalyst-feed P05 | 15min | 3 tasks | 8 files |
| Phase 01-data-integrity-catalyst-feed P06 | 15min | 2 tasks tasks | 6 files files |
| Phase 02 P01 | 2min | 3 tasks tasks | 7 files files |
| Phase 02-contracts-knowledge-base-skeleton P02 | 3min | 2 tasks tasks | 2 files files |
| Phase 02-contracts-knowledge-base-skeleton P03 | 2min | 2 tasks tasks | 3 files files |
| Phase 02-contracts-knowledge-base-skeleton P04 | 4min | 3 tasks tasks | 4 files files |
| Phase 03 P02 | 5min | 2 tasks tasks | 1 file files |
| Phase 03 P03 | 4min | 2 tasks tasks | 1 file files |
| Phase 03 P04 | 6min | 2 tasks tasks | 1 file files |
| Phase 03 P05 | 4min | 3 tasks tasks | 4 files files |
| Phase 03 P06 | 4min | 2 tasks tasks | 2 files files |
| Phase 03-quant-tool-library-rubric-base-rates P07 | 4min | 3 tasks | 6 files |
| Phase 03-quant-tool-library-rubric-base-rates P08 | 12min | 2 tasks tasks | 3 files files |
| Phase 04-analyst-desk-bull-bear-debate-workflow-1a P01 | 4min | 1 task tasks | 2 files files |
| Phase 04 P02 | 4min | 3 tasks tasks | 8 files files |
| Phase 04-analyst-desk-bull-bear-debate-workflow-1a P03 | 4min | 1 task tasks | 3 files files |
| Phase 04-analyst-desk-bull-bear-debate-workflow-1a P04 | 4min | 1 tasks | 6 files |
| Phase 04-analyst-desk-bull-bear-debate-workflow-1a P05 | 8min | 1 tasks | 5 files |
| Phase 04-analyst-desk-bull-bear-debate-workflow-1a P06 | 6min | 1 task tasks | 3 files files |
| Phase 04-analyst-desk-bull-bear-debate-workflow-1a P07 | 9min | 2 tasks | 11 files |
| Phase 05 P01 | 3min | 2 tasks | 2 files |
| Phase 05 P02 | 20min | 3 tasks tasks | 5 files files |
| Phase 05 P03 | 8min | 2 tasks | 3 files |
| Phase 05 P04 | 18min | 3 tasks | 6 files |
| Phase 05 P05 | 9min | 2 tasks tasks | 3 files files |
| Phase 05 P06 | 18min | 2 tasks tasks | 3 files files |
| Phase 05 P07 | 22min | 3 tasks tasks | 6 files files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap: Build strict dependency order — data integrity FIRST (a wrong catalyst date is a total loss), execution (real money) STRICTLY LAST.
- Research correction: Robinhood shipped an official Agentic Trading MCP (2026-05-27) — use it, never `robin_stocks`.
- Research correction: Kùzu is archived (Apple acq. Oct 2025) — KB is SQLite graph-shaped + sqlite-vec, not Kùzu.
- Long/long is only a hedge if the peer is an inverse-payoff competitor (rises when target falls); honest hedge + ruin-avoidant sizing are inline in Phase 5, not a later hardening pass.
- [Phase 01]: No-LLM-date invariant enforced at the pydantic boundary (Catalyst.sources may not be empty); per-source date_type persisted so verify.py re-derives uncertainty (DATA-04)
- [Phase 01]: Partial dates (YYYY-MM/YYYY) are ALWAYS window; firm is structurally unreachable from a partial date (DATA-04 classifier)
- [Phase 01-data-integrity-catalyst-feed]: [Phase 01]: Providers attach provenance at the boundary (Pattern 1) — every date leaves a provider inside a CatalystSource; no bare/LLM-sourced dates (DATA-01)
- [Phase 01-data-integrity-catalyst-feed]: [Phase 01]: FMP 'confirmed' expressed via CatalystSource.date_type=actual (no new field); CT.gov attribution by curated exact lead-sponsor name (DATA-04)
- [Phase 01-data-integrity-catalyst-feed]: Atomic write-path (store.insert_catalyst) is the physical no-LLM-date enforcement: catalyst+sources in one transaction, rollback on failure, sourceless rejected
- [Phase 01-data-integrity-catalyst-feed]: Single tradeable gate: is_tradeable(c)=status=='verified'; all origins (provider/curated/ad-hoc) flow through the same insert->verify pipeline, no bypass
- [Phase 01-data-integrity-catalyst-feed]: T-2 trigger is day-precision only + dedup-marker-row (trigger_event UNIQUE catalyst_id+event_date) for exactly-once firing across idempotent runs (DATA-05)
- [Phase 01-data-integrity-catalyst-feed]: refresh restamps last_verified_at only on re-verified catalysts, so a near-event date that cannot re-verify keeps its stale stamp and is excluded (DATA-03 48h re-verify)
- [Phase 01-data-integrity-catalyst-feed]: Universe snapshots are append-only per as_of_date cohort (never UPDATE/DELETE); universe_as_of returns latest cohort <= D — survivorship-free (DATA-06)
- [Phase 01-data-integrity-catalyst-feed]: Seed/PDUFA curation is a carry-forward human task (no LLM-invented dates); code+tests complete, data files ship as labelled templates + data/README.md guide
- [Phase 02]: KB extension loaded in db.connect() (not migrate) so both prod + the shared db fixture get vec0 before migrate() runs (KB-01)
- [Phase 02]: kb_vec dimension baked at 384 (MiniLM-aligned); deterministic sha256 hash_embed is the offline default, real model is a later one-line swap behind the injectable callable
- [Phase 02-contracts-knowledge-base-skeleton]: Six inter-layer contracts enforce extra='forbid' + bounded score/confidence + required non-empty evidence_ref — anti-hallucination at every agent message boundary (contract-side half of KB-02)
- [Phase 02]: insert_claim mirrors store.insert_catalyst verbatim — reject uncited claim before write + try/commit/except-rollback, application-level invariant not a DB trigger (KB-02); no orphan node/edge/vec on failure
- [Phase 02]: CITES routed through the same no-commit add_edge helper Plan 02-04 uses for HEDGE_PEER — one edge-insert path; evidence deduped on url+snippet_hash
- [Phase 02]: analog_query is two-tier: structural SQL filter builds candidate set THEN KNN over-fetch (k*4) intersected in python — version-robust vs sqlite-vec alpha metadata-filter API; RESULTED_IN traverse attaches realized outcome (KB-03)
- [Phase 02]: Hedge relationship stored as a CITED hedge_peer node via insert_claim (nodes cite; edges cannot carry :CITES) + a HEDGE_PEER traversal edge; payoff_direction stored as explicit sign (+1/-1), polarity not hard-coded (KB-04)
- [Phase 03]: risk_of_ruin has NO return-target parameter — structural guarantee sizing is never coupled to the 1%/week target (survival-first)
- [Phase 03]: risk_of_ruin = bankroll recurrence (loss_length) + exact streak-probability DP over n_trades, deterministic (no Monte Carlo), reproducible + testable
- [Phase 03]: cointegration delegates to statsmodels coint (Engle-Granger) + coint_johansen (Johansen trace); hedge ratio = OLS slope np.polyfit(price_b, price_a); conditional_payoff value = un-netted worst cell (PITFALLS #1 honest hedge)
- [Phase 03]: implied_move: straddle method preferred (model-free) and wins when both methods supplied; gross exposure uses abs so two longs show 2× not netted (PITFALLS #1)
- [Phase 03]: periods_per_year is a REQUIRED arg on sharpe+sortino — freq-footgun cured by design; tested 252==52×√(252/52)
- [Phase 03]: Sortino denominator = target semideviation over all obs; attribution reconciles components to total within 1e-6 rel tolerance or raises
- [Phase 03]: load_weights rejects any weight outside [0,1] (not just Σ≈1) — a learning-loop rewrite with a negative/>1 weight could score nonsensically even when the row sums to 1.0 (plan-checker addendum)
- [Phase 03]: base_rate raises on both zero matches (unknown key) and multiple matches (ambiguous) — no silent None, no arbitrary first-row pick; caller narrows phase/indication (FRAME-03)
- [Phase 03]: Quant library exposes one public import surface (catalyst_trader.quant); a single parametrized test enforces inputs==kwargs reproducibility across every tool (QUANT-03) — pipeline_value stays submodule-only since its snapshot is derived, not verbatim
- [Phase 04-analyst-desk-bull-bear-debate-workflow-1a]: DebateVerdict.direction is a binary Literal[positive,negative] + required non-empty kill_criteria — CALL-03 binary-verdict + falsification criteria enforced at the pydantic boundary
- [Phase 04]: evidence_ref format standardized: kb:<evidence_source_node_id> (resolves via kb.get_node, evidence_source-only) and tool:<tool_name>#<inputs_hash> (resolved-by-construction); resolves RESEARCH Open Q2 (CALL-04)
- [Phase 04]: One SDK seam: desk.runtime.run_structured is the ONLY claude_agent_sdk touchpoint (output_format json_schema -> model_validate boundary); every agent test monkeypatches it -> zero live API in pytest
- [Phase 04-analyst-desk-bull-bear-debate-workflow-1a]: quant/ + kb.py exposed as ONE in-process SDK MCP server (build_quant_server, name 'quant'); analysts call+interpret, never compute (CALL-01)
- [Phase 04-analyst-desk-bull-bear-debate-workflow-1a]: analog_query/query_playbooks cited as tool:<fn>#<hash> (resolved-by-construction), NEVER kb: (they return node ids, not evidence_source ids) — CALL-04 verifier guard
- [Phase 04-analyst-desk-bull-bear-debate-workflow-1a]: run_analyst threads caller-injected mcp_servers/allowed_tools + defaults to the sonnet tier (configured once, not per call site); analysts CALL mcp__quant__* and cite the returned evidence_ref, never compute — uncited payloads rejected at the AnalystSignal boundary (CALL-01)
- [Phase 04]: Debate isolation enforced by threading only Argument.argument (shareable) never Argument.scratchpad (private) — scratchpad exists so the isolation test has something that must not cross sides (CALL-02)
- [Phase 04]: Moderator (opus) hard-requires anchoring confidence to a cited base_rate/analog and lowering per unknown; no-positioning guarded by extra=forbid + a denylist-disjoint test (CALL-03)
- [Phase 04]: Verifier enforces source-quote-or-drop: deterministic structural gate (resolve + quote-substring) runs first with no LLM; opus semantic support-check spent only on load-bearing structural survivors; losing all support raises VerdictUnsupportedError and blocks finalize (CALL-04)
- [Phase 04]: tool: refs (quant results AND KB analog_query/query_playbooks) survive structural resolution by construction; the same analog cited as kb:<node_id> is dropped as unresolvable — the CALL-04 regression guard for 04-03's tool:-ref minting
- [Phase 04-analyst-desk-bull-bear-debate-workflow-1a]: run_desk wires Workflow-1a end-to-end: asyncio.gather 4 analysts -> bounded debate -> verifier.enforce gated finalize; a thin composition over Plans 03-06, no new logic
- [Phase 05]: Hedge.covers validator makes a fake idiosyncratic hedge raise at model_validate; inverse_etf is sector_beta-only; put_option legal-but-unpromotable (HEDGE-01/04, options-ready)
- [Phase 05]: RiskAssessment carries the validated Hedge OBJECT (hedge: Hedge | None), distinct from hedge_valid, so 05-07 reconciles it onto the promoted proposal (BLOCKER-1)
- [Phase 05]: catalyst_move_estimate: implied_move is a magnitude prior only (per-branch blend); sign comes solely from the p_positive mixture — a prior can never flip trade direction (PITFALLS #10)
- [Phase 05]: hold_vs_exit decides by expected-LOG-growth at the survival-constrained f (Kelly-consistent), never raw EV — a positive-EV hold with a fat down-tail provably exits (BLOCKER-2); non-survivable (1+f·R)<=0 raises, never silent -inf
- [Phase 05]: adaptive_sl_tp_levels delegates to sl_tp_levels so the gap-exposed advisory gate lives in one place; every quant threshold read from params (missing key raises, no numeric fallback)
- [Phase 05]: load_params is the frozen model-fit param seam (top-confidence fitted_params:<type> row, else labeled BOOTSTRAP_DEFAULT deep-copy); fitted param sets are cited, confidence-versioned playbook claims, builder thresholds homed in the default/CSV — 05-06 reads them, Phase-9 refit replaces the SOURCE without rewrite
- [Phase 05]: size_for_survival has no return-target param (structural anti-1%-coupling); sizes on risk_of_ruin down-move, 1% is never a sizing input (PORT-03)
- [Phase 05]: validate_hedge: a hedge is only a -1 inverse peer passing conditional_payoff worst-cell + cointegration + catalyst-clean THIS catalyst, else None (honest fallback, HEDGE-01..04); assess calls it ONCE, threads onto both hedge object + hedge_valid (BLOCKER-1)
- [Phase 05]: enforce_estimate is the estimate-layer mirror of verifier.enforce: cite-or-drop on every estimator input (reusing evidence.resolve/quote_supported) + deterministic consistency (P(positive)↔verdict, down-move sanity band, hold-through/non-advisory SL) + one gated opus analog-comparability check; reject raises EstimateRejectedError blocking finalize (PORT-02/OPS-01)
- [Phase 05]: Down-move sanity band centers on params['estimator']['default_down_move'] (the cited per-type fitted param), not quant.base_rate — base_rates.csv has no per-catalyst-type down-move row; band [0.5x,2x] is a named calibration knob
- [Phase 05]: [Phase 05] builder: DebateVerdict -> TradeProposal, single-leg estimated-move construction; hold-vs-exit via quant hold_vs_exit (log-growth, never raw EV, BLOCKER-2); sized on estimated down-move; SL advisory on hold-through; every threshold from params[builder] (missing raises); estimate vetted before finalize
- [Phase 05]: 05-07 run_portfolio RECONCILES risk.recommended_size_pct + risk.hedge onto each proposal (model_copy) right after risk.assess and BEFORE select_book — the builder's preliminary size/hedge are never promoted (BLOCKER-1 fix)
- [Phase 05]: 05-07 select_book aggregates toward ~1% by SELECTION only (greedy by expected_move/size under weekly budget + concentration heat cap); it never resizes a leg above its survival size; zero-trade + all-kill weeks are valid successes
- [Phase 05]: 05-07 memo + pre-mortem authored in run_structured calls SEPARATE from and BEFORE the opus PM decision (author != approver, OPS-01/02); which_risk_covered derived from validated+payoff+instrument so an unvalidated hedge can never report idiosyncratic (HEDGE-05)

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 1: No clean free PDUFA/AdCom API — needs a spike (pure hand-curation vs a paid tracker like BPIQ). Research flag.
- Phase 5: Cointegration validation (Engle-Granger/Johansen) + conditional-on-catalyst payoff modeling is domain-specific quant with real-money consequences — verify approach before implementation. Research flag.
- Phase 11: Robinhood MCP tool surface, schemas, OAuth flow, rate limits, PDT enforcement state all UNVERIFIED — expect a small real-money probing spike before building. Research flag.

## Session Continuity

Last session: 2026-08-15T08:04:07.559Z
Stopped at: Completed 05-07-PLAN.md
Resume file: None
