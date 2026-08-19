# Quick 260819-p1x — Root Cause + Mitigations (DRAFT)

Analysis of why the daily "reflex" exit turns a **+1.30 Sharpe** weekly baseline into a
**-2.13 Sharpe** disaster. Evidence from `scripts/_diag_exit_breakdown.py` (throwaway diagnostic,
cache-only `allow_fetch=False`, over the real `daily_bar` cache, window 2025-08-17 → 2026-08-10).

---

## TL;DR — the two decision inputs first

**1. Is the apples-to-apples comparison fixed? YES — and the reflex STILL loses badly.**
The original FINDINGS §1 compared weekly-on-108-legs vs daily-on-108-legs, but those leg
populations differ (weekly fills every catalyst leg from the weekly store; the daily path only
fills the ~42–48 legs the daily cache covers, and drops the rest). I re-ran the fair comparison:
**the same covered catalyst legs, priced both ways.** On the identical 48 covered legs:

| Path (same 48 legs) | mean return | win rate | avg_win | avg_loss | sum of returns |
| ------------------- | ----------- | -------- | ------- | -------- | -------------- |
| **Weekly hold** | **+12.68%** | 47.9% | +33.61% | -6.57% | **+608.8%** |
| **Daily reflex (T+0)** | **-4.18%** | 45.8% | +8.61% | -15.01% | **-200.8%** |

The reflex destroys **~810 return-points on identical legs** (weekly-minus-daily = +809.6%). It
**hurt 24 legs, helped 18, ~same on 6**. This is **not** a coverage/measurement artifact — on a
byte-for-byte identical leg set the reflex mechanically vaporizes the edge. The negative result is
real.

**2. Task-B go/no-go: FIX THE REFLEX FIRST, DEFER Task B.**
off_map is **1/48 covered legs (~2%)**. The money is **not** leaking in the off-map escalation
path — it is leaking in the **on-map reflex timing** (tp/band/stop firing on intraweek noise on
positions that are supposed to hold through the event). Building the Task-B off-map reasoning agent
now would be polishing a rounding error while the on-map path bleeds 800 points. **No-go on Task B
until the on-map reflex respects the hold-through-catalyst contract.**

---

## Root cause #1 — the reflex does NOT respect `holds_through_catalyst` (CONFIRMED)

**Evidence.** `reflex_exit` (`backtest/fill.py:127`) receives **no** `held_through` flag and **no**
`event_date` — only `time_barrier=exit_by`. The `holds_through_catalyst=True` flag threaded into
`adaptive_sl_tp_levels` (`quant/sizing.py:201`) only stamps `advisory=True` / a reason string into
the detail dict — **it never changes the stop/target values and the reflex never reads it.** So the
band-breach / adaptive-stop / take-profit branches fire on **any** triggering bar, before or across
the binary event. The whole design principle — *"hold through the binary event; the pre-event stop is
advisory because a gap jumps it; sizing is the defense, not the stop"* — is silently violated in the
daily path.

The 48 covered legs are all `held_through=True` catalyst legs, and the reflex exited **45 of them on
a price trigger** (band 23, tp 20, stop 2) and only 3 on the time barrier. A hold-through book should
be dominated by time-barrier / post-event exits, not intraweek price stops.

## Root cause #2 — exit thresholds are calibrated to WEEKLY drift, so they fire on daily NOISE (CONFIRMED, dominant)

**Evidence.** The band/stop/target are built from weekly-scale numbers:
- `vol_move = stat_gap = |hard_veto_drop| = 0.15` → `sl_pct = sl_vol_mult(1.0)·0.15` → **stop = 0.85·entry**, and **band lower = 0.85·entry** (identical).
- `up_move = ev = base-rate mean_next`, floored at `target_weekly = 0.01` → **band upper = entry·(1+up_move) ≈ entry·1.01–1.05**.
- `tp_pct = tp_frac(0.8)·up_move` → **target = entry·(1+0.8·up_move) ≈ entry·1.008–1.04** — *below* the band upper, so **take-profit is the binding upside constraint and it sits ~1% above entry.**

A biotech name into a binary catalyst routinely swings several percent intraday. So the reflex
**take-profits on the first intraday tick ~1% above entry**, then fills at the next bar's open —
which for a pre-event blip is often a gap *down*. That is why the tp bucket has a **negative** mean
return:

| exit reason | n | pre-evt | post-evt | mean return | sum of returns |
| ----------- | -- | ------- | -------- | ----------- | -------------- |
| tp | 20 | 8 | 12 | **-6.66%** | **-133.25%** |
| band | 23 | 6 | 17 | -0.56% | -12.96% |
| stop | 2 | 0 | 2 | -13.70% | -27.39% |
| time | 3 | 0 | 3 | -9.07% | -27.20% |

**The `tp` bucket alone burns -133 points** — a "take-profit" that produces losses because it sells
the start of every move and fills into reversals. The `avg_win` collapse is direct: on the covered
subset weekly `avg_win` = **+33.61%** → daily `avg_win` = **+8.61%**. Of the **7 real catalyst
winners** (weekly return > +5%, mean **+107.14%**), the reflex cut them to a **mean +3.77%**. That
single line is the "avg_win 35% → 6.7%" smoking gun.

**Pre- vs post-event nuance (honest correction to the leading hypothesis).** The leading hypothesis
was "the reflex exits *pre-event* on noise." Partly true, but **not the dominant channel**:
pre-event exits are 14/48 legs contributing only **-11.4pp**. The bulk of the damage is
**post-event** (34 legs, -189.5pp) — because the thresholds are so tight the reflex exits on the
*first touch* at the very start of a multi-day catalyst move and misses the bulk, and/or fills into
the reversal. So the true statement is: **the triggers fire far too early relative to the size and
duration of a catalyst move**, both before and after the event date.

## Root cause #3 — the T+0 < T+1 < T+2 inversion is REAL, and it proves #2 (not a bug)

**Evidence.** Re-running the paired 48 legs at each latency:

| latency | n | mean return | win rate | avg_win | max return | reason mix |
| ------- | -- | ----------- | -------- | ------- | ---------- | ---------- |
| T+0 | 48 | -4.18% | 45.8% | +8.61% | +32.3% | tp20 time3 band23 stop2 |
| T+1 | 48 | +8.49% | 45.8% | +38.27% | **+458.0%** | tp20 time3 band23 stop2 |
| T+2 | 48 | +9.39% | 35.4% | +54.89% | +425.4% | tp20 time3 band23 stop2 |

The **reason mix is identical across latencies** — the *trigger* bar is the same; only the *fill*
bar shifts. So the inversion is a pure fill-timing effect: the same too-early trigger, filled 1–2
bars later, catches more of the catalyst run (max return jumps +32% → +458%). This **rules out a
`degrade_to_last` artifact** (degrade only fires on window overshoot and would flatten, not inflate,
tail returns; the growing tails show real later bars being caught). Mechanically it confirms #2: the
exit signal fires at the *start* of the move, and only accidental execution delay lets you hold
through it. This is the strategy's own "hold through the event" thesis leaking back in through a bug.

---

## Mitigations (ranked by expected impact)

### M1 — Suppress price-based exits on a hold-through leg until `event_date` (catastrophic-gap guard aside)
- **(a) Problem it fixes:** Root cause #1. The reflex stop/band/tp-exits a hold-through position
  before the thesis (the catalyst) has even fired. Pre-event exits leak -11.4pp directly, and the
  contract violation is what lets #2 do its damage at all.
- **(b) Technique:** Thread `held_through` **and** `event_date` into `reflex_exit`. When
  `held_through` and `bar["week_end"] < event_date`, **only the TIME barrier and a catastrophic-gap
  guard may fire** — the band/stop/tp branches are skipped. The catastrophic guard is a wide, sizing-
  consistent floor (e.g. intraday `close < entry·(1 - 2·vol_move)`, i.e. a >30% pre-event collapse =
  fraud/halt/leak), *not* the ordinary -15% stop. On/after `event_date` the existing branches
  resume.
- **(c) Alignment:** This *is* the stated design — "spend judgment at entry, execute at the event;
  the pre-event stop is advisory because a gap jumps it; sizing is the defense." It makes the reflex
  finally honor the `advisory=True` flag `adaptive_sl_tp_levels` already computes.
- **(d) Risk / look-ahead:** No look-ahead — `event_date` is authored at entry (it is the thesis /
  the catalyst calendar, already on `rec["catalysts"][*]["event_date"]`). Risk: a genuine pre-event
  blowup you now sit through — mitigated by the catastrophic-gap guard and by the fact that sizing
  (`size_for_survival`) already assumes a -70% adverse gap. New bias: none; it removes an
  anti-thesis bias.
- **(e) Implementation surface:** `reflex_exit` signature (+`held_through`, `event_date` params,
  guard the three price branches); the daily branch of `_fill_leg` (`backtest/engine.py:209-230`) to
  pass them; `run_layer_a`'s catalyst loop already holds `cat["event_date"]` (`engine.py:300`) — pass
  it into `_fill_leg`. ~15 lines, no rebuild.

### M2 — Recalibrate the exit thresholds to catalyst magnitude; kill the noise take-profit for hold-through legs
- **(a) Problem it fixes:** Root cause #2 (dominant, -133pp from tp alone; avg_win 33.6%→8.6%). A
  target ~1% above entry is nonsensical for a binary that moves 30–100%.
- **(b) Technique:** For hold-through catalyst legs, (i) **drop the exit-on-first-touch tp entirely**
  and replace it with the exit plan's `approval_action="hold_and_trail"` — hold post-event, trail a
  stop a full `vol_move` below the running high; (ii) if a hard tp is kept, anchor it to the
  *catalyst* `approval_target = entry·(1+up_move)` using the estimator's **catalyst** move (not the
  1%-floored weekly `mean_next`), and require **close** past target, not an intraday high touch; (iii)
  widen the band upper to the same catalyst up-edge so a normal event pop doesn't breach it.
- **(c) Alignment:** The catalyst *is* the thesis — you must let the event move play out. `exit_plan.py`
  already authors `approval_target` and `approval_action="hold_and_trail"`; this wires the reflex to
  the plan that was already written at entry instead of a weekly-drift proxy.
- **(d) Risk / look-ahead:** Trailing gives back some open profit on a spike-and-fade (acceptable vs
  cutting every winner to +3.77%). No look-ahead — trail uses only realized highs to date. Bias risk:
  a too-wide band could let a real thesis-break run; M1's post-event stop and the time barrier bound
  it.
- **(e) Implementation surface:** `_fill_leg` daily branch (`engine.py:219-227`) — change how `band`/
  `target` are derived (use catalyst up-move, drop or re-anchor tp); optionally add a trailing-stop
  branch to `reflex_exit`. `adaptive_sl_tp_levels` unchanged (it already flags advisory). ~20–30 lines.

### M3 — Fix take-profit fill semantics (exit-on-touch-into-gap = mislabeled loss)
- **(a) Problem it fixes:** The residual of #2 — a tp that triggers on an intraday high but fills at
  a next-open *below* entry is a loss wearing a "tp" label (mean tp return -6.66%).
- **(b) Technique:** Post-event, trigger exits on **close confirmation** rather than intraday touch,
  and when a tp/band trigger fills worse than the trigger reference, **flag it off_map** (it's a
  regime the plan didn't anticipate) rather than silently booking it as a clean take-profit.
- **(c) Alignment:** Honest execution modelling; surfaces genuine off-map events to Task B instead of
  hiding them inside a mislabeled tp.
- **(d) Risk / look-ahead:** Close-confirmation adds a bar of exposure (bounded by M1's post-event
  stop). No look-ahead. Largely subsumed by M1+M2 — low marginal effort once those land.
- **(e) Implementation surface:** `reflex_exit` trigger conditions (`fill.py:187-208`). Small.

### M4 — Measurement hygiene: report the paired covered-subset comparison as the headline
- **(a) Problem it fixes:** The original FINDINGS §1 weekly-vs-daily is apples-to-oranges (different
  leg populations). It understated the reflex damage on the catalyst legs and mixed in unchanged
  statistical/defensive legs.
- **(b) Technique:** Have `run_daily_backtest.py` also emit the **paired catalyst-leg** stats (each
  covered leg priced weekly *and* daily) — the comparison in this doc's TL;DR table — as the primary
  go/no-go input.
- **(c) Alignment:** Trustworthy metrics before any capital decision (CLAUDE.md paper-first rigor).
- **(d) Risk / look-ahead:** None — reporting only.
- **(e) Implementation surface:** `scripts/run_daily_backtest.py` (add a paired-subset section);
  reuse the collection logic from `scripts/_diag_exit_breakdown.py`. No engine change.

---

## Ranking rationale

M1 + M2 together are the fix: M1 restores the hold-through contract (unblocks the strategy's actual
edge), M2 stops the weekly-drift thresholds from harvesting noise (recovers the -133pp tp bleak and
the avg_win collapse). Expected effect: the daily path should converge toward — and, via a genuine
post-event trailing exit, potentially *beat* — the +12.68% paired weekly mean, instead of -4.18%. M3
is cleanup that mostly falls out of M1+M2. M4 is non-code hygiene so the next run is trustworthy.

**Do M1+M2 first, re-run the paired comparison, then re-decide Task B.** off_map at ~2% says the
off-map brain is not where the money is today.

---

### Diagnostic artifact
`scripts/_diag_exit_breakdown.py` — throwaway, cache-only. Reproduces every number above. Safe to
delete; left in place so the evidence is re-runnable.
