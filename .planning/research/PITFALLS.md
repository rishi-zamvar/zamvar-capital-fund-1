# Pitfalls Research

**Domain:** Event-driven biotech catalyst trading (LLM multi-agent desk + Robinhood equities execution, real money)
**Researched:** 2026-08-14
**Confidence:** HIGH on finance/domain pitfalls (well-established base rates + exchange rules); MEDIUM on LLM-specific mitigations (active research, fewer settled patterns)

> Read order: the first four pitfalls are **total-loss-capable and, worse, three of them are baked into the current design as written in PROJECT.md**. If the roadmap fixes nothing else, fix these. Everything below Pitfall 5 is "will bleed you / will fool you," not "will end you."

---

## Critical Pitfalls

### Pitfall 1: The long/long "hedge" does not hedge a binary single-name outcome — and can double the loss

**What goes wrong:**
The core design hedges a target long with "a correlated peer long." Correlation is a *sector/beta* relationship measured in normal markets. A Phase 3 readout or PDUFA decision is an **idiosyncratic single-name** event — the exact risk that correlation does not span. Three failure modes:
1. **Best case, hedge does nothing:** peer barely moves while your name gaps -70%. You ate the full binary loss; the "hedge" was decoration.
2. **Common case, hedge moves the wrong way:** on a drug failure, a *competing* peer often *rallies* (one fewer competitor / read-through that the mechanism is hard / the peer's asset now looks better). You are long the loser AND long a peer — but the peer going up doesn't offset because you *wanted* the peer to fall to hedge a long. A long peer only hedges if the peer *falls* with your name. It won't on idiosyncratic good-for-peer news. Documented repeatedly: a single Phase 3 failure sends "winners and losers in opposite directions" across a therapeutic area (MarketBeat, 2025).
3. **Correlation-breakdown-at-the-worst-time:** even genuinely correlated names decouple precisely on single-name catalysts — the correlation you measured is conditional on *no idiosyncratic event*, which is the one condition that fails on catalyst day.

Two longs is **not a hedge, it is 2x gross long exposure** with an unfounded belief in protection. Sizing "toward ~1%/week" on a notionally hedged book means you are likely running far more real directional risk than the model thinks.

**Why it happens:**
Robinhood can't short, so the team reached for the only long-only construct that *looks* like a hedge. The word "correlated" is doing enormous unearned work — nobody validated that the correlation holds *conditional on the catalyst*, which is the only moment that matters.

**How to avoid:**
- **Stop calling it a hedge.** Model the pair honestly as two independent long exposures and size to the *combined* worst-case, not the netted one.
- Require the Risk layer to compute the pair's payoff **conditional on the catalyst outcome** (target -70% / peer +X%, target +40% / peer -Y%), using historical analog gaps — not unconditional daily correlation. If the "hedge leg" doesn't reliably *fall* when the target *falls* on the specific event type, it provides zero downside protection and must be scored as such.
- The honest hedges available in a long-only account are: **cash (don't take the position / size it tiny)**, or **exiting before the binary resolves** (trade the *run-up* into the catalyst, close before the event). Consider making "close before the event" the default and holding-through the exception.
- If a peer long is kept, justify it as a *directional conviction* position, not risk reduction.

**Warning signs:**
- Risk dossier cites a single unconditional correlation number (e.g. "0.7 correlated") as hedge justification.
- Backtest shows the pair losing on *both* legs on any historical failure day.
- "Hedged" positions are sized larger than you'd ever size an unhedged single-name binary.

**Phase to address:** Risk Management layer (Pipeline 1) + Trade Builder pair construction; verified in the paper-ledger phase against real historical catalyst days.

---

### Pitfall 2: Stop-losses do not work across a binary event — the gap jumps the stop

**What goes wrong:**
The design sets "stop-loss/take-profit" on one-week holds spanning the catalyst. Binary biotech events gap **overnight/pre-market**, straight through any stop. Real 2025-2026 examples: GlycoMimetics -72% on a Phase 3 failure ($1.83 → $0.51 pre-market); Karyopharm's failed Phase 3 erased most of the market cap overnight. A stop at -10% executes at the *next available print* — which can be -70%. The stop creates a **false sense of bounded risk** on exactly the position type where risk is unbounded-to-near-total.

**Why it happens:**
Stops work fine for continuous, liquid, non-event price action, so they get applied reflexively. Nobody distinguishes "stop protects against drift" from "stop is useless against a gap."

**How to avoid:**
- **Default policy: do not hold through the binary event.** If the strategy edge is the *run-up*, define exit *before* the readout/PDUFA window opens. This converts the position from binary-gap risk to ordinary drift risk, where stops actually work.
- If holding through is ever allowed, the ONLY real risk control is **position size** — size the position so a -70% (or worse; halts + delisting can approach -100%) is a survivable, pre-budgeted loss, and disclose to the user that no stop protects it.
- Treat the stop-loss field on a held-through position as *advisory only* and label it as such in the dossier and dashboard, so the user is never told a number that won't be honored.

**Warning signs:**
- Dossier shows a stop-loss on a position whose hold window *contains* the catalyst date.
- Backtest fills assume stops execute at the stop price on gap days (see Pitfall 8).
- Dashboard displays "max loss = stop distance" for a held-through binary.

**Phase to address:** Trade Builder (entry/exit design) + Risk layer; the dashboard KPI phase must not display a fictitious bounded loss.

---

### Pitfall 3: A wrong or stale catalyst date is a total loss — and readout dates are ranges, not dates

**What goes wrong:**
The entire edge depends on the catalyst date. Get it wrong and you're either holding through an event you thought was next week, or exited before an event that already moved the stock. Specific traps:
- **PDUFA dates move:** FDA can act early, act late (extend the review by 3 months on a major amendment), or issue a CRL near the date. The date is a *deadline*, not a scheduled reveal.
- **Trial readouts are windows, not dates:** companies guide "1H 2026" or "second half"; "topline data expected" slips constantly. Treating a guided quarter as a firm date will systematically mis-time entries/exits.
- **Stale/mis-sourced dates:** a scraped or LLM-recalled date that's outdated or hallucinated (see Pitfall 4) points the whole desk at the wrong day.
- **Conference presentations** can leak/embargo-break; the move can happen on the abstract release days before the talk.

**Why it happens:**
Calendar data is scattered across IR pages, FDA calendars, ClinicalTrials.gov, and third-party trackers of varying quality. LLMs will confidently emit a plausible date from stale training data.

**How to avoid:**
- **Two-source rule for every catalyst date**, at least one being primary (company IR / FDA / ClinicalTrials.gov), reconciled programmatically; flag disagreement to the user, never auto-trade on a single unverified date.
- Store dates with an **explicit uncertainty type**: `firm` (PDUFA deadline), `window` (guided quarter/half), `soft` (analyst estimate). Sizing and exit logic must treat `window`/`soft` differently — you cannot precision-time a window.
- **Freshness stamp + re-verify within 48h of any trade.** Refuse to trade on a date not re-confirmed against a primary source recently.
- Never let a date originate from an LLM's parametric memory. LLM may *read* a source; it may not *recall* a date.

**Warning signs:**
- A catalyst date with a single source, or sourced only to a model's answer.
- Date field is a single day for a company that only guided a quarter.
- No `last_verified` timestamp on the calendar row.

**Phase to address:** Universe & Catalyst Feed phase (data integrity is foundational — build this rigor *first*, everything downstream trusts it).

---

### Pitfall 4: LLM agents hallucinate medical/regulatory/statistical facts and rationalize a trade

**What goes wrong:**
The desk makes money decisions from LLM claims about trial endpoints, p-values, powering, PDUFA dates, prior FDA precedent, short interest, runway. LLMs confidently fabricate all of these ("plausible-sounding misinformation users accept as fact" — 2025 hallucination surveys explicitly flag financial/medical domains as highest-harm). Compounding failures specific to this design:
- **Bull/bear are not truly independent** if they share context, a system prompt lineage, or the same upstream analyst summary — they'll converge and manufacture false consensus. Confirmation bias gets *laundered* through a debate that looks adversarial but isn't.
- **Trade-shaped output bias:** an "analyst desk" asked to produce a trade will produce a trade. The expected/rewarded output is a recommendation, so the system drifts toward always finding a reason to act. "No trade" must be a first-class, rewarded outcome or the desk over-trades by construction (feeds Pitfall 6).
- **Overconfidence:** models emit high certainty without calibration; a 55%-true claim is stated like a 95%-true one.

**Why it happens:**
LLMs optimize for fluent, helpful, complete answers — not calibrated, sourced, falsifiable ones. Debate framing feels rigorous but doesn't create genuine independence or ground truth.

**How to avoid:**
- **Every fact that touches sizing must carry a source URL + verbatim quote.** No quote, no fact — the claim is dropped, not softened. Numbers (p-values, endpoints, dates, cash runway) must be extracted from a primary document, not asserted.
- **Force calibrated, falsifiable claims:** require each key claim as a probability with a stated basis, and a "what would prove this wrong" line. Downweight uncalibrated assertions.
- **Real independence for bull/bear:** separate context windows, no shared draft, ideally different retrieval sets; forbid one from seeing the other's conclusion before forming its own. The Diligence pipeline (Pipeline 2) must run on *raw sources*, not on Pipeline 1's summary, or it just ratifies upstream errors.
- **"No trade" is the default.** The desk must clear an explicit evidentiary bar to act; abstaining is a success, not a failure, in the eval loop (Pitfall 13).
- **Statistical sanity gate:** a deterministic (non-LLM) check on the numbers the LLM extracted — does the p-value/endpoint/enrollment math even parse; is the runway arithmetic right.

**Warning signs:**
- Dossier claims without a source quote, or with a source that doesn't contain the number.
- Bull and bear agree suspiciously often, or bear's counterpoints are strawmen.
- Diligence pipeline reaches the same conclusion via the same evidence as the identifier (no independent value added).
- Recommendation rate near 100% of analyzed catalysts.

**Phase to address:** Analyst desk (Pipeline 1) design + independent Diligence (Pipeline 2) architecture; sourcing/calibration harness is a cross-cutting requirement, not a feature.

---

### Pitfall 5: Chasing a fixed 1%/week over binary events maximizes risk of ruin

**What goes wrong:**
~1%/week ≈ **68%/yr compounded** — a top-decile hedge-fund return, targeted by an individual on the *highest-variance event class in equities*. The danger isn't the target's ambition; it's what a **fixed weekly return target does to sizing**. Fixed-return targeting forces you to *increase size after losses* to "make it back," which is the classic path to ruin. On binary events with fat left tails, a short string of losses is not just possible, it's expected: even at a 58% Phase-3 success base rate, runs of 3-4 adverse outcomes happen routinely, and each can be -50% to -70% on the position. A few of those, oversized, is account death.
- **Over-trading:** "every qualifying catalyst" + a weekly quota = forced trades on marginal setups. Volume of binary bets is the enemy; each one is a coin-flip-with-a-cliff.
- **Kelly on binary events is brutally small.** For a bet that can lose 70% of the *position*, the Kelly-optimal *fraction of capital* is tiny; most retail sizing is many multiples of Kelly, i.e. in the guaranteed-ruin region even with a real edge.

**Why it happens:**
A round, motivating target ("1%/week") gets translated directly into position size ("size toward 1%"), coupling *sizing* to a *return goal* instead of to *survival*. Compounding math makes 1%/week sound modest; the variance math makes it lethal.

**How to avoid:**
- **Size for survival, not for the target.** Sizing must be driven by risk-of-ruin / fractional-Kelly on the *position's* downside gap (assume -70%), capped so no single catalyst can cost more than a small fixed % of the account (e.g. a hard per-event cap and a portfolio heat cap). The 1%/week is an *outcome to measure*, never a *sizing input*.
- **Reframe the target as a research/quality goal**, not a quota: "when we find a trade that clears the bar," not "one per week." Explicitly allow zero-trade weeks.
- Model **risk of ruin explicitly** in the paper phase: simulate strings of losses at the intended size; if P(50% drawdown) over a year isn't tiny, the size is wrong.
- Never martingale — size must not increase to recover losses. If anything, size *down* in drawdown.

**Warning signs:**
- Position size is computed from "how much do we need to make 1% this week."
- A week with no qualifying trade is treated as a miss.
- Any single position could cost >~2-3% of the account.
- Post-loss sizing is larger than pre-loss.

**Phase to address:** Risk Management layer + Portfolio Manager (sizing rules); stress-tested in the paper-ledger phase before any real capital.

---

## High-Severity Pitfalls

### Pitfall 6: Prompt injection via scraped web content hijacks the desk

**What goes wrong:**
The desk ingests scraped web content (IR pages, news, forums, filings). Indirect prompt injection — malicious instructions embedded in that content — can alter agent behavior: fabricate a bullish thesis, suppress a red flag, or (with Robinhood MCP wired) attempt to trigger an order. Documented in the wild in 2025 (Unit 42; OWASP LLM01:2025 lists prompt injection as the #1 GenAI risk; AutoRedTrader specifically red-teams trading agents via injected misinformation).

**How to avoid:**
- **Treat all scraped content as untrusted data, never as instructions.** Structural separation: retrieved text goes into a clearly delimited data channel, never concatenated into the instruction context.
- **The execution boundary is the hard line:** no agent path from scraped content to an order. Robinhood MCP calls require the human approval gate (already a constraint — keep it inviolable and make it impossible to bypass programmatically).
- Prefer **primary structured sources** (FDA, ClinicalTrials.gov, SEC EDGAR APIs) over open-web scrape where possible; whitelist domains.
- Sanitize/strip instruction-like patterns; log provenance of every retrieved snippet.

**Warning signs:** dossier text echoing odd imperatives; sudden thesis flips traceable to one source; any order attempt not originating from a human tap.

**Phase to address:** Retrieval/ingestion layer + Execution phase (MCP boundary hardening).

---

### Pitfall 7: Paper-to-live gap — good paper fills, tiny sample, overfit playbooks

**What goes wrong:**
Four compounding illusions:
1. **Unrealistic fills:** an internal sim ledger fills at the mid or last quote. Real small-cap biotech has **wide spreads, thin depth, and gaps**; you cross the spread on entry AND exit, and event-day liquidity evaporates. Paper P&L will be systematically, sometimes wildly, too good.
2. **1-month sample is statistically meaningless.** Maybe 4-8 catalysts. You cannot distinguish edge from luck at n<10 on binary outcomes. "Paper proved it out" after a month is a dangerous false conclusion.
3. **Overfitting playbooks** to that tiny sample — the continuous-learning loop will happily tune configs to fit 6 data points (noise), producing confident garbage.
4. **No stops honored on gaps** (Pitfall 2) if the sim assumes stop-price fills.

**How to avoid:**
- **Model fills pessimistically:** fill at the *far* side of the quoted spread (buy at ask, sell at bid), add explicit slippage that scales with position-vs-ADV, and for held-through events fill exits at the *actual historical gap open*, not a stop price. Paper P&L should feel punishing.
- **Set an honest evidence bar for going live:** define it by number of *independent* catalysts and a confidence interval, not by calendar time. A month is a *shakedown of the plumbing*, not proof of edge — state this explicitly to the user.
- **Walk-forward, not in-sample:** the learning loop tunes on past catalysts and is scored only on *subsequent, unseen* ones. Never report an in-sample fit as performance.
- Track **paper-vs-what-real-fill-would-have-been** as a first-class metric so the fill model itself is validated.

**Warning signs:** paper Sharpe implausibly high; fills at mid; "1 month done, let's go live"; learning-loop metrics improving on the same data they trained on.

**Phase to address:** Paper-ledger phase (fill model) + Continuous-learning loop (walk-forward discipline).

---

### Pitfall 8: Look-ahead and survivorship bias in universe + backtest

**What goes wrong:**
- **Survivorship:** building the ~20-name universe from *today's* liquid, still-listed biotechs excludes the ones that blew up and delisted — the exact left-tail you're exposed to. Backtests on survivors look far safer than reality.
- **Look-ahead:** using the *final* catalyst date/outcome/estimate as if known in advance; using restated financials; using a "known good" universe selected with hindsight. Also using data timestamped *after* your simulated decision moment.

**How to avoid:**
- Build the historical universe **point-in-time** — the names that qualified *then*, including subsequently-delisted ones.
- Every backtest datum must carry an **as-of timestamp**; the sim may only see data available at the decision moment (the guided date as known then, not the actual date).
- Include **failed/delisted names** in any base-rate estimate.

**Warning signs:** universe built from a current screen; no as-of timestamps; base rates that look better than published Phase-3 success rates (~58%, BIO/Wong et al.).

**Phase to address:** Universe construction + any backtest/learning phase.

---

### Pitfall 9: Robinhood unofficial API — ToS/ban, no paper mode, order collars, reliability

**What goes wrong:**
- **There is no official Robinhood trading API for individuals.** Community wrappers (`robin_stocks`, `pyrh`) reverse-engineer the private mobile API. Use **violates Robinhood ToS** and risks **account suspension without notice**. These libraries break whenever Robinhood changes auth/CAPTCHA/endpoints — your execution layer can die mid-strategy.
- **No true paper mode** on Robinhood — hence the internal sim ledger (correct call), but it means live is the *first* real fill test.
- **Market-order collars:** Robinhood applies price collars and will **reject** orders in fast/illiquid markets; market orders can fill with severe slippage or not at all around volatile events. Trading halts (common on biotech catalyst days) freeze you in or out.
- **Order-type limits:** confirm the actual MCP tool surface (PROJECT.md notes options/shorting unconfirmed) — assume equities market/limit only.

**How to avoid:**
- **Assume the execution path is fragile and impersonal.** Human-approval gate stays mandatory (also mitigates Pitfall 6). Never build anything that *requires* the API to be up to avoid a loss (e.g. don't rely on an automated stop firing via the API).
- **Use limit orders, not market orders,** for illiquid names — accept non-fills over catastrophic fills. Budget for partial fills and rejections.
- **Fail-safe on API breakage:** if the wrapper errors, the system halts and alerts the user; it never retries blindly into a live account.
- Keep a **manual-execution fallback** documented — the user can place the trade by hand if automation is down.
- Understand a personal account can be frozen; don't run capital you can't afford to have locked.

**Warning signs:** auth failures/CAPTCHA prompts; order rejections; fills far from quote; any design that treats the API as reliable infrastructure.

**Phase to address:** Execution phase (Robinhood MCP integration + fallback + limit-order discipline).

---

### Pitfall 10: Misreading options-implied move / IV crush (even though you trade equities)

**What goes wrong:**
You trade equities, so IV crush doesn't hit your P&L directly — but the **options-implied move is your best market estimate of the catalyst's magnitude**, and the design already lists "options-implied move" in Diligence. Two mistakes: (1) ignoring it and under-appreciating the expected gap; (2) misinterpreting elevated pre-event IV (150-300% annualized is normal for biotech binaries) as a *tradeable equity signal* rather than a *sizing input*. The implied move tells you how big the gap could be — feed it into sizing (Pitfall 5) and the "don't hold through" decision (Pitfall 2).

**How to avoid:** Use the implied move as a *magnitude prior* for the downside gap in sizing; never as directional signal. Cross-check the implied move against historical analog gaps for the same event type.

**Warning signs:** sizing that ignores a large implied move; treating high IV as bullish/bearish.

**Phase to address:** Diligence (Pipeline 2) + Risk sizing.

---

## Medium-Severity Pitfalls

### Pitfall 11: Corporate actions, reverse splits, delisting (data corruption that silently poisons everything)

**What goes wrong:** Small-cap biotech does **reverse splits constantly** (to hold listing standards) and gets delisted after failures. Unadjusted prices make a reverse split look like a +1000% move; a split during a hold corrupts P&L and share counts; a delisting can strand a position. Split/dividend-unadjusted historical data silently breaks backtests and analog matching.

**How to avoid:** Use split/dividend-adjusted price series; reconcile share counts on corporate actions; flag names near listing-standard thresholds (sub-$1, going-concern) as elevated delisting risk in Diligence.

**Warning signs:** impossible historical returns; share count mismatches; a universe name trading sub-$1.

**Phase to address:** Data integrity (Universe/Catalyst feed) + Diligence financial dimension.

---

### Pitfall 12: Pattern Day Trader rule / same-day round trips (rule currently in flux)

**What goes wrong:** Weekly holds mostly avoid PDT, but a stop or a "close before the event" exit that lands **same-day as entry** counts as a day trade; 4+ in 5 business days on a margin account historically triggered the $25k PDT requirement and can freeze trading. **Note the regime change:** the SEC approved eliminating the $25k PDT minimum (FINRA Rule 4210 amendment, effective 2026-06-04) but **brokers have until 2027-10-20 to implement** — so Robinhood may still enforce the old rule when you go live. Don't assume it's gone.

**How to avoid:** Track round-trip count; prefer overnight+ holds; verify Robinhood's *current* PDT enforcement at go-live rather than trusting the headline rule change. Use a cash account if day-trade classification is a problem (settlement constraints instead).

**Phase to address:** Execution phase.

---

### Pitfall 13: Continuous-learning loop overfits, leaks, or reward-hacks

**What goes wrong:** The self-iterating loop (DoorDash-agentic-inspired) is the most seductive failure surface: it can (a) overfit configs to a handful of outcomes, (b) leak future info into "learned" playbooks, (c) reward-hack — optimize the *metric* (e.g. recommendation accuracy on logged trades) rather than real risk-adjusted P&L, and (d) entrench early lucky biases as "playbooks."

**How to avoid:** Walk-forward evaluation only (Pitfall 8); freeze a holdout of catalysts the loop never trains on; score on *out-of-sample realized P&L net of modeled slippage*, not on self-reported prediction quality; require a *minimum sample* before any config change is accepted; version and A/B config changes rather than letting the loop mutate freely.

**Phase to address:** Continuous-learning / eval-loop phase.

---

### Pitfall 14: Compliance / personal-use lines

**What goes wrong:** This is a **personal** system. Lines that turn it into a regulated activity or a ToS/legal problem: (1) giving trade recommendations to *others* can constitute unregistered investment advice; (2) automated access violates Robinhood ToS (Pitfall 9) — a personal-use, human-gated posture is the least-bad framing but still ToS-adverse; (3) acting on **material non-public information** (e.g. leaked trial data, embargoed abstracts) is insider trading — the desk must only use *public* sources.

**How to avoid:** Keep it single-user, human-gated, public-data-only. No sharing recommendations as advice. Document the personal-use, educational framing. Don't scrape/act on anything embargoed or non-public.

**Phase to address:** Cross-cutting; note in project charter and Diligence sourcing rules.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Sim ledger fills at mid/last | Fast to build, pretty P&L | Live P&L craters vs paper; false go-live confidence (Pitfall 7) | Never for the go-live decision; OK only as a first plumbing test clearly labeled optimistic |
| Single-source catalyst dates | Simpler feed | One bad date = total loss on the position (Pitfall 3) | Never |
| LLM-asserted facts without source quotes | Faster dossiers | Hallucinated p-values/dates drive real trades (Pitfall 4) | Never on anything touching sizing |
| Treating peer long as "the hedge" in sizing | Lets you size bigger | 2x hidden directional risk, ruin (Pitfall 1) | Never — model as 2 longs |
| Market orders for convenience | Guaranteed(ish) fill | Collar rejection / catastrophic slippage on illiquid biotech (Pitfall 9) | Only for highly liquid names, small size |
| Relying on API-fired stops | "Automated protection" | API breaks / gaps jump stop → false safety (Pitfalls 2, 9) | Never as the sole risk control |
| Bull/bear sharing context | Simpler orchestration | Fake consensus, laundered confirmation bias (Pitfall 4) | Never |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Robinhood (unofficial) | Treating as reliable infra; market orders; auto-execute | Human-gated, limit orders, fail-safe halt on breakage, manual fallback |
| Web scrape / news | Feeding content into instruction context | Untrusted data channel, whitelist primary sources, no path to execution |
| ClinicalTrials.gov / FDA / EDGAR | Assuming dates are firm | Encode date uncertainty type; re-verify within 48h; two-source rule |
| LLM fact extraction | Trusting recalled numbers | Extract from primary doc with verbatim quote + deterministic sanity check |
| Options data (implied move) | Reading as directional signal | Use as magnitude prior for sizing only |

## "Looks Done But Isn't" Checklist

- [ ] **Hedge logic:** verify the "hedge" leg actually *falls* with the target on the specific catalyst type — else it's not a hedge (Pitfall 1).
- [ ] **Stop-loss on held-through positions:** verify it's labeled advisory and sizing assumes -70% gap, not stop distance (Pitfall 2).
- [ ] **Catalyst dates:** verify two sources, uncertainty type, and a fresh `last_verified` (Pitfall 3).
- [ ] **Every dossier fact:** verify a source URL + verbatim quote exists and contains the number (Pitfall 4).
- [ ] **Position sizing:** verify it's driven by risk-of-ruin, not by the 1% target; per-event and portfolio caps enforced (Pitfall 5).
- [ ] **Bull/bear/diligence independence:** verify separate contexts and that Diligence runs on raw sources, not Pipeline 1's summary (Pitfall 4).
- [ ] **Paper fills:** verify far-side-of-spread + slippage + real gap opens, and that go-live gate is sample-based not calendar-based (Pitfall 7).
- [ ] **Universe/backtest:** verify point-in-time construction with delisted names and as-of timestamps (Pitfall 8).
- [ ] **Execution boundary:** verify no path from scraped content to an order without a human tap (Pitfall 6).
- [ ] **"No trade":** verify the desk actually abstains sometimes and abstaining scores as success (Pitfalls 4, 5).

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Peer long isn't a hedge | HIGH | Halt live trading; re-model all pairs as 2 longs; re-size to worst-case; prefer exit-before-event |
| Stop jumped by gap | HIGH (loss realized) | Accept loss; audit why the position was held through; enforce close-before-event default |
| Wrong catalyst date | HIGH (total position) | Post-mortem the source; add second source + freshness gate; refuse single-source dates |
| Hallucinated fact traded | HIGH | Kill the trade; add source-quote requirement + deterministic sanity gate; audit the loop for other unsourced facts |
| Oversized / ruin path | MEDIUM if caught early | Cut size to fractional-Kelly on -70% assumption; add hard caps; decouple sizing from the 1% target |
| API breakage mid-trade | LOW-MEDIUM | Fail-safe halt already fired; execute manually; wait for wrapper fix |
| Overfit learning loop | MEDIUM | Revert to last A/B-validated config; enforce walk-forward + minimum sample |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1 Peer long ≠ hedge | Risk layer + Trade Builder | Pair payoff modeled conditional on catalyst; loses on both legs → flagged |
| 2 Stop jumped by gap | Trade Builder + Risk + Dashboard | Held-through positions size for -70%; stop labeled advisory |
| 3 Wrong catalyst date | Universe & Catalyst Feed (foundational, first) | Two sources + uncertainty type + `last_verified` enforced |
| 4 LLM hallucination | Pipeline 1 + independent Pipeline 2 | Every sizing fact has source quote; bull/bear independence; deterministic number check |
| 5 Ruin from 1% target | Risk layer + Portfolio Manager | Sizing = f(risk-of-ruin), caps enforced; zero-trade weeks allowed |
| 6 Prompt injection | Ingestion + Execution boundary | No scrape→order path; content in data channel only |
| 7 Paper-to-live gap | Paper ledger + Learning loop | Pessimistic fills; sample-based go-live gate; walk-forward |
| 8 Look-ahead/survivorship | Universe + Backtest | Point-in-time universe w/ delisted names; as-of timestamps |
| 9 Robinhood fragility | Execution | Limit orders, fail-safe halt, manual fallback, human gate |
| 10 Implied-move misread | Diligence + Risk | Implied move used as magnitude prior only |
| 11 Corporate actions | Data integrity + Diligence | Adjusted prices; delisting-risk flag |
| 12 PDT / round trips | Execution | Round-trip counter; verify RH's current PDT enforcement at go-live |
| 13 Learning loop overfit | Learning/eval loop | Walk-forward + frozen holdout + min-sample gate |
| 14 Compliance framing | Charter + Diligence sourcing | Single-user, public-data-only, no advice to others |

## Sources

- FINRA Regulatory Notice 26-10 / SEC approval of Rule 4210 amendment (PDT $25k eliminated 2026-06-04, brokers implement by 2027-10-20): https://www.finra.org/rules-guidance/notices/26-10 ; https://www.schwab.com/learn/story/sec-approves-scrapping-25000-day-trader-minimum — HIGH
- Robinhood unofficial API / robin_stocks ToS + ban + no paper mode (AlgoTrading101; Bitget): https://algotrading101.com/learn/robinhood-api-guide/ ; https://www.bitget.com/wiki/does-robinhood-allows-api-based-trading-for-stocks — MEDIUM (secondary sources, consistent)
- Robinhood order collars / rejections / gapping / halts (Robinhood support + market volatility overview PDF): https://robinhood.com/support/articles/why-was-my-order-rejected ; https://cdn.robinhood.com/assets/robinhood/legal/rhf-rhs-market-volatility-overview.pdf — HIGH
- Phase 3 success ~58% and further ~50% attrition to approval (BIO/Wong-style clinical success rates): https://academic.oup.com/biostatistics/article/20/2/273/4817524 ; https://diyhpl.us/~nmz787/pdf/Clinical_development_success_rates_for_investigational_drugs.pdf — HIGH
- Real binary-event drops (GlycoMimetics -72%, Karyopharm) + peers moving opposite directions on a Phase 3 failure: https://www.fiercebiotech.com/biotech/glycomimetics-fails-phase-3-blood-cancer-trial-causing-investors-sour-stock ; https://www.marketbeat.com/articles/the-phase-3-failure-that-sent-biotech-winners-and-losers-in-opposite-directions/ — HIGH
- IV crush / 150-300% pre-event IV on biotech binaries: https://quantstrategy.io/blog/options-trading-strategies-for-high-volatility-biotech/ ; https://www.benzinga.com/pro/blog/how-to-trade-biotech-stocks-strategies-and-tools-for-fda-plays — MEDIUM
- LLM prompt injection (#1 GenAI risk) + indirect injection in the wild + trading-agent red-teaming + hallucination in financial domains: https://genai.owasp.org/llmrisk/llm01-prompt-injection/ ; https://unit42.paloaltonetworks.com/ai-agent-prompt-injection/ ; https://arxiv.org/pdf/2605.09185 (AutoRedTrader) ; https://arxiv.org/html/2512.02261v1 (TradeTrap) ; https://arxiv.org/html/2509.18970v1 (LLM agent hallucination survey) — HIGH for existence of risk, MEDIUM for mitigation maturity
- Kelly criterion / risk of ruin (standard finance; fractional-Kelly on fat-left-tail binaries) — HIGH (established theory, no single URL)

---
*Pitfalls research for: event-driven biotech catalyst trading with an LLM agent desk*
*Researched: 2026-08-14*
