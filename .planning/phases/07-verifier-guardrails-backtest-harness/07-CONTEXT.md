# Phase 7: Verifier/Guardrails + Backtest Harness - Context

**Gathered:** 2026-08-15
**Status:** Ready for research
**Mode:** Auto-generated from ROADMAP success criteria + PROJECT.md backtest decisions + the operator's data-latency directive

<domain>
## Phase Boundary

Prove the CORRECTED strategy honestly against ~1yr of history, and stand up the runtime safety gates — BEFORE any capital (real or paper). Three things: (1) runtime guardrails/monitors enforced on the live pipeline, (2) a point-in-time historical event set, (3) two backtest layers — Layer A mechanical (no LLM, trustworthy baseline) and Layer B guarded-agentic (labeled biased-optimistic). Produces a baseline distribution + an explicit go/no-go gate before paper trading (Phase 8). Stops at the baseline + gate — NO paper ledger (Phase 8), NO live execution (Phase 11).
</domain>

<decisions>
## Implementation Decisions (from ROADMAP + PROJECT.md + operator directives)

### 1. Backtest measures the CORRECTED strategy (not the pre-correction one)
Layer A must run the actual shipped mechanics: weekly build/exit cadence (`run_weekly`), target-within-survival-cap sizing, no-zero-trade defensive fallback, the universe-wide thesis engine (`thesis_scan`), and honest hedge/single-leg selection. It is a MECHANICAL replay (deterministic pair/leg selection + sizing + entry 1-2d pre-event + SL/TP + 1-week exit) with NO LLM.

### 2. Pessimistic fill model (money-honesty)
Fill at historical price with a tunable slippage haircut; on a held-through binary event, fill at the GAP-OPEN (far-side), NOT the stop level (a stop can't fill inside the gap — this is the Phase-5 hold-through truth applied to the backtest). Skip an event only if halted/delisted/zero-volume/zero-quote (volume caps ignored by design). Tunable slippage knob.

### 3. DATA-GATHERING TIMING simulation (operator directive, 2026-08-15)
The backtest must replay ONLY data that would ACTUALLY have been available at decision time given our free-source lag + fetch cadence — no look-ahead on delayed options quotes, bi-monthly short interest, EOD calibration. Add a tunable DATA-LATENCY knob (alongside the slippage knob) to stress how stale-data degrades the edge. This keeps the baseline honest about the real free-data pipeline, not an idealized instant feed. (Reuse the point-in-time discipline already in `bars_asof`/`card_asof`/`universe_as_of`.)

### 4. Point-in-time event set (BACK-01)
~1yr of universe earnings calendars (dense, precisely-dated → meaningful N) + dateable biotech catalysts, point-in-time, INCLUDING delisted names (survivorship-free). Reuse `universe_as_of` + the catalyst store.

### 5. Layer B guarded-agentic replay (BACK-03) — labeled biased-optimistic
Run the REAL agent pipeline (run_desk/run_portfolio/run_diligence/reconcile) on historical catalysts with look-ahead GUARDRAILS: web blocked/archived-only, point-in-time fundamentals, outcome-blind prompts. Results explicitly LABELED biased-optimistic (LLM memorization leaks past outcomes — this is honest, not a bug). This is expensive → run on a SAMPLE, and log what was sampled/dropped (no silent caps).

### 6. Runtime guardrails/monitors (OPS-03)
Active + enforced on the live pipeline: catalyst-date freshness, fact-check, provenance, the Workflow-3 firewall, net-long/concentration caps, and NO PATH from scraped/raw content to an order. Many of these already exist as invariants in shipped code — this phase makes them a runtime GATE, tested.

### 7. The go/no-go gate (BACK-05)
The baseline (win rate, avg win/loss, Sharpe, Sortino, max DD, hedge-effectiveness) unlocks config tuning and produces an explicit, SAMPLE-BASED go/no-go gate before paper trading (never calendar-based).

### 8. Reuse + discipline
Reuse the quant performance tools (Sharpe/Sortino/returns/attribution/max-DD — Phase 3), `run_weekly`/`thesis_scan`/`select_book`/sizing (Phase 5/6.5), the desk pipeline (Phase 4/5/6/6.7), the stores (`bars_asof`/`universe_as_of`/catalyst). Layer A is pure deterministic Python; Layer B reuses the real desk behind guardrails. Full TDD (`.venv/bin/python -m pytest`, bare python NOT on PATH), fully offline (synthetic history fixtures; Layer B mocks run_structured). Graphify graph-first (2593 nodes, fresh).
</decisions>

<code_context>
## Existing Code Insights

**Graphify LIVE + fresh (2593 nodes).** Navigate via `graphify explain <symbol>` — do NOT re-read src/. Reuse: `quant/performance.py` (Sharpe/Sortino/returns/attribution/max-DD), `store.py` (`bars_asof` point-in-time price history — the backtest's price source), `universe/build.py::universe_as_of` (survivorship-free membership), the catalyst store, `desk/weekly.py::run_weekly` + `quant/weekly.thesis_scan` (the mechanics Layer A replays), `desk/orchestrator.py`/`desk/md.py` (the real pipeline Layer B replays behind guardrails), the `run_structured` seam (Layer B mocks it). Likely new module(s): `backtest/` (Layer A mechanical engine, the event-set builder, the fill model + slippage/latency knobs, the guardrail gate, Layer B guarded replay + labeling).
</code_context>

<specifics>
## Specific Ideas
Success criteria: ROADMAP Phase 7 (5 criteria). Requirement IDs: BACK-01, BACK-02, BACK-03, BACK-04, BACK-05, OPS-03.
Key honesty invariants: pessimistic gap-open fill on held-through binaries; data-latency knob (no look-ahead on delayed free data); Layer B labeled biased-optimistic; survivorship-free event set; sample-based go/no-go; no silent truncation (log dropped events). The backtest must measure the CORRECTED strategy (weekly cadence, target-within-cap sizing, no-zero-trade).
</specifics>

<deferred>
## Deferred Ideas
- The paper ledger (Layer C, forward out-of-sample) — Phase 8.
- Live free-data fetchers — data-layer component (backtest uses historical fixtures + the latency knob to simulate their lag).
- Config auto-tuning from the baseline — the gate UNLOCKS it; the actual refit loop is Phase 10.
</deferred>
