# Universe Expansion (≥1 tradeable catalyst/week) + Catalyst-Outcome Playbook Dataset — Research

**Researched:** 2026-08-16
**Domain:** Biotech catalyst-density sizing · point-in-time no-look-ahead dataset design · KB/contract reuse
**Confidence:** Part A arithmetic MEDIUM (base rates derived from our own candidates doc + BIO LoA data, not a published catalyst-density stat — but *measurable* once the historical pass runs); Part A sourcing HIGH (all sources already built + live-verified); Part B/C HIGH (maps onto shipped KB/store/backtest contracts, signatures confirmed against source).

## Summary

The catalyst feed is effectively **vacuous today**: `catalyst.db` holds 19 catalysts, all `earnings`, all `unverified`, all inside a stale 2-week window (2026-07-29 → 08-12). Zero PDUFA/trial catalysts are in the store, zero universe cohorts exist, the KB is empty. So "≥1 tradeable catalyst/week" is not a tuning problem — it is a **sourcing-and-sizing** problem, and the machinery to solve it (CT.gov, EDGAR-8K PDUFA tracker, edgartools screen, price cascade, `universe.build.build_snapshot`) is already built and live-verified.

Working backward from the target, a universe of **~20 names cannot reliably yield ≥1 tradeable catalyst/week** — a name selected for catalyst density produces ~2 dateable binary catalysts/year, of which ~50-65% survive the tradeability/verify culls, and clustering (JPM/ASCO/ESMO/AHA/ASH readout seasons) bunches them. To clear ≥1/week with margin the universe must roughly **triple to N ≈ 70-90 names (central recommendation ~80)**. Critically, we do **not** have to guess this number: the honest design makes the universe-builder **measure realized catalyst density** from our own free feeds and expand the shortlist until trailing-12-month tradeable density clears the target. N is an *output*, not a hard-coded constant.

The playbook dataset is a point-in-time, no-look-ahead record per catalyst (pre-event setup → event → post-event outcome → structured rationale) that maps **entirely onto shipped KB contracts** — `catalyst`/`prediction`/`outcome`/`playbook`/`evidence_source` nodes, `RESULTED_IN`/`CITES` edges, `insert_claim`'s cite-or-drop invariant, and the `load_params`→`fitted_params:<type>` seam. The no-look-ahead guarantee is the same `week_end <= as_of` guard already money-critical in `bars_asof`/`card_asof`/`build_event_set`. New surface is **one helper module + two scripts**; no new dependency, no schema migration.

**Primary recommendation:** Expand the universe to ~80 names via a **data-driven builder** that sources candidates from CT.gov (Ph2/Ph3 near-term `primaryCompletionDate` → sponsor → ticker) + an **unfiltered** EDGAR-8K PDUFA efts pass + edgartools/price/CBOE tradeability screen, feeding `build_snapshot` (survivorship-free, append-only `universe_as_of`). Then build the catalyst-outcome record as a `catalyst→prediction(setup)→outcome` KB graph written in two separate point-in-time passes (historical backfill + the forward WEEK-05 seam), and refit `fitted_params:<type>` from the cohort-grouped records.

---

## Project Constraints (from CLAUDE.md + PROJECT.md)

- **FREE data only.** No paid tracker (operator explicitly rejected BPIQ). Every source below is $0/keyless or free-keyed.
- **no-LLM-dates + no-LLM-arithmetic on money numbers.** Deterministic Python computes moves/features/density; agents only interpret and write rationale with citations. Enforced structurally at the pydantic boundary (`Catalyst.sources` non-empty) and in `insert_claim`/`insert_catalyst` (cite-or-drop, reject-before-write).
- **Point-in-time / no-look-ahead is money-critical.** Pre-event features must never peek at the outcome. Use only the shipped `<= as_of` guards.
- **Survivorship-free.** Include delisted names (`delisted=1` retained; `universe_as_of` append-only per cohort). Note the **RNA ticker-recycling trap** (universe-candidates §2.12): key names by CIK/legal entity, not ticker alone, or history silently splices Avidity into Atrium.
- **Reuse the KB/store/contracts/backtest — minimal new surface.** `.venv/bin/python`; Graphify graph-first (signatures here confirmed against source).
- **Human gate inviolable.** Auto-verification makes a catalyst *tradeable-eligible*; the trade still requires explicit LP approval.

---

# PART A — Universe expansion sized to catalyst density

## A.1 The arithmetic (work backward from ≥1 tradeable catalyst/week)

### Per-name catalyst base rate

A name admitted to this universe is admitted *because* it has catalyst density (universe-criteria Screen A criterion 1 = "≥2 dateable binaries/yr"). Grounding that against reality — the candidates doc's own "next ~90 days" calendar listed **~10 tradeable events across ~20 names in one quarter** (RARE Aug 23, IONS ESC, PHVS Q3, AMLX Q3, ACAD Sep-Oct, SMMT Nov 14, SVRA ~Nov 22, CLDX Q4, PCVX Q4, IVA H2). That is ~40 gross dateable events/year / 20 names ≈ **2.0 binary catalysts/name/year** (MEDIUM confidence — observed from our own doc, not a published stat).

Catalyst mix per active clinical-stage name/year (MEDIUM, derived):

| Catalyst type | ~per name/yr | Tradeable? |
|---|---|---|
| PDUFA / BLA decision | 0.3–0.5 | Yes (firm date, high edge) |
| Ph2/Ph3 pivotal topline readout | 1.0–1.5 | Yes (window; firms 48h out) |
| AdCom | ~0.1 | Yes |
| Earnings | 4 | **Excluded** as a *binary* catalyst — this fund trades ±30-70% clinical/regulatory events; earnings are a confound (universe-candidates treats them as noise). Earnings feed the weekly mean-reversion/continuation sleeve, not the ≥1/week binary target. |

→ **~2.0 binary (PDUFA+readout+AdCom) catalysts/name/year.**

### Tradeability cull (not every catalyst is tradeable)

The desk's verify + liquidity + precision gates cull gross catalysts to tradeable ones:

| Gate | Survival | Rationale |
|---|---|---|
| Date-firmness / verify (`status='verified'`, 48h re-verify) | ~0.85 | Some windows never firm to a tradeable date |
| Liquidity / optionability | ~0.95 | Names pre-screened; a few drop below ADV floor by event time |
| Precision / attribution (illiquid options, muddled name, low expected move — e.g. SRPT) | ~0.80 | Culls the un-tradeable-in-practice |

Net tradeable fraction ≈ 0.85 × 0.95 × 0.80 ≈ **0.65** (optimistic). A **conservative** read (many "H2 2026" windows never firm; more attribution muddle) is ≈ **0.50**.

→ Tradeable catalysts/year ≈ **(1.0 to 1.3) × N**.

### From annual count to "reliably ≥1 per week"

≥1/week = 52/yr *if perfectly uniform*. Catalysts are not uniform — they **cluster** in readout seasons, so lean weeks are worse than Poisson. Model weekly arrivals as Poisson with mean λ = tradeable_per_year / 52; P(a week has zero) = e^(−λ):

| Weekly mean λ | Tradeable/yr | P(zero week), Poisson | Real (clustered) empty-week rate |
|---|---:|---:|---:|
| 1.0 | 52 | 37% | ~45% |
| 1.5 | 78 | 22% | ~30% |
| 2.0 | 104 | 13.5% | ~20% |
| 3.0 | 156 | 5% | ~10% |

The operator's **no-zero-trade defensive path already exists** (Phase 6.5 `build_defensive_book` + the statistical sleeve), so genuinely empty catalyst-weeks are backstopped — we do not need λ=3. The honest target is a weekly mean that puts a catalyst on the desk in the large majority of weeks, with the defensive/statistical sleeve covering the lean tail.

**Target: λ ≈ 1.5–2.0 → 78–104 tradeable binary catalysts/year.**

### Solving for N

| Net rate | λ=1.5 (78/yr) | λ=2.0 (104/yr) |
|---|---:|---:|
| Optimistic (1.3·N) | N ≈ 60 | N ≈ 80 |
| Conservative (1.0·N) | N ≈ 78 | N ≈ 104 |

**Recommended N ≈ 80** (band 70–90), up from ~20. This targets ~90–100 gross tradeable binaries/year (λ≈1.75), covering the large majority of weeks; the defensive/statistical sleeve covers the ~15-20% lean weeks. Cap near ~80 for the diligence-load reason in A.4.

> **The ponytail-correct refinement:** don't hard-code N. Once the historical EDGAR-8K + CT.gov pass runs (road-to-backtest Stage 1), we can **measure** realized tradeable catalyst density directly from our own store. Make the builder grow the shortlist until trailing-12-month tradeable density ≥ target λ, and re-measure each rebuild. N becomes an output. The estimate above is only the starting shortlist size. Mark the per-name rate for **recalibration from measured data** — this is a money-critical assumption exactly like the road-to-backtest calibration warning.

## A.2 Selection screen (tradeability + fit-ability)

Concrete thresholds, consolidating universe-criteria.html Screen A, the candidates doc, and free-data-sources §1.9. Current `universe/build.py` defaults are too loose ($1M ADV) — tighten:

| Criterion | Threshold | Source / rationale |
|---|---|---|
| **Dollar-ADV floor** | ≥ **$5M/day** standard; **$2–5M = "size-tiny" tier** (position capped, or exit-before-event) | Candidates doc flagged <$5M (IVA $3.8M, SION $3.1M) as un-buildable at size. Raise `DEFAULT_MIN_ADV_USD` 1M→5M; add a tier flag rather than hard-drop (IVA has the biggest binary in MASH). |
| **Market-cap floor** | ≥ **$200M** | Current default. Excludes micro-caps / post-blowup shells (SION at $292M ≈ cash). |
| **Market-cap ceiling** | ≤ **$10B** for core; band exceptions to ~$16B only as designated hedge-peers | Above ~$10B a single readout no longer moves ±30-70% (INSM $26.8B, RVMD $43B excluded; BBIO $15.6B kept only as ATTR hedge-peer). |
| **Optionability** | listed options with an expiry **at/after the catalyst date**, ATM **OI ≥ ~100**, ATM **spread/mid < ~60%**, **bid>0 both legs** | free-data-sources §1.9 liquidity gate. Equities-only v1 uses options for the implied-move input + future hedge legs; a name with no usable chain loses its implied-move signal. |
| **Catalyst density** | ≥ **1 upcoming tradeable catalyst** in the density window (default 6mo); prefer ≥2 dateable binaries/yr | `build_snapshot` already counts this from the `catalyst` table. |
| **TA + catalyst-type diversity** | no therapeutic-area cluster **> ~4 names**; ≥ 6–8 TAs represented | So cohort-level fitting (catalyst_type × TA × drop_regime) has populated cells — this is a **dataset-quality** constraint, not just risk. |
| **Anti-correlation** | cap same-mechanism/same-indication clusters | The IONS/ALNY silencer read-through lesson (§3.1): same-class "peers" co-move, so an over-concentrated cluster is one bet, not N, and pollutes cohort independence. |

**Hard disqualifiers** (from candidates doc, verified live): acquired/delisted-by-M&A for the *live* set (KALV/CDTX/RNA/ETNB/AKRO — but **retain in history**, survivorship-free); attribution-muddled going-concern/safety-fallout names for *core* (SRPT); ticker-recycled entities keyed by CIK not ticker (RNA).

## A.3 Data-driven universe builder (→ `universe_as_of`, not a static list)

Reuse `universe.build.build_snapshot` unchanged (it is already criteria-driven, append-only, survivorship-free, and writes `universe_snapshot` with `included=0`+reason rather than silently dropping). The expansion replaces the **static seed CSV** with a **sourcing pipeline** that emits `seed_rows` dynamically. All sources are already built and live-verified:

**Stage 1 — candidate discovery (from our OWN free feeds):**
1. **CT.gov v2** (`providers/clinicaltrials.py`, live-verified): active **interventional Ph2/Ph3** studies with `primaryCompletionDate` in the next N months → `leadSponsor.name` → ticker via **reverse `ticker_sponsor_map.csv`** (extend the map — it currently has 19 rows; the recycling/subsidiary gotchas are already handled, e.g. BBIO→QED/Calcilytix). This is the trial-readout density driver.
2. **EDGAR-8K PDUFA tracker** (`providers/pdufa_edgar.py`, live-verified on IMNM/CAPR): today it filters efts hits to the *current* universe CIK set. **Un-filter the discovery** — run the "PDUFA target action date" efts phrase set across all biotech 8-K filers, then resolve ticker per hit (efts hit metadata carries `ciks` + `display_names` with ticker in parens). This is the regulatory-density driver *and* the candidate-discovery engine simultaneously.
3. **EDGAR 10-K/10-Q language** (`edgartools`): pending NDA/BLA mentions as a secondary discovery signal.

**Stage 2 — tradeability + fit screen (from our OWN free feeds):**
- `edgartools` (built): market cap, shares outstanding, float, cash-runway → cap band + runway-clears-catalyst.
- `providers/prices.py` cascade (built, N-source median): 30-day dollar-ADV → liquidity floor/tier.
- `providers/options_cboe.py` (built): ATM OI/spread/expiry → optionability gate.
- TA tag (from CT.gov condition / curated) → diversity + cohort-cell check.

**Stage 3 — size to density target:**
- For the screened shortlist, count trailing-12-month tradeable catalysts (from the store, after the historical pass). Grow the shortlist (admit the next-best names, widen thin TAs) until projected weekly density ≥ λ target. Emit the final `seed_rows`.

**Stage 4 — snapshot:**
- Feed `seed_rows` → `build_snapshot(conn, as_of_date, seed_rows, criteria={min_adv_usd: 5_000_000, ...})` → new append-only `universe_as_of` cohort. Delisted names retained. Re-run periodically; each run is a new cohort, never an overwrite (survivorship-free by construction — the shipped invariant).

**Output:** repeatable, provenance-tagged, survivorship-free `universe_as_of` cohorts — a living universe, not a hand-picked list. This *is* DATA-06, extended from the static CSV to a sourced pipeline.

## A.4 The honest breadth/depth tradeoff + money-safety

More names = more catalysts to choose from, but **more diligence load and less per-name operator familiarity**. Three honest points:

1. **≥1/week is about SELECTION, not throughput.** The weekly desk picks the best 1–3 candidates from the week's tradeable set; it does not trade all 80 names. A bigger universe raises the *floor* of choice quality, it does not raise position count. The per-catalyst diligence firewall (Phase 6) + verify gate + risk-of-ruin sizing still gate every trade individually.
2. **The operator can no longer eyeball every name** at N=80 the way they could at N=20. This is the real money-safety cost. The pipeline compensates: (a) **automated two-stage screening** (deterministic Stage-1 flaggers → Haiku Stage-2 once-over, Phase 6.8) surfaces only material names; (b) **provenance/cite-or-drop** on every datum makes each admission auditable; (c) the **human approval gate stays inviolable** on the handful that reach a trade. Breadth lives in *discovery*; the human gate stays narrow at *execution*.
3. **Depth is recovered at the cohort level, not per name.** 1yr × 80 names is still thin per name (the road-to-backtest warning), so per-stock fitting stays data-starved — fit at cohort level (catalyst_type × TA × drop_regime) and pull a **3–5yr survivorship-free window** for statistical power. A bigger universe *helps* here: it populates more cohort cells, which is why the TA/type-diversity screen (A.2) is a dataset-quality requirement.

---

# PART B — The catalyst-outcome playbook record (schema + no-look-ahead)

## B.1 The record as a KB graph (reuse, zero migration)

The record is a small graph over **existing** `kb_node` kinds (migration 003 enum: `company, drug, indication, trial, catalyst, outcome, trade, playbook, evidence_source, prediction, hedge_peer`). No new node kind, no schema change:

```
company ──HAS──▶ catalyst ──RESULTED_IN──▶ outcome
                    │                          ▲
                    └──PRECEDED_BY──▶ prediction (SETUP)
   every node ──CITES──▶ evidence_source
   playbook ──GENERALIZES──▶ outcome (via CITES to the outcomes it summarizes)
```

| Record part | KB node | ref_id / key attrs | as-of |
|---|---|---|---|
| **The event** | `catalyst` (ref_id → Phase-1 `catalyst.id`) | type, ticker, event_date, verified status, authoritative `source_name` | event_date |
| **Pre-event SETUP** | `prediction` *(reuse this enum kind — it already means "the as-of-before view")* | the pre-event feature vector (below), each stamped `as_of = pre_event_asof` | **pre_event_asof (T-2 / last bar strictly before event)** |
| **Post-event OUTCOME** | `outcome` (RESULTED_IN edge) | realized move, IV crush, hedge-leg behavior, surprise | post-event bars |
| **RATIONALE** | structured attrs on `outcome` (+ carried into `playbook`) | mechanism, surprise_vs_expected, predictive_signals | derived |
| **Provenance** | `evidence_source` via CITES | url, retrieved_at, snippet_hash, quote | — |

### Pre-event SETUP features (the no-look-ahead crux)

Every feature read **strictly through the shipped `<= pre_event_asof` guards** and stamped as-of that date:

| Feature | Source (all built) | Deterministic? |
|---|---|---|
| drop-regime / drop-class | `quant/weekly.classify_drop` over `store.bars_asof(pre_event_asof)` | yes |
| base rates: LoA by phase/indication, prior-CRL penalty, AdCom follow-through | `quant.base_rate` (base_rates.csv) | yes |
| positioning: short interest | `providers/finra.py`, via `card_asof` | yes |
| options-implied move + IV | `providers/options_cboe.py` (straddle/spot; `iv30`) | yes |
| fundamentals: runway, float, shares | `edgartools` | yes |
| prior analogs | `kb.analog_query(embed, context, filters, k)` | yes (retrieval) |
| analyst signals (optional) | AnalystSignal (if a desk run exists for that week) | — |

### Post-event OUTCOME (deterministic — no LLM arithmetic)

Computed in Python from price bars only, using the pessimistic fill model already built (`backtest/fill.py`):
- **realized move** magnitude + direction, at **1-day and 1-week** windows (from `bars_asof` post-event minus the pre-event close).
- **vs expected move** — realized vs the pre-event straddle-implied expected move → `surprise = realized − expected` (sign + magnitude). Answers "was it a surprise?"
- **IV crush** — front-expiry ATM IV pre vs post (CBOE `iv30` delta).
- **hedge-leg behavior** — the peer's realized move over the same window (validates/refutes the inverse-payoff claim, e.g. BBIO +15.1% on the IONS failure vs ALNY −3.3% co-move).

### The RATIONALE (structured, cite-or-drop, inferred-vs-sourced)

The operator's explicit ask — "why and what before pointed to this" — as structured attrs, **not free-text LLM speculation**:

```json
"rationale": {
  "mechanism": "CRL | approval | hit_primary | missed_primary | mixed",   // sourced from the outcome filing (CITES the 8-K/PR)
  "mechanism_grounding": "sourced",                                        // sourced | inferred (labeled)
  "surprise_vs_expected": {"expected": 0.42, "realized": -0.24, "surprise": -0.66, "sign_flip": true},  // deterministic
  "predictive_signals": [                                                  // computed: which pre-features pointed the right way
    {"feature": "drop_class", "pre_value": "busted_-15", "implied_dir": "down", "matched_realized": true, "grounding": "sourced"},
    {"feature": "implied_move", "pre_value": 0.42, "implied_dir": "high_vol", "matched_realized": true, "grounding": "sourced"}
  ]
}
```
- **mechanism** cites the resolving filing/PR (cite-or-drop; the same authoritative sources — SEC EDGAR / CT.gov / Federal Register — used for dates).
- **surprise_vs_expected** and **predictive_signals.matched_realized** are **deterministic** (sign comparison), never LLM-judged. `predictive_signals` is exactly what the Stage-3 fit needs to learn *which pre-signals matter* per cohort.
- An agent may only *interpret/narrate* (labeled `grounding:"inferred"`); every money-touching value is Python-computed and every mechanism claim is source-grounded.

## B.2 The no-look-ahead guarantee

Structural, mirroring `build_event_set` (Phase 7) exactly:

1. **Two separate passes, two disjoint as-ofs.** The `prediction` (setup) node is written in a pass keyed to `pre_event_asof`; the `outcome` node in a later pass keyed to post-event bars. They never share an as-of and the setup pass has no access to the outcome pass's data.
2. **Every setup read goes through a `<= pre_event_asof` guard**: `bars_asof`, `card_asof`, `scan_flags_asof`, and the mandatory `last_verified_at <= effective_asof` catalyst post-filter (the verification look-ahead the status-only store does not guard — `build_event_set` L81-86). `analog_query` filters must exclude the event's own outcome node.
3. **A setup feature that cannot be read at `pre_event_asof` is dropped, never imputed** (cite-or-drop). This is the same discipline as the daemon's degrade-to-None.
4. **Test-enforced** (Wave 0): a regression test that assembling a setup with a poisoned future bar in the store still returns only `<= as_of` bars (the `bars_asof` invariant is already tested; extend it to the record builder).

## B.3 Mapping to what exists (fitted_params + analog_query + Phase-7 event set)

- **analog_query** (KB-03, shipped): live desk retrieves "similar past scenarios with outcomes" the moment records exist — no code change, `analog_query` already traverses `RESULTED_IN` to attach the realized outcome. Today it returns nothing (KB empty); after the historical pass it returns real analogs.
- **fitted_params seam** (`kb.load_params` → top-confidence `fitted_params:<type>` playbook, else `BOOTSTRAP_DEFAULT`, shipped + frozen signature): Stage-3 groups records by cohort, computes the move distribution / base rates / SL-TP / IV-crush / hedge payoff per cohort, and writes them as **versioned, confidence-scored `fitted_params:<type>` playbooks** via the existing `seed_fitted_params` / `insert_playbook` path at confidence > the 0.3 bootstrap, so `load_params` shadows the bootstrap automatically. The tools stay pure (they take the dict in). **This is the moat** — the tools are commodities, the calibrated cohort assumptions are the edge.
- **Phase-7 event set** (`build_event_set`, shipped): the historical record-builder walks exactly the event set `build_event_set` produces — same point-in-time, survivorship-free records — so the dataset and the backtest read identical ground truth.

## B.4 New surface (minimal — ponytail)

- **ONE helper**, `kb.insert_catalyst_record(conn, catalyst, setup_attrs, outcome_attrs, rationale, evidence, *, embed=None)` (~40 lines) that writes the `catalyst → prediction(setup) → outcome` graph + `RESULTED_IN`/`PRECEDED_BY` edges + rationale atomically, routing every node through `insert_claim` so cite-or-drop holds by construction (exactly like `insert_hedge_peer` composes `insert_claim` + `add_edge`). **No new node kind, no migration.**
- Everything else is reuse. `record_weekly_outcome` (WEEK-05) is the forward-path caller; a backfill script is the historical caller (Part C).

---

# PART C — The collection pipeline (historical + forward)

Two population paths, both reusing shipped machinery; point-in-time + cite-or-drop throughout.

## C.1 Historical backfill (backtest events → records) — road-to-backtest Stages 1/3/4

**Prerequisite (Stage 1):** one historical ingestion pass populates the store over a **3–5yr survivorship-free window** (not 1yr — the depth warning): prices via the built N-source cascade; trial readouts via CT.gov; earnings via Nasdaq; **PDUFA/AdCom via a historical (past-dated) EDGAR-8K efts pass** — `pdufa_edgar` already found *forward* events; run the same phrase set over the past year(s). `ingest_history` already stamps `last_verified_at` point-in-time from the source's `published_date` (BACK-01).

**The build (Stage 3/4):** `scripts/build_playbooks.py` (new, thin) walks `build_event_set(conn, start, end)`; for each catalyst event:
1. assemble the pre-event SETUP from the point-in-time stores at `pre_event_asof` (B.1);
2. compute the OUTCOME deterministically from post-event bars via `fill.py` (B.1);
3. derive the RATIONALE (deterministic surprise + predictive-signal match; agent narrates the mechanism *with* the resolving-filing citation);
4. `kb.insert_catalyst_record(...)`.
Then group records by cohort and write `fitted_params:<type>` playbooks (B.3).

**Result:** `analog_query` returns real analogs to every analyst on every live catalyst; `load_params` returns calibrated cohort params.

## C.2 Forward (each resolved weekly trade → a record) — the WEEK-05 seam

`desk/weekly.record_weekly_outcome` already writes a per-leg `outcome` claim (thesis_type, trigger, p_quoted, size, realized_ret, win) cited by a resolved-by-construction `tool:weekly_base_rate#<hash>` ref. **Extend it** (not replace) so that when a *catalyst* leg resolves, it also writes the full `catalyst → prediction(setup) → outcome + rationale` record via `insert_catalyst_record`, capturing the pre-event setup that was live at build time. Same `insert_claim` cite-or-drop path; nothing downstream changes. Each resolved weekly trade thus grows the training set — the loop the road-to-backtest Stage 5 / Phase 10 closes.

## C.3 Point-in-time discipline (throughout)

- Setup features: `<= pre_event_asof` guards only.
- Outcome: post-event bars, separate pass.
- Provenance: every node via `insert_claim`; the daemon's raw-snapshot lake (`data/raw`) preserves the exact fetched bytes for re-parse/audit.
- Plugs in cleanly: Stage 1 = event set (`build_event_set`), Stage 3 = `fitted_params` refit, Stage 4 = playbook population.

---

# Proposed ROADMAP phase(s)

The universe expansion **precedes** the historical ingestion pass (it defines *what* to ingest), and the playbook dataset **is** road-to-backtest Stages 3/4 (post-backtest calibration). These are cleanly two phases; recommend the split.

## Phase 6.12 — Data-Driven Universe Expansion (→ ≥1 tradeable catalyst/week)

**Goal:** Grow the universe from ~20 to a **density-sized** ~80 names via a repeatable, survivorship-free, provenance-tagged builder that sources candidates from our own free feeds and sizes N to a measured tradeable-catalyst-per-week target — so the catalyst feed reliably offers ≥1 tradeable catalyst to *choose from* most weeks, with the defensive sleeve backstopping the lean tail.

**Depends on:** Phase 1 (universe builder + catalyst pipeline), Phase 6.9/6.10 (price cascade + edgartools screen + daemon), Phase 6.11 (`pdufa_edgar`).

**Requirements:**
- **UNIV-01** — Candidate discovery from CT.gov (near-term Ph2/Ph3 `primaryCompletionDate` → sponsor → ticker via reverse `ticker_sponsor_map`) + **un-filtered** EDGAR-8K PDUFA efts pass (resolve ticker per hit, exact CIK, no fuzzy title).
- **UNIV-02** — Tradeability + fit screen: ADV ≥ $5M (size-tiny tier $2–5M), cap $200M–$10B (hedge-peer band exception), optionability gate (OI/spread/expiry), TA + catalyst-type diversity caps (no cluster > ~4), CIK-keyed (RNA-recycling-safe).
- **UNIV-03** — Density-sizing loop: measure trailing-12-month tradeable-catalyst count; grow the shortlist until projected weekly density ≥ target λ (default ~1.75); N is an output, not a constant.
- **UNIV-04** — Emit dynamic `seed_rows` → `build_snapshot` → append-only survivorship-free `universe_as_of` cohort (delisted retained; `included=0`+reason, never silent-drop).
- **UNIV-05** — Provenance on every admission (source_url + fetch_ts + grade); the operator can audit why any name is in the cohort.

**Success criteria:**
1. A single builder run produces a survivorship-free `universe_as_of` cohort of ~70–90 names sourced (not hand-picked) from CT.gov + EDGAR, each with an auditable admission reason.
2. Over the ingested window, the cohort's trailing-12-month tradeable-catalyst density clears the λ target (measured, not asserted); lean-week rate documented.
3. No name is admitted without passing the ADV/cap/optionability/density thresholds; delisted + ticker-recycled names are handled by CIK.
4. Re-running the builder writes a NEW cohort, never overwrites (survivorship-free regression-tested).

**Reuse vs build:** REUSE `build_snapshot`/`universe_as_of`, `clinicaltrials.py`, `pdufa_edgar.py` (un-filter discovery), `edgartools`/`prices`/`options_cboe`, `ticker_sponsor_map`. BUILD one `universe/discover.py` (sourcing + screen + density loop) + extend `ticker_sponsor_map`. No new dependency, no migration.

## Phase 7.5 — Catalyst-Outcome Playbook Dataset & Per-Cohort Calibration (road-to-backtest Stages 3/4)

**Goal:** Turn the historical event set + realized outcomes into a point-in-time, no-look-ahead catalyst-outcome record per event (setup → event → outcome → rationale), populate the KB so `analog_query` returns real analogs, and refit `fitted_params:<type>` per cohort — the moat.

**Depends on:** Phase 6.12 (expanded universe defines the ingest set), Phase 7 (`build_event_set` + backtest + fill model), Phase 2/5 (KB + `load_params` seam), Phase 6.5 (WEEK-05 seam).

**Requirements:**
- **PLAY-01** — `kb.insert_catalyst_record` writes the `catalyst→prediction(setup)→outcome` graph + rationale atomically, cite-or-drop by construction, zero migration (reuse existing node kinds).
- **PLAY-02** — Pre-event setup features assembled STRICTLY via `<= pre_event_asof` guards; a feature unreadable as-of is dropped, not imputed; test-enforced no-look-ahead.
- **PLAY-03** — Outcome (realized 1d/1wk move, surprise-vs-expected, IV crush, hedge-leg behavior) computed deterministically from bars + fill model; no LLM arithmetic.
- **PLAY-04** — Structured rationale (mechanism sourced-and-cited, surprise deterministic, predictive-signal match deterministic, inferred-vs-sourced labeled).
- **PLAY-05** — Historical backfill script walks `build_event_set` over a 3–5yr window → records; cohort-grouped refit writes versioned confidence-scored `fitted_params:<type>` playbooks that `load_params` shadows the bootstrap with.
- **PLAY-06** — Forward path: `record_weekly_outcome` extended to write the full catalyst record on a resolved catalyst leg (same cite-or-drop path).

**Success criteria:**
1. `analog_query` on a live catalyst returns real past analogs with their realized outcomes (not bootstrap stubs).
2. Every record's setup provably reads no post-event data (no-look-ahead test green); every money number is Python-computed; every rationale mechanism cites a resolving filing.
3. `load_params` returns calibrated cohort params (confidence > 0.3 bootstrap) for cohorts with sufficient n; data-starved cohorts fall back to bootstrap with the fallback labeled.
4. Each resolved forward weekly catalyst trade adds one record (loop seam live).

**Reuse vs build:** REUSE `insert_claim`/`add_edge`/`analog_query`/`load_params`/`seed_fitted_params`/`insert_playbook`, `build_event_set`, `fill.py`, `bars_asof`/`card_asof`, `record_weekly_outcome`, all built providers. BUILD one `kb.insert_catalyst_record` helper + `scripts/build_playbooks.py` + the cohort refit function. No new dependency, no migration.

---

## Environment Availability

| Dependency | Required by | Available | Notes |
|---|---|---|---|
| CT.gov v2 | UNIV-01 | ✓ live-verified | keyless |
| EDGAR efts + edgartools | UNIV-01/02, Stage 1 | ✓ live-verified (edgartools v5.49.0) | keyless, SEC UA required |
| price cascade / CBOE / FINRA | UNIV-02, setup features | ✓ built + live | free |
| KB (sqlite-vec) + `insert_claim`/`analog_query`/`load_params` | Part B/C | ✓ shipped | `fastembed` optional; hash embedder offline fallback |
| `build_event_set` / `fill.py` | C.1 | ✓ shipped | — |
| FMP float/short-interest premium endpoints | screen enrichment | ✗ (HTTP 402 free tier) | Fallback: edgartools shares-outstanding (exact) + yfinance float (estimate-grade, labeled) — no blocker |

**No blocking gaps.** Float stays estimate-grade everywhere free (labeled); everything else is built.

## Common Pitfalls

1. **Sizing N to 52/yr uniform.** Clustering makes lean weeks worse than the mean implies; size to λ≈1.75–2 (78–104/yr), not 52, and lean on the defensive sleeve for the tail.
2. **Counting earnings as tradeable binaries.** They are a ±5% confound, not the ±30-70% event this fund trades; exclude from the ≥1/week binary target (keep for the mean-reversion sleeve).
3. **Ticker-keyed history (RNA→Atrium splice).** Key by CIK/legal entity or the record dataset silently merges two companies.
4. **Look-ahead via `last_verified_at`.** `tradeable_catalysts` is status-only; the record builder MUST re-apply the `last_verified_at <= effective_asof` post-filter (the exact bug `build_event_set` fixes).
5. **LLM arithmetic sneaking into the outcome/surprise.** All money numbers Python-computed; the agent only narrates the mechanism *with a citation*. Enforced by `insert_claim` cite-or-drop.
6. **Per-name fitting on 1–3 events.** Fit at cohort level; pull 3–5yr; label data-starved cohorts as bootstrap-fallback.
7. **Hard-coding N.** Measure density from the store and grow the shortlist to target; re-measure each rebuild.

## Sources

**Primary (HIGH — codebase, signatures confirmed against source):**
- `src/catalyst_trader/kb.py` — `insert_claim`/`add_edge`/`analog_query`/`insert_playbook`/`seed_fitted_params`/`load_params`/`BOOTSTRAP_DEFAULT`, node-kind enum.
- `src/catalyst_trader/store.py` — `insert_catalyst`, `upsert_bars`/`bars_asof`, `write_card`/`card_asof`, `write_scan_flag`/`scan_flags_asof` (the `<= as_of` guards).
- `src/catalyst_trader/universe/build.py` — `build_snapshot`/`universe_as_of` (append-only, criteria-driven, survivorship-free).
- `src/catalyst_trader/backtest/events.py` — `build_event_set` (point-in-time + `last_verified_at <= effective_asof` post-filter).
- `src/catalyst_trader/desk/weekly.py` — `record_weekly_outcome` (WEEK-05 seam).
- `src/catalyst_trader/models.py` — `Catalyst`/`CatalystSource`/`CatalystType`.
- `catalyst.db` live query (2026-08-16): 19 unverified earnings-only catalysts, 0 universe cohorts, empty KB — the vacuous-feed grounding.

**Secondary (HIGH-MEDIUM — project research, live-verified):**
- `.planning/research/universe-candidates.md` — 33-name verification, event studies, hedgeability verdict, exclusions.
- `.planning/research/free-data-sources.md` — CT.gov/EDGAR/CBOE/FINRA/Nasdaq live tests + liquidity gate (§1.9).
- `.planning/research/own-pdufa-and-robinhood-data.md` — EDGAR-8K PDUFA extraction (live IMNM/CAPR).
- `docs/road-to-backtest.html` — the 5-stage plan (Stage 1 ingest, Stage 3 fit, Stage 4 playbooks) + the thin-data warning.
- `data/base_rates.csv` — BIO/Biomedtracker LoA, prior-CRL, AdCom follow-through.

**Tertiary (MEDIUM — derived, flagged for recalibration):**
- Per-name catalyst rate (~2 binaries/name/yr) and cull fractions — derived from the candidates doc's own event calendar, not a published stat. **Recalibrate from measured store density once the historical pass runs** (money-critical assumption).

## Metadata

- **Confidence:** universe sourcing HIGH (built + live-verified); sizing arithmetic MEDIUM (derived base rates, measurable later); record schema + no-look-ahead HIGH (maps onto shipped contracts); pitfalls HIGH.
- **Research date:** 2026-08-16 · **Valid until:** ~2026-09-15 (feeds stable; catalyst dates + density shift weekly — re-measure density from the store rather than trusting the estimate).
