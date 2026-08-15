# Weekly Universe-Wide Thesis Engine — Research

**Date:** 2026-08-15 · **Author:** quant-strategy researcher (single sequential agent)
**Scope:** the capability that generates a data-backed thesis on EVERY universe name every week — mean-reversion, continuation, or catalyst — so the desk always has a portfolio to build. Long-only, one-week holds, ~20-name biotech universe, no zero-trade weeks, sizing = target-within-survival-cap.

**Citation discipline note:** the session's WebSearch budget was exhausted before this research began. All load-bearing citations below were verified via direct WebFetch of the journal/RePEc record (marked **VERIFIED**); items I could not confirm online are established-finance-literature knowledge marked **UNVERIFIED — established knowledge, confirm before quoting numbers**. Measured numbers computed from yfinance in this session are labeled **MEASURED (this session)** with the exact script parameters.

---

## Section 1 — The three thesis types: is each a REAL, measurable edge?

### 1.1 Mean-reversion ("it dropped last week — is the bounce proven?")

**The academic base case is real, old, and well-replicated — but it is a *portfolio* effect, and it has decayed.**

- **Lehmann (1990), "Fads, Martingales, and Market Efficiency," *Quarterly Journal of Economics* 105(1), 1–28** — **VERIFIED.** Stocks with large price moves exhibit "sizeable return reversals the next week"; a zero-cost winners-minus-losers weekly contrarian portfolio earned apparent arbitrage profits over 1962–1986. This is the canonical *weekly-horizon* reversal paper — exactly our hold period.
- **Jegadeesh (1990), "Evidence of Predictable Behavior of Security Returns," *Journal of Finance* 45(3), 881–898** — **VERIFIED.** Highly significant negative serial correlation in *monthly* returns; extreme-decile spread ≈ 2.49%/month (1934–87). Confirms reversal at the 1-month horizon; positive serial correlation reappears at ~12-month lags (the momentum seam).
- **De Bondt & Thaler (1985), "Does the Stock Market Overreact?", *Journal of Finance* 40(3)** — **UNVERIFIED — established knowledge.** The overreaction hypothesis, but at the **3–5 year** horizon (long-term losers beat long-term winners). Relevant as the *psychological mechanism* (overreaction), NOT as evidence for a weekly bounce. Do not cite it for weekly reversal.

**Three critical caveats before treating this as our edge:**

1. **The classic profits were partly a market-microstructure illusion.** A large slice of measured weekly-reversal profit comes from bid-ask bounce and from effectively *providing liquidity* (buying at other people's fire-sale prices). Once you pay the spread instead of earning it, the paper profit shrinks drastically — this is the standard post-Lehmann critique (Conrad, Gultekin & Kaul 1997 on bid-ask bias; Avramov, Chordia & Goyal 2006 tie reversal profits to illiquidity and turnover — **UNVERIFIED — established knowledge**). Nagel (2012, "Evaporating Liquidity," *Review of Financial Studies*) frames short-term reversal returns as *compensation for liquidity provision* that spikes in stressed markets — **UNVERIFIED — established knowledge**. For us, trading small size in reasonably liquid names via Robinhood at zero commission, the spread-cost objection is survivable but the *interpretation* matters: the bounce edge is largest precisely in the small, illiquid names where our fills are worst.
2. **The edge has decayed since the 1990s.** Post-decimalization/HFT, simple weekly reversal in large caps is close to arbitraged away; what remains concentrates in small/micro caps and in high-volatility weeks. Any base rate we measure on 1990s-flavored assumptions will disappoint live. This is why the engine must measure base rates on **recent** windows (5–10y) and re-measure continuously.
3. **THE decisive conditioning variable is *why* it dropped.** This is the single most important finding for our engine:
   - **Savor (2012), "Stock returns after major price shocks: the impact of information," *Journal of Financial Economics* 106(3), 635–659** — **VERIFIED, including the key sentence:** "price events accompanied by information are followed by **drift**, while no-information ones result in **reversals**." A big drop *with* real news keeps going; a big drop *without* news bounces.
   - **Chan (2003), "Stock price reaction to news and no-news: drift and reversal after headlines," *Journal of Financial Economics* 70(2), 223–260** — **VERIFIED (title/journal; abstract paywalled).** Same architecture: drift after news (especially bad news), reversal after no-news moves.
   - **Da, Liu & Schaumburg (2014), "A Closer Look at the Short-Term Return Reversal," *Management Science* 60(3), 658–674** — **VERIFIED.** Decomposes reversal: profits on the long (buy-the-loser) side are attributable to **liquidity shocks**, i.e. reversal works when the drop was a liquidity/sentiment event, not a cash-flow-news event (they proxy cash-flow news with analyst forecast revisions).

**Biotech-specific behavior.** In small-cap biotech the news/no-news split is not a nuance — it is the whole game, because the dominant "news" is *binary and permanent*:

- A **failed pivotal trial or CRL is a permanent repricing**, not an overreaction. The stock's rNPV genuinely lost a program; there is no mean to revert to. Event studies of clinical-trial announcements show large, immediate, and *persistent* negative revaluations on failures (Rothenstein et al. 2011, *JNCI*, oncology trial results — documented pre-announcement run-ups and immediate repricing; Hwang 2013, *JAMA Internal Medicine*, stock returns around clinical-trial results — both **UNVERIFIED — established knowledge, confirm before quoting magnitudes**). Buying that dip is the falling-knife trap, and academic evidence (Savor/Chan) says the *expected* continuation after informed bad news is DOWN, not up.
- Conversely, biotech's high idiosyncratic volatility and retail/sentiment-driven flow mean **non-news drops (sector beta days, fund liquidations, tax-loss selling, index rebalances, sympathy moves on a competitor's news) overshoot routinely** — this is where the measurable bounce lives. Da–Liu–Schaumburg's "liquidity-shock long side" is a precise description of a small biotech down 15% because XBI had a bad week.
- **Post-crash long-horizon evidence:** even after catastrophic biotech failures, some names recover over months (pipeline optionality, cash floor) — but that is a *months* horizon, not our week. At the one-week horizon, the empirically defensible bounce candidates are the **no-fundamental-news** drops.

**Verdict — mean-reversion:** REAL but conditional. As an unconditional "buy last week's losers" rule: weak-to-dead after costs in the modern market. As a **conditioned** rule — buy the loser *only when the drop was sector-beta or liquidity/sentiment driven, with no busted-catalyst news* — it is backed by the strongest event-conditioned results in the short-horizon literature (Savor 2012; Da–Liu–Schaumburg 2014) and matches biotech microstructure. It must be measured per-cohort (Section 2), and the measured edge will be modest: this is a base-hit thesis (~50–58% weekly win rates in plausible cohorts), not a catalyst-sized edge. If our own measured base rate on the conditioned cohort is ≤ ~52% with a near-symmetric win/loss ratio, the honest call is DROP (see 2.6).

### 1.2 Continuation / momentum (weekly)

**The academic evidence at the ONE-WEEK horizon actually leans *against* naive continuation — with two specific, well-documented exceptions that we can condition on.**

- Classic momentum — **Jegadeesh & Titman (1993), "Returns to Buying Winners and Selling Losers," *Journal of Finance* 48(1)** (**UNVERIFIED — established knowledge**) — is a **3–12 month formation / 3–12 month holding** effect. Critically, the standard construction *skips the most recent week/month precisely because the short horizon reverses* (Lehmann/Jegadeesh above). Naively projecting "it went up last week so it'll go up this week" is not supported; at one week the unconditional autocorrelation is negative.
- **Exception 1 — news-driven moves drift.** The same Savor (2012) / Chan (2003) results that kill bounce-buying on informed drops are *evidence for continuation*: moves accompanied by real information drift in the move's direction for weeks. Chan's result is asymmetric — the drift is strongest after **bad** news (investors underreact to bad news; short-sale constraints slow the correction — and since we are long-only, "bad-news drift" is mostly a *do-not-buy-the-dip* signal, not a tradeable long). The tradeable long side is **good-news continuation**: positive catalyst surprise, approval, partnership, strong data → drift up.
- **PEAD — Bernard & Thomas (1989), "Post-Earnings-Announcement Drift: Delayed Price Response or Risk Premium?", *Journal of Accounting Research* 27** (**UNVERIFIED — established knowledge**) — the most replicated anomaly in accounting-finance: prices drift in the direction of an earnings surprise for ~60 days, strongest in small caps with low analyst coverage — which describes our universe. Biotech "earnings" surprise is often not EPS but *data/regulatory* surprise; the PEAD logic transfers: markets underreact to complex, hard-to-value news, and biotech clinical data is maximally complex. A week-scale slice of a 60-day drift is a small but real expected edge.
- **Exception 2 — turnover-conditioned short-term momentum. Medhat & Schmeling (2022), "Short-term Momentum," *Review of Financial Studies* 35(3), 1480–1526** — **VERIFIED, including the key sentence:** "significant short-term reversal among **low-turnover** stocks, whereas **high-turnover** stocks exhibit short-term momentum," an effect "as profitable and as persistent as conventional price momentum" that "survives transaction costs." This gives us a second deterministic conditioner: last week's *share turnover* separates the bounce cohort from the continuation cohort. A biotech up big on huge volume (new information being absorbed) is a continuation candidate; up on thin volume is a fade.
- **Sector momentum:** Moskowitz & Grinblatt (1999), "Do Industries Explain Momentum?", *Journal of Finance* (**UNVERIFIED — established knowledge**) — industry-level momentum is strong at 1–12 month horizons; XBI/sector trend is a legitimate *tilt* input (be bigger in continuation names when the sector itself is trending up), though at one week it is a weak signal on its own.

**Biotech-specific behavior:** positive-readout drift is plausible and matches PEAD logic (complex data, thin coverage, staged institutional accumulation after de-risking events); post-approval drift is often muted or reversed ("sell the news") when approval was fully priced — meaning even the continuation thesis needs the *surprise* component measured, not just the direction of the move. Bad-news drift (CRL, failed trial, offering) is well-supported but long-only means we express it as *exclusion* (never bounce-buy these) rather than as a position.

**Verdict — continuation:** REAL at one week ONLY when conditioned on (a) an identified information event driving the move (Savor/Chan/PEAD family) or (b) high turnover during the move (Medhat–Schmeling). Unconditional weekly momentum is the wrong sign. Like reversal, it is a base-hit edge to be measured per-cohort, with the extra long-only asymmetry: bad-news drift is a veto signal, good-news drift is a candidate long.

### 1.3 Catalyst (existing Workflow-1) — composition with the non-catalyst theses

Nothing new to research here — the catalyst call is built (Phases 4–5). What matters is **composition**:

- **Precedence:** a name with an imminent catalyst inside the hold week is a CATALYST name, full stop. The catalyst's binary event risk dominates any ±1–2% weekly statistical edge by an order of magnitude; running a mean-reversion thesis *through* a readout is taking catalyst risk without catalyst analysis. Rule: **catalyst thesis preempts**; the statistical theses only apply to names with no catalyst falling within the hold window (plus a buffer for date-uncertain readouts — "estimated Q3" trial completions are latent catalysts).
- **A name can have both signals** (e.g., dropped 12% last week AND has a PDUFA in 9 days). The drop is then *pre-catalyst positioning*, not a liquidity shock — Savor's information regime. Feed the drop to Workflow-1 as context (entry-price improvement, sentiment input), don't trade it as a standalone bounce.
- **Post-catalyst names flow INTO the statistical theses**: last week's readout name is this week's drift/reversal candidate, and the drop-classifier (Section 2) will tag its move `busted_catalyst` or `positive_catalyst` — the KB's recorded outcome for that catalyst is exactly the "how/why it dropped" feature. This is where Workflow-1's output becomes the thesis engine's input.

### 1.4 Summary table

| Thesis | Weekly-horizon evidence | Strength (honest) | The conditioning that makes it real |
|---|---|---|---|
| Mean-reversion | Lehmann 1990 (VERIFIED); Jegadeesh 1990 (VERIFIED); decay + liquidity critiques | Weak unconditional; modest conditioned | Drop was sector-beta / no-news / liquidity (Savor 2012, Da-Liu-Schaumburg 2014, both VERIFIED); low turnover (Medhat–Schmeling 2022, VERIFIED) |
| Continuation | Wrong sign unconditional at 1w; PEAD + news-drift + high-turnover momentum | Modest conditioned | Identified information event (Savor/Chan) or high turnover (Medhat–Schmeling); good-news side only (long-only) |
| Catalyst | Workflow-1's own event edge | Largest per-event edge | Already built; preempts statistical theses within the hold window |

---

## Section 2 — Making each thesis MEASURED and cite-or-drop (the moat mechanics)

### 2.1 The core object: a conditional weekly base rate

"Is the bounce proven for THIS name?" becomes one deterministic, reproducible number:

> **P(next-week return > 0 | trigger condition, cohort)** plus the conditional mean/median next-week return and the sample size — computed from historical weekly bars, frozen into a `ToolResult` (tool name + version + verbatim inputs), exactly like every other quant tool in `src/catalyst_trader/quant/`.

The trigger condition is a small, enumerable grammar, NOT free-form (free-form = overfitting):

- `drop_pct` bucket: last-week return ≤ −5% / −10% / −15% (3 buckets, no finer)
- `drop_class`: `idio_no_news` / `sector_beta` / `busted_catalyst` / `positive_catalyst` / `dilution` (from the drop-classifier, 2.4)
- `turnover`: last-week share turnover above/below the name's trailing median (the Medhat–Schmeling conditioner)
- cohort level: `name` → `therapeutic-area cohort` → `universe` → `sector ETF constituents` (the shrinkage ladder, 2.3)

That grammar yields ~tens of cells, each with a measurable n — small enough to audit by hand, large enough to separate bounce from knife.

### 2.2 Sanity check — MEASURED (this session)

To confirm the effect exists at all in our asset class at our horizon, I computed the naive version on 18 liquid biotech names (VRTX REGN ALNY SRPT BMRN IONS NBIX INCY EXEL UTHR RARE ACAD MRNA JAZZ HALO CYTK INSM AXSM; KRTX/APLS failed download — both acquired, which itself illustrates the survivorship problem), weekly W-FRI closes, 2016-01-01→2026-08-01, yfinance auto-adjusted, beta vs XBI (full-sample):

| Trigger (last wk) | Mode | n | P(next wk up) | mean next | median next |
|---|---|---|---|---|---|
| ≤ −5% | raw | 1515 | **0.544** | +0.94% | +0.61% |
| ≤ −5% | idio-driven | 1239 | **0.553** | +1.20% | +0.69% |
| ≤ −5% | sector-driven | 251 | 0.518 | +0.14% | +0.39% |
| ≤ −10% | raw | 463 | **0.546** | +1.17% | +0.86% |
| ≤ −10% | idio-driven | 396 | 0.543 | +1.25% | +0.69% |
| ≤ −10% | sector-driven | 64 | 0.578 | +1.33% | +1.36% |
| ≤ −15% | raw | 160 | **0.488** | +0.48% | **−0.31%** |
| ≤ −15% | idio-driven | 141 | 0.482 | +0.20% | −0.37% |
| ≥ +5% (continuation) | raw | 1729 | 0.500 | +0.52% | 0.00% |
| ≥ +10% (continuation) | raw | 577 | 0.503 | +0.78% | +0.05% |
| — unconditional | all weeks | 9766 | 0.513 | +0.44% | +0.18% |

Script: `.planning/research/weekly_reversal_check.py` (parameters above; pooled overlapping events; full-sample beta) — rerunnable.

**What this MEASURES:** (a) a modest, real bounce after −5%/−10% weeks (~54–55% vs 51% unconditional; +0.5–0.8%/wk of conditional mean over baseline); (b) **the falling-knife regime is visible in our own data** — after −15% weeks P(up) falls BELOW the unconditional rate and the median next week is negative, exactly the Savor/Chan "informed drop keeps drifting" prediction, because −15% biotech weeks usually had real news; (c) **unconditional continuation is a coin flip (50.0–50.3%)** — confirming that continuation is only tradeable with news/turnover conditioning, which this naive script did not apply.

**What this does NOT prove (honesty box):** the cohort is survivorship-biased (18 names selected in 2026 that all survived/succeeded — inflates every number, probably by 1–3 points of win rate); no news conditioning; full-sample beta is look-ahead; pooled events overlap in calendar time (cross-sectionally correlated, so effective n is smaller than printed n); yfinance quality caveats per CLAUDE.md (fine for a sanity check, NOT for the production tool — production uses the FMP/EOD store). The production base-rate tool must fix all four: point-in-time universe (the Phase-1 store already keeps delisted names for exactly this reason), rolling beta, event de-overlap or cluster-aware CIs, and drop-class conditioning.

### 2.3 Thin samples: the shrinkage ladder (mirrors the estimator's pattern)

Per-name n is unavoidably thin: one name has ~10 weeks/decade of −10% drops. Never quote a raw per-name rate on n<30. Instead shrink toward the parent cohort, exactly the pattern the Phase-5 estimator and verifier already use (`uncertainty_widened` / "cold-start shrink-to-base-rate" in `contracts/__init__.py:113` and `desk/verifier.py:219`):

```
p_hat(name, cell) = (k_name * p_name + k_prior * p_cohort) / (k_name + k_prior)
```

— an empirical-Bayes / beta-binomial shrink where `k_name` = per-name event count in the cell and `k_prior` ≈ 20–50 pseudo-observations from the cohort rate (therapeutic-area cohort → universe → XBI-constituent pool, first level with n ≥ ~100). The `ToolResult.detail` must always carry: raw per-name n, the level actually used, the prior weight, and both the raw and shrunk p — so an agent can never quote "68% bounce rate for ACME" off n=3; the tool itself reports "55.1% (shrunk from 3 name-events toward area cohort n=214)". James-Stein/empirical-Bayes shrinkage is standard practice (**UNVERIFIED — established knowledge**; Efron & Morris 1975 popularized it), and the desk already accepted the principle in Phase 5 — this reuses the decision, not just the code.

### 2.4 Bounce vs falling knife: the drop-classifier

The deterministic feature that separates them, reusing the existing sector/idio decomposition (`quant/pairs.py:correlation_beta`):

1. **Sector vs idio split:** rolling beta vs XBI (point-in-time window, e.g. 104 weeks) → `idio_ret = ret − β·XBI_ret`. `|idio| < 0.5·|ret|` → `sector_beta` drop (bounce cohort per Savor logic + our 57.8%@n=64 sanity cell); idio-dominant → needs step 2.
2. **News gate:** did a KB-recorded or feed-recorded event land in the drop week? Catalyst table (readout/PDUFA/AdCom/earnings) → `busted_catalyst` / `positive_catalyst`; SEC filing S-1/424B (offering) → `dilution`; otherwise `idio_no_news`. This is deterministic joins against data we already ingest — no LLM judgment in the classifier. The LLM analysts *interpret* the classification and can VETO a cell (e.g. "classified idio_no_news but there's an unindexed short report") — agents interpret, tools compute, vetoes only remove trades, never add.
3. **Turnover flag:** last-week share turnover vs trailing median (volume from the price store; float from FMP) — the Medhat–Schmeling momentum/reversal switch.

Class → thesis mapping (each cell still requires its own measured base rate before trading):

| drop_class | Thesis eligibility |
|---|---|
| `sector_beta` | mean-reversion candidate (strongest literature + sanity support) |
| `idio_no_news` + low turnover | mean-reversion candidate |
| `idio_no_news` + high turnover | ambiguous — likely un-indexed news; smallest size or skip |
| `busted_catalyst` | **NEVER bounce-buy.** Long-only → no drift trade either; excluded to cash |
| `positive_catalyst` (up-move) | continuation candidate (PEAD/news-drift cohort) |
| `dilution` | excluded ~2 weeks (overhang), then re-eligible |

### 2.5 Tool signatures (deterministic; frozen ToolResult; agents interpret)

```python
# quant/weekly.py (new) — all return ToolResult (tool, tool_version, inputs, value, detail)

def weekly_base_rate(
    ticker: str, trigger: str,          # trigger from the fixed grammar: "drop_le_-0.10", "up_ge_0.10"
    drop_class: str | None,             # None = unconditioned; else a class from 2.4
    turnover: str | None,               # "high"/"low"/None
    as_of: date, window_years: int = 10,
    store: PriceStore, ...
) -> ToolResult:
    # value = shrunk P(next-week > 0)
    # detail = {n_name, n_cohort, cohort_level, p_raw, p_shrunk, mean_next, median_next,
    #           win_loss_ratio, ci_low, ci_high (cluster-aware), events: [...dates]}

def classify_drop(ticker: str, week_end: date, store, kb) -> ToolResult:
    # detail = {ret, beta, idio_ret, sector_frac, drop_class, turnover_flag,
    #           news_hits: [event ids joined from catalyst table / filings]}

def thesis_scan(universe: list[str], week_end: date, ...) -> ToolResult:
    # the weekly driver: for every name → classify_drop + weekly_base_rate for the
    # matching trigger cell → detail = per-name {thesis_type, p, mean_next, n, eligible, veto_reasons}
```

Reuse, don't rebuild: `correlation_beta` (beta), `base_rate` CSV pattern (the *catalyst* base rates stay where they are; weekly rates are computed from bars, not curated CSV — different tool, same ToolResult discipline), `analog_query` (KB analogs enrich the *interpretation* — "last 4 times this name dropped on an XBI beta week it bounced 3/4" is an analog narrative on top of the number, and the drop-class label should be inserted as a KB claim so analogs accumulate), the estimator's shrinkage/`uncertainty_widened` seam (2.3).

### 2.6 Where the edge is too weak to trade — the honest thresholds

Cite-or-drop applied to ourselves. A thesis cell is **tradeable** only if ALL hold:

1. shrunk P(up) − unconditional cohort P(up) ≥ **2 points** (else it's the market, not an edge),
2. effective n (cluster-adjusted) ≥ **30** at the level actually quoted,
3. conditional mean next-week return > **2× the estimated round-trip cost** (spread + slippage haircut; commissions are zero on Robinhood but spread on small biotech is 10–50bp),
4. the lower CI bound of mean next-week return > 0.

From the sanity table, plausibly-passing cells: −5%..−10% idio/raw drops (≈54–55%, mean ≈ +1%). Certain fails: −15% drops (worse than baseline — this cell is a *veto*, which is also valuable output), unconditional continuation (50%). Expect after survivorship correction that some currently-passing cells fail — **the honest expected outcome is that only 2–4 cells of the grammar are tradeable**, and names outside them get "no measured edge this week" (Section 3 handles that).

---

## Section 3 — Weekly cycle mechanics

### 3.1 The loop and its clock

Free-data cadence is EOD, so the natural clock is: **screen on Friday close → desk over the weekend → MD dossier Sunday → enter Monday → hold → exit the following Monday** (or Friday close — see the PM decision in 4.5). One iteration:

1. **Fri close — deterministic pass (zero LLM):** `thesis_scan(universe, week_end)` runs on the price store: every name gets `classify_drop` + the matching `weekly_base_rate` cell + the catalyst-calendar join. Output: a frozen per-name table — thesis type, p, expected move, n, eligible/veto. This is cheap, reproducible, and IS the "every name gets a weekly read" guarantee: even a name with no signal gets an explicit row saying *no measured edge, reason X* — a thesis of "no thesis" is still a data-backed read.
2. **Weekend — desk pass (LLM, shortlist only):** the existing analyst desk does NOT run on all ~20 names. It runs on (a) catalyst names (Workflow-1, as today) and (b) the top-k statistical candidates (k ≈ 3–6) surfaced by the scan, doing what agents are for: veto checks the classifier can't see (unindexed short reports, insider selling, pending litigation), analog narrative from `analog_query`, and interpretation. Agents can only *remove or shrink* statistical legs, never inflate p — the number is the tool's.
3. **Sunday — assembly:** candidate legs (catalyst legs from Workflow-1/2 + statistical legs) → risk committee sizes each via the existing `clamp(target_size, floor, survival_cap)` rule → `select_book` composes the week's book toward ~1% expected within the weekly budget and heat cap, unchanged (`desk/portfolio.py:select_book` already aggregates survivable legs by selection-only — statistical legs are just more, smaller candidates in its input). MD/GP promote/kill → dossier.
4. **Mon open — enter.** 5. **Hold week** — the (Phase-8.5, deferred) monitor watches SL/TP and news; a `busted_catalyst`-class event on a held bounce name is an immediate-exit trigger, not a hold-and-hope. 6. **Exit at horizon** — default rule: statistical legs ALWAYS exit at the one-week horizon (the base rate was measured on exactly one week; holding a winner longer is an unmeasured trade). Catalyst legs keep Workflow-1's hold-vs-exit logic. 7. **Record + learn** (3.3). Then rebuild.

**Measurement-convention trap (important):** the sanity table is Fri-close→Fri-close. If execution is Mon-open→Mon-open, the production `weekly_base_rate` must be measured Mon→Mon, or the number cited to the PM is subtly wrong (weekend effects, Monday gaps). Whatever the PM picks in 4.5, **the tool's measurement window must equal the execution window.** Same for entry style: base rates measured close-to-close, so enter at/near open-auction close-equivalent prices, not with limit orders that only fill on adverse selection.

### 3.2 What the statistical legs contribute to ~1%

Honest arithmetic: a passing bounce cell has mean next-week ≈ +1% conditional with a ~55% win rate — per-leg expected contribution after costs ≈ +0.5–0.8%. A book of 4–6 such legs at small size plus 0–2 catalyst legs is how ~1% expected is assembled in catalyst-light weeks; in catalyst-rich weeks the statistical legs shrink toward zero (catalyst legs consume the budget and carry bigger edges). `select_book` needs no change for this — it already selects among offered legs toward the target; the thesis engine just widens its candidate pool every week.

### 3.3 The learning loop (which theses actually paid)

Weekly, deterministic, appended to the KB:

- Per leg: record {thesis_type, cell, p_quoted, size, realized_ret, win} — the same outcome-recording pattern as catalyst outcomes.
- Per cell: rolling realized-vs-quoted calibration (Brier score on the cell's p — the exact "assumptions are the moat" mechanism from PROJECT.md §Knowledge, applied to weekly cells instead of catalyst priors). A cell whose realized rate underruns its quoted rate beyond CI for ~8–12 weeks gets auto-demoted to non-tradeable — cells must re-earn eligibility.
- Per classifier: log every `drop_class` label; when the desk vetoes a label or an outcome contradicts it (an "idio_no_news" name halved on news next week), that's a classifier bug to fix in code, not a prompt to tweak.
- Base rates themselves need no separate refit step: they're recomputed from bars each week (rolling window), so new outcomes flow in automatically; the learning loop governs *eligibility, vetoes, and calibration*, not the arithmetic.

### 3.4 No-zero-trade-weeks: the honest handling of no-signal names

The constraint is "always produce a book," and the survival cap already says a weak week is a SMALLER book, not zero. The honest ladder for a week where few/no cells pass:

1. **Never force a statistical trade from a failing cell.** Quoting an untradeable cell as a thesis to satisfy the constraint would be manufacturing edge — the exact thing cite-or-drop forbids. A forced bad trade is strictly worse than a small defensive book.
2. **Defensive placeholder book:** allocate the residual (or the whole book) at small size to (a) a T-bill ETF (SGOV/BIL — long-only ETFs, Robinhood-tradeable, the true cash-like leg) and/or (b) the sector anchor (XBI or the 1–2 largest, most liquid universe names) at minimal size. The dossier states plainly: *"No measured edge this week; book is defensive; expected return ≈ risk-free / market, not 1%."* This satisfies process continuity (the loop, the ledger, the learning data, the LP report all still run) without pretending to an edge that isn't there.
3. **The ~1%/week target is a portfolio objective, not a weekly entitlement.** Weeks without edge contribute ≈0 by design; the target is met on average by the weeks that have one. Baking this into the dossier language keeps the LP conversation honest.

This should be written into the requirement's acceptance criteria: "no zero-trade weeks" = *a book is always produced*, explicitly including the defensive book — NOT *a directional thesis is always asserted*.

---

## Section 4 — Scope + design recommendation for OUR build

### 4.1 What to build (one new module, three tools)

`src/catalyst_trader/quant/weekly.py` — signatures in 2.5:

| Tool | Computes | Reuses |
|---|---|---|
| `classify_drop` | drop_class + turnover flag for (ticker, week) | `correlation_beta` (rolling window) for the sector/idio split; catalyst table + filings feed for the news gate |
| `weekly_base_rate` | shrunk P(up next wk), mean/median, CI, n for a (trigger, class, turnover, cohort) cell | the estimator's beta-binomial shrink + `uncertainty_widened` seam; ToolResult contract from `quant/result.py`; price store (point-in-time, keeps delisted names) |
| `thesis_scan` | the whole universe's weekly read in one frozen table | both tools above + catalyst-calendar join; this is the artifact the desk and dossier consume |

Plus two small non-tool pieces: the **weekly outcome-recording rows** in the KB (same pattern as catalyst outcomes; add the drop_class label as a claim so `analog_query` accumulates analogs), and the **eligibility ledger** (which cells are currently tradeable + the auto-demotion rule from 3.3 — a small table, not a framework).

Explicitly NOT built: any new sizing math (risk committee + `clamp` + `select_book` unchanged), any new agent roles (the existing desk interprets the scan for a shortlist), free-form signal discovery (the trigger grammar is fixed), an intraday anything.

### 4.2 How it feeds the trade builder

The thesis engine's output slot is *upstream of the existing Pipeline-2 input*: today the builder consumes catalyst calls; now it consumes **candidate legs** = catalyst calls ∪ statistical candidates, each carrying {thesis_type, p, expected move, measured cell + n, veto list}. Statistical legs are single-leg (no inverse-hedge peer — the inverse-payoff hedge logic is catalyst-specific; a bounce leg's risk control is small size + SL + the one-week hard exit, and the no-valid-hedge fallback path Phase 5 already built ("size-tiny") is exactly the right template). Everything downstream — vetting gate, risk committee, `select_book`, MD dossier — is unchanged plumbing.

### 4.3 Design decisions (recommended)

1. **Fixed trigger grammar** (3 drop buckets × 5 classes × 2 turnover flags + 2 up-triggers), no free parameters an agent can twist. New cells require a code change + PM sign-off.
2. **Compute base rates from bars at query time** (rolling 8–10y window, point-in-time universe) rather than a curated CSV — unlike catalyst base rates, these are mechanical and must refresh weekly. Same ToolResult discipline, different storage.
3. **Measurement window = execution window** (3.1). Locked in the tool: `weekly_base_rate(..., anchor="MON_OPEN")` or whatever the PM picks — one anchor, used everywhere.
4. **Agents interpret, only downward.** The desk can veto/shrink a statistical leg, never raise p or add an off-grammar trade. Enforced in the builder's input validation, not by prompt.
5. **Tradeability thresholds from 2.6** hard-coded into `thesis_scan`'s `eligible` flag (edge ≥ 2pts over cohort baseline, effective n ≥ 30, mean > 2× cost, CI low > 0), so an ineligible cell can't reach the builder at all.
6. **Defensive-book rule from 3.4** written into the WEEK requirement's acceptance criteria.
7. **Backtest hook:** the Phase-7 mechanical backtest must run `thesis_scan` historically (it's deterministic — this is free) to produce the *out-of-sample-ish* weekly-thesis baseline with the data-latency knob, before the paper month. This is the go/no-go evidence for the whole engine.

### 4.4 Honest risks

- **Overfitting thin weekly data (the big one).** ~20 names × 52 weeks = ~1,000 name-weeks/yr spread over ~40 cells; some cells will look great by chance. Mitigations: fixed grammar (no data mining), shrinkage, cluster-aware CIs (biotech weekly moves are heavily cross-correlated — 20 names in one sector is maybe 4–6 independent bets in a bad week), auto-demotion, and the Phase-7 backtest as the only admissible evidence of aggregate edge. Expect the backtest to *kill* some of the sanity table's apparent edge — survivorship correction alone will cost points.
- **Transaction-cost drag.** ~100% weekly turnover on the statistical sleeve. Zero commission ≠ zero cost: small-biotech spreads (10–50bp) + slippage ≈ 0.2–1.0%/round-trip against a ~0.5–0.8% expected leg — costs can eat the whole statistical edge in the less-liquid names. Mitigations: liquidity floor on statistical legs (top-liquidity subset of the universe only), the 2.6 threshold #3 (mean > 2× cost), and the backtest's slippage knob stress.
- **The falling-knife trap under classifier error.** The engine's worst failure mode is `classify_drop` calling a real-news drop "no news" (delayed news, foreign-venue disclosure, un-indexed short report) and the book bounce-buying a −40% continuation. Mitigations: −15%+ drops are *never* bounce-eligible regardless of class (our own data says this cell fails anyway), the desk's veto pass on every statistical leg, survival-cap sizing, and the hard one-week exit + SL.
- **Regime risk / decay.** The 54–55% cells are 2016–2026 phenomena; reversal edges decay and invert in liquidity crises (Nagel 2012's point — reversal is liquidity provision, and its "premium" spikes exactly when holding it is most dangerous). The rolling window + auto-demotion is the defense; there is no static defense.
- **Effort-vs-edge honesty:** the statistical sleeve's realistic contribution is ~0.3–0.6%/wk expected on the weeks it trades, after costs, if the backtest confirms it. That is *useful* (it fills catalyst-light weeks and feeds the learning loop) but it is not the moat — the catalyst engine and the calibrated-assumption library remain the moat. Build this lean.

### 4.5 What the PM must decide

1. **Exit/entry anchor:** Mon-open→Mon-open vs Fri-close→Fri-close (affects the desk's weekend runway AND the base-rate measurement convention — one decision, two consequences).
2. **Defensive-book instrument(s):** SGOV/BIL vs tiny-XBI vs large-cap anchors, and the max defensive fraction (100% allowed?).
3. **Tradeability thresholds:** ratify or amend the 2.6 numbers (2pts edge / n ≥ 30 / 2× cost / CI > 0) — these gate every statistical trade.
4. **Statistical-sleeve budget cap:** max fraction of the weekly book in statistical legs when catalyst legs exist (recommend statistical ≤ 50% of risk budget in catalyst weeks).
5. **The −15% hard veto:** ratify "large drops are never bounce-eligible" (recommended; our own measured cell supports it).
6. **Shortlist size k** for the desk's weekend pass (token cost vs coverage; recommend 4).
7. **Go/no-go criterion:** what the Phase-7 backtest must show for the statistical sleeve to trade real money at all (recommend: positive net-of-cost mean at the book level with the data-latency knob at realistic settings, across ≥ 2 disjoint sub-periods).

---

## Source list

**VERIFIED this session (WebFetch of journal/RePEc records):**
- Lehmann, B. (1990). "Fads, Martingales, and Market Efficiency." *QJE* 105(1), 1–28.
- Jegadeesh, N. (1990). "Evidence of Predictable Behavior of Security Returns." *JF* 45(3), 881–898.
- Savor, P. (2012). "Stock returns after major price shocks: The impact of information." *JFE* 106(3), 635–659.
- Chan, W. (2003). "Stock price reaction to news and no-news: drift and reversal after headlines." *JFE* 70(2), 223–260. (title/journal verified; abstract paywalled)
- Medhat, M. & Schmeling, M. (2022). "Short-term Momentum." *RFS* 35(3), 1480–1526.
- Da, Z., Liu, Q. & Schaumburg, E. (2014). "A Closer Look at the Short-Term Return Reversal." *Management Science* 60(3), 658–674.

**UNVERIFIED — established finance knowledge (WebSearch budget exhausted; confirm before quoting numbers externally):** De Bondt & Thaler 1985 (*JF*); Jegadeesh & Titman 1993 (*JF*); Bernard & Thomas 1989 (*JAR*); Conrad, Gultekin & Kaul 1997; Avramov, Chordia & Goyal 2006 (*JF*); Nagel 2012 (*RFS* "Evaporating Liquidity"); Moskowitz & Grinblatt 1999 (*JF*); Efron & Morris 1975; Rothenstein et al. 2011 (*JNCI*); Hwang 2013 (*JAMA Int. Med.*).

**MEASURED (this session):** `.planning/research/weekly_reversal_check.py` — 18 liquid biotech names + XBI, W-FRI weekly, 2016-01-01→2026-08-01, yfinance (sanity check only; survivorship-biased; production numbers must come from the point-in-time store).
