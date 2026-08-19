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
- 2026-08-19: STEP 1 COMPLETE. plan→check(REVISE:1 blocker fixed)→execute(3/3, 13 tests)→live cache pull(75/76 tickers, 7542 daily bars, price_bar untouched)→backtest. Commits pushed (06efd21). **NEGATIVE RESULT:** weekly Sharpe 1.30 → daily reflex -2.13; avg_win 35%→6.7% (reflex CUTS WINNERS, keeps losers); T+0<T+1<T+2 latency inversion (delay HELPS → reflex fires on transient dips pre-event); off_map only 0.9% (NOT where money leaks); coverage 36.8% (possible apples-to-oranges — weekly on all legs, daily on 42). FINDINGS.md written.
- 2026-08-19: STEP 2 dispatched — analyst to (1) verify "reflex exits pre-event, cuts catalyst winner" hypothesis w/ instrumented exit-reason×pre/post-event breakdown, (2) explain T+0<T+1<T+2 mechanically, (3) FIX apples-to-apples (weekly vs daily on SAME 42 covered legs), (4) draft ranked mitigations. Early read: Task B (off-map, 0.9%) likely DEFER; fix on-map reflex timing (holds_through pre-event) first.
- 2026-08-19: STEP 2 COMPLETE (MITIGATIONS-DRAFT.md + scripts/_diag_exit_breakdown.py). Root causes CONFIRMED w/ numbers: (#1) reflex ignores holds_through_catalyst — 45/48 covered legs price-exited, only 3 on time; (#2, DOMINANT) thresholds calibrated to weekly drift → tp sits ~1% above entry → sells first tick, tp bucket alone -133pp, cuts 7 real winners from +107% mean to +3.77%; (#3) T+0<T+1<T+2 inversion REAL (identical reason mix, only fill bar shifts; max ret +32%→+458%) — not a bug, symptom of #2. Apples-to-apples FIXED: same 48 legs weekly +12.68% vs daily -4.18% (~810pp destroyed) — reflex genuinely destroys edge. Task B = DEFER (off_map ~2%). Mitigations M1(suppress price exits pre-event on hold-through; catastrophic-gap guard only)+M2(recalibrate to catalyst magnitude / kill noise tp / hold_and_trail)+M3(tp fill semantics/off_map flag)+M4(paired-subset headline).
- 2026-08-19: STEP 3 dispatched — adversarial skeptic/PM vet. Key challenges: (a) DON'T curve-fit thresholds to 48-leg/7-winner in-sample-biased set (structural rules safe, tuned params dangerous); (b) does M2 trailing stop smuggle back CEO-rejected technicals?; (c) M1/M2 magic-number check (2·vol_move guard, trail dist → params dict?); (d) re-verify no-look-ahead; (e) is off_map artificially low b/c reflex mislabels off-map as tp/band (would change Task-B calculus)? Expect: adopt M1-as-principle + M4, MODIFY/trim M2 to structural-only, likely reject tuned parts.
- 2026-08-19: STEP 3 COMPLETE (MITIGATIONS-VETTED.md). Every draft number reproduced. Verdicts: M1 MODIFY→WIDEN to WHOLE-HOLD suppression (pre-event-only fixes just -11.4pp; dominant damage is post-event -189.5pp) + CUT catastrophic-gap guard (magic number + contradicts sizing-is-the-stop). M2 REJECT (trailing=smuggled technical + Kaminski-Lo says destroys value on fade; catalyst re-anchor=PHANTOM input, Layer-A up_move is weekly base-rate not football-field). M3 REJECT off_map-flag + DEFER close-confirm. M4 ADOPT + in-sample warning + entry-basis caveat + post-fix off_map re-emit. Task B DEFER (provisional — re-measure off_map post-M1). Apples-to-apples sound for DIRECTION not levels (entry-basis mismatch: weekly@close vs daily@next-open). SCOPE = M1(whole-hold)+M4 only, NO threshold tuning.
- 2026-08-19: STEP 4 dispatched (quick 260819-x4m, full GSD) — M1 whole-hold price-exit suppression (held_through → only time-barrier fires; ~15 lines reflex_exit+_fill_leg; non-hold-through unchanged) + M4 paired-subset headline w/ caveats. Then re-run backtest to prove daily hold-through ≈ weekly (edge restored). Task B decision (Step 5) after off_map re-measure.
- 2026-08-19: STEP 4 plan-check REVISE→fixed. Guard placement CONFIRMED correct (time-barrier at TOP of reflex_exit loop, reachable after `continue`). BLOCKER-1: a SECOND pre-fix test (test_backtest_latency_sweep.py::test_off_map_leg_carries_flag) also asserts old band-exit/off_map — both tests updated to new time-exit contract. CONCERN-1: don't lift _diag collect() verbatim (empty under --smoke) → derive paired subset from computed LegOutcomes. Plan patched, executor dispatched. WATCH: Task-3 re-run paired daily-vs-weekly (edge restored?) + re-measured off_map (Task-B go/no-go).
- 2026-08-19: STEP 4 COMPLETE + VERIFIED 4/4 (commits 45db37e/7fb2054/802b27c/4dc633a, not yet pushed). **EDGE RESTORED:** daily reflex paired mean -4.18% → +7.67% (was destroying ~810pp, now net-positive); off_map 0.0%. Full suite 1588 pass. Backward-compat sacred. Verifier CHALLENGE (key insight): residual daily+7.67 vs weekly+15.31 is NOT noise — weekly exits at the event GAP-OPEN (captures the pop), daily holds to time-barrier (rides the fade). The winning behavior = EXIT AT THE EVENT. Corrects the vetter's "weekly=hold-to-barrier" premise (it's hold-to-gap-open).
- 2026-08-19: STEP 5 DECISION (STEP5-TASKB-DECISION.md): original Task B (off-map brain) = PERMANENT DEFER (off_map 0.0%, not where value is). REAL next lever = event-anchored EXIT TIMING (exit at event-resolution/gap vs hold-to-barrier), but calibrate on the FORWARD PAPER MONTH, NOT the 42 in-sample legs (curve-fit trap). Fixed exit engine is paper-ready. CHAIN COMPLETE — building morning artifact + push.
