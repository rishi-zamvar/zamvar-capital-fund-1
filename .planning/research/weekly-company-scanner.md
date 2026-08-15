# Weekly Company-Vetting Scanner (SCAN / Phase 6.8) — Deterministic Flaggers → KB-Armed Haiku Once-Over

Research date: 2026-08-15. Purpose: design the weekly company scanner (SCAN-01..04, the qualitative producer of WEEK-06 flags) — a cheap, refreshable, Haiku-tier replica of the diligence workflow that vets each of the ~20 universe COMPANIES forward for the upcoming week and surfaces trading OPPORTUNITIES from possible volatility, routing them up to the MD (RECON-08).

**The shape (operator-locked):**

```
STAGE 1  deterministic flaggers          — pure Python over data we ALREADY have; computes each
         (per name, weekly, $0 LLM)        name's company card + week-over-week deltas; decides
                                           WHO gets looked at (monitor-by-exception)
            │ tripped flags + card pair
            ▼
STAGE 2  Haiku analyst once-over         — full KB + playbook access (analog_query, query_playbooks);
         (flagged names only)              answers: what is of interest, is it a REAL explorable
                                           opportunity, what specifically to build into the week
            │ OpportunityFlag (thesis-to-verify, never a trusted answer)
            ▼
MD router (RECON-08) → verification workflow (catalyst call / measured edge / mini-backtest)
            → verified assumptions into run_weekly portfolio → monitored intra-week (Phase 8.5)
```

**Method + confidence note:** grounded in direct reads of the shipped modules (`src/catalyst_trader/desk/diligence.py`, `src/catalyst_trader/quant/weekly.py`, `src/catalyst_trader/desk/weekly.py`, `src/catalyst_trader/desk/tools.py`, `src/catalyst_trader/kb.py::analog_query/query_playbooks`, `src/catalyst_trader/store.py::bars_asof`, `src/catalyst_trader/desk/runtime.py::run_structured`, `src/catalyst_trader/migrations/005_price_bars.sql`) and the project's live-verified research docs (`.planning/research/intra-week-monitoring.md`, `.planning/research/free-data-sources.md` — both carry their own fetch/live-test provenance). WebSearch budget was unavailable; external finance claims not re-fetched today are marked **📚 ESTABLISHED** with author/title so a human can verify. Thresholds that are design choices are labeled "our proposal." Flags needing data we do NOT have are explicitly marked **FUTURE** — nothing below invents a feed.

---

## Section 1 — Structure: the DD workflow re-pointed, and STAGE 1's concrete deterministic flaggers

### 1.0 What changes when the DD workflow vets a company-week instead of a trade

`desk/diligence.py` answers *"here is a proposed trade — kill it."* The scanner answers *"here is a company — what could make it volatile/tradeable in the next 5 trading days?"* Three structural consequences:

1. **Direction-agnostic output.** DD emits go/no-go on a directional trade. The scanner emits a volatility/opportunity read with a candidate thesis **to verify** — direction is what the downstream verification (Workflow-1 catalyst call) exists to establish (SCAN-04). A scanner that emits trusted direction is doing Workflow-1's job badly on a cheaper model.
2. **The adversarial polarity flips.** DD kills a trade the promoting desk loves. The scanner's adversarial job is to kill a *false opportunity*: "assume this delta is noise / already priced in / untradeable — prove it real before flagging." Same assume-the-promoter-is-wrong discipline, aimed at the scanner's own trigger. This matters because the scanner's failure mode is the mirror image of DD's: DD fails by letting a bad trade through; the scanner fails by spamming the MD with noise.
3. **The fan-out inverts from LLM-heavy to deterministic-heavy.** DD runs 8 LLM dimension agents per trade because a promoted trade is rare and worth the scrutiny. The scanner covers 20 names × 52 weeks; a naive 8-agent replica is 160+ LLM calls/week. So the 8 DD dimensions survive **as deterministic card fields + flag rules (Stage 1)**, and the LLM runs as **one consolidated analyst pass per flagged name (Stage 2)** — the dimensions become the analyst's checklist, not 8 separate agents.

Dimension mapping (what carries over, what re-frames):

| DD dimension | Company-forward re-framing | Where it lands |
|---|---|---|
| `trial_stats` | readout proximity: trial status/completion-date changes near the week | Stage-1 flags F1–F2 |
| `regulatory` | PDUFA/AdCom proximity (days-to-catalyst bands) | Stage-1 flag F1 |
| `financials` | dilution pressure: runway bands + shelf/offering filings | Stage-1 flags F8–F9 |
| `ownership_flow` | unusual positioning: short-interest / days-to-cover shifts | Stage-1 flag F6 |
| `options_move` | forward vol expectation: iv30, expected move, term kink | Stage-1 flags F4–F5 |
| `hedge_revalidation` | **replaced** by competitor-event watch (a mapped peer's catalyst repricing this name); hedge construction belongs to Workflow-2 *after* verification | Stage-1 flag F3 |
| `liquidity` | tradeability if an opportunity fires — reuse `diligence.options_liquid` / `zero_liquidity` as card booleans | card field, gate on Stage-2 output |
| `historical_analog` | measured-cell membership (`thesis_scan` row) + KB analogs on flag | Stage-1 flag F12 + Stage-2's `analog_query` |

### 1.1 STAGE 1 — the deterministic flagger catalog (the cheap layer that decides who gets looked at)

Design rules, inherited verbatim from the intra-week research (§2, "every trigger is a pure function of data we already pull") and `quant/weekly.py` (no literals in tool bodies — every threshold read from `params["scan"]` by direct subscript, missing-key-raises):

- Every rule is computable in plain Python from a feed this repo already has or has live-verified. **No invented data.**
- Every rule is expressed as a **week-over-week delta on the persisted company card** (Section 2) — a band TRANSITION, not a level (§2.1) — so a standing condition fires once, not every week.
- Flags are tiered: **PRINCIPAL** (any one wakes the Stage-2 analyst) vs **CORROBORATOR** (log-only alone; wakes only alongside another flag) — the intra-week P5-solo-is-log-only philosophy.

| # | Flag | Exact computable condition (proposal) | Data source (real, in-stack) | Week-over-week delta form | Materiality threshold + basis | Tier |
|---|---|---|---|---|---|---|
| F1 | `catalyst_entered_window` | `days_to_catalyst(t) ≤ B < days_to_catalyst(t-1)` for band B ∈ {14, 7} | curated catalyst table (`store.tradeable_catalysts`: verified PDUFA/AdCom/readout/earnings rows) | band crossing on `days_to_catalyst` | B=7 hard, B=14 soft — the fund's T-2 premise widened one notch; scheduled events carry a priced event-jump premium (📚 ESTABLISHED — Dubinsky & Johannes, "Earnings Announcements and Equity Options," 2006) | PRINCIPAL |
| F2 | `ct_gov_changed` | any diff in a tracked NCT's `status` or `primaryCompletionDate` that moves an event into/out of the next-4-weeks window | ClinicalTrials.gov API v2 (GREEN, free — `free-data-sources.md` §2; same E3 diff intra-week research specified) | field diff vs last week's stored values | only window-crossing changes (intra-week E3 rule verbatim — date edits that don't cross are admin noise) | PRINCIPAL |
| F3 | `competitor_catalyst_7d` | F1's check run over the name's mapped competitors: any mapped peer has `days_to_catalyst ≤ 7` | catalyst table + `disease-competitor-pairs.md` map (exists) | band crossing on peer's `days_to_catalyst` | ≤7 days — a rival readout reprices our name with no filing of its own (intra-week §1.2.4) | PRINCIPAL |
| F4 | `iv_spike` | `iv30(t) − iv30(t-1) ≥ 5` vol points, OR `straddle_move_pct(t) ≥ 1.5 × median(straddle_move_pct, last 8 cards)` | CBOE delayed-quotes JSON — ✅ live-verified (`free-data-sources.md` §1.1: symbol-level `iv30`, `iv30_change`; §1.8: straddle expected move = (ATM call mid + put mid)/spot) | arithmetic delta on stored `iv30`; ratio vs own trailing median | 5 pts = half the "distrust >10 pts disagreement" scale from §1; own-median normalization mirrors intra-week P2's ATR-normalization (fat-vol names must not fire weekly) | PRINCIPAL |
| F5 | `term_kink` | `term_spread = frontATM_IV − nextATM_IV` flips sign or moves ≥ 5 pts vs last card | same CBOE JSON, both expiries in one GET (§1.8's stated event signal) | signed delta on stored `term_spread` | sign flip = event premium appearing/collapsing in the front expiry | PRINCIPAL |
| F6 | `si_shift` | `(SI(t) − SI(t-1))/SI(t-1) ≥ 0.20` OR `days_to_cover(t) − days_to_cover(t-1) ≥ 2.0` | FINRA Query API short interest — ✅ triple-verified live vs Nasdaq + Yahoo (`free-data-sources.md` §3.1–3.2) | relative delta on stored SI / DTC (only when a NEW settlement date appears — bi-monthly + ~9bd lag, stored as `si_settlement_date` so staleness is visible) | 20%/2-day steps sized to publication cadence; short interest carries return/vol information (📚 ESTABLISHED — Dechow, Hutton, Meulbroek & Sloan, *JFE* 2001); DTC step is our proposal, UNVERIFIED as a literature constant | PRINCIPAL |
| F7 | `vol_regime` | `σ(last 5 weekly rets) ≥ 2.0 × σ(last 20 weekly rets)` newly true | `store.bars_asof` weekly OHLCV (shipped, $0) | boolean transition (latched) | intra-week R3's σ5/σ20 ≥ 2 rule verbatim; vol clusters (📚 ESTABLISHED — Engle, ARCH literature) | CORROBORATOR |
| F8 | `runway_band_drop` | `runway_band(t) < runway_band(t-1)`, bands {>18, 12–18, 6–12, <6 months} | FMP statements → existing `mcp__quant__cash_runway` tool computes months (agent never does the division — diligence.py precedent) | band step on stored `runway_band` (quarterly data → fires ~4×/yr) | any band step; sub-12-month biotech runway = predictable financing event | PRINCIPAL |
| F9 | `offering_signal` | new EDGAR accession with form ∈ {424B5, FWP} — or new S-3 while `ret_4w > +20%` | EDGAR submissions JSON (GREEN, verified in free-data-sources; same E1 poll intra-week specified, weekly cadence here) | new-accession diff vs last card's seen-accessions set | hard set fires alone; post-pop shelf = the classic biotech ambush (intra-week §1.2.5 — 📚 ESTABLISHED financing pattern) | PRINCIPAL |
| F10 | `ma_cross` | weekly close crosses the 12-week MA in either direction (close(t) vs MA12 sign ≠ close(t-1) vs MA12 sign) | `bars_asof` | sign transition on stored `px_vs_ma12` | the weekly close IS the confirmation bar at this cadence (intra-week §3.3: "act on a close beyond the level, not a single tick") | CORROBORATOR |
| F11 | `volume_anomaly` | `turnover_flag` flips low→high AND latest volume ≥ 3× trailing median | `bars_asof` volumes via `quant/weekly._turnover_flag` logic (reuse, don't re-derive) | flag transition + ratio | 3× = intra-week P5's multiplier; abnormal volume around information events is the classic leak tell (📚 ESTABLISHED — Beaver, *JAR* 1968) | CORROBORATOR |
| F12 | `quant_row_change` | this week's `thesis_scan` row differs materially from last week's: `eligible` flips, `drop_class` changes, a `veto_reason` appears/clears, or `trigger` cell changes | `quant/weekly.thesis_scan` — already runs weekly inside `run_weekly`; the scanner CONSUMES the row (Section 3.3) | field diff on the embedded thesis row | any of the four listed transitions — these are the quant layer's own state changes | PRINCIPAL |
| F13 | `big_move_unexplained` | `drop_class == "idio_no_news"` AND \|ret_1w\| ≥ 10% | `classify_drop` (shipped: sector/idio split via `correlation_beta` vs XBI + news gate) | class+magnitude on current card (transition-latched on the class) | a ≥10% idio move with no verified catalyst = information we don't have yet — the scanner's job is exactly to get an analyst's eyes on it | PRINCIPAL |
| — | analyst rating / price-target changes | — | **FUTURE — no free reliable feed identified** (`free-data-sources.md` has no GREEN/YELLOW source for this) | — | — | — |
| — | 13F ownership shifts | — | **FUTURE — 45-day filing lag makes it stale at weekly horizon**; EDGAR 13D/G could be added to F9's form set later | — | — | — |
| — | intraday halts / stop proximity / heat | — | **NOT THIS MODULE** — intra-week monitor's job (Phase 8.5); the scanner is a weekly, pre-positioning instrument | — | — | — |

Anti-whipsaw mechanics carried over from intra-week §3.3, translated to weekly cadence: **latching** (each fired flag records `fired[flag] = week_end` on the card and cannot re-fire while the condition persists), **hysteresis** (re-arm only after the metric retreats past 50% of its threshold distance), **corroboration** (F7/F10/F11 never wake Stage 2 alone), and a **wake cap** (`max_stage2_wakes` per week, default 8 — our proposal — beyond which lowest-confidence flags batch into one review, mirroring intra-week's batching rule).

The Stage-1 output for every name — flagged or not — is a stored deterministic row: `{ticker, week_end, flags_tripped: [...], no_material_change: bool}`. Most names most weeks are the cheap `no_material_change` row, which is itself a valid, comparable, data-backed read (`thesis_scan`'s "'no measured edge' row is itself a valid read" precedent).

### 1.2 STAGE 2 — the Haiku analyst once-over, armed with the KB + playbooks

When a name trips (any PRINCIPAL, or ≥2 CORROBORATORs), ONE Haiku analyst call runs for that name. What makes the once-over smart rather than generic is **full KB + playbook access** — the same quant MCP server DD's dimensions use (`tools.build_quant_server(conn)`, reusing `ALLOWED_TOOLS` from diligence.py: `base_rate`, `analog_query`, `query_playbooks`, `rnpv`, `cash_runway`, `implied_move`, `correlation_beta`).

**Input (the firewall):** a typed `ScanInput` (extra="forbid", mirroring `DiligenceInput`) carrying ONLY `{ticker, week_end, card_prev, card_cur, tripped: [{flag, prev, cur, threshold}]}`. No Workflow-1/2 verdicts, no open-position context, no MD state — the analyst cannot be anchored by what the desk already believes, and a leak is a type error, not a policy check.

**Prescribed tool calls** (hard rules in the prompt, exactly the diligence.py "CALL the tool, never compute" discipline):

1. **`mcp__quant__analog_query`** — MANDATORY on every wake. `context` = a *deterministic* serialization of the tripped flags built by Python, not the LLM (e.g. `"KURA week 2026-08-21: iv_spike +9pts to 96; catalyst_entered_window PDUFA in 6d; si 18.2% dtc 6.1"`), `filters` = `{"ticker": ...}` and, when F1/F2 tripped, `{"catalyst_type": ...}`; `k=5`. Returns the nearest past scenarios **with their realized Outcomes** (`kb.analog_query` does structural SQL filter → semantic KNN → attaches outcomes), each minted a `tool:analog_query#<hash>` evidence ref by construction (`tools.py`). This is the "similar past situations + how they resolved" memory.
2. **`mcp__quant__query_playbooks`** — MANDATORY when the candidate opportunity type maps to a known scenario vocabulary. `scenario_type` = the card's catalyst type for F1/F2 fires (the playbook store's vocabulary is catalyst-shaped today: `fitted_params:<type>` + scenario playbooks keyed by `scenario_type`); returns confidence-desc learned plays. **Honest gap:** non-catalyst opportunity types (`squeeze_setup`, `dilution_risk`, …) have no playbook vocabulary yet — the analyst reports "no playbook" as an unknown, and scanner-specific playbook types accrete via the Phase-10 LEARN loop (FUTURE, flagged in §5.4).
3. **`mcp__quant__base_rate`** — when F1/F2 tripped and the event is clinical: the cited phase-transition/LoA prior for the indication.
4. **`mcp__quant__implied_move` / `cash_runway`** — to re-cite the card's options/runway numbers as tool refs (the card carries the values; the tool call mints the citable ref — same "re-call the tool to cite it" instruction `options_context` already uses).
5. **The `weekly_base_rate` cell** — NOT re-called: the card embeds this week's `thesis_scan` row with its tool ref; the analyst cites the embedded ref.

**The three questions the analyst must answer for THIS company THIS coming week** (the prompt's core, replacing DD's kill-the-trade brief):

1. *What is of interest?* — interpret the tripped deltas against the KB analogs: is this pattern one that historically preceded a tradeable move, or one that resolved as noise? (Adversarial framing: start from "this is noise / already priced in / untradeable" and try to defeat that.)
2. *Is it a real explorable opportunity?* — check against the card's liquidity booleans (`options_liquid` / `zero_liquidity` — an untradeable name is never an opportunity), the analog outcomes, and any playbook.
3. *What specifically should be built into the weekly portfolio?* — NOT a trade: a **falsifiable thesis-to-verify** plus which verification workflow must test it (SCAN-04 vocabulary: `catalyst_call` for direction, `measured_edge` for a statistical cell, `mini_backtest` for a novel setup, `diligence` for a full DD pass).

**Output — the `OpportunityFlag` contract** (new, extra="forbid"; Section 4 for the routing semantics):

```python
class OpportunityFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str
    week_end: str
    opportunity_type: Literal["catalyst_vol", "squeeze_setup", "dilution_risk",
                              "technical_reversal", "continuation",
                              "competitor_event", "unknown_vol", "no_opportunity"]
    thesis_to_verify: str            # ONE falsifiable sentence; a hypothesis, never a call
    verification_needed: Literal["catalyst_call", "measured_edge", "mini_backtest", "diligence"]
    key_findings: list[KeyFinding]   # REUSE — claim + evidence_ref, cite-or-drop enforced by the model
    kb_analogs: list[str]            # the analog_query evidence refs leaned on (may be empty w/ unknown)
    tripped_flags: list[str]         # echo of the Stage-1 flags (deterministic, threaded by Python)
    unknowns: list[str]              # gaps a tool could not close — the gap-not-answer payload
    confidence: float                # [0,1]
```

`no_opportunity` is a first-class, *expected* outcome — the adversarial pass killing its own trigger is the scanner working, and it is stored (not routed) so the false-positive rate of each Stage-1 flag is measurable (feeds threshold retuning, §5.4). Fixed vocabularies keep flags machine-routable and comparable week-over-week (the `_TRIGGERS` fixed-grammar discipline).

**Cite-or-drop enforcement:** structural stage only — every `key_finding.evidence_ref` must resolve via `evidence.resolve` (tool refs resolve by construction); unresolvable findings are dropped in Python before routing. DD's second-stage *opus* semantic support check (`enforce_dossier`) is deliberately NOT copied: it costs more than the whole scan, and SCAN-04 sends every flag through a real verification workflow anyway — a stronger check than a second LLM opinion.

**Escalation:** `confidence < params["scan"]["escalate_conf_floor"]` (proposal 0.4) or contradictory flags (e.g. `iv_spike` + `offering_signal` + price up) → ONE re-run on Sonnet; still ambiguous → flag ships with both readings in `unknowns` (intra-week §3.4's escalate-don't-guess rule).

### 1.3 Reuse-vs-new verdict against `desk/diligence.py`

Follow the **mirror-not-import** precedent diligence.py documents about itself vs `analysts.py` (`run_dimension` hard-refs `DILIGENCE_PROMPTS`, so a sibling carries its own prompts):

| Piece | Verdict |
|---|---|
| `runtime.run_structured` | **REUSE** — the one LLM seam; `model` is already a parameter (pass `"haiku"`) |
| `tools.build_quant_server` + diligence `ALLOWED_TOOLS` | **REUSE** — identical quant/KB MCP surface |
| `kb.analog_query` / `kb.query_playbooks` | **REUSE** — via the existing MCP tools; no new KB surface |
| `contracts.KeyFinding` | **REUSE** — inside `OpportunityFlag` |
| `evidence.resolve` / `tool_ref_for` | **REUSE** — structural cite-or-drop |
| `diligence.options_liquid` / `zero_liquidity` | **REUSE (import)** — pure functions, the liquidity card fields |
| `quant/weekly.classify_drop` / `thesis_scan` / `_turnover_flag` logic | **REUSE (consume outputs)** — §3.3 |
| `store.bars_asof` | **REUSE** — all price/vol/volume fields, point-in-time |
| 8-dim `gather_dimensions` fan-out | **DO NOT COPY** — one consolidated pass per flagged name (SCAN-03) |
| `synthesize_verdict` / `MONEY_TOUCHING` | **DO NOT COPY** — no go/no-go; the deterministic decision here is `material_deltas()` (who wakes Stage 2), same "LLM cannot touch the trigger" architecture |
| `enforce_dossier` opus semantic stage | **DO NOT COPY** — structural-only + downstream verification (above) |
| Card builder, delta layer, scan prompt, `ScanInput`, `OpportunityFlag`, migration | **NEW** — the actual new surface, small (§5.1) |

---

## Section 2 — Refreshable week-over-week: the persisted company card (SCAN-02)

### 2.1 The design law: signal = TRANSITION of persisted state, not level, not re-derivation

WEEK-06's words: the weekly read is "a REFRESH of the SAME standing analysis... the signal is the CHANGE vs the standing baseline." Mechanically:

- A **card** is built for every name every week by pure deterministic code and persisted keyed `(ticker, week_end)` — write-once point-in-time rows, the `price_bar` pattern, so any week's scan replays byte-identically from the store.
- `delta(card[t-1], card[t])` is a pure function — no LLM, no network. The Stage-1 flag catalog (§1.1) IS this function's rule set.
- **Noise vs real change is decided structurally, not judgmentally:** a real change is a band/sign/set transition from an un-latched state; noise is oscillation inside a band, a re-touch of a latched flag, or a delta below the hysteresis re-arm line. The LLM never sees un-flagged names, so it cannot be the source of week-over-week inconsistency.

### 2.2 Card schema (the fields behind §1.1's flags, each with its feed)

All fields deterministic; `card_version` string inside the JSON pins schema evolution.

| Group | Fields | Feed (all in-stack) |
|---|---|---|
| catalyst | `days_to_catalyst`, `next_catalyst {type, date, id}`, `catalysts_4w`, `competitor_next_7d`, tracked NCT `{status, primaryCompletionDate}` snapshots | catalyst table, CT.gov v2, competitor map |
| options | `iv30`, `term_spread`, `straddle_move_pct`, `options_liquid`, `underlying_price` | CBOE JSON (1 GET/name/wk) |
| positioning | `short_interest`, `days_to_cover`, `si_settlement_date` | FINRA Query API |
| price/vol | `ret_1w`, `ret_4w`, `px_vs_ma4`, `px_vs_ma12`, `sigma5`, `sigma20`, `turnover_flag`, `vol_vs_median` | `bars_asof` |
| balance sheet | `cash_runway_months`, `runway_band`, `seen_accessions` (EDGAR form+accession set), `live_shelf` | FMP + EDGAR |
| quant row | the full `thesis_scan` row for this name (drop_class, trigger, p_shrunk, edge, eligible, veto_reasons) + its tool ref | `quant/weekly.py` (already runs) |
| latching | `fired: {flag_name: week_end}` | internal |

Why these are the right metrics (each sourced in §1.1's table): implied vol is the market's own forward-vol forecast and subsumes historical vol (📚 ESTABLISHED — Christensen & Prabhala, *JFE* 1998); catalyst proximity is the priced-event-jump premise (Dubinsky & Johannes 2006); short interest carries return/vol information (Dechow et al. 2001); abnormal volume flags information arrival (Beaver 1968); info-vs-noise move classification is the project's own verified Savor-2012 conditioning (Phase 6.5 design, measured on our 18-name/10-yr data); runway pressure predicts the post-pop offering ambush (intra-week §1.2.5).

### 2.3 Storage

New migration `006_company_card.sql`, the `005_price_bars.sql` shape:

```sql
CREATE TABLE company_card (
  id INTEGER PRIMARY KEY,
  ticker TEXT NOT NULL,
  week_end TEXT NOT NULL,        -- the ONE params["weekly"]["anchor"] date (measurement == execution)
  card TEXT NOT NULL,            -- JSON: §2.2 fields + latching state + card_version
  UNIQUE(ticker, week_end)
);
CREATE INDEX idx_company_card_ticker_week ON company_card(ticker, week_end);
```

One JSON column (ponytail: no per-metric columns until a query needs them — SQLite JSON1 can index later). Stage-2 outputs (`OpportunityFlag` / `no_opportunity` rows) and Stage-1 `no_material_change` rows persist alongside (a `scan_flag` table, §5.1) so the MD's log and the false-positive ledger are queryable. `bars_asof`'s `week_end <= as_of` guard pattern applies to card reads — a backtest of the scanner can never see a future card.

### 2.4 Honest cadence flags (real-change claims must respect feed cadence)

- **Short interest:** bi-monthly settlement + ~9 business-day publication lag (FINRA, verified) — an SI "delta" is between settlement dates, not weeks; `si_settlement_date` rides the card so Stage 2 and the MD see staleness. F6 fires at most ~2×/month per name by construction.
- **Runway:** quarterly statements — F8 fires ~4×/yr per name.
- **CBOE quotes:** 15-min delayed, weekly snapshot — fine for a weekly scanner; the intra-week monitor owns real-time.
- **CT.gov:** date edits happen continuously; only window-crossing edits fire (F2).

---

## Section 3 — Light / not token-heavy (SCAN-03)

### 3.1 Deterministic-first, LLM-by-exception

The architecture already guarantees the cost profile: Stage 1 is plain Python over ~20 GETs + the existing SQLite store — **$0 LLM**. The only LLM spend is Stage-2 wakes, bounded by the flag catalog's latching + corroboration + the `max_stage2_wakes` cap. Most weeks most names are a `no_material_change` row. This is precisely intra-week §1.0's monitor-by-exception structure ("real desks put the expensive resource behind exception gates and leave the always-on layer to dumb, fast systems" — 📚 ESTABLISHED, Grinold & Kahn attribution there), applied at weekly cadence.

### 3.2 Cost estimate (pricing per intra-week §4.2: Haiku 4.5 $1/MTok in, $5/MTok out; Sonnet $3/$15 — verified there via the claude-api skill)

Per Stage-2 wake: ScanInput (card pair + tripped flags, ~1.5K tok) + tool results threaded back (~1K) ≈ 2.5–3K in, ~500 out → **≈ $0.006/wake**. Sonnet escalation (~4K/700) ≈ $0.023.

| Weekly scenario | LLM calls | Cost |
|---|---|---|
| Quiet week (0–2 wakes) | 0–2 Haiku | **$0.00–0.01** |
| Typical week (4 wakes + 1 escalation) | 4 Haiku + 1 Sonnet | **≈ $0.05** |
| Heavy week (cap: 8 wakes + 2 escalations) | 8 Haiku + 2 Sonnet | **≈ $0.10** |
| Pathological all-20-names (cap disabled) | 20 Haiku + 4 Sonnet | **≈ $0.21** |
| **Anti-pattern for contrast: naive 8-dim DD replica on all 20 names** | 160 dimension calls + 20 narrative + enforce passes | **≈ $2.5–4/week on Sonnet-class, ~50×**, plus ~500K tokens of context churn — this is what SCAN-03 forbids |

Even the pathological week costs less than one Sonnet DD dimension pass. Annualized typical: ~$2.6/yr. Cost is a non-issue *because* the LLM only runs on transitions — the same argument, same pricing, as intra-week §4.2.

### 3.3 Composition with `quant/weekly.py` (don't duplicate — it IS part of the delta layer)

- `thesis_scan` already produces a deterministic per-name row weekly inside `run_weekly`. The card **embeds** that row; F12/F13 flag on its transitions. The scanner never recomputes returns, base rates, drop classes, or turnover — `classify_drop`/`weekly_base_rate` remain the single source of those numbers (agents-never-do-arithmetic extends to modules: one computation site per number).
- Sequencing: `run_weekly` calls `thesis_scan` → the scanner builds cards from `bars_asof` + providers + that scan's rows → deltas → Stage-2 wakes → flags to MD. One shared `params["weekly"]["anchor"]` keeps card `week_end`, thesis rows, and price bars on the same date spine (the measurement==execution trap, closed the same way `desk/weekly.py` closes it).
- Catalyst precedence is inherited, not re-implemented: names whose thesis row says `thesis_type == "catalyst"` are already routed to Workflow-1 by `run_weekly`; the scanner still cards them (the card is universal) but a bare F1 fire on an already-routed name emits a log row, not an MD flag — no double-flagging one event.

---

## Section 4 — Routing: opportunity → MD → verification → portfolio → monitor (SCAN-04)

### 4.1 The flow

```
scanner OpportunityFlag ──▶ MD (Phase 6.7 reconcile, generalized per RECON-08:
                             the MD is the router for ALL flags, not just DD findings)
        MD decides: ACT ─▶ route to the verification the flag names (gap-not-answer):
          catalyst_call  → Workflow-1 run_desk debate: establishes DIRECTION + kill criteria
          measured_edge  → quant/weekly weekly_base_rate on the named cell; the FOUR-GATE
                           tradeability bar (edge≥min, n≥min, mean>cost, CI>0) is the verdict
          mini_backtest  → Phase-7 Layer-A harness on the specific trigger cell/setup
          diligence      → full DD pass (rare; when the flag is big enough to pre-vet)
        MD decides: LOG ─▶ stored, never forced (WEEK-06: "unactioned flags are logged, never forced")
                     │
        verification PASSES ─▶ the verified assumption enters run_weekly as a shortlisted
                               candidate (statistical → single-leg Candidate through
                               size_for_survival; directional catalyst → Workflow-1's normal
                               promote path) ─▶ built into the week's StrategyDossier
                     │
        position opens ─▶ intra-week monitor (Phase 8.5) watches it from the position card
```

### 4.2 Contract discipline

- **Gap-not-answer:** `thesis_to_verify` is a falsifiable hypothesis + `verification_needed` names the test — the flag never carries a conclusion the downstream workflow could lazily adopt. This is exactly RECON-08's `RetriggerFlag` discipline ("the fact + why-material, never the answer"), so the MD's generalized reconcile input accepts an `OpportunityFlag` with no new machinery beyond a union type.
- **Never trusted un-verified:** SCAN-04's hard rule. The scanner's confidence field ranks MD attention; it is not evidence. A flag that skips verification into the portfolio must be structurally impossible — enforced because `run_weekly`'s shortlist only admits catalyst names (Workflow-1 output) and four-gate-passing statistical rows (quant tools' output); there is no code path from `OpportunityFlag` to `Candidate` (test-pinned, §5.3).
- **Firewall preserved:** if the MD routes to `diligence`, DD still receives only `DiligenceInput{ticker, catalyst, pair}` — the flag routes *to* DD, its content does not leak *into* DD's sealed input (RECON-04 pattern).
- **Audit:** every flag (routed, logged, `no_opportunity`) persists with its tripped Stage-1 flags, so per-flag false-positive rates are measurable and thresholds retunable (§5.4).

---

## Section 5 — Scope + design recommendation + Validation Architecture

### 5.1 Build scope (new surface, deliberately small)

| Artifact | Contents | Est. size |
|---|---|---|
| `desk/company_scan.py` | `SCAN_PARAMS`-style `params["scan"]` group (thresholds §1.1, wake cap, escalate floor); `build_card(conn, ticker, week_end, raw)` — deterministic, `raw` = provider dict injected by caller exactly like `run_diligence`'s `market_data` (live fetchers are Phase-7 work; tests mock); `delta_card(prev, cur, params)` → tripped flags (pure); `SCAN_PROMPT` (adversarial once-over, §1.2's three questions + DD's HARD RULES block); `run_scan(conn, embed, week_end, raw_by_ticker)` orchestrator: cards → persist → deltas → wake Stage 2 per flagged name via `run_structured(..., model="haiku")` with `build_quant_server` → structural cite-or-drop → persist + route flags | ~300 lines |
| `contracts/__init__.py` additions | `ScanInput`, `OpportunityFlag` (both `extra="forbid"`; reuse `KeyFinding`) | ~40 lines |
| `migrations/006_company_card.sql` | `company_card` + `scan_flag` (`ticker, week_end, payload JSON, routed INTEGER`) tables | ~20 lines |
| MD hookup (Phase 6.7 repo work, not this module) | reconcile input union accepts `OpportunityFlag` (RECON-08 already specifies the generalization) | ~10 lines there |

Everything else is reuse per §1.3. No new KB surface, no new quant tools, no new LLM seam, no live fetchers in this phase.

### 5.2 Design decisions a PM must confirm (either/or, with recommendations)

1. **Stage-2 shape:** (a) one consolidated Haiku pass per flagged name (recommended — the checklist lives in one prompt; ~$0.006/name), or (b) a mini fan-out of 2–3 dimension agents per name (closer DD replica, ~3× cost, better isolation of citations). **Recommend (a); revisit only if Haiku citation quality on multi-flag names proves poor.**
2. **Wake cap:** `max_stage2_wakes` = 8/week with overflow batched into one review (recommended), or uncapped (max ~$0.21/week — cost is fine; the real risk is MD attention spam, not tokens). **Recommend capped for MD-attention reasons, not cost.**
3. **Threshold numbers:** every §1.1 proposal (5 vol pts, 20% SI, 2.0 σ-ratio, 3× volume, band edges) — accept research defaults for the paper month, then retune from the measured per-flag false-positive ledger. **Recommend defaults + mandatory post-paper-month retune.**
4. **Catalyst-precedence suppression (§3.3):** suppress bare F1 flags on names `run_weekly` already routed to Workflow-1 (recommended — no double-flagging), or let both fire (belt-and-braces, noisier MD queue).
5. **SI staleness policy:** accept bi-monthly+9bd-lag FINRA data with visible `si_settlement_date` (recommended; only free option), or buy a daily short-interest estimate feed (paid, e.g. S3/Ortex — **FUTURE**, UNVERIFIED pricing).
6. **Escalation floor:** Sonnet re-run below confidence 0.4 (proposal) — number is a PM knob.

### 5.3 Validation Architecture (per-requirement → named pytest, fully offline)

All tests offline: synthetic cards/bars inserted via the existing fixtures pattern, providers passed as `raw_by_ticker` dicts, `run_structured` monkeypatched (the seam exists for exactly this — every desk test already does it).

| Requirement | Test (in new `tests/test_company_scan.py`) | Proves |
|---|---|---|
| SCAN-01 structure | `test_scan_prompt_carries_hard_rules_and_three_questions` — prompt string contains the cite-or-drop HARD RULES + interest/explorable/build questions; `test_scan_input_firewall_forbids_desk_artifacts` — constructing `ScanInput` with a `verdict`/`thesis` field raises (extra="forbid") | Haiku DD-replica discipline + firewall |
| SCAN-01 output | `test_flag_vocabulary_fixed` — `opportunity_type`/`verification_needed` reject out-of-vocab values; `test_no_opportunity_is_valid_and_stored_not_routed` | direction-agnostic, adversarial-kill outcome first-class |
| SCAN-02 card | `test_card_written_once_per_ticker_week` (UNIQUE violated on rewrite); `test_card_point_in_time` — card built at week T reads only `bars_asof ≤ T`; `test_delta_pure_and_reproducible` — same two stored cards → identical tripped flags on repeat calls | persisted, reproducible refresh |
| SCAN-02 materiality | `test_band_transition_fires_level_does_not` — SI at 25% two weeks running fires once; `test_hysteresis_rearm_at_half_threshold`; `test_corroborator_never_wakes_alone` (F11 solo → no LLM call); `test_si_delta_only_on_new_settlement_date` | anti-whipsaw reuse, honest cadence |
| SCAN-03 light | `test_no_llm_when_no_material_delta` — monkeypatched `run_structured` raises if called; scan of 20 unchanged names completes; `test_wake_count_le_flagged_names` — N flagged → ≤ N (+escalations) `run_structured` calls; `test_wake_cap_batches_overflow` | deterministic-first, monitor-by-exception |
| SCAN-03 composition | `test_card_embeds_thesis_row_no_recompute` — `weekly_base_rate` monkeypatched-to-raise during card build; F12 fires purely off stored rows | no duplication of quant/weekly |
| Stage-2 KB access | `test_stage2_allowed_tools_include_analog_and_playbooks` — pins the ALLOWED_TOOLS reuse; `test_uncited_finding_dropped` — canned Haiku response with an unresolvable ref → finding stripped before routing; `test_analog_context_built_by_python_not_llm` — the analog_query context string is the deterministic serialization | KB-armed, cite-or-drop |
| SCAN-04 routing | `test_flag_carries_gap_not_answer` — `thesis_to_verify` + `verification_needed` present, no direction/size fields exist on the model; `test_no_code_path_flag_to_candidate` — grep-level/API-level: `OpportunityFlag` is not accepted by `run_portfolio`/`Candidate` constructors; `test_routed_flag_lands_in_md_queue` (against the Phase-6.7 reconcile input once it exists — xfail until then, per the ship-the-wiring-test-with-the-introducing-PR rule) | never trusted un-verified; MD is the router |

Run: `pytest tests/test_company_scan.py` — no network, no keys, deterministic.

### 5.4 Honest risks

- **False opportunities / MD spam** — the top risk. Mitigations are structural (latching, corroboration tiers, wake cap, adversarial no-opportunity outcome, verification gate) plus measurable: the `scan_flag` ledger gives per-flag false-positive rates for retuning. Residual: a paper-month with >50% `no_opportunity` outcomes on a given flag means its threshold is wrong — plan the retune, don't ship-and-forget.
- **Haiku quality on nuanced biotech.** Contained by design: Haiku never computes (tools do), never decides who gets scanned (Stage 1 does), never gets trusted (verification does), and escalates to Sonnet on low confidence. The residual exposure is a *missed* opportunity (Haiku talks itself out of a real one) — cheap to accept, since Stage-1 flags persist in the log and the MD can act on a raw flag regardless.
- **Cost if everything triggers** — bounded at ~$0.21/week uncapped (§3.2); genuinely a non-issue. The scarce resource is MD/LP attention, hence the wake cap.
- **Feed fragility/ToS:** CBOE JSON is YELLOW (undocumented-but-public; personal low-volume use posture per free-data-sources §1.1 — don't redistribute); FINRA/CT.gov/EDGAR are GREEN. A CBOE break disables F4/F5, not the scanner (cards record `options_liquid=false`-style degradation, the `options_context` graceful-degradation precedent).
- **Playbook vocabulary gap:** non-catalyst opportunity types have no learned playbooks yet — Stage 2 is honest about it via `unknowns`; scanner-specific playbooks accrete only after the Phase-10 LEARN loop records verified-flag outcomes. Until then the KB edge comes mostly from `analog_query`.
- **Stage-1 blind spot:** the scanner sees only what its feeds carry — no analyst-rating feed, no daily SI, no intraday tape (all marked FUTURE/not-this-module). A volatility source outside the card schema will not flag; F13 (`big_move_unexplained`) is the catch-all that at least fires *after* the first move.

*(End of research, 2026-08-15. Grounding reads and provenance per the method note; pricing per `intra-week-monitoring.md` §4.2; data-source verification per `free-data-sources.md`.)*
