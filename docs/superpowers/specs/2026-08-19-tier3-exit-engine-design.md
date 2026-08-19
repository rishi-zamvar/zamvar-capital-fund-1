# Tier 3 — Exit Engine Design (approved 2026-08-19)

**Status:** Approved. Building Task A (reflex + honest-latency backtest) first; Task B (off-map agentic brain + re-entry) next.

## Principle
Research (3 briefs: event-driven exit management, execution mechanics, agent-set adaptive levels) is unanimous: **spend judgment at ENTRY, execution at the EVENT.** This resolves the speed-vs-reasoning tension — the agent reasons where it has time (before the catalyst); the moment of the event is pre-decided. No technical-indicator combinations (levels are structural, tied to the thesis and the expected move).

## ① The Exit Plan — authored at entry (agent-set, data on the position)
- **expectation_band** [low, high] from the options-implied expected move + football-field. The "no-stop zone": moves inside it are noise → no reaction.
- **scenario table**: approval / rejection / mixed / delay, each with a probability + football-field target + a PRE-COMMITTED action (hold-and-trail the pop · exit on the open · exit half · lean on pairs hedge).
- **thesis_invalidation**: typed triggers (outcome, magnitude_floor, disqualifying_news[]) — exit if the reason breaks, up or down.
- **survival-first sizing**: a full rejection-scenario loss must be survivable; sizing IS the stop (no stop fills through a biotech gap/halt). Vol-scaled (best-evidenced lever).
- **time barrier**: hard exit by Friday / end of session after resolution (IV-crush + weekly-flat discipline). Triple-barrier = TP / thesis-stop / TIME, first to hit.
- **EV-flip guard**: after a big pre-event run-up, compare remaining approval-branch upside×P vs rejection downside×(1−P); when negative, trim/exit pre-event even if the outcome is likely ("am I the exit liquidity?").

## ② The Reflex — executes at the event (deterministic, no reasoning)
- Runs at the monitoring-granularity knob. Watches: price vs band, adaptive stop, TP, and CATALYST-RESOLUTION signals (trading halt, fresh 8-K on EDGAR, gap) — NOT technicals.
- Reads outcome → compares to band → fires the pre-stored branch action instantly.
- Halted → hold the pairs hedge (the one lever available during a halt) → act on the resumption print.
- OFF-MAP outcome only → escalate to a single reasoning agent (Task B). This is the only "reason before exit" case; everything on-map is pre-committed.

## ③ Honest backtest timing (the CEO's latency requirement)
- Signal-at-close → fills at the NEXT bar on ENTRIES AND EXITS (no same-bar fill bias).
- Stops modeled at the GAP OPEN, not the stop price. Halts fill at the re-open auction.
- Granularity knob: backtest hourly, paper 15-min; pessimistic same-bar rule.
- T+0 / T+1 / T+2 latency sweep — an edge that only survives at T+0 is fragile.
- Off-map reasoning path carries a reasoning-latency parameter (calibrated from the live paper month) → agentic decisions fill at the market price AFTER the reasoning time.

## Re-entry
Never reflexive. Post-event, re-underwrite as a fresh thesis once price discovery settles (Task B; optional post-event fade is a separate, clearly-labeled module).

## Build sequencing
- **Task A (now):** Exit Plan (scenario table, band, thesis-invalidation, survival sizing, time barrier, EV-flip) + deterministic reflex execution + latency-honest backtest (gap-open fills, halt handling, T+0/1/2 sweep). Safety-critical core; makes the production-replica backtest runnable.
- **Task B (next):** off-map agentic brain (the single reasoning-before-exit escalation, reasoning-latency-modeled) + re-entry logic.

## Reuse (no rebuild)
adaptive_sl_tp_levels, size_for_survival, hold_vs_exit, the weekly engine (desk/weekly), md.reconcile, backtest/engine (already has a pessimistic same-bar rule + granularity). Wire the scenario-conditioned Exit Plan + the honest latency model into these.

## Key research anchors
Kaminski & Lo (stops add value only in momentum, destroy it in mean-reversion → don't stop inside the band pre-event; trail only post-event trend). Straddle×0.85 ≈ 1σ expected move, but binaries are bimodal → size by band, EXIT BY SCENARIO not σ. BioCatalysts "why good news fails" (EV-flip after run-up). No-stop-through-a-gap → sizing + pairs-hedge + (later) options collar are the real gap defense.
