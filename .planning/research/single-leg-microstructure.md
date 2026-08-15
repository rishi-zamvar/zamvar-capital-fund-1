# Single-Leg Long Around a Binary Biotech Catalyst — Model-Derived Entry / Exit / SL / TP

Research brief for Zamvar Capital Fund 1. Scope: one **long equity/ETF** leg, opened and
closed within ~5 trading days around a **known, scheduled binary catalyst** (PDUFA, Phase 3
readout, medical-conference data drop, earnings). Every control — entry timing, exit timing,
stop-loss, take-profit, hold-vs-exit — must trace to a **fitted statistical model over
observable data**, not a round number. Where a control cannot be tied to a model, it is
flagged `HEURISTIC-ONLY`. Where a claim cannot be sourced, it is flagged `UNVERIFIED`.

**Hard desk constraints respected throughout:** long-only equities/ETFs via Robinhood MCP (no
options for execution or hedging); ~1-week single leg; ~5-minute data cadence, ~1yr catalyst/
earnings history for backtest; options data is *reference-only* (no live options feed via
Robinhood — every options-derived input carries a data-source note).

> **Method note (2026-08-15):** This session's WebSearch budget was exhausted (200/200) before
> this task. Findings rely on (a) sources verified live via WebFetch this session — flagged
> `[FETCH-VERIFIED]`; (b) canonical literature the author knows with high confidence but could
> not re-fetch — flagged `[CITED-FROM-KNOWLEDGE]` with enough detail (author/year/journal/vol)
> to locate; (c) standard market mechanics stated as such. Anything genuinely uncertain is
> `UNVERIFIED`. The PM should treat `[CITED-FROM-KNOWLEDGE]` items as "verify the exact
> coefficient before it drives real money," per the cite-or-drop rule.

---

## Section 1 — Entry timing model

### 1.1 The phenomenon: scheduled binary events carry a pre-event drift, and in biotech the drift's *sign* leaks the outcome

Three layers of evidence, from general to biotech-specific:

**(a) Scheduled events carry a systematic pre-event risk premium (general equities).**
- **Lucca & Moench (2015), "The Pre-FOMC Announcement Drift," *Journal of Finance* 70(1),
  329–371** `[CITED-FROM-KNOWLEDGE]`. Since 1994, the S&P 500 earned ~**49 bps of excess
  return in the 24 hours *before* scheduled FOMC announcements**, accounting for a large share
  of the total equity premium over the sample. The mechanism generalizes: *scheduled* risk
  events are compensated *before* the print, not only after. This is the theoretical license
  for entering ahead of a dated catalyst rather than trading only the reaction.
- **Savor & Wilson (2013), "How Much Do Investors Care About Macroeconomic Risk? Evidence from
  Scheduled Economic Announcements," *JFQA* 48(2)**, and **Savor & Wilson (2016), "Earnings
  Announcements and Systematic Risk," *Journal of Finance* 71(1)** `[CITED-FROM-KNOWLEDGE]`.
  Average returns are markedly higher on scheduled announcement days — an *announcement risk
  premium*. For a long-only desk this is a tailwind: expected return into a scheduled print is
  positive on average, before any name-specific edge.

**(b) Pre-announcement run-up from information leakage ("buy the rumor").**
- **Keown & Pinkerton (1981), "Merger Announcements and Insider Trading Activity," *Journal of
  Finance* 36(4)** `[CITED-FROM-KNOWLEDGE]`. The classic pre-event run-up: target prices drift
  up over the weeks *before* a merger is announced, evidence of leakage/informed trading. The
  "buy the rumor, sell the news" pattern is real and measurable, not folklore.

**(c) Biotech-specific: the run-up predicts the trial outcome — this is the fittable signal.**
- **Rothenstein, Tomlinson, Tannock & Detsky (2011), "Company Stock Prices Before and After
  Public Announcements Related to Oncology Drugs," *JNCI: Journal of the National Cancer
  Institute* 103(20), 1507–1512** `[FETCH-VERIFIED]`. Companies that went on to announce
  **positive** Phase III oncology trials had a **mean stock price +13.7% over the 120 trading
  days before** the announcement; companies with **negative** results were **−0.7%** over the
  same window. A day −60 window analysis found the divergence statistically significant
  (P = .03; +9.4% positive vs −4.5% negative). Plainly: *names that will succeed tend to run
  up beforehand; names that will fail don't.* The pre-event price path carries outcome
  information (leakage + informed positioning).

**The catch for a ≤5-day horizon.** Rothenstein's run-up is measured over **120 / 60 trading
days** — far longer than our week. We cannot capture the whole drift. What we *can* do is use
"is this name already running up into its catalyst?" as an **entry filter / feature**, and
capture the **tail slice** of the drift in the final 1–2 days, consistent with the desk's
existing "enter 1–2 days pre-event" design (PROJECT.md).

### 1.2 The fittable model: features → expected pre-event drift

**Model form.** A cross-sectional predictive regression (or shallow gradient-boosted tree) of
the realized short-window pre-event return on observable features:

```
R_pre(i)  =  β·X(i)  +  ε(i)
```
where `R_pre(i)` = the abnormal return of name *i* from entry (T−2 or T−1) to the last close
before the print, and `X(i)` is:

| Feature | Source (desk has it?) | Rationale / citation |
|---|---|---|
| Trailing CAR over last 20–60d (the run-up itself) | FMP/yfinance prices — **YES** | Strongest per Rothenstein 2011 — outcome leaks into the path |
| Abnormal volume trend (5–20d) | prices/volume — **YES** | Informed accumulation shows up in volume |
| Short interest & Δ short interest | FINRA bulk / FMP — **YES (bi-monthly)** | Crowded shorts → squeeze risk on a positive print |
| Days-to-event | catalyst calendar — **YES** | Drift concentrates near the event (Lucca–Moench) |
| Catalyst-type dummy (PDUFA/Ph3/conf/earnings) | calendar — **YES** | Different leakage/drift profiles |
| Options-implied skew / risk-reversal | **NO live feed** (RH) — proxy only | If ever sourced, risk-reversal sign ≈ market's directional lean |

**Fitting.** Estimate on the ~1yr event set. **Earnings supplies the dense N** (every universe
name, 4×/yr, precisely dated) to fit the *general* pre-event-drift coefficients; the sparse
drug catalysts (PDUFA/Ph3) are then fit as **offsets/shrinkage adjustments** toward the
earnings-estimated β, because pure-biotech N is too small to fit standalone (Section 4.4
methodology). Regularize (ridge/elastic-net) — with a handful of drug events, an unregularized
fit will overfit noise.

**Output used by the desk.** Two numbers: (i) `Ê[R_pre]` — expected drift captured by entering
now and exiting before the print (feeds the Section 3 hold-vs-exit EV comparison); (ii) a
**directional lean prior** — sign/strength of the run-up as a *soft* input to the catalyst-call
confidence (never the sole basis; leakage can reverse).

### 1.3 Entry-timing decision (which day to enter)

The honest state of the art at our data cadence:

- **Direction (enter before, not at, the print):** model-supported. Lucca–Moench + Savor–Wilson
  establish a positive pre-event premium; Rothenstein establishes the biotech run-up. Entering
  ahead captures drift the reaction-only trader forgoes.
- **Exact optimal day d\*:** the drift accelerates toward the event (Lucca–Moench) while the
  variance of holding also grows. The *fittable* rule is: pick the entry day that maximizes
  `Ê[R_pre(d)] − λ·Var[R(d)]` (a mean-variance objective; λ = the desk's risk aversion, itself
  pinned by the Section 5 sizing). Until that curve is fit from the event set, the default of
  **T−2 to T−1** is `HEURISTIC-ONLY` — defensible (drift is concentrated near the event; earlier
  entry adds multi-day idiosyncratic noise unrelated to the catalyst) but not yet a fitted d\*.

**Data gap (flag for PM):** fitting `Ê[R_pre(d)]` per-day needs the intraday (5-min) path over
the last 1–2 days for each historical event; ~1yr history is thin for the drug-catalyst slice.
Expect the *earnings*-fit d\* to be trustworthy first; the drug-catalyst d\* stays shrinkage-
tied to it until N grows.

---

## Section 2 — The catalyst move estimator (the core model)

This is the deterministic estimator tool the whole desk feeds off. It must output, per event:
**p** (P(positive), from the catalyst call), the **up-move u**, the **down-move d**, and their
dispersions — kept SEPARATE, because d drives sizing (§5) and u anchors take-profit (§4).

### 2.1 What we're estimating: the binary two-state structure

A binary catalyst forces the post-event price into (approximately) one of two regions. For the
pre-event price `S₀` to be fair, it is the probability-weighted average of the two states:

```
Up state:   S₀·(1 + u)   with probability p        (positive outcome)
Down state: S₀·(1 − d)   with probability (1 − p)   (negative outcome)
```

- **Probability-weighted expected move:**  `E[R] = p·u − (1−p)·d`  ← the drift a hold-through leg earns in expectation.
- **Expected absolute move (what a straddle prices):**  `E[|R|] ≈ p·u + (1−p)·d`.
- Near-fair pricing implies `p·u ≈ (1−p)·d`; a large gap between the two is either genuine edge or a mis-estimate — the tool should **flag** it for reconciliation.

### 2.2 Estimator A — Straddle / option-implied expected move (best single estimator; needs options data we don't have live)

- **ATM straddle ≈ expected absolute move.** For a near-driftless underlying, the mean absolute
  move of a normal is `E|R| = S·σ·√(T)·√(2/π) ≈ 0.80·S·σ·√T` (exact fact: `E|X| = σ√(2/π)` for
  `X~N(0,σ²)`). The Brenner–Subrahmanyam ATM approximation gives the same 0.80 constant:
  `C_ATM ≈ 0.40·S·σ·√T`, so `straddle = call+put ≈ 0.80·S·σ·√T`. **Brenner & Subrahmanyam
  (1988), "A Simple Formula to Compute the Implied Standard Deviation," *Financial Analysts
  Journal* 44(5), 80–83** `[CITED-FROM-KNOWLEDGE]`. Practitioner shorthand: **expected 1σ move
  ≈ ATM straddle price** (some desks apply a ~0.85 haircut; that 0.85 is a rule of thumb —
  `HEURISTIC-ONLY`).
- **DATA-SOURCE NOTE (critical):** Robinhood gives us **no live options feed**. To use this
  estimator at all we must source IV/straddle elsewhere — **Polygon.io Options** (paid; computes
  IV — already flagged as the escalation in STACK.md) or an equivalent daily IV snapshot. If we
  will not pay for options data, Estimator A is **reference/cross-check only** and the desk runs
  on Estimators B+C below.

### 2.3 Estimator B — Realized-vol term structure / event-jump decomposition (the theory behind the proxy)

- **Dubinsky, Johannes, Kaeck & Seeger (2019), "Option Pricing of Earnings Announcement Risks,"
  *Review of Financial Studies* 32(2), 646–687** `[FETCH-VERIFIED]` (existence/venue confirmed;
  methodology `[CITED-FROM-KNOWLEDGE]`). Total implied variance to expiry decomposes into a
  **smooth diffusive component + a discrete announcement-jump component**. With IV at two
  maturities that straddle the event, the *excess* variance in the maturity containing the event
  isolates the **event-day expected move**: `move_event ≈ √(σ²_incl·T_incl − σ²_excl·T_excl)`.
  This is exactly how "implied earnings move" is computed on desks.
- **No-options proxy (what the desk actually runs):** we don't have the IV term structure, so we
  substitute the **realized** analog — the event-jump the options market prices is, on average,
  the historical gap. Use realized vol of the underlying for the *continuous* (non-event) part
  of the week, and the **historical conditional gap distribution (Estimator C)** for the jump.

### 2.4 Estimator C — Historical GAP distribution conditioned on catalyst TYPE (the options-free core)

The estimator the desk can fit today. Build an empirical distribution of **event gap returns**
(last-close → post-event open + first-session move) per **catalyst type × market-cap tier**,
labeled by realized outcome (positive/negative).

Evidence on magnitude and asymmetry:
- **Hwang (2013), "Stock Market Returns Around Clinical Trial Announcements," *PLOS ONE* 8(8):
  e71966** `[FETCH-VERIFIED]`. Market-model event study, S&P 500 benchmark, 300-day estimation,
  ±2-day windows, Wilcoxon signed-rank. **Median CAR +0.8% (positive) vs −2.0% (negative)** on
  announcement day; reaction is **asymmetric** (negatives larger and more persistent); no
  significant difference by phase or indication. **CRITICAL CAVEAT: this is LARGE biopharma** —
  one trial is a small fraction of firm value, so moves are muted. It sets the *floor*, not the
  magnitude for our targets.
- **Single-asset small/mid-cap biotech** — where one drug ≈ the whole company — moves are far
  larger (commonly quoted ±30–70%+; failures −50% to −80%, positive Ph3/approval +20% to +60%).
  A clean peer-reviewed figure could not be sourced this session → **UNVERIFIED**; **the desk
  MUST fit this from its own labeled gap dataset by cap-tier**, never a folk constant. This is
  the whole reason the estimator is empirical-per-tier rather than a fixed number.

**Fit form.** Per (catalyst type × cap tier): estimate `u = mean(positive-outcome gaps)`,
`d = mean(|negative-outcome gaps|)`, and dispersions `σ_u, σ_d`, from labeled events. Small N →
shrink toward the catalyst-type pooled estimate, then toward the all-biotech base rate
(empirical-Bayes, §4.4). Store the full empirical gap *distribution* (not just the mean) so §5
sizing can use tail quantiles, not just the average down-move.

### 2.5 The concrete model form: two-state mixture with P(positive) as the mixing weight

```
R  ~  p · Up  +  (1 − p) · Down
Up   :  mean +u,  dispersion σ_u     (positive-outcome state)
Down :  mean −d,  dispersion σ_d     (negative-outcome state)
```
Lognormal (or empirical-quantile) components; the two-point/mixture structure is the standard
way to represent a binary-event return distribution.

- **p = P(positive) comes from Pipeline-1's calibrated catalyst call — NOT from price.** Clean
  separation the project wants: the *prediction* pipeline supplies p; the *estimator* supplies
  u, d, σ_u, σ_d from historical gaps. (The §1 run-up lean is a soft prior into p, never the
  whole of it.)
- Outputs consumed downstream: **E[R] = p·u − (1−p)·d** (→ §3 hold EV), **d and its tail
  quantile** (→ §5 sizing), **u** (→ §4 take-profit), **E[|R|] = p·u + (1−p)·d** (→ cross-check
  vs any options-implied move).

**Reference method to extract risk-neutral u, d, p from options (if ever sourced):** **Breeden &
Litzenberger (1978), "Prices of State-Contingent Claims Implicit in Option Prices," *Journal of
Business* 51(4)** `[CITED-FROM-KNOWLEDGE]` — the risk-neutral density is `∂²C/∂K²`. Around a
binary event the RND is **bimodal**; the two modes are the up/down states, their mass ratio ≈
risk-neutral p. Reference-only (needs a live option chain we lack via RH), but it is the exact
options-world analog of our empirical mixture — useful as a validation target if we buy one
option snapshot per event.

**Data gaps (flag for PM):** (i) no live options feed → Estimators A/B are reference-only unless
we pay Polygon; (ii) ~1yr history gives thin N for the drug-catalyst gap distribution per
cap-tier — earnings gaps fit first, drug gaps stay shrinkage-tied; (iii) the small-cap binary
magnitudes are currently UNVERIFIED folk numbers until the desk's own gap dataset replaces them.

> **Edge vs commodity (the moat).** *Commodity math:* the mixture algebra, the 0.80 straddle
> constant, the Breeden–Litzenberger derivative. *Where the edge lives:* the **per-catalyst-type
> × cap-tier gap distribution (u, d, σ_u, σ_d)** and its **tails** — this is the assumption every
> other desk approximates with a constant and we fit from labeled outcomes. Calibration metric:
> **estimated-vs-realized magnitude error** (mean abs error of predicted |move| vs realized gap;
> track separately for u and d). Refit: rolling per-tier means with empirical-Bayes shrinkage
> (§4.4). Post-trade attribution: on a loss, was it the **direction** (p wrong, §3) or the
> **magnitude** (d underestimated)? Log which, per trade.

---

## Section 3 — Hold-through vs exit-before-event decision model

### 3.1 The mechanical fact that governs everything: a stop-loss does NOT fill on a gap

A stop-loss is a **resting order that converts to a market order when the stop price trades**.
Binary catalysts print **after the close, pre-market, or during a trading halt** (PDUFA and
many readouts are released off-hours; the exchange often halts on news). The next print is a
**discontinuous gap** — price does not pass through the intervening levels. So:

- A "−8% stop" on a name that **gaps −60%** fills near **−60%**, not −8%. The stop level is
  fiction across a gap.
- **Holding through a binary print therefore converts a bounded loss into gap risk** capped only
  by the down-state `d` (§2). Across the print, **only position SIZE controls the downside — the
  stop does not** (this is the §4 regime distinction and the §5 sizing tie-in).

This is standard order-mechanics, stated as mechanics — not a modeled claim.

### 3.2 The decision: two mutually exclusive strategies, compared by growth-optimal EV

**Strategy A — Exit before the print.** Capture the pre-event drift, carry zero gap risk:
```
EV_exit  =  Ê[R_pre]  −  costs        (Ê[R_pre] from §1; continuous price → §4 stop is real)
```

**Strategy B — Hold through the print.** Earn the probability-weighted move, bear the full
down-state with prob (1−p), unprotected by any stop:
```
EV_hold  =  p·u  −  (1−p)·d  −  costs     (u, d, p from §2)
```

**Why raw EV is the wrong criterion, and what to use instead.** A −60% down-state can be a
book-ending event, so the decision must be **growth-optimal (Kelly-consistent), not
EV-maximal**. Compare *expected log growth* at the survival-constrained size `f` (§5):
```
Hold through  ⇔   E[ log(1 + f·R_hold) ]  >  E[ log(1 + f·R_exit) ]
                  AND the down-state is survivable at f (§5 risk-of-ruin constraint)
```
The `log` penalizes the fat down-tail automatically — this is why a positive-EV hold can still
be *rejected*: the geometric-growth cost of the (1−p) crash outweighs the arithmetic edge. This
is the formal version of the desk's existing "size to combined worst-case / never a fake hedge"
instinct, applied to the single leg.

### 3.3 Fitted conditions: when hold-through wins vs when to take the drift and leave

Hold-through is positive-EV **and** survivable when, from the fitted inputs:
- **p is high and well-calibrated** (confident, reliable positive call), AND
- **payoff is asymmetric in our favor**: `p·u − (1−p)·d` clearly exceeds `Ê[R_pre]` net of the
  extra round-trip, AND
- **d is bounded enough** that survival-size `f` keeps worst-case portfolio loss inside budget
  (§5). For a single-asset small-cap where `d` ≈ −70%, `f` is forced so tiny the leg barely
  moves the book — usually a sign to **exit before** instead.

Exit-before dominates when: **p is uncertain / poorly calibrated**, or **d is large** (big-gap
names), or **Ê[R_pre] already captures most of the outcome signal** — which is exactly what
Rothenstein (2011, §1) implies: the informative run-up can be harvested *before* the print, so
you pocket the leaked signal and skip the coin-flip. "Buy the rumor, sell the news," formalized.

### 3.4 Edge vs commodity, and calibration

> **Edge vs commodity (the moat).** *Commodity:* the EV / log-growth comparison itself. *Edge:*
> the two assumptions fed in — **p's calibration** and **d's accuracy**. A hold-through is only
> as good as whether "p = 0.7" *actually* wins 70% of the time and whether "d = −45%" *actually*
> is the average crash. Calibration metrics: **Brier score + reliability diagram for p**
> (predicted vs realized hit-rate by confidence bucket); **estimated-vs-realized error for d**.
> **Post-trade attribution (money-critical):** every hold-through loss is tagged — *direction
> miss* (p said positive, outcome negative → prediction pipeline fault) vs *magnitude miss*
> (direction right, gap worse than d → estimator fault). Over time this tells the desk whether
> to trust its calls (hold more) or distrust its magnitudes (exit more). Refit cadence: §4.4.

**Data source / gaps:** needs fitted p (Pipeline 1), fitted u/d (§2), realized-vol for
cost/slippage. The log-growth comparison is trivial to compute; its honesty depends entirely on
p-calibration and d-accuracy, which need accumulated outcomes to earn trust — thin at n small.

---

## Section 4 — Adaptive SL/TP models (the ones that GROW with data)

### 4.1 Take-profit — anchored to the estimated up-move u (§2)

```
TP_level  =  entry × (1 + k·u)          k ∈ (0, 1]  = capture fraction
```
- `u` is the fitted up-move (§2.4), NOT a round number. `k` < 1 because you never sell the exact
  top and pay slippage. `k` is **fittable**: from backtest, the value maximizing *realized held
  capture* — i.e., historically, what fraction of `u` was actually reachable and held over the
  ≤5-day window. Until fit, a default `k ≈ 0.6–0.7` is `HEURISTIC-ONLY`.
- Continuous-regime alternative: `TP = entry + m·ATR` (volatility multiple). Anchoring to `u` is
  more principled for event trades; the ATR form is the fallback when no per-name `u` exists.

### 4.2 Stop-loss — from volatility (three interchangeable fittable forms)

```
(i)  ATR stop:        SL = entry − n·ATR(period)
(ii) Realized-vol:    SL = entry − z·σ_daily·√(holding_days)·entry
(iii)Implied-move:    SL = entry − c·(implied move)        [needs options data — reference only]
```
- **ATR** — **Wilder (1978), *New Concepts in Technical Trading Systems*** `[CITED-FROM-KNOWLEDGE]`
  (origin of Average True Range). Trailing variant = **Chandelier stop** (highest-high − n·ATR),
  Chuck LeBeau `[CITED-FROM-KNOWLEDGE]`.
- **Realized-vol band:** `σ_daily` estimated from OHLC (we have 5-min bars → use **Yang–Zhang**
  or **Garman–Klass** OHLC estimators, more efficient than close-to-close) `[CITED-FROM-KNOWLEDGE:
  Yang & Zhang 2000, J. Business; Garman & Klass 1980, J. Business]`. `z` set so the stop sits
  *outside* ordinary noise (a 2σ stop should be hit by noise alone ~5% of the time) but inside
  the risk budget.
- The multiplier (`n`, `z`, `c`) is **fittable**: choose it to maximize expected log-growth of
  the continuous strategy — trading off *premature stop-outs* (knocked out by noise, then the
  trade would have worked) against *loss size*. Fit by walk-forward backtest, per catalyst type.

### 4.3 The THREE regimes — is the SL a real control or false comfort?

| Regime | Price path | Is the SL real? | What actually controls downside |
|---|---|---|---|
| **(a) Exit-before-event** | continuous (no print held) | ✅ **REAL** — fills at/near the level | ATR/vol-band SL as designed + TP |
| **(b) Continuous post-gap drift** | continuous (gap already happened) | ✅ **REAL** — fills at/near the level | SL on the drift; ride PEAD (below) |
| **(c) Hold-through the binary print** | **discontinuous gap** | ❌ **FALSE COMFORT** — fills at the gapped open, not the level | **SIZE ONLY** (§5). The SL is fiction across the print. |

- Regime (b) is where **post-earnings-announcement drift** lives: **Bernard & Thomas (1989,
  *J. Accounting Research*; 1990, *J. Accounting & Economics*)** `[CITED-FROM-KNOWLEDGE]` — prices
  keep drifting in the direction of the surprise for weeks. A stop on that continuous drift is a
  real control, and entering *after* the print to ride the drift is a legitimate continuous-price
  variant of this strategy (dodges the gap entirely).
- Regime (c) is the blunt truth the desk must never blur: **across a held binary print the stop
  is theater; only the position size is the control.** This is the hinge between §3, §4 and §5.

### 4.4 Refittable methodology — how the playbook GROWS without overfitting

Two update loops running at different speeds:

**(1) Continuous per-trade Bayesian update (cheap, every realized outcome).**
- **P(positive) p:** Beta-Binomial conjugate. Prior `Beta(a,b)` = the catalyst-type base rate;
  posterior mean after n outcomes = `(a + wins)/(a + b + n)`. Automatically **shrinks to base
  rate at small n, converges to the empirical rate as n grows** — this is the "grows with data"
  property, built-in.
- **Magnitudes u, d:** Normal-Normal (or hierarchical) conjugate update of the per-cell mean and
  variance as gaps realize.

**(2) Periodic structural refit (monthly / every N events) with shrinkage.**
- **Empirical-Bayes shrinkage across cells** (catalyst type × cap tier):
  `θ_cell = w·θ_cell_MLE + (1−w)·θ_pool`, with `w = n_cell/(n_cell + n₀)`. Small cell → `w→0`
  (lean on the pooled/base-rate estimate); as events accumulate → `w→1` (trust the cell). This
  is **James–Stein / empirical-Bayes shrinkage**: **Efron & Morris (1975), "Data Analysis Using
  Stein's Estimator and Its Generalizations," *JASA* 70(350)** `[CITED-FROM-KNOWLEDGE]`. It is
  literally "shrink toward base rates when n is small," done rigorously.
- **Hierarchical pooling:** the sparse drug-catalyst cells **borrow strength** from the dense
  earnings pool (~200 events) so a 3-event PDUFA cell isn't fit on 3 points alone.

**Overfitting guards (mandatory at our small N):**
1. Walk-forward / out-of-sample only — never fit and evaluate on the same events.
2. Minimum-N gate: don't let a cell override the pool until `n_cell ≥ N_min`.
3. Step-size cap between refits — one trade can't swing a parameter wildly.
4. Regularize every regression (ridge/elastic-net); shrink every cell mean.

**Calibration metrics (what "getting better" means, measurably):**
- **p:** Brier score + reliability diagram (predicted 70% should win ~70%).
- **u, d:** rolling estimated-vs-realized MAE, tracked separately.
- **SL/TP:** realized stop-out rate vs intended (a 2σ stop hitting 30% of the time is mis-set);
  realized TP-capture vs `k·u`.

> **Edge vs commodity (the moat).** *Commodity:* the ATR formula, Beta-Binomial, James–Stein —
> every desk has these. *Edge:* the **fitted multipliers (n, z, k)** and the **shrinkage
> structure** (which sparse cell borrows from which dense pool, and how fast `w` opens up) — fit
> to *our* realized outcomes. Two desks with identical ATR code get different stops because their
> assumption libraries differ. **The accumulating, calibrated per-cell parameter table IS the
> moat.**

---

## Section 5 — Position sizing & the 1%-week book target

### 5.1 The estimated DOWN-move drives the Kelly fraction

For the held binary (`R = +u` w.p. `p`, `−d` w.p. `1−p`), the growth-optimal fraction of book to
stake maximizes `g(f) = p·ln(1+f·u) + (1−p)·ln(1−f·d)`. Setting `g'(f)=0` gives a clean closed
form:
```
f*  =  [ p·u − (1−p)·d ]  /  (u · d)   =   E[R] / (u·d)
```
- **Kelly (1956), "A New Interpretation of Information Rate," *Bell System Technical Journal*
  35(4)** `[CITED-FROM-KNOWLEDGE]`. The **estimated down-move `d` sits in the denominator** (and
  the numerator) — a bigger `d` → smaller `f`. This is exactly the mandate: sizing keyed to the
  *estimated* `d` (from §2's per-name gap distribution), **not** a generic −70%. A name with a
  −45% estimated down-state is sized very differently from one with −75%.

### 5.2 Fractional Kelly + parameter-uncertainty haircut (survival, not maximal growth)

- **Never full Kelly.** Use `f = λ·f*`, `λ ≈ 0.25–0.5`. Half-Kelly retains ~3/4 of the growth
  at ~1/2 the variance; the reduction in drawdown risk is worth the growth given-up. **MacLean,
  Thorp & Ziemba (2011), *The Kelly Capital Growth Investment Criterion*, World Scientific**
  `[CITED-FROM-KNOWLEDGE]` (survey of fractional-Kelly growth/variance trade-off).
- **Estimation-error shrink.** `p, u, d` are *estimates*, so the effective Kelly must be shrunk
  further — full Kelly on estimated edge systematically over-bets. Tie `λ` to the confidence of
  the fit (wider posterior on p/d → smaller λ). The exact λ-schedule is `HEURISTIC-ONLY` until
  fit against realized drawdowns, but the *direction* (more uncertainty → smaller bet) is a
  theorem, not a preference.

### 5.3 Risk-of-ruin cap — regime-dependent, and it OVERRIDES Kelly

Kelly maximizes long-run growth but tolerates deep drawdowns; a real desk adds a hard survival
cap. The cap uses a **different downside per regime** (§4.3):
```
Hold-through (SL is fiction):   worst-case leg loss = f·d        → require f·d ≤ B_leg
Exit-before / continuous (SL real): worst-case leg loss ≈ f·(stop_distance)  → require f·(stop_distance) ≤ B_leg
```
where `B_leg` = the max fraction of NAV any single leg may lose. Because `stop_distance` (e.g.
`n·ATR`, a few %) ≪ `d` (tens of %), **the same dollar risk allows a much larger position when
you can exit before the print** than when you hold through — the sizing math itself rewards
dodging the gap. `f_final = min(λ·f*, risk-of-ruin cap)`. For big-`d` single-asset small-caps
the cap binds hard and the leg is tiny — often the signal to exit-before instead (§3.3).

### 5.4 Aggregating a week of legs to the ~1% book target

**Principle (from PROJECT.md): 1% is a measured OUTCOME, never a sizing input.** Legs are sized
for *survival* first (5.1–5.3); the ~1% emerges from **selection**, not from levering up.

```
Book expected return  =  Σᵢ fᵢ · E[Rᵢ]          (target ≈ 1%/week)
subject to:
  fᵢ  ≤  min( λ·fᵢ* , risk-of-ruin cap )         (each leg independently survivable)
  CVaRα( Σᵢ fᵢ·Rᵢ )  ≤  B_book                   (aggregate tail survivable, correlation-aware)
```
- **Aggregate tail via CVaR, not variance** — the down-states are fat-tailed and can co-move
  (sector-wide selloffs, FDA-policy shocks, class read-throughs), so an aggregate **Conditional
  Value-at-Risk** constraint is the right survival control. **Rockafellar & Uryasev (2000),
  "Optimization of Conditional Value-at-Risk," *Journal of Risk* 2(3)** `[CITED-FROM-KNOWLEDGE]`
  — CVaR optimization is convex/tractable. Model the joint via the §2 mixtures + an estimated
  cross-name correlation (biotech names are *mostly* idiosyncratic per-indication → diversifying,
  but **do not assume full independence** on the tail).
- **Mechanism:** size every candidate leg for survival, then **select** the subset whose
  probability-weighted expected return lands near 1% while satisfying the CVaR cap. If the
  survival-sized book over-shoots 1%, trim (fewer/smaller legs); if it under-shoots, accept less
  — **never oversize to reach 1%.** This is a small constrained optimization (or greedy selection
  by expected-return-per-unit-tail-risk), trivial at ~20 names / handful of weekly catalysts.

> **Edge vs commodity (the moat).** *Commodity:* the Kelly closed form, fractional-Kelly, CVaR
> optimization — textbook. *Edge:* the **`d` and `p` fed in.** Kelly is only survival-sizing if
> `d` is the *real* average crash and `p` is *calibrated*; an optimistic `d` turns "survival
> sizing" into ruin-sizing. The moat is the accuracy of the down-move assumption per name-tier
> (§2.4) and the correlation assumption on the tail. Calibration: back-test realized max-drawdown
> vs the CVaR budget; if realized DD routinely exceeds budget, `d` or the correlation is too
> optimistic — attribute and refit (§4.4).

**Data gaps (flag for PM):** cross-name tail correlation needs a joint event dataset we barely
have at ~1yr; default to a conservative (higher) correlation on the tail until estimated. `λ` and
`B_leg`/`B_book` are risk-appetite parameters the PM must set — they are `HEURISTIC-ONLY` by
nature (risk preference), but their *consequences* (drawdown, ruin probability) are modeled.

---

## Section 6 — Synthesis: the model stack

### 6.1 The pipeline (diagram-in-prose)

```
 CATALYST (dated, typed)                                                    Pipeline-1 CALL
 PDUFA / Ph3 / conf / earnings                                             p = P(positive) + calib.
        │                                                                          │
        ▼                                                                          ▼
 [1] ENTRY MODEL ──────────►  Ê[R_pre] (drift) + run-up lean  ──soft prior──►  (into p)
        │  regression/GBT on run-up CAR, volume, short-int, days-to-event                │
        ▼                                                                                ▼
 [2] MOVE ESTIMATOR ────────►  u, d, σ_u, σ_d   (two-state mixture; p as mixing weight)
        │  per catalyst-type × cap-tier gap distribution (+ options cross-check if sourced)
        ▼
 [3] HOLD vs EXIT ──────────►  choose max E[log(1+f·R)]:  hold-through  |  exit-before
        │  (gap fact: SL is fiction across a held print)
        ├───────────────► if EXIT-BEFORE  → continuous price → SL/TP are REAL controls
        └───────────────► if HOLD-THROUGH → gap-exposed      → SIZE is the only control
        ▼
 [4] ADAPTIVE SL/TP ────────►  TP = entry·(1+k·u) ;  SL = entry − n·ATR (or z·σ√t)
        │  regime-tagged: real (exit-before / post-gap drift) vs false-comfort (hold-through)
        ▼
 [5] SURVIVAL SIZE ─────────►  f = min(λ·f*, risk-of-ruin cap) ; f* = E[R]/(u·d)  [d-driven]
        │
        ▼
 [WEEKLY BOOK] ─────────────►  select legs s.t. Σ fᵢ·E[Rᵢ] ≈ 1%  AND  CVaRα ≤ B_book
        │
        ▼
 REALIZED OUTCOMES ─────────►  Brier(p) · MAE(u,d) · stop-out rate · drawdown-vs-CVaR
        └──────────── refit (§4.4: continuous Bayes + monthly shrinkage) ──────────┐
                                                                                    ▼
                                                            back into [1][2][3][4][5]
```

### 6.2 Stage table — model · fitted params · data source · refit cadence

| Stage | Model | Fitted parameters (the assumptions) | Data source | Refit cadence |
|---|---|---|---|---|
| **1 Entry** | Regularized cross-sectional regression / shallow GBT | drift β on run-up CAR, volume, short-int, days-to-event, type dummies; optimal day d\* | FMP/yfinance prices+volume, FINRA short-int, calendar | Monthly structural; earnings-fit trusted first |
| **2 Move estimator** | Two-state lognormal/empirical mixture; option-implied (ref) | **u, d, σ_u, σ_d per catalyst-type × cap-tier**; p from Pipeline-1 | Own labeled gap dataset (core); Polygon options (ref, paid) | Continuous Bayes per event + monthly shrinkage |
| **3 Hold vs exit** | Expected-log-growth comparison, survival-constrained | (uses p, u, d, Ê[R_pre]; no own params) | outputs of 1,2,5 | n/a (decision rule) |
| **4 SL/TP** | TP=entry(1+k·u); SL=n·ATR / z·σ√t (regime-tagged) | **k, n, z** per catalyst type | 5-min OHLC (Yang–Zhang σ, ATR) | Walk-forward monthly |
| **5 Sizing** | Fractional Kelly + risk-of-ruin cap | f\*=E[R]/(u·d); λ (uncertainty haircut); B_leg | outputs of 2; PM risk appetite | λ recalibrated vs realized DD |
| **Book** | CVaR-constrained selection to ~1% target | cross-name tail correlation; B_book | joint event dataset | Monthly |

### 6.3 Assumption calibration & the moat (governing lens)

**Assumptions are the moat, not the models.** Every desk has implied-move math, ATR bands, Kelly,
and drift regressions — commodity. The edge is the **assumptions fed in and fine-tuned against
realized outcomes**. Per stage:

| Stage | Commodity math | **The assumption that carries the edge** | Calibration metric | Refit / anti-overfit |
|---|---|---|---|---|
| 1 Entry | OLS/GBT, event-study CAR | **the drift β** (does run-up predict outcome *for us*) + d\* | estimated-vs-realized pre-drift error | ridge + shrink drug→earnings pool |
| 2 Move | mixture algebra, 0.80 straddle const, Breeden–Litzenberger | **per-type×tier gap distribution (u,d,tails)** | MAE(predicted \|move\| vs realized), separately u/d | empirical-Bayes shrinkage; min-N gate |
| 3 Hold/exit | EV / log-growth comparison | **p-calibration + d-accuracy** | **Brier(p) + reliability diagram**; d MAE | continuous Beta-Binomial update |
| 4 SL/TP | ATR, Yang–Zhang, Beta-Binomial | **multipliers k,n,z + shrinkage structure** | stop-out rate vs intended; TP capture vs k·u | walk-forward; step-size cap |
| 5 Size | Kelly closed form, CVaR (Rockafellar–Uryasev) | **d and the tail correlation** | realized max-DD vs CVaR budget | λ shrinks to fit confidence |

**Post-trade attribution (the loop that compounds the moat).** Every closed trade is decomposed:
was the loss a **direction miss** (p wrong → prediction pipeline fault) or a **magnitude miss**
(d/u wrong → estimator fault) or a **timing miss** (drift faded → entry model)? The tag routes
the correction to the right model. This is what turns "a handful of trades" into an accumulating,
**calibrated assumption library** — the actual competitive asset.

**Refit cadence & overfitting discipline (one place):** (i) continuous conjugate-Bayes updates
per outcome (p via Beta-Binomial, u/d via Normal-Normal) — cheap, self-shrinking to base rates at
small n; (ii) monthly structural refit with James–Stein/empirical-Bayes shrinkage across cells +
walk-forward validation + min-N gates + parameter step-size caps. Sparse drug cells **borrow
strength** from the dense earnings pool until they earn independence (`w = n/(n+n₀)`).

### 6.4 Honest data gaps for the PM (where we currently CANNOT fully fit the model)

1. **No live options feed via Robinhood.** Estimators A (straddle-implied) and B (IV
   term-structure event-jump) are **reference/cross-check only** unless we pay for Polygon options
   or a daily IV snapshot. The desk runs on the **realized gap distribution (Estimator C)**. Cheap
   mitigation: buy *one* option-chain snapshot per event to validate the empirical mixture against
   the risk-neutral (Breeden–Litzenberger) density.
2. **~1yr history is thin for drug catalysts.** PDUFA/Ph3 cells have tiny N; they are
   **shrinkage-tied to the dense earnings pool** until enough outcomes accumulate. Earnings-based
   parameters are trustworthy first; pure-biotech parameters are provisional.
3. **Small-cap binary magnitudes are UNVERIFIED folk numbers** (±30–70%) until the desk's own
   labeled gap dataset replaces them. Do not hard-code −70%.
4. **Cross-name tail correlation** for the book CVaR is barely estimable at ~1yr → default
   **conservative (high) tail correlation** until fit; this under-sizes the book (safe direction).
5. **Optimal entry day d\*** and the SL/TP multipliers **k, n, z** need the 5-min intraday path
   per historical event; fit **earnings first**, drug catalysts lag.
6. **λ (Kelly haircut), B_leg, B_book** are risk-appetite inputs the PM sets — `HEURISTIC-ONLY`
   by nature, but their drawdown/ruin consequences are modeled and back-testable.

### 6.5 What is model-derived vs what stays HEURISTIC-ONLY (the honest scorecard)

| Control | Status | Model / source |
|---|---|---|
| Enter *before* the print (direction) | ✅ Model-derived | Lucca–Moench 2015; Savor–Wilson 2013/16; Rothenstein 2011 |
| Exact entry day d\* | ⚠️ HEURISTIC until fit | mean-variance on fitted Ê[R_pre(d)] (T−2/T−1 default) |
| Up-move u / down-move d / p-weighted move | ✅ Model-derived | two-state mixture; gap distribution (Estimator C); Dubinsky et al. 2019 |
| P(positive) p | ✅ Model-derived | Pipeline-1 call; Beta-Binomial calibration |
| Hold-through vs exit-before | ✅ Model-derived | expected-log-growth comparison (Kelly-consistent) |
| SL is real (exit-before / post-gap) vs fiction (hold-through) | ✅ Model-derived (mechanics) | order mechanics + Bernard–Thomas PEAD for post-gap drift |
| TP level (k·u) | ✅ form derived; ⚠️ k fit-pending | anchored to estimated u; k from capture backtest |
| SL level (n·ATR / z·σ√t) | ✅ form derived; ⚠️ n,z fit-pending | Wilder 1978 ATR; Yang–Zhang 2000 σ |
| Position size f | ✅ Model-derived | fractional Kelly f\*=E[R]/(u·d) + risk-of-ruin cap |
| Kelly haircut λ, B_leg, B_book | ⚠️ HEURISTIC (risk appetite) | consequences modeled; levels are PM choice |
| ~1% weekly book | ✅ Model-derived (as outcome) | CVaR-constrained selection (Rockafellar–Uryasev 2000) |

---

## References (consolidated)

- Lucca, D. O. & Moench, E. (2015). *The Pre-FOMC Announcement Drift.* Journal of Finance 70(1), 329–371. `[CITED-FROM-KNOWLEDGE]`
- Savor, P. & Wilson, M. (2013). *How Much Do Investors Care About Macroeconomic Risk? Evidence from Scheduled Economic Announcements.* JFQA 48(2). `[CITED-FROM-KNOWLEDGE]`
- Savor, P. & Wilson, M. (2016). *Earnings Announcements and Systematic Risk.* Journal of Finance 71(1). `[CITED-FROM-KNOWLEDGE]`
- Keown, A. J. & Pinkerton, J. M. (1981). *Merger Announcements and Insider Trading Activity.* Journal of Finance 36(4). `[CITED-FROM-KNOWLEDGE]`
- Rothenstein, J. M., Tomlinson, G., Tannock, I. F. & Detsky, A. S. (2011). *Company Stock Prices Before and After Public Announcements Related to Oncology Drugs.* JNCI 103(20), 1507–1512. `[FETCH-VERIFIED]`
- Hwang, T. J. (2013). *Stock Market Returns Around Clinical Trial Announcements.* PLOS ONE 8(8): e71966. `[FETCH-VERIFIED]`
- Brenner, M. & Subrahmanyam, M. G. (1988). *A Simple Formula to Compute the Implied Standard Deviation.* Financial Analysts Journal 44(5), 80–83. `[CITED-FROM-KNOWLEDGE]`
- Dubinsky, A., Johannes, M., Kaeck, A. & Seeger, N. J. (2019). *Option Pricing of Earnings Announcement Risks.* Review of Financial Studies 32(2), 646–687. `[FETCH-VERIFIED — venue/vol/pages]`
- Breeden, D. T. & Litzenberger, R. H. (1978). *Prices of State-Contingent Claims Implicit in Option Prices.* Journal of Business 51(4). `[CITED-FROM-KNOWLEDGE]`
- Wilder, J. W. (1978). *New Concepts in Technical Trading Systems.* (ATR origin.) `[CITED-FROM-KNOWLEDGE]`
- Garman, M. B. & Klass, M. J. (1980); Yang, D. & Zhang, Q. (2000). OHLC volatility estimators, Journal of Business. `[CITED-FROM-KNOWLEDGE]`
- Bernard, V. L. & Thomas, J. K. (1989, 1990). Post-earnings-announcement drift. J. Accounting Research / J. Accounting & Economics. `[CITED-FROM-KNOWLEDGE]`
- Efron, B. & Morris, C. (1975). *Data Analysis Using Stein's Estimator and Its Generalizations.* JASA 70(350). `[CITED-FROM-KNOWLEDGE]`
- Kelly, J. L. (1956). *A New Interpretation of Information Rate.* Bell System Technical Journal 35(4). `[CITED-FROM-KNOWLEDGE]`
- MacLean, L. C., Thorp, E. O. & Ziemba, W. T. (2011). *The Kelly Capital Growth Investment Criterion.* World Scientific. `[CITED-FROM-KNOWLEDGE]`
- Rockafellar, R. T. & Uryasev, S. (2000). *Optimization of Conditional Value-at-Risk.* Journal of Risk 2(3). `[CITED-FROM-KNOWLEDGE]`
