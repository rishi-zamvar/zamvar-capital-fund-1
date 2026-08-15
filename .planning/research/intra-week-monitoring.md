# Intra-Week Position Monitoring — How Real Desks Watch an Open Book, and What Our MON Workflow Should Copy

Research date: 2026-08-15. Purpose: design the event-triggered intra-week watchdog (MON) that monitors the open one-week book between the weekly build and the weekly exit, and routes material changes back to the portfolio builder. It does NOT place orders.

**Method + confidence note:** WebSearch budget was exhausted before this research started (confirmed at first call). Findings rest on: (a) direct WebFetch of specific primary sources (SEC investor.gov, Nasdaq Trader halt codes, StockCharts indicator references, Seykota's risk essay) — marked ✅ FETCHED; (b) live endpoint tests run today from this machine (Nasdaq trade-halts RSS) — marked ✅ VERIFIED LIVE; (c) well-established risk-management/desk-practice knowledge from standard texts (Wilder 1978, the Turtle rules / Faith 2007, Schwager's Market Wizards interviews, Grinold & Kahn) where the fetch failed or wasn't attempted — marked 📚 ESTABLISHED (title + author given so a human can verify); (d) anything weaker is marked UNVERIFIED. Cite-or-drop applies: no number below is invented; where a threshold is a design choice rather than a sourced fact, it is labeled "our proposal."

---

## Section 1 — What a real desk monitors intra-day / intra-week on an open position

### 1.0 The structural insight first: desks monitor by exception, not by staring

The load-bearing fact for our design: real desks split monitoring into two layers. A **cheap always-on layer** (limit systems, price alerts, halt feeds, P&L dashboards) computes deterministic conditions continuously, and the **expensive layer** (a human PM/trader's attention) is summoned only when a condition breaches. Middle-office risk teams pre-agree limits with the PM (position size, stop distance, drawdown caps, concentration); a breach is not a debate — it forces a defined review or action. This is exactly the architecture the task brief proposes (deterministic monitors wake a light agent), so we are copying the real structure, not inventing one. — 📚 ESTABLISHED (standard front-office/middle-office limit-monitoring practice; see e.g. Grinold & Kahn, *Active Portfolio Management*, and any prime-broker risk-limit framework; also Seykota below on pre-agreed risk budgets).

Ed Seykota's risk essay states the pre-agreement principle directly: define risk as "the possibility of loss," size positions on a risk basis (stop distance), track the aggregate as portfolio **heat**, and agree the drawdown "Uncle Point" with investors *in advance* so the response to a breach is mechanical, not emotional. "Stick to the system." — ✅ FETCHED (Ed Seykota, "Risk Management," seykota.com/tribe/risk).

### 1.1 The monitor list — what triggers a human look, and what action follows

| Monitor | What specifically makes a trader look | Typical action | Source |
|---|---|---|---|
| **Adverse price vs. stop level** | Price trades through, or approaches, the pre-set stop. Volatility-scaled stops are the desk standard: the Turtles used 2N (2 × 20-day ATR) from entry; LeBeau's Chandelier Exit trails at highest-high − 3 × ATR(22). | Stop hit → exit, non-negotiable (the whole point of pre-setting it). Stop approached → re-check thesis, often trim. | 📚 ESTABLISHED (Curtis Faith, *Way of the Turtle*, 2007 — 2N stops; original Turtle rules PDF 404'd today, UNVERIFIED-fetch). ✅ FETCHED (Chandelier Exit: StockCharts ChartSchool — LeBeau, 22-period, 3×ATR trailing stop). |
| **Position drawdown / heat cap** | Unrealized loss on the position exceeds its risk budget (the amount "bet" on it), or total portfolio heat exceeds the cap. Multi-strategy platforms famously enforce hard PM drawdown rules — widely reported as ~5% drawdown → capital cut, ~7.5% → book closed (Millennium-style). | Forced de-grossing: trim or close to bring heat back under cap. At platform level this is not discretionary. | ✅ FETCHED (Seykota — heat, risk-basis sizing, Uncle Point). 📚 ESTABLISHED / press-reported for the multi-strat numbers (widely covered in FT/Bloomberg profiles of Millennium/Citadel pod rules; exact thresholds vary by pod — treat numbers as illustrative, UNVERIFIED precisely). |
| **Volatility spike** | Realized (or implied) vol jumps so the position's risk no longer matches the size it was given. Vol-targeting desks size ∝ 1/vol, so a vol doubling means the position is 2× over-risked at unchanged share count. | Trim to restore vol-normalized size; occasionally exit if the spike accompanies news. | 📚 ESTABLISHED (volatility targeting / risk parity sizing literature; Seykota's risk-basis sizing is the same idea; Wilder's ATR was invented for exactly this normalization — ✅ FETCHED StockCharts ATR page: Wilder 1978, *New Concepts in Technical Trading Systems*, TR = max of H−L, |H−C_prev|, |L−C_prev|, 14-period smoothing). |
| **Volume / liquidity anomaly** | Volume running far above average daily volume (ADV) with no visible news — the classic tell that news is leaking or imminent — or quoted spreads widening so the exit cost assumption breaks. | Investigate immediately (check halt feed, filings, news); recompute days-to-liquidate; often pre-emptively trim if nothing explains it. | 📚 ESTABLISHED (unusual-volume-precedes-news is standard surveillance practice — it is literally what FINRA/exchange surveillance and every "unusual volume" scanner monetize; days-to-liquidate = position ÷ (participation% × ADV) is the standard liquidity-risk metric). |
| **Gap risk into a known event** | A catalyst (readout, AdCom, PDUFA, earnings, court date) newly appears — or moves — inside the holding window. Key desk truth: **stops do not protect through gaps or halts.** A biotech reopening −60% after a halted readout blows straight through any stop. Therefore event risk is managed by *position size before the event*, not by stops. | Decide before the event: hold through (size for the worst-case gap), trim to a size that survives the gap, or exit ahead. | 📚 ESTABLISHED (stop orders execute at next available price after a gap/halt reopen — mechanical fact of market microstructure, documented in every broker's stop-order disclosure; sizing-for-gap-risk is standard event-driven practice). Halt mechanics ✅ FETCHED below. |
| **Correlation / hedge drift** | For a hedged pair (our long/long pairs), the correlation that justified the pair breaks — partner stops tracking, or both legs start moving together *down* on sector beta. The hedge is only as good as the current correlation. | Rebuild or re-pair; if the hedge is dead, the position is now an unhedged single-name bet and gets resized as one. | 📚 ESTABLISHED (pairs-trading practice: Gatev, Goetzmann & Rouwenhorst, "Pairs Trading: Performance of a Relative-Value Arbitrage Rule," *Review of Financial Studies* 2006 — divergence beyond historical relationship is the exit/re-evaluate trigger). |
| **Sector move vs. idiosyncratic move** | The first question a PM asks on any adverse move: is it *my name* or *the sector*? An XBI-wide −4% day means the position's move carries little information about the thesis; a −8% idio move on flat XBI is a fire alarm. | Sector move → usually hold (thesis intact), re-check heat. Idio move with no news → investigate hard, treat as information. | 📚 ESTABLISHED (beta decomposition of P&L is standard attribution practice; Grinold & Kahn, *Active Portfolio Management*, ch. on risk decomposition). |
| **NEWS — the biotech-critical monitor** (detailed below) | Any headline on a held ticker: FDA action, trial halt, competitor readout, M&A, offering, short report, trading halt. | Ranges from hold (irrelevant PR) to instant exit decision (clinical hold). See 1.2. | Sources per item below. |

### 1.2 The biotech news taxonomy — unscheduled events that hit a held name intra-week

These are the events that make our one-week holds dangerous, ranked roughly by severity. Each row = what it is → how it manifests in data → what a desk does.

1. **Trading halt (news pending / volatility).** The exchange halts the stock. Codes that matter (Nasdaq Trader, ✅ FETCHED): **T1** "Trading is halted pending the release of material news"; **T2** news released, dissemination in progress; **T12** halted pending additional information requested by Nasdaq; **LUDP** volatility trading pause (Limit Up-Limit Down); **H10** SEC trading suspension. A T1 on a held biotech almost always precedes binary news (FDA action, readout, M&A). Regulatory halts on the primary listing are honored by all other US venues (SEC investor.gov, ✅ FETCHED — "when a security's primary market implements a regulatory halt, the other U.S. markets... honor this halt"). LULD mechanics (📚 ESTABLISHED, exact bands per the SEC-approved LULD NMS Plan — luldplan.com FAQ and Nasdaq FAQ PDF both failed to fetch today, so band percentages are from standing knowledge, UNVERIFIED-fetch): price bands around a 5-min reference price — 5% (Tier 1 large caps), 10% (Tier 2, most of our universe), 20% for stocks $0.75–$3.00; a limit state that doesn't resolve in 15 seconds becomes a 5-minute trading pause; bands double in the last 25 minutes of trading. **Desk reaction to a T1 on a held name: you cannot trade — the only decision is preparing the reopen plan (exit ladder vs. hold) while halted.** Detection: Nasdaq trade-halts RSS (✅ VERIFIED LIVE today — see Section 2).
2. **FDA action — CRL, approval, clinical hold.** A **clinical hold** (21 CFR 312.42 — FDA orders a trial delayed/suspended; eCFR fetch was bot-walled today, regulation number 📚 ESTABLISHED) or a Complete Response Letter is thesis-invalidating for a catalyst trade: the catalyst we sized for is gone or postponed. Desk reaction: exit or cut hard — the position's reason to exist has changed, and the market reprices in one gap. Detection: company 8-K/PR (EDGAR full-text, GREEN per our free-data-sources research), RTTNews FDA calendar backfills outcomes.
3. **DSMB/IDMC trial halt** (for futility or safety). Same severity class as a clinical hold; announced via PR/8-K. Futility halt on the lead asset ≈ worst case for a development-stage name.
4. **Competitor readout.** A rival's success/failure in the same indication repricing our name without any filing from our name. Hardest to catch deterministically — it fires on a *different* ticker. Mitigation: our universe is curated, so the competitor map is known in advance (we already maintain disease/competitor pairs — `.planning/research/disease-competitor-pairs.md`); monitor held names' mapped competitors too.
5. **Dilution / offering.** Biotechs sell equity into strength — a pop on good news is routinely followed within days by a shelf takedown (424B5 prospectus supplement / 8-K Item 3.02 / announced offering PR) that caps the stock. For a one-week hold bought *because* of good news, this is the classic intra-week ambush. Desk reaction: usually trim/exit on the announcement (pricing pressure + signal that management sells here). Detection: EDGAR new-filing poll (424B5, S-3 takedown, FWP, 8-K). — 📚 ESTABLISHED (post-catalyst equity offerings are the standard biotech financing pattern; the filing types are mechanical SEC facts).
6. **M&A.** Acquisition of our name (gap up — decision: take the gift now vs. hold for bump) or our name's partner/competitor (repricing). Detection: halt feed + 8-K + headline.
7. **Short-seller report.** Activist short publishes mid-day; stock drops fast on high volume, sometimes halted LUDP. No reliable free deterministic feed exists for "a short report dropped" — it manifests as our price/volume triggers firing simultaneously. Desk reaction: read the report before acting; the first move is often not the last (bounces and second legs both common). — 📚 ESTABLISHED (activist-short event studies, e.g. on Hindenburg/Citron campaigns, document the immediate-drop pattern; UNVERIFIED for any specific stat).

### 1.3 The action vocabulary (and what it maps to for a long-only weekly book)

Real desks act from a small menu: **hold / trim / exit / hedge / add**. Constraints for us: long-only (no hedging via shorts/options), one-week horizon (no "average down and wait"), human gate downstream (MON recommends, never executes). So our menu collapses to:

- **HOLD** (with a logged note — the default for sector-beta moves and immaterial news),
- **TRIM** (restore risk to budget after a vol spike / ahead of a surfaced event / heat breach),
- **EXIT** (stop hit, thesis invalidated: CRL, clinical hold, futility halt, offering),
- **FLAG-FOR-REBUILD** (pair correlation broke, competitor readout changed the landscape — the *structure* needs the weekly builder's full machinery, not a quick trim).

"Add" exists on real desks but is deliberately excluded from MON's menu: adding risk intra-week is a build decision and belongs to the weekly builder + human gate, not the watchdog. (Our proposal, consistent with the fund's human-gate constraint.)

---
## Section 2 — Deterministic TRIGGERS: the cheap layer that fires before any LLM

Design rule: every trigger below is a pure function of data we already pull for free — computable in plain Python in milliseconds, no LLM anywhere. A trigger firing does not mean "act"; it means "wake the light agent with this payload." Data-source claims below reference our verified free-data-sources research (`.planning/research/free-data-sources.md`) plus two live tests run today: **Nasdaq trade-halts RSS** (`https://www.nasdaqtrader.com/rss.aspx?feed=tradehalts` — ✅ VERIFIED LIVE today: XML with per-item `IssueSymbol`, `ReasonCode` (T1/T2/T12/LUDP/…), halt time, resumption time; no auth; feed `ttl` = 1 minute) and **yfinance intraday bars** (✅ VERIFIED LIVE today: KURA `interval="5m"` → 156 bars/2d with OHLCV, and 30d daily bars for ATR/ADV — yfinance supports 5m granularity for roughly the trailing 60 days).

### 2.1 Trigger catalog — rule, data, false-positive risk, verdict

**P — Price/technical (compute per 5-min cycle during RTH, from yfinance 5m bars + cached daily ATR/ADV):**

| # | Trigger | Exact computable rule (our proposal, with sourced basis) | Data needed / have it? | False-positive risk | Verdict |
|---|---|---|---|---|---|
| P1 | **Halt detected** | Held ticker appears in Nasdaq trade-halts RSS with `ReasonCode ∈ {T1, T2, T12, H4, H9, H10, LUDP}` | Halts RSS ✅ live-verified; poll 1/min costs one GET | ~zero (it IS the event; LUDP on a wild tape is still worth a look) | **KEEP — highest signal-to-noise monitor we can build** |
| P2 | **ATR-normalized adverse move** | `(prev_close − last) / ATR14_daily ≥ 2.0` (fires on drops; a mirrored +2 ATR "gift" fire is optional). ATR14 per Wilder (✅ FETCHED StockCharts: TR = max(H−L, \|H−C₋₁\|, \|L−C₋₁\|), 14-period smoothed), computed once daily EOD. | yfinance 5m last + daily bars ✅ | Moderate: biotech ATRs are fat; 2 ATR intraday ≈ genuinely unusual. ATR-normalization exists precisely to kill the "high-vol name fires daily" FP that a fixed % band has. | **KEEP — the primary price trigger** |
| P3 | Fixed % band (e.g. \|move\| > 7%) | `abs(last/prev_close − 1) ≥ X%` | same | High on volatile names, blind on quiet ones — dominated by P2 | **SKIP (P2 supersedes; keep only as sanity floor `max(2·ATR, 10%)` inside P2)** |
| P4 | **Stop-proximity** | Two levels: `last ≤ stop` → HARD fire; `last ≤ entry − 0.75 × (entry − stop)` → APPROACH fire (once). Stop itself set by the builder at entry (e.g. 2×ATR14 below entry, Turtle-style — 📚 ESTABLISHED, Faith 2007). | Position ledger (entry, stop) + 5m last ✅ | Low if stops are ATR-scaled; APPROACH fires at most once per position via latching | **KEEP — this is the monitor's core job** |
| P5 | **Volume spike** | `cum_volume_today ≥ 3 × (elapsed_fraction_of_day × ADV20)`, evaluated after 10:30 ET (first hour excluded — open volume is structurally lumpy). Time-of-day proration avoids the "every morning fires" FP. | 5m volume + daily ADV20 ✅ | Moderate: index rebalances, option expiry, sympathy moves. Alone it's noisy → require **P5 AND (P2 or news-hit)** to escalate beyond a log line, else log-only. | **KEEP as corroborator, log-only when solo** |
| P6 | New 5-day low/high | daily close < min(prior 5 closes) | daily bars ✅ | On a 1-week hold this mostly re-detects P2/P4 a day late | **SKIP for v1** |
| P7 | VWAP deviation | \|last − VWAP_today\| / VWAP > 3% | computable from 5m bars (approx) ✅ | High; VWAP is an execution benchmark, not a risk signal, on our horizon | **SKIP** |
| P8 | RSI/MACD extremes, MA crosses | RSI14 < 30 etc. (Wilder 1978 📚) | daily bars ✅ | These are *entry-timing* indicators; on a 5-day hold they lag the ATR/stop triggers and add nothing but whipsaw | **SKIP — wrong tool for a watchdog** |

**R — Risk/book-level (compute EOD + on any P-fire):**

| # | Trigger | Exact rule | Data / have it? | FP risk | Verdict |
|---|---|---|---|---|---|
| R1 | **Position heat breach** | `unrealized_pnl ≤ −1.0 × risk_budget` where `risk_budget = shares × (entry − stop)` — i.e., the position has lost what we planned to risk (should coincide with P4-hard; divergence itself is a bug alarm) | ledger + last ✅ | Low | **KEEP** |
| R2 | **Portfolio heat cap** | `Σ_open shares_i × (last_i − stop_i)⁺ ≥ heat_cap` (Seykota's heat, ✅ FETCHED — total open risk to stops), heat_cap set by PM (e.g. 2–4% of NAV; number = PM decision, Section 5) | ledger + lasts ✅ | Low | **KEEP (EOD + on any fire)** |
| R3 | **Realized-vol jump** | `σ(5d, close-to-close) ≥ 2 × σ(20d)` → position size no longer matches entry-time risk | daily bars ✅ | Moderate — one big day mechanically inflates 5d σ; that big day already fired P2. Value-add is catching *grinding* vol regimes | **KEEP, EOD-only** |
| R4 | **Pair-correlation break** | For each long/long pair: 20d rolling corr < 0.3 when the builder's entry assumption was ≥ 0.6, OR 5-day return spread between legs > 2 × its 20d σ (divergence trigger per pairs-trading practice — Gatev et al. 2006 📚) | daily bars ✅ | Moderate — 20d corr on 5d windows is noisy; EOD cadence + 2-day confirmation | **KEEP, EOD-only → routes to FLAG-FOR-REBUILD** |

**E — Event/news (poll cadence per source):**

| # | Trigger | Exact rule | Data / have it? | FP risk | Verdict |
|---|---|---|---|---|---|
| E1 | **New SEC filing on held ticker** | Poll `data.sec.gov/submissions/CIK{...}.json` (✅ verified GREEN in free-data-sources) every 10 min per held name; fire on any new accession with form ∈ {8-K, 424B5, S-3, FWP, SC 13D, 25-NSE}; payload includes form type + doc URL | EDGAR ✅ (UA header, ≤10 req/s) | Low: filings are facts. FP = immaterial 8-Ks (routine comp, §5.02 appointments) — the *agent's* job is materiality triage, cheap on Haiku | **KEEP — the authoritative news wire, free** |
| E2 | **Headline hit on held ticker** | Keyword screen on free headline feeds (yfinance `Ticker.news` + RTTNews page we already scrape daily): regex over title for {FDA, CRL, complete response, clinical hold, halt(ed), discontinu, offering, priced, dilut, DSMB, futility, acquir, merger, buyout, short seller, data, topline, phase [123]} | yfinance news (YELLOW, best-effort) + RTTNews ✅ | High-ish: headline noise, dupes, PR fluff. Mitigate: dedupe by URL hash, fire once per story, and treat as corroborator unless keyword ∈ hard set {CRL, clinical hold, halted, offering, DSMB, futility} | **KEEP with hard/soft keyword tiers** |
| E3 | **New catalyst date inside hold window** | Daily diff of ClinicalTrials.gov v2 fields (status, primaryCompletionDate) for held names' trials + Federal Register AdCom notices + RTTNews rows: fire if a new/changed event lands ≤ our exit date | All ✅ GREEN (free-data-sources §2, §4.1) | Low; CT.gov date edits can be admin noise → fire only on changes that cross into the hold window | **KEEP, daily (these sources move at daily cadence anyway)** |
| E4 | Competitor-readout watch | Run E1+E2 keyword screens over the *mapped competitors* of held names (from disease-competitor-pairs), fire tagged `competitor` | same sources ✅ | Same as E1/E2 | **KEEP if pair map exists (it does); payload marks it non-held ticker** |
| E5 | Dedicated short-report feed | — | No reliable free deterministic source | — | **SKIP — P2+P5 catch the price effect; agent reads the news after the fact** |

### 2.2 Recommended starter set (v1)

Eight monitors: **P1 halts (1-min RSS poll), P2 ATR-move + P4 stop-proximity + P5 volume (5-min loop over ≤20 names), E1 EDGAR filings (10-min), E2 headlines (15-min), E3 catalyst-date diff + R2/R3/R4 book checks (EOD)**. Everything else is cut for v1. This set covers every row of the Section 1 monitor table except "vol spike intraday" (deliberately EOD — a true intraday vol event fires P2 anyway).

False-positive philosophy: P-triggers are *corroborated* (P5 solo = log only; P2 solo on a red-sector day gets down-weighted by the agent's sector check), E-triggers are *facts* triaged for materiality by the agent, R-triggers are *policy* (a heat breach is actionable by definition — the PM set the cap). Total infra cost: ~1 GET/min (halts) + ~20 yfinance calls/5min + ~120 EDGAR GETs/hr worst case — all free, all within polite-use limits documented in free-data-sources.md.

---
## Section 3 — What the LIGHT agent group does once triggered

### 3.1 Minimal context (the "position card" pattern)

The agent should never re-research the position from scratch — the weekly builder already did that. It receives a compact, pre-assembled payload (~1–2K tokens):

1. **Trigger payload** — which rule fired, the computed values (e.g. "P2: −2.4 ATR, last 10.86 vs prev close 12.05"), and any corroborating fires in the same window.
2. **Position card** (written by the builder at entry, stored in the ledger): ticker, entry price/date, size, stop, planned exit date, the thesis in ≤3 sentences, the catalyst and its date, the pair partner + entry correlation, and the pre-declared invalidation conditions ("exit if: CRL, offering, hold; hold through: sector beta").
3. **Deterministic tool outputs on demand** — the agent calls tools that *compute* (current price/ATR/volume context, sector ETF (XBI) move today, halt status, the filing text/URL for E-fires, CBOE `iv30` and its change). Tools return numbers + source URLs; the agent interprets. Agents never estimate a number a tool can fetch — the cite-or-drop invariant from our data-stack research carries over verbatim: every claim in its output carries `{value, source_url, fetch_ts}` or is dropped.

This mirrors how a real desk works a risk alert: the risk system pages with the breach numbers; the PM pulls up the position blotter (card) and the tape (tools); nobody re-derives the thesis. — 📚 ESTABLISHED (standard alert-triage workflow).

### 3.2 Decision rubric (deterministic skeleton, judgment only at the leaves)

The agent walks a fixed tree; the LLM's judgment is confined to two nodes (materiality and thesis-impact), which is what keeps Haiku sufficient:

```
1. Is the ticker halted (P1)?            → yes: no action possible; output PREPARE-REOPEN note + page human. Done.
2. Is this a hard-stop breach (P4-hard/R1)? → yes: recommend EXIT (policy, not judgment). Route to human gate. Done.
3. Is there a hard-keyword event (E1/E2 hard set: CRL, clinical hold, DSMB/futility, offering priced)?
                                          → yes: verify against primary source (8-K/PR URL — cite or drop).
                                            Confirmed → recommend EXIT (thesis invalidated). Unconfirmed → HOLD + re-arm + escalate model tier.
4. Is the move explained by sector beta (tool: XBI day move; idio residual = stock move − β·XBI move)?
                                          → mostly sector: HOLD with note. Done.
5. Materiality judgment (the LLM node): does the trigger + news context plausibly change the entry thesis
   before our exit date?                  → no: HOLD with note.
                                          → partially (vol spike, surfaced event in window, heat): TRIM to restore risk budget.
                                          → structurally (pair broke, competitor readout, catalyst moved): FLAG-FOR-REBUILD.
                                          → fully (thesis dead): EXIT.
6. Every output: action ∈ {HOLD, TRIM x%, EXIT, FLAG-FOR-REBUILD} + ≤5-sentence rationale + citations + confidence.
   Anything ≥ TRIM routes to the human gate; HOLD is logged only.
```

### 3.3 Anti-whipsaw: how real desks avoid overreacting (and our translations)

| Desk practice | Rationale | Our deterministic translation |
|---|---|---|
| **Act on confirmation, not first print** — e.g., act on a close beyond the level, or a second bar, not a single tick | Single prints are noise; LULD reopens overshoot | P2/P5 require **two consecutive 5-min bars** beyond threshold before firing (except P1/P4-hard, which are never debounced) |
| **Cooldown after action** — a stopped-out name isn't re-entered immediately (Turtle re-entry required a fresh breakout — 📚 Faith 2007) | Prevents ping-pong | Per (ticker, trigger-type) cooldown: 60 min after a fire; per-ticker cap of 4 agent-wakes/day, then batch to EOD |
| **Hysteresis on thresholds** | A price oscillating at the band would re-fire forever | Re-arm a fired trigger only after the metric retreats to 50% of threshold |
| **Hard rules for hard events, judgment for soft ones** — stops are non-negotiable; "it feels heavy" is not | Discipline beats discretion at the panic moment (Seykota: "stick to the system" ✅ FETCHED) | Tree levels 1–3 are policy (no LLM latitude to override an EXIT recommendation on a hard stop); level 5 is judgment |
| **Escalate ambiguity, don't guess** | Junior trader calls the PM | Haiku sets `confidence`; below threshold or on conflicting evidence → re-run once on Sonnet-class; still ambiguous → HOLD + page human with both readings |

### 3.4 Escalation path

- **Auto (no human):** logging HOLDs, re-arming, EOD digests.
- **Human gate (existing approval channel, same as builder):** every TRIM / EXIT / FLAG-FOR-REBUILD recommendation — per the fund's hard constraint, *no order without explicit approval*, including stop-loss exits. Consequence to accept: a hard-stop EXIT waits for a human tap. Mitigation: hard-stop pages are pushed loudest (ZeeChat), and Section 5 asks the PM whether resting stop orders at the broker should back-stop the human gate.
- **Model escalation:** Haiku → Sonnet-class only on (a) hard-keyword E-fires whose primary source is ambiguous, (b) confidence below floor, (c) conflicting triggers (e.g. price up + offering filed). Never escalate for HOLDs.

---
## Section 4 — Cadence, cost, and the "many times a day" design

### 4.1 Cadence stack

| Layer | Cadence | Cost character |
|---|---|---|
| Halt RSS poll | 60s during RTH (feed TTL is 1 min — ✅ verified) | 1 GET/min, zero LLM |
| Price/volume loop (P2/P4/P5) over ≤20 names | 5 min during RTH (78 cycles/day) | ~20 yfinance calls/cycle, zero LLM |
| EDGAR submissions poll | 10 min per held name | zero LLM |
| Headlines (E2) | 15 min | zero LLM |
| Catalyst-date diff (E3), book risk (R2–R4) | EOD, once | zero LLM |
| **Light agent** | **event-driven only** | Haiku, only on fires |
| EOD digest | once/day | one Haiku call summarizing the day's log |

Debouncing (2-bar confirmation), cooldowns (60 min per ticker-trigger), hysteresis (re-arm at 50%), and the 4-wakes/day/ticker cap are what make "can fire many times a day" safe: the deterministic layer may *evaluate* thousands of times daily but *fires* a handful.

**Batching:** fires within a 5-min window across tickers are coalesced into ONE agent invocation with N flagged positions — a market-wide selloff triggers one contextual review ("XBI −5%, 6 names breached P2") instead of 6 independent panics. This materially improves decisions (sector context is shared) and cuts cost ~N×.

### 4.2 Cost framing (verified pricing, claude-api skill, cached 2026-06)

Haiku 4.5 = $1/MTok in, $5/MTok out; Sonnet-class = $3/$15. A typical wake: ~2.5K tokens in (card + payload + tool outputs) / ~400 out ≈ **$0.0045**. Pessimistic day — 15 wakes + 3 Sonnet escalations (~4K/600) + EOD digest: 15×$0.0045 + 3×$0.021 + $0.01 ≈ **$0.14/day**, ~$0.70/week. Quiet day: 2–3 wakes ≈ $0.02. The deterministic layer costs effectively $0 (free APIs + a Python loop on the Mac). **Even at 10× these volumes, MON costs less than one commission-free trade's slippage** — cost is a non-issue *because* the LLM only runs on fires; continuous LLM polling at 5-min cadence would be ~78 calls/day/name = ~$35/week for zero added signal, which is precisely why real desks put the expensive resource (analyst attention ↔ big-model tokens) behind exception gates and leave the always-on layer to dumb, fast systems. — pricing ✅ verified via claude-api skill; the desk analogy 📚 ESTABLISHED (Section 1.0).

---
## Section 5 — Recommended MON design + decisions for the PM

### 5.1 The design in one diagram

```
                    ┌──────────── DETERMINISTIC LAYER (Python, $0) ────────────┐
  Nasdaq halts RSS──┤ P1 halt   (60s)                                          │
  yfinance 5m ──────┤ P2 ATR-move · P4 stop-prox · P5 volume  (5 min, RTH)     │
  EDGAR ────────────┤ E1 filings (10 min)      E2 headlines (15 min)           │
  CT.gov/FedReg/RTT─┤ E3 catalyst-date diff · R2 heat · R3 vol · R4 pair (EOD) │
                    └───────── debounce · cooldown · hysteresis · batch ───────┘
                                        │ fires (payload + position card)
                                        ▼
                    ┌── LIGHT AGENT (Haiku 4.5, event-driven) ──┐
                    │ fixed decision tree (§3.2)                │
                    │ tools compute · agent interprets · cite-or-drop │
                    │ escalate→Sonnet only on genuine ambiguity │
                    └───────────────┬───────────────────────────┘
              HOLD → log only       │ TRIM / EXIT / FLAG-FOR-REBUILD
                                    ▼
                    HUMAN GATE (iOS approval, ZeeChat page on hard fires)
                                    │ approved
                                    ▼
                    PORTFOLIO BUILDER / EXECUTION (existing weekly machinery;
                    FLAG-FOR-REBUILD enqueues a mid-week mini-build run)
```

Trigger set: the 8 starter monitors of §2.2. Rubric: §3.2. Routing: MON writes a `MonitorRecommendation{ticker, action, rationale, citations, confidence, trigger_ids}` record; TRIM/EXIT go to the human gate as one-tap approvals executed by the existing execution path; FLAG-FOR-REBUILD enqueues the builder with the MON dossier attached (builder decides re-pair vs. exit vs. re-size with its full machinery). Cost: ~$0.10–0.70/week (§4.2).

### 5.2 Decisions the PM must make (explicit either/or)

1. **Stop mechanics:** (a) *soft stops only* — MON detects, human approves every exit (pure to the fund's human-gate constraint; risk: an unattended −2 ATR afternoon keeps falling while the page sits unread), or (b) *resting broker stop orders as backstop* — human gate governs discretionary changes but a GTC stop-loss at the hard level rests at Robinhood (risk: gap-through executes at a bad print; also verify the RH MCP even supports stop orders). **Recommend (a) for paper month, revisit after measuring page-to-approval latency.**
2. **Adjustment aggressiveness:** may MON recommend (a) *exit-only* (binary: keep or kill — simplest, no partial-fill bookkeeping), (b) *exit + fixed-ratio trim* (TRIM = sell 50%, one size fits all), or (c) *free resize* (agent proposes any %)? **Recommend (b): one trim size keeps the ledger and the approval UI trivial.**
3. **Human gate scope intra-week:** (a) *everything gated* (including hard-stop exits — status quo constraint), or (b) *pre-authorized hard stops* (PM pre-approves the stop at build time; MON's hard-stop fire executes without a second tap, discretionary actions still gated). (b) is how real desks treat stops — the decision was made at entry — but it loosens the fund's stated no-trade-without-approval rule, so it is a PM call, not ours. **Recommend (a) during paper trading, (b) considered only with real money + measured latency.**
4. **Cadence ceiling:** (a) *5-min price loop* (as designed — catches intraday collapses ~hours earlier), or (b) *EOD-only MON* (radically simpler, near-zero infra, but a Tuesday-morning CRL is seen Tuesday night). Given biotech's intraday binary risk, **recommend (a); (b) is defensible only if the PM accepts overnight-sized reaction lag on a book explicitly built around binary events.**
5. **Competitor watch (E4) in v1:** (a) include held names' mapped competitors in E1/E2 polling (≈2× the polling surface, catches the readout-by-proxy case), or (b) defer to v2. **Recommend (a) — the pair map already exists and the marginal cost is a few extra GETs.**
6. **Heat cap number (R2):** portfolio open-risk-to-stops cap as % of NAV — 2%, 3%, or 4%. Pure risk-appetite call (Seykota's "Uncle Point" is explicitly investor-set — ✅ FETCHED). Needed before R2 can be armed. **No recommendation — this is the PM's risk budget by definition.**

### 5.3 What we did NOT verify (honest flags)

- LULD band percentages (5/10/20%, doubling in last 25 min): both authoritative fetch targets failed today (luldplan.com FAQ 404, Nasdaq FAQ PDF unparseable); figures are standing market-structure knowledge — re-verify before quoting in any external doc.
- Multi-strat drawdown thresholds (5%/7.5%): press-reported folklore, illustrative only.
- Original Turtle rules PDF (trendfollowing.com) 404'd; 2N-stop and re-entry rules cited from Faith, *Way of the Turtle* (2007) from knowledge.
- Whether Robinhood's agentic MCP supports resting stop orders (decision 1b depends on it) — flagged as a must-verify in the fund's STACK research already.
- yfinance `Ticker.news` reliability as a headline feed (YELLOW source; E2 is deliberately a corroborator, with EDGAR E1 as the authoritative wire).

*(End of research, 2026-08-15. Live tests this date: Nasdaq halts RSS, yfinance 5m/daily bars, CBOE/EDGAR/FINRA/CT.gov per free-data-sources.md. Fetched sources: investor.gov trading-halts glossary; nasdaqtrader.com halt codes; StockCharts ChartSchool ATR + Chandelier Exit; seykota.com risk essay.)*
