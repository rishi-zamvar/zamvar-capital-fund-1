# MITIGATIONS-VETTED — adversarial vet of the Tier-3 exit-engine fixes

**Reviewer stance:** extreme skeptic. The backtest is in-sample, tiny (48 legs / 7 real
winners), and optimistic by construction. Anything that *fits a number* to these 48 legs is
guilty until proven innocent. Structural rules that honor the hold-through contract are cheap
and safe; tuned multipliers are expensive and dangerous. I re-ran `_diag_exit_breakdown.py`
cache-only — **every number in the draft reproduces exactly** (tp -133.25pp, avg_win
33.61%→8.61%, 7 winners 107.14%→3.77%, off_map 1/48, weekly-minus-daily +809.6%). The
diagnosis is real. The *cure* is where the draft overreaches.

---

## Verdict table

| # | Draft proposal | Verdict | One-line reason |
|---|----------------|---------|-----------------|
| **M1** | Suppress price exits pre-event on hold-through legs + catastrophic-gap guard @ `2·vol_move` | **MODIFY** | Adopt the suppression as a *whole-hold* structural rule; **cut** the catastrophic-gap guard (magic number + contradicts "sizing IS the stop"). |
| **M2** | Drop the 1% tp; re-anchor to catalyst move; trailing stop `vol_move` below running high | **REJECT (as written) / fold structural core into M1** | Trailing stop = smuggled technical + magic number the evidence doesn't need; catalyst-magnitude anchor is a **phantom input** (Layer-A has no implied-move). The one correct idea — "don't take profit on a 1% weekly-drift target for a binary" — is just M1 extended post-event. |
| **M3** | Close-confirm exits; flag worse-than-trigger fills as off_map | **REJECT the off_map-flag / DEFER close-confirm** | Off_map-flagging pollutes the Task-B signal with fill-slippage noise; close-confirm is moot once hold-through legs stop firing price exits. |
| **M4** | Emit the paired covered-subset comparison as the headline metric | **ADOPT (with health warning)** | Pure reporting, no look-ahead. Must carry the in-sample + entry-basis caveats so the point estimate isn't over-trusted. |

**Net:** the safe, correct fix is **M1-as-a-principle (whole-hold suppression → exit at the TIME
barrier) + M4 (measurement hygiene)**. Do **not** tune any threshold on 48 legs. Everything in M2
beyond "stop taking 1% profits on a binary" is either a rejected-technical, a phantom input, or a
curve-fit, and belongs in Task B (outcome-conditioned scenario logic), not Task A.

---

## Which mitigation actually earns its keep?

The draft ranks "M1 + M2 together are the fix." Read the numbers adversarially:

- **M1 (pre-event suppression) fixes -11.4pp of an ~810pp gap.** By the draft's own attribution,
  pre-event exits are 14/48 legs, -11.4pp. So **M1-as-scoped-in-the-draft is oversold as a headline
  fix.** It is necessary (it restores the contract the design already claims to enforce) but it is
  ~1.4% of the damage.
- **The dominant damage is POST-event: 34 legs, -189.5pp**, because the tp/band price legs fire on
  the *first touch* at the start of a multi-day catalyst move and miss the run (or fill into the
  fade). The tp bucket alone is -133.25pp.
- Therefore **the load-bearing fix is suppressing the POST-event price legs too**, not the pre-event
  ones. The draft puts that inside M2 (dressed up as "re-anchor + trail"). Stripped of the tuning,
  the load-bearing change is simply: *a hold-through leg does not exit on a price band/stop/tp — it
  exits at the TIME barrier.* That is a one-guard structural rule, and the paired weekly baseline
  (+12.68%, which IS hold-to-barrier) is the direct evidence that it works. **No trailing stop and no
  re-anchored target are required to recover the edge — the weekly hold already recovers it.**

That reframing matters: it moves the real fix out of the curve-fit-risky M2 and into a
zero-parameter structural rule.

---

## M1 — detail

**Real fix or cosmetic?** Real but narrow as scoped (-11.4pp). Its true value is *structural*: it
makes the reflex finally honor the `advisory=True` flag `adaptive_sl_tp_levels` already computes and
the design already promises ("spend judgment at entry, execute at the event; the pre-event stop is
advisory because a gap jumps it; sizing is the defense"). **Recommend widening it from
pre-event-only to whole-hold** — that absorbs the -189.5pp post-event damage and makes M2's
structural half redundant.

**Curve-fit risk: LOW.** It's a principle, not a fitted parameter. `event_date` is exogenous (the
catalyst calendar). If we suppress whole-hold we don't even need `event_date` threaded — only
`held_through` — which is *simpler and safer* than the draft (drops one param and the pre/post
boundary ambiguity).

**Look-ahead: none.** Confirmed independently — `event_date = cat["event_date"]` comes from the
point-in-time `build_event_set` record, authored at entry. The whole-hold variant doesn't read it at
all.

**Standing-constraint violation — the catastrophic-gap guard fails two:**
1. **Magic number.** `2·vol_move` (= 0.30) is a new literal. If kept it must live in `EXIT_PARAMS`,
   not the body — but see #2.
2. **It contradicts the design's own thesis.** The design says *"no stop fills through a gap; sizing
   + pairs-hedge are the gap defense,"* and `fill.py` models held-through fills at the gap-open far
   side **precisely because you cannot fill inside the gap.** A "catastrophic-gap guard" that exits
   on `close < entry·(1-2·vol_move)` therefore either (a) fires on a *tradeable slow bleed* — in
   which case it is just a wide price stop, i.e. the technical/advisory-stop exit the design
   rejects — or (b) fires on a *real gap/halt/fraud* — in which case it **cannot fill there** and
   sizing (`size_for_survival`, already assuming -70%) was the intended defense. Either way it adds a
   number and buys nothing the sizing didn't already buy. **Cut it from Task A.** If pre-event
   downside protection is genuinely wanted later, tie it to `thesis_invalidation.disqualifying_news`
   (a structural news/halt signal) — that's Task B, and it's thesis-aligned, not a price threshold.

**M1 verdict: MODIFY** → suppress band/stop/tp for the *whole hold* on `held_through` legs; keep only
the TIME barrier active (Task A). Drop the catastrophic-gap guard. ~10-15 lines, one guard in the
shared `reflex_exit`.

---

## M2 — detail (the dangerous one)

**Is the trailing stop a structural exit or a smuggled technical?** It is a **technical.** A stop
trailed `vol_move` below the *running high* is a price-path construct — it reacts to the chart, not
to the thesis or the catalyst outcome. That is exactly what the CEO means by "technicals aren't
real." Worse, the design's own research anchor (Kaminski & Lo) says stops add value **only in
momentum and destroy it in mean-reversion**, and warns to "trail only post-event *trend*." Biotech
post-catalyst tape is frequently a **spike-and-fade (mean-reverting)** — the regime where a trail
*destroys* value. So M2's trailing stop is both a rejected technical and, by the design's own cited
evidence, likely value-destructive on the post-event fade it's meant to harvest.

**The thesis-aligned alternative already exists and needs no trail:** hold through the event → exit
at the **TIME barrier** (the hard Friday/weekly-flat leg the triple-barrier already defines), with
outcome-conditioned scenario actions + EV-flip reserved for Task B. The paired weekly baseline is
literally hold-to-barrier and makes **+12.68%**. The evidence says the trail is unnecessary.

**The catalyst-magnitude re-anchor (M2 ii/iii) is a phantom input.** I verified: in the Layer-A
daily path `up_move` = `ev` = the **weekly base-rate `mean_next`, floored at `target_weekly`=0.01**
(`engine._ev_from_mean_next`), and `vol_move` = `|hard_veto_drop|` = 0.15. With `tp_frac`=0.8 and
`sl_vol_mult`=1.0 (confirmed in params): stop = band-lower = 0.85·entry, band-upper ≈ 1.01·entry,
tp ≈ 1.008·entry. The options-implied expected move / football-field magnitude that M2 wants to
anchor to lives in the **LLM builder** (`exit_plan.build_exit_plan`'s `up_move` from `est.detail`),
**not in the deterministic Layer-A backtest.** So "anchor the tp to the catalyst move, not the
weekly mean" is **not implementable in this backtest** without wiring a new data source in — the
draft glosses over this. And even if it were wired, fitting a target magnitude to 48 legs / 7
winners is textbook curve-fit.

**Curve-fit risk: HIGH.** Trail distance (`vol_move`), any tp re-anchor multiplier, and the band
widening are all knobs that would be judged good/bad by their P&L on the same 48 in-sample legs the
playbook was built on. That is the exact failure mode the standing constraints warn against.

**Look-ahead:** the draft's "trail uses only realized highs" claim is technically true (no
look-ahead), but no-look-ahead is not the bar here — *rejected-technical* and *curve-fit* are the
disqualifiers.

**The one correct idea inside M2:** "a target ~1% above entry is nonsensical for a binary that moves
30-100%." Agreed — but the fix is **not** re-anchoring to a fitted magnitude, it's **not taking a
price-based profit at all on a hold-through leg.** That is M1-extended-post-event. Fold it into M1.

**M2 verdict: REJECT as written.** Fold only its structural core (suppress the price-based tp/band on
hold-through legs) into M1's whole-hold rule. No trailing stop in Task A. No catalyst-magnitude
re-anchor in Task A (phantom input + curve-fit). Trailing/EV-flip/scenario-magnitude belong in Task
B, gated on a real outcome signal and calibrated on the forward paper month, never on these 48 legs.

---

## M3 — detail

**Off_map-flagging (flag a fill worse than the trigger reference as off_map): REJECT.** A fill worse
than the trigger is a *fill-timing/slippage artifact*, not evidence of a regime the plan didn't
anticipate. Wiring it into `off_map` conflates two different things and **pollutes the Task-B trigger
signal** — the exact number the Task-B go/no-go depends on. It would make off_map look bigger for a
reason that has nothing to do with off-map outcomes.

**Close-confirmation (trigger on close past a level, not an intraday wick): DEFER.** It's honest
execution realism and not a technical — but once M1 suppresses price exits on the 48 hold-through
legs, there are no tp/band triggers left on them to close-confirm. It only affects non-hold-through
legs, which aren't where the damage is. The draft itself concedes M3 is "largely subsumed." Adopt it
only if/when the reflex's price legs are active for non-hold-through legs; not needed for this fix.

**M3 verdict: REJECT the off_map-flag; DEFER close-confirm.**

---

## M4 — detail

**ADOPT.** Pure reporting, no engine change, no look-ahead. The paired covered-subset comparison is
the right primary go/no-go input and the original FINDINGS §1 (weekly-108 vs daily-48, different
populations) genuinely was apples-to-oranges.

**Required guardrails on M4 so the metric isn't over-trusted:**
1. **Print the in-sample health warning inline** with the number: 48 legs, 7 winners, in-sample,
   winner-concentrated (the +12.68% is dominated by 7 legs at mean +107%). The *direction* (reflex
   is net-harmful) is robust; the *magnitude* is not a forward estimate.
2. **Disclose the entry-basis caveat** (see next section) — the paired comparison is not a pure
   exit-only isolation.
3. **Re-emit off_map from the corrected run** (post-M1), and mark the pre-fix 2% as provisional.

---

## Decision 1 — Task B go/no-go: **DEFER (agree), but make the defer provisional.**

The draft says defer because off_map ≈ 2%. The sharper question the brief raises: *is off_map
artificially low because the reflex mislabels off-map events as tp/band exits?* **No — and the
mechanism runs the opposite way to the worry.** The 20 mislabeled "tp" exits are not hidden off-map
outcomes; they are artifacts of a take-profit set ~30× too tight. When M1 suppresses price exits on
hold-through legs, those tp triggers **cease to fire at all** — they become held-to-barrier legs, not
reclassified off-map cases. So fixing the reflex **shrinks the mislabeled bucket to zero rather than
promoting it into off_map.** There is no reason to expect off_map to balloon.

**Caveat that makes it provisional, not permanent:** the current off_map = 1/48 is measured under a
*broken band* (band-upper ≈ 1.01·entry). A correctly-scoped hold-through book will measure off_map
differently. So: **defer Task B now** (the money is demonstrably in the on-map hold-through timing,
not the off-map path), but **re-measure off_map on the post-M1 run before making the defer
permanent.** Don't build the Task-B agent on a rounding error, but don't certify "off-map is
negligible forever" off a number produced by the very bug we're fixing.

## Decision 2 — is the paired 48-leg comparison methodologically sound?

**Sound for the directional conclusion; do not trust the point estimates.** Two flaws:

1. **Entry-basis mismatch (real, under-disclosed).** The weekly path enters at the **decision-week
   close** (`entry_bars[-1]["close"]`); the daily path enters at the **next tradeable daily open**
   (`entry_open`). The two legs are priced off *different entry bases*, so "weekly-minus-daily =
   810pp" conflates exit-timing differences with an entry-basis difference. Almost certainly small
   against 810pp, but it means this is **not** a clean exit-only isolation, and M4 should say so.
2. **In-sample + winner-concentrated.** +12.68% weekly mean is driven by 7 legs at mean +107%. The
   *ranking* (reflex vaporizes edge: 24 hurt vs 18 helped, every big winner cut to +3.77%) is robust
   and is enough for the go/no-go direction. The *levels* (+12.68% vs -4.18%) are in-sample noise and
   must not be forward-projected or used to "size" the expected gain from the fix.

Symmetry checks that pass: both paths apply `apply_costs=True` (half-spread on entry+exit), both use
`held_through=True` for the weekly leg, both cache-only. The comparison is honest; it's just not a
forward oracle.

---

## Recommended implementation scope for the next step

**Build (Task A):**
1. **M1 as a whole-hold structural rule.** Thread `held_through` into `reflex_exit`; on a
   `held_through` leg, skip the band / stop / tp branches for the entire hold and exit only on the
   TIME barrier (+ halt handling, unchanged). One guard in the shared `reflex_exit` (root-cause fix
   — every caller routes through it). `event_date` threading optional (not needed for whole-hold
   suppression). No new params, no magic numbers, no technicals. Expected effect: the daily
   hold-through path converges to the weekly hold (~+12.68% in-sample) instead of -4.18%.
2. **M4 measurement hygiene**, with the in-sample health warning, the entry-basis caveat, and a
   re-emitted post-fix off_map.

**Explicitly EXCLUDE from the next step (curve-fit / rejected-technical / phantom-input / magic-number):**
- M2's **trailing stop** (technical; Kaminski-Lo says it destroys value on the post-event fade; magic
  trail distance).
- M2's **catalyst-magnitude tp re-anchor and band widening** (phantom input — Layer-A has no
  implied-move; and curve-fit on 48 legs).
- M1's **catastrophic-gap guard** (magic `2·vol_move`; contradicts sizing-IS-the-stop; unfillable in
  a real gap).
- M3's **off_map-mislabel flag** (pollutes the Task-B signal); M3 close-confirm **deferred**.

**Defer to Task B (and calibrate on the forward paper month, never on these 48 legs):** outcome-
conditioned scenario actions, the EV-flip guard, any post-event trailing/fade module, and the off-map
reasoning agent — re-decided against the *corrected* off_map number.

**Bottom line:** adopt the structural contract fix (M1 as a whole-hold principle) + measurement
hygiene (M4). Do **not** tune any threshold on 48 legs. The evidence that "just hold to the time
barrier" recovers the edge is already sitting in the weekly baseline; nothing fancier is justified
until the forward paper month gives a non-in-sample read.
