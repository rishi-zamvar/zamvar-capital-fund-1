# Overnight Autonomous Run — 2026-08-19 (CEO out for the night)

CEO authorized a full autonomous chain, all with **full GSD** (plan → plan-check → execute → verify). Lock decisions upfront, run uninterrupted, report in the morning. This runbook is the durable spine so the chain survives any compaction.

## The chain (sequential — each step gates the next)

- [ ] **STEP 1 — Production-replica backtest (quick 260819-p1x, full GSD).**
  Wire the REAL daily price feed (`providers.prices.get_daily_bars`) into the backtest daily path as an as-of-scoped, cache-first `daily_bars_provider`; run the honest daily+latency backtest over the warm-playbook events; produce a weekly-vs-daily comparison + T+0/1/2 latency sweep report.
  - Frugality (MANDATORY): cache-first; ONE wide-window daily pull per DISTINCT ticker covering all event windows, not per-event; free source first (get_daily_bars already ranks Tiingo/Nasdaq daily); enumerate distinct tickers + report intended call volume BEFORE any pull; degrade gracefully (missing bars → that event abstains, never errors/blocks).
  - No-look-ahead: provider scoped to [as_of, exit_by]; reflex already reads signal-bar-onward.
  - Output: `260819-p1x-FINDINGS.md` (weekly vs daily outcomes, latency degradation, data-coverage %, abstain count).

- [ ] **STEP 2 — Analyze + draft mitigations (me, after Step 1 verifies).**
  Read the backtest results. Identify failure modes / error sources (data gaps, degenerate fills, look-ahead leaks, halt handling, thin coverage, unstable edge under latency, etc.). Draft concrete mitigation techniques for each. Write `MITIGATIONS-DRAFT.md`.

- [ ] **STEP 3 — Vet mitigations (separate independent agent).**
  Spawn a skeptic / hedge-fund-PM-lens agent to adversarially vet the mitigations: which are real fixes vs cosmetic, which introduce new bias/look-ahead, which are over-engineering. Verdict per technique: adopt / modify / reject + why. Write `MITIGATIONS-VETTED.md`.

- [ ] **STEP 4 — Implement vetted mitigations (full GSD, quick task).**
  Only the adopt/modify techniques. TDD, reuse, no new magic numbers. New quick task.

- [ ] **STEP 5 — Task B go/no-go (decided from the data).**
  Criterion: is the off-map / judgment layer where the money actually leaks? Look at Step-1 off_map leg frequency + whether daily-reflex-vs-weekly gains are concentrated in cases a deterministic reflex mishandles. If YES → build Task B (off-map agentic brain: single reason-before-exit escalation with reasoning-latency-modeled fill + re-entry) with full GSD. If NO → document why deferred, don't build.

## Locked decisions (do NOT re-ask)
- Daily source = get_daily_bars cascade (free-first), cache-first, one wide pull/ticker.
- Backtest = daily granularity, latency sweep T+0/1/2, weekly path stays the byte-for-byte baseline for comparison.
- Backtest bias is ACCEPTED (same-history overfit is for config tuning; forward paper month is the real proof) — do NOT treat optimism as a bug, but DO flag if daily+latency ERASES the edge entirely.
- All tests offline/in-memory where code; the live data pull is a vetted main-dir step.
- Mitigation vetting = independent agent, adversarial.
- Task B is conditional on Step-1 evidence.

## Morning deliverable
A single published HTML artifact summarizing the whole overnight run: what Task 1 found, the mitigations (drafted → vetted → implemented), and the Task B decision with its evidence. Hand the CEO the URL.

## EXECUTION-MODEL CORRECTION (CEO question 2026-08-19 — fold into Step 2 analysis)
Verified the Robinhood MCP order surface: `place_equity_order` supports `stop_market`/`stop_limit` + `stop_price` + `time_in_force=gtc`. So ON-MAP exits are RESTING SERVER-SIDE orders placed at entry — NO agent in the loop, ~zero reasoning latency:
- SL = resting `stop_market` (gtc); TP = resting `limit` (gtc). Broker triggers at market on cross.
Caveats (already modeled in Task A, keep honest):
1. `stop_market` fills at MARKET on trigger → through a gap/halt = the GAP-OPEN, not the stop level. Sizing is the real defense, not the stop.
2. Stops are REGULAR-HOURS-ONLY → overnight/pre-market catalyst prints don't fire a resting stop; it queues to the regular open and fills the gap. (= the gap-open the backtest assumes.)
3. NO native OCO/bracket in the MCP → when one of SL/TP fills, WE must cancel the sibling (`cancel_equity_order`). Lightweight poll+cancel loop, NOT agent reasoning.
**Modeling consequence for Step 1/2:** `exit_latency_bars` is currently a GLOBAL knob, but reasoning latency applies ONLY to the OFF-MAP (Task B) path. On-map SL/TP legs = broker-side, model at gap-open/next-bar with ~zero reasoning delay. Attribute the latency-sweep degradation to off-map legs; do NOT penalize resting SL/TP with reasoning latency. This split is itself a candidate mitigation to implement in Step 4 (make latency per-exit-type, not global).

## Progress log
- 2026-08-19: chain authorized, runbook written, Step 1 planner dispatched.
- 2026-08-19: CEO asked re SL/TP latency → verified RH resting-stop support, logged execution-model correction above (per-exit-type latency, on-map = broker-side/no agent).
