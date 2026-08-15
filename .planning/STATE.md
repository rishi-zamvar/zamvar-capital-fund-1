---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 03-03-PLAN.md
last_updated: "2026-08-15T02:09:40.986Z"
last_activity: 2026-08-15
progress:
  total_phases: 11
  completed_phases: 2
  total_plans: 18
  completed_plans: 13
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-08-14)

**Core value:** Given an imminent biotech catalyst, produce a data-backed, portfolio-aware, hedged one-week trade recommendation the user can trust enough to approve — and get measurably better at it every week.
**Current focus:** Phase 3 — Quant Tool Library + Rubric & Base-Rates

## Current Position

Phase: 3 (Quant Tool Library + Rubric & Base-Rates) — EXECUTING
Plan: 3 of 8
Status: Ready to execute
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

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 1: No clean free PDUFA/AdCom API — needs a spike (pure hand-curation vs a paid tracker like BPIQ). Research flag.
- Phase 5: Cointegration validation (Engle-Granger/Johansen) + conditional-on-catalyst payoff modeling is domain-specific quant with real-money consequences — verify approach before implementation. Research flag.
- Phase 11: Robinhood MCP tool surface, schemas, OAuth flow, rate limits, PDT enforcement state all UNVERIFIED — expect a small real-money probing spike before building. Research flag.

## Session Continuity

Last session: 2026-08-15T02:09:34.123Z
Stopped at: Completed 03-03-PLAN.md
Resume file: None
