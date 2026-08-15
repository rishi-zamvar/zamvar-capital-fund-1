# Phase 5: Trade Builder, Honest Hedge & Ruin-Avoidant Sizing (Workflow 1b/2) - Context

**Gathered:** 2026-08-15
**Status:** Ready for planning
**Mode:** Auto-generated (discuss skipped) + one locked user decision (hedging strategy)

<domain>
## Phase Boundary

Turn the week's catalyst calls (Phase-4 DebateVerdicts) into ONE recommended portfolio: build each trade, honestly validate/select the hedge, size for survival, run the 3-way risk debate, and have the MD/PM promote or kill into a StrategyDossier. Stops at the dossier for review — NO live execution (Phase 11), NO catalyst prediction (that's Phase 4).
</domain>

<decisions>
## Implementation Decisions

### LOCKED USER DECISION — hedging strategy (2026-08-15): "Both — survival-size now, options-ready"
The pair-correlation research proved long-only STOCK pairs mostly do NOT hedge (only ~1-in-5, none statistically airtight; PHVS/BCRX was empirically an ANTI-hedge). Therefore Phase 5:
1. **Survival-first sizing is the backbone** — risk-of-ruin / fractional-Kelly on a −70% binary gap; the ~1%/week target is a MEASURED outcome, NEVER a sizing input; zero-trade weeks are allowed.
2. **Pair ONLY where mechanism AND data both validate the inverse** — the Risk agent runs `quant.conditional_payoff` (+ cointegration, catalyst-clean check) PER TRADE against KB analogs. NO hardcoded/assumed pairs (PHVS/BCRX proved same-disease ≠ hedge). If the peer doesn't reliably rise when the target falls on THIS catalyst → reject the hedge.
3. **No-valid-hedge is the DEFAULT, not the exception** — fall back to size-tiny or exit-before-event. Never a fake hedge.
4. **LABD (inverse biotech ETF) only as a sector-beta damper** for event-week, explicitly labeled as NOT hedging the idiosyncratic binary.
5. **Options-ready architecture** — model the hedge as an abstraction (e.g. a `Hedge` protocol / instrument type) so a put-option hedge slots in later WITHOUT a rewrite, even though v1 is equities-only. Do NOT build options execution now; just don't foreclose it.

### Claude's Discretion (rest)
Follow ROADMAP criteria + PROJECT.md + CLAUDE.md. Reuse Phase-3 quant tools (conditional_payoff, risk_of_ruin, fractional_kelly, cointegration, sl_tp, concentration, exposure — all return ToolResult), the Phase-2 KB hedge-relationship store + analog query, the Phase-4 DebateVerdict as input, and the contracts (TradeProposal, RiskAssessment, StrategyDossier). Agents interpret; the quant tools compute. Full TDD, offline (mock the run_structured seam; no live API). SL/TP is ADVISORY only (a stop can't save you across a binary gap — sizing + exit-timing are the real controls).
</decisions>

<code_context>
## Existing Code Insights

**Graphify LIVE + fresh.** Navigate via `graphify explain <symbol>` / the graphify skill — do NOT re-read the src/ tree. Reuse: `quant/` (conditional_payoff, risk_of_ruin, fractional_kelly, cointegration, sl_tp, concentration, exposure), `kb.py` (hedge_peers, analog_query — validate, don't trust), `contracts/` (TradeProposal, RiskAssessment, StrategyDossier — extend if a field is missing, mirroring the Phase-4 DebateVerdict extension), `desk/` (runtime seam, evidence, orchestrator pattern — the 3-way risk debate + PM reuse the debate/verifier machinery). New module likely `desk/portfolio.py` or `desk/builder.py`.
</code_context>

<specifics>
## Specific Ideas

Success criteria (from ROADMAP):
1. Trade Builder selects an inverse-payoff peer (cointegration-validated, catalyst-clean over the hold), sets entry, hold-vs-exit-before-event, advisory-only SL/TP.
2. Risk agent re-analyzes each hedge conditional on THIS catalyst → conditional payoff matrix; no valid inverse peer → flag + fall back to size-tiny/exit (never a fake hedge).
3. 3-way Risk Committee (aggressive/conservative/neutral) sizes for survival via risk-of-ruin/fractional-Kelly on a −70% gap; 1% is a measured outcome; zero-trade weeks allowed.
4. Each trade ships a position memo with explicit kill criteria + a documented pre-mortem, authored separately from approval; MD/PM promotes/kills against the live book → StrategyDossier stating residual net-long risk + which risk is actually covered.

Requirement IDs: PORT-01..05, HEDGE-01..05, OPS-01, OPS-02.
</specifics>

<deferred>
## Deferred Ideas

- Options/put-hedge EXECUTION (architect for it, don't build it) — v2 / when options access exists.
- Live order placement — Phase 11.
- Independent diligence on the built portfolio — Phase 6.
</deferred>
