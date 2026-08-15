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

### LOCKED USER DECISION — single-leg / no-hedge construction (2026-08-15): estimated-move-driven position building
When no valid hedge exists (the DEFAULT), the trade builder does NOT just "size tiny and pray." It builds a single-leg long position engineered to minimize downside while the WEEK'S BOOK targets ~1%:
1. **Estimate the catalyst's +/− payoff distribution FIRST** — P(positive) from the Phase-4 verdict + KB analogs + base rates; up-move and down-move magnitudes from `quant.implied_move` + historical catalyst-gap distribution for that catalyst TYPE (PDUFA vs Ph3 readout vs conf). This distribution is the input to everything else. Agents interpret; the quant tools compute the distribution — no eyeballed magnitudes.
2. **The estimate drives hold-through vs exit-before-event.** Positive expected value AND survivable downside → may hold through. Otherwise exit before the print (capture the run-up, dodge the gap) or pass.
3. **Downside control depends on which regime the trade is in — and the SL is honest about the gap:**
   - **Hold-through-the-binary:** the ONLY real downside control is POSITION SIZE (risk-of-ruin / fractional-Kelly on the estimated DOWN-move, not a generic −70%). A stop-loss CANNOT fill inside an overnight gap — it executes at the gapped open. So on hold-through legs the "stop" is sizing + the exit-before decision, and any SL is labeled explicitly as gap-exposed / advisory.
   - **Exit-before-event & continuous drift:** adaptive SL/TP ARE the real control (price moves continuously). Set them from data — TP anchored near the estimated up-move, SL from volatility (ATR / implied move), both adaptive to the estimate, not fixed %.
4. **1% is a BOOK-level target, not a leg-level sizing input.** Selection + aggregate construction aim the week's probability-weighted expected return at ~1%; each individual leg is still sized survival-first. Zero-trade weeks remain allowed. This reconciles "target 1%" (shapes the book) with "never size toward 1%" (governs the leg).
5. New/extended quant surface likely needed: a catalyst-move estimator (probability-weighted expected move + up/down magnitudes from base rates + implied move + analog gaps) and an adaptive SL/TP tool that takes the estimated distribution + regime and returns levels — both returning frozen `ToolResult`. Reuse `implied_move`, `conditional_payoff`, `risk_of_ruin`, `fractional_kelly`, `sl_tp` where they already cover it; extend rather than duplicate.

### LOCKED USER DECISION — SL/TP & estimator are MODEL-FIT and grow over time (2026-08-15)
The SL/TP and catalyst-move-estimator tools are NOT static heuristics with hardcoded constants. They are dedicated deterministic tools whose PARAMETERS are FIT FROM DATA (statistical models over historical + accumulating outcomes) and REFIT as the playbook grows:
1. **Every threshold is model-derived, never hand-tuned.** Per-catalyst-type gap distributions, drift coefficients, volatility multipliers, TP/SL bands — all come from fitted models over the historical catalyst set + the realized-outcome playbook. No magic numbers in the tool body; constants that must exist are bootstrap parameters loaded from data, clearly labeled as such.
2. **Playbook-parameterized read seam (built NOW, in Phase 5).** The tools read their parameters from the KB/playbook (a `params` input or a `load_sl_tp_params(catalyst_type)` seam), with a bootstrap parameter set derived from base rates / historical gaps so the tools work from trade #1. The tool stays deterministic + fully offline-testable (params passed in → frozen ToolResult); only the SOURCE of params changes over time.
3. **The refit LOOP is Phase 9 (LEARN/continuous-iteration), not Phase 5.** Phase 5 builds the tools + the seam + the bootstrap params + the playbook records that will later be refit against. Phase 9 closes the loop: realized outcomes → refit params → tools improve. Do NOT build the refit loop in Phase 5; DO build the seam so Phase 9 slots in without a rewrite (mirror the options-ready-hedge abstraction discipline).
4. **Provenance holds:** a fitted parameter set is itself evidence — record which data/model produced it so a level can always be traced back (no unsourced number, consistent with the desk's cite-or-drop invariant).

### LOCKED USER DECISION — trade builder VETS the estimator/SL-TP assumptions before consuming them (2026-08-15)
The `catalyst_move_estimate` and `adaptive_sl_tp_levels` outputs are not trusted blindly. A builder-side VETTING GATE (an agent role, mirroring `desk/verifier.py`'s source-quote-or-drop machinery — reuse it, don't rebuild) independently audits the ASSUMPTIONS and INPUTS behind those outputs from the trade builder's point of view, so garbage-in is caught before it becomes a position. Critically: the gate audits assumptions + evidence, it does NOT recompute money numbers — "agents never do arithmetic" stays intact (the deterministic tools already own the math and are unit-tested).
1. **Input provenance (cite-or-drop applied to model inputs).** Every input to the estimator — P(positive), the analog set returned by `analog_query`, the `implied_move` value, the catalyst-TYPE classification, the vol proxy — must trace to a cited source. An uncited input is dropped, exactly as an uncited claim is in Phase 4.
2. **Analog comparability.** Are the KB analogs actually comparable to THIS catalyst (same type, similar phase/indication/drug-class)? Reject cherry-picked or off-type analogs feeding the gap distribution.
3. **Consistency.** P(positive) consistent with the Phase-4 DebateVerdict direction/confidence; the estimated down-move consistent with base rates for the type; SL/TP levels consistent with the estimated distribution AND the chosen regime (a hold-through leg's SL must be flagged gap-exposed/advisory — a non-advisory SL on a hold-through leg is a rejectable inconsistency).
4. **Cold-start / small-n red flags.** If the analog set is too thin, the gate flags reliance on the implied-move fallback and requires the estimate to widen uncertainty / shrink toward base rate rather than overclaim from a handful of points.
5. **Blocking.** A rejected estimate BLOCKS the trade from finalizing (mirrors Phase-4 blocking unsupported verdicts) → forces re-derivation with vetted inputs or a pass (zero-trade weeks allowed). The vetting verdict (endorse / reject-with-reasons) is recorded on the dossier as part of the audit trail.

### Claude's Discretion (rest)
Follow ROADMAP criteria + PROJECT.md + CLAUDE.md. Reuse Phase-3 quant tools (conditional_payoff, risk_of_ruin, fractional_kelly, cointegration, sl_tp, concentration, exposure — all return ToolResult), the Phase-2 KB hedge-relationship store + analog query, the Phase-4 DebateVerdict as input, and the contracts (TradeProposal, RiskAssessment, StrategyDossier). Agents interpret; the quant tools compute. Full TDD, offline (mock the run_structured seam; no live API). SL/TP is ADVISORY only (a stop can't save you across a binary gap — sizing + exit-timing are the real controls).
</decisions>

<model_forms>
## Model Forms to Implement (from `.planning/research/single-leg-microstructure.md` — READ THAT FILE for citations + full derivation)

The estimator/SL-TP/sizing tools implement these SPECIFIC, cited forms — not ad-hoc heuristics. Every threshold is a loaded param (see the model-fit decision), never a literal.
- **Catalyst move estimator** = two-state up/down MIXTURE with `P(positive)` as the mixing weight; outputs separate `up_move` (u), `down_move` (d), `sigma`. Core ALWAYS-AVAILABLE source = historical gap distribution per **catalyst-type × cap-tier** (from the KB `Outcome` nodes) — the estimator MUST work from this alone (offline, from trade #1). Options-implied move (straddle-implied / IV term-structure) is a PLUGGABLE ENRICHING input behind an `implied_move` SOURCE SEAM, NOT a hard dependency: when options data is present it corroborates/tightens the estimate; when absent the estimator falls back to the historical-gap core with no loss of function. Source of that options data is a data-layer concern (RH read + external options-chain + the dedicated web-scraper agent — see PROJECT.md) sitting behind the seam; Phase 5 builds the seam + the offline core, NOT the scraper. Small-cap binary magnitudes (±30-70%) are UNVERIFIED → must be fit from the desk's own accumulating gap dataset, shrunk toward the dense earnings pool when the drug cell is thin.
- **Hold-through vs exit-before** = decide by **expected-LOG-growth** (Kelly-consistent, penalizes the fat down-tail), NOT raw expected value.
- **Adaptive SL/TP** = `TP = entry·(1 + k·u)`; `SL = n·ATR` or `z·σ√t`. Three-regime rule is structural: SL is a real control for exit-before-event + post-gap drift; it is FALSE COMFORT across a held binary print (gap-exposed → advisory label, already locked).
- **Sizing** = fractional Kelly `f* = E[R] / (u·d)` — the estimated `down_move` (d) is in the denominator (reuse `fractional_kelly`/`risk_of_ruin`, pass estimated d, never −70% generic); risk-of-ruin cap differs by regime (f·d for hold-through vs f·stop-distance for exit-before).
- **Book selection to ~1%** = CVaR-constrained selection (Rockafellar–Uryasev) toward ~1% as an OUTCOME not a sizing input (the `select_book` selector, forbidden from resizing any leg above its survival size).
- **Entry timing** = regression of pre-event drift on run-up CAR / volume / short-interest; entry day T−2/T−1 is HEURISTIC until fit. Fine to bootstrap heuristic + leave the fit seam.

**Honest data gaps (design around, don't fake):** no live options feed (options-implied = reference-only); ~1yr history thin for drug cells (shrinkage to earnings pool); small-cap magnitudes fit-from-own-data only.
</model_forms>

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
