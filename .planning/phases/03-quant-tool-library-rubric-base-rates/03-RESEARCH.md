# Phase 3: Quant Tool Library + Rubric & Base-Rates - Research

**Researched:** 2026-08-14
**Domain:** Deterministic financial/clinical math library (biotech-catalyst desk) + tunable rubric + cited base-rate table
**Confidence:** HIGH (formulas, edge cases, stack, existing-code patterns all verified; base-rate numbers HIGH from FEATURES.md sources)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
Discuss was skipped — no locked decisions beyond the hard constraints below. Everything else is Claude's discretion, bounded by ROADMAP success criteria, PROJECT.md, CLAUDE.md, FEATURES.md, and PITFALLS.md.

**Hard constraints (treat as locked):**
- **No LLM arithmetic on money-critical numbers** — these tools ARE the arithmetic layer; agents only supply parameters and interpret output.
- **Every tool output records the exact inputs used** (reproducible, auditable) — QUANT-03.
- **TDD with EXHAUSTIVE edge cases, tests before logic** (OPS-04) — money-critical: division-by-zero, negative inputs, empty/short series, NaN, extreme values, partial data.
- **Rubric weights are a tunable config** the learning loop (Phase 10) can adjust — do not hardcode.
- **Base rates are data** (a citable table), not magic numbers in code.
- **Simplicity + minimal deps:** prefer numpy/statsmodels/scipy already implied; cointegration via statsmodels (Engle-Granger/Johansen); Sharpe/returns via a lean calc or quantstats/empyrical (CLAUDE.md notes quantstats, avoid vectorbt's freq footgun).

### Claude's Discretion
- Module layout, exact function signatures, result-object shape, choice between CSV/JSON/TOML for the rubric config and base-rate table, whether base rates also seed the KB.
- Which tools take numpy vs. pure-python.
- Metric-library choice (hand-roll vs. quantstats vs. empyrical) — see the Standard Stack recommendation.

### Deferred Ideas (OUT OF SCOPE)
None — discuss phase skipped. (Downstream-phase concerns explicitly NOT in this phase: the agents that *call* these tools, the paper-ledger that *feeds* the metrics, the learning loop that *tunes* the rubric. This phase ships the callable library + config + table only.)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| QUANT-01 | Callable, unit-tested tool library — agents supply parameters, interpret output; no LLM arithmetic | Module layout + `ToolResult` pattern (§Architecture); every tool is a pure function returning a result object |
| QUANT-02 | Tools: rNPV/pipeline valuation, cash-runway, Kelly/risk-of-ruin, cointegration, correlation/β, conditional-payoff matrix, options-implied move, IV-crush, Sharpe/returns/attribution, SL/TP, portfolio concentration/exposure | Each tool's exact formula + library + numpy-vs-pure-python (§Tool Catalog) |
| QUANT-03 | Every tool output records the inputs used (reproducible, auditable) | `ToolResult` pydantic model carrying frozen `inputs` snapshot, mirroring `contracts/__init__.py` (§Reproducible Output Record) |
| FRAME-01 | Distill a concrete biotech scoring rubric (8 factors) | FEATURES.md A2 gives the 8 factors + weights verbatim (§Rubric) |
| FRAME-02 | Rubric weights are a tunable config the learning loop can adjust | JSON config file + validated loader + `score_rubric()` (§Rubric) |
| FRAME-03 | Clinical base-rate table (LoA by phase/indication, prior-CRL penalty, AdCom follow-through) available to agents as data | CSV/JSON data file with per-row citations + typed loader (§Base-Rate Table); numbers from FEATURES.md A3 |
| OPS-04 | Full TDD coverage; money-critical tools have exhaustive edge-case suites | Per-tool edge-case matrix (§Exhaustive Edge-Case TDD) — the biggest quality lever |
</phase_requirements>

## Summary

This phase builds `src/catalyst_trader/quant/` — a library of **pure, deterministic, reproducible functions** that do every money-critical calculation so the LLM agents never do arithmetic. Every function takes explicit parameters, validates them, and returns a pydantic `ToolResult` that carries a frozen snapshot of its inputs (QUANT-03) plus a `tool` name and `tool_version` string. This exactly mirrors the anti-hallucination discipline already established in `contracts/__init__.py` (`extra="forbid"`, bounded fields, reject-at-boundary) and the atomic-write discipline in `kb.py`/`store.py`.

**The dependency call is the most important decision here.** The environment is Python **3.14.6** with a deliberately minimal dep set (httpx, pydantic, pydantic-settings, sqlite-vec). Only **one** family of tools genuinely needs a heavy library: **cointegration** (Engle-Granger ADF + Johansen trace test with correct critical values) is a "don't hand-roll" — use `statsmodels`. Adding statsmodels pulls numpy+scipy+pandas+patsy (all have verified cp314 wheels). Once numpy is in the tree, correlation/β are numpy one-liners. **Everything else — rNPV, cash-runway, Kelly, risk-of-ruin, conditional-payoff matrix, implied-move, IV-crush, Sharpe/Sortino/returns/attribution, SL/TP, concentration/exposure — is pure-python arithmetic** (a few lines each) and MUST NOT pull a library. In particular, **do NOT add quantstats** (it drags in matplotlib + seaborn + yfinance + curl_cffi + lxml + pillow + protobuf — a plotting/data-download monster that violates minimal-deps for what is a 15-line Sharpe formula) and **do NOT add empyrical-reloaded** (leaner, but still adds pandas + scipy + peewee + Bottleneck for a handful of formulas numpy already covers). Hand-rolling Sharpe/Sortino is the *lazy-correct* call precisely because the "freq footgun" — the annualization factor — becomes an explicit, required, tested `periods_per_year` argument instead of a silent library default.

The **rubric** is the 8-factor weighting from FEATURES.md A2, stored as an editable JSON file + validated loader + a `score_rubric()` consumer (FRAME-01/02). The **base-rate table** (Phase-I LoA 7.9%, Ph2→3 28.9%, oncology 3.4%, prior-CRL −28%, AdCom ~90% follow-through) is stored as a CSV/JSON data file with a source column per row so it is citable (FRAME-03), matching the existing `data/*.csv` convention.

**Primary recommendation:** Create `src/catalyst_trader/quant/` with one pure function per tool, each returning a `ToolResult(extra="forbid")` that snapshots its inputs. Add **only `statsmodels`** to dependencies (for cointegration; numpy/scipy/pandas come with it). Hand-roll all metrics and valuation math in pure python/numpy. Write the exhaustive edge-case tests FIRST (RED), then the logic. Store the rubric as `data/rubric_weights.json` and base rates as `data/base_rates.csv`.

## Project Constraints (from CLAUDE.md)

- **Minimal dependencies, boring over clever, readable end-to-end.** Simplify the code, never the analysis. → drives the "hand-roll metrics, only add statsmodels" decision.
- **TDD, tests before logic, exhaustive edge cases on money-critical deterministic tools. No new code without tests.** → OPS-04 is a first-class constraint, not a nicety.
- **No LLM arithmetic on money-critical numbers.** → the entire reason this library exists.
- **Env-first secrets; never hardcode.** → n/a this phase (no secrets), but base rates/weights live in data files, not code.
- **quantstats noted as an option; avoid vectorbt's `freq` footgun.** → this research recommends hand-rolling over quantstats for minimal-deps reasons, and turns the freq footgun into an explicit required argument. Flagged as a deliberate divergence from the CLAUDE.md hint for the planner to ratify.
- **Graphify: query the graph, don't re-read src/.** → followed; navigated via `graphify explain`.
- **Phase-completion HTML report + TOKEN-NOTES update are MANDATORY at phase close** (CONVENTIONS). Planner must include both as end-of-phase tasks.

## Standard Stack

### Core (add exactly one dependency)
| Library | Version (verified cp314) | Purpose | Why Standard |
|---------|--------------------------|---------|--------------|
| **statsmodels** | 0.14.6 | Cointegration: `tsa.stattools.coint` (Engle-Granger two-step ADF) + `tsa.vector_ar.vecm.coint_johansen` (Johansen trace/eigen with critical values) | The ADF unit-root test and Johansen trace statistics with correct critical-value tables are genuinely hard to get right — this is the canonical, peer-used implementation. Hand-rolling it would be a money-critical bug farm. |
| numpy | 2.5.2 (pulled by statsmodels) | Vector math: correlation, β (OLS slope), Sharpe/Sortino array ops | Comes free with statsmodels; std for numeric arrays |
| scipy | 1.18.0 (pulled by statsmodels) | Available if a closed-form dist (e.g. `scipy.stats.norm` for an implied-move probability) is wanted | Transitive; use sparingly |
| pandas | 3.0.5 (pulled by statsmodels) | Transitive only | Do NOT build the API around pandas; keep tool signatures on plain lists/numpy arrays |

**Verified:** `pip install --dry-run statsmodels` on this venv resolves `statsmodels-0.14.6-cp314`, `numpy-2.5.2-cp314`, `scipy-1.18.0-cp314`, `pandas-3.0.5-cp314`, `patsy-1.0.2` — all wheels, no source build. ( Run 2026-08-14.)

### Everything else: pure python (stdlib `math`)
rNPV, cash-runway, Kelly, fractional-Kelly, risk-of-ruin, conditional-payoff matrix, options-implied move, IV-crush, SL/TP, portfolio concentration/exposure, returns, attribution — **no library**. Sharpe/Sortino use numpy (already present) or pure python.

### Alternatives Considered (and rejected)
| Instead of | Could Use | Verdict |
|------------|-----------|---------|
| Hand-rolled Sharpe/Sortino | **quantstats** | ❌ REJECT. Dry-run pulls matplotlib, seaborn, yfinance, curl_cffi, lxml, pillow, protobuf, peewee — a tearsheet/plotting/data-download stack. Massive minimal-deps violation for ~15 lines of math. Its value (HTML tearsheets, plots) is not needed by a tool library. |
| Hand-rolled Sharpe/Sortino | **empyrical-reloaded** | ❌ REJECT (for now). Leaner than quantstats but still adds pandas+scipy+peewee+Bottleneck. numpy (already in-tree via statsmodels) covers the formulas in a few lines each, and hand-rolling makes the annualization factor explicit + testable. Note for planner: if attribution grows complex, empyrical is the *escalation*, not quantstats. |
| statsmodels cointegration | hand-rolled ADF/Johansen | ❌ REJECT. Critical-value tables + regression are error-prone; this is the one "don't hand-roll." |
| numpy correlation/β | statsmodels OLS | ⚠️ Either works. `numpy.corrcoef` / `numpy.polyfit(x,y,1)[0]` for β are simpler; use them. statsmodels OLS only if you want the full regression summary (you don't). |
| JSON rubric config | TOML (`tomllib`, stdlib in 3.14) | Either fine. **Recommend JSON** — the learning loop (Phase 10) must *write* weights programmatically, and stdlib `tomllib` is read-only (no writer). `json.dump` round-trips. |
| CSV base-rate table | JSON / KB nodes | **Recommend CSV** to match existing `data/pdufa_curated.csv` convention (already has source columns). JSON is fine if the phase×indication nesting feels cleaner. Seeding into the KB is optional and deferable (see §Base-Rate Table). |

**Installation:**
```bash
# adds statsmodels + its numpy/scipy/pandas/patsy chain (all cp314 wheels)
pip install statsmodels==0.14.6
# then pin into pyproject.toml [project.dependencies]
```

## Architecture Patterns

### Recommended Module Structure
```
src/catalyst_trader/quant/
├── __init__.py        # re-export ToolResult + every tool (one import surface for agents)
├── result.py          # ToolResult base (pydantic, extra="forbid", carries inputs snapshot) — QUANT-03
├── valuation.py       # rnpv(), cash_runway()
├── sizing.py          # kelly(), fractional_kelly(), risk_of_ruin(), sl_tp_levels()
├── pairs.py           # cointegration() [statsmodels], correlation_beta(), conditional_payoff()
├── options.py         # implied_move(), iv_crush()
├── performance.py     # sharpe(), sortino(), cumulative_return(), attribution()
├── portfolio.py       # concentration(), exposure()
├── rubric.py          # load_weights(), score_rubric()          — FRAME-01/02
└── base_rates.py      # load_base_rates(), base_rate(phase, indication) — FRAME-03

data/
├── rubric_weights.json   # the 8-factor weights (editable; learning loop writes it)
└── base_rates.csv        # LoA/CRL/AdCom numbers + source columns

tests/
├── test_quant_result.py      # QUANT-03: inputs snapshot round-trips, immutable
├── test_valuation.py         # rNPV + runway edge cases
├── test_sizing.py            # Kelly/RoR/SL-TP edge cases (biggest money lever)
├── test_pairs.py             # cointegration/corr/β/conditional-payoff
├── test_options.py           # implied-move/IV-crush
├── test_performance.py       # Sharpe/Sortino/returns/attribution (freq footgun!)
├── test_portfolio.py         # concentration/exposure
├── test_rubric.py            # weights sum-to-1, tunability, scoring
└── test_base_rates.py        # loads, cites, queryable
```

### Pattern 1: Every tool is a pure function returning a `ToolResult`
**What:** No classes, no state, no I/O inside a tool. Input params → validate → compute → return `ToolResult` snapshotting the inputs. This is the QUANT-01 + QUANT-03 spine.
**When to use:** Every tool, no exceptions.
**Example (shape mirrors `contracts/__init__.py`):**
```python
# src/catalyst_trader/quant/result.py
from pydantic import BaseModel, ConfigDict

class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)  # frozen = auditable, immutable
    tool: str
    tool_version: str          # QUANT-01 "versioned"; bump when formula changes
    inputs: dict               # QUANT-03: exact params used, verbatim
    value: float | None = None # primary scalar (None when the tool returns a matrix/dict)
    detail: dict = {}          # tool-specific extras (e.g. conditional-payoff matrix, p-value)

# src/catalyst_trader/quant/valuation.py
import math
from .result import ToolResult

_VERSION = "1.0.0"

def cash_runway(cash_usd: float, monthly_burn_usd: float) -> ToolResult:
    """Months of cash at current burn. QUANT-02 cash-runway.
    Raises on burn<=0 (a company that isn't burning has infinite/undefined runway — the caller
    must decide, we refuse to emit a misleading number)."""
    if cash_usd < 0:
        raise ValueError("cash_usd cannot be negative")
    if monthly_burn_usd <= 0:
        raise ValueError("monthly_burn_usd must be > 0 (div-by-zero / undefined runway)")
    months = cash_usd / monthly_burn_usd
    return ToolResult(tool="cash_runway", tool_version=_VERSION,
                      inputs={"cash_usd": cash_usd, "monthly_burn_usd": monthly_burn_usd},
                      value=months)
```

### Pattern 2: Validate at the boundary, reject — never emit a misleading number
**What:** Money-critical tools raise `ValueError` on out-of-domain input rather than returning NaN/inf/0. Mirrors `store.insert_catalyst` rejecting a source-less catalyst and `contracts` rejecting an uncited finding.
**Why:** A silently-wrong money number is worse than a loud failure. An agent that gets a `ValueError` knows to fix its inputs; an agent that gets `inf` sizes a position on garbage.

### Pattern 3: Keep tool signatures on plain types
Take `list[float]` / numpy arrays / scalars — **not** pandas Series or DataFrames — so agents (and tests) call tools with plain JSON-able values. Convert to numpy internally where needed. Keeps the public surface readable and the reproducible `inputs` snapshot JSON-serializable.

### Anti-Patterns to Avoid
- **Returning a bare float.** Loses the inputs snapshot → violates QUANT-03. Always wrap in `ToolResult`.
- **Building the API around pandas.** pandas is a transitive dep, not a design choice; keep it out of signatures.
- **A single god-module `quant.py`.** Split by concern (valuation/sizing/pairs/…) — matches the existing `providers/`, `calendar/`, `universe/` package style.
- **Silent annualization defaults** in Sharpe/Sortino (the vectorbt/quantstats freq footgun). Make `periods_per_year` a **required** argument.

## Tool Catalog — exact formula + library + dependency

> `pp` = pure-python (stdlib `math` only). `np` = numpy (already in-tree via statsmodels). `sm` = statsmodels.

### 1. rNPV / pipeline valuation — `pp`
Risk-adjusted NPV: probability-weight each phase's projected cash flow by the **cumulative** PoS of reaching it, discount to present.
```
rNPV = Σ_t  CF_t · P_cumulative_success(t) / (1 + r)^t   −   Σ_t  Cost_t · P_reach(t) / (1 + r)^t
```
- PoS at each gate comes from the **base-rate table** (§FRAME-03) — the agent passes per-phase PoS or a phase/indication key the tool looks up.
- `r` = discount rate 15–40% (higher = earlier stage) — a required input, not hardcoded.
- Pure arithmetic over a list of `(year, cashflow, cumulative_pos)` tuples. **No library.**
- Pipeline valuation = Σ rNPV of each asset (concentration surfaced separately, see tool 12).
- Source: FEATURES.md A2 (rNPV is "the gold standard" for pre-revenue biotech).

### 2. Cash runway — `pp`
`runway_months = cash / monthly_burn`. Guard `burn <= 0`, `cash < 0`. (Code above.) Surface "funded past catalyst?" as a boolean when a `months_to_catalyst` arg is supplied. Source: FEATURES.md A2 factor 2.

### 3. Kelly + fractional-Kelly — `pp`
Two-outcome (asymmetric binary) Kelly. For a bet that wins `+W` (fraction of stake) with prob `p` and loses `−L` with prob `q=1−p`:
```
f* = p/L − q/W          # fraction of bankroll (general asymmetric form)
```
For the classic odds form with net odds `b = W/L`: `f* = (p·b − q) / b`. Clamp `f* < 0` → 0 (no edge = no bet). `fractional_kelly(f*, fraction=0.25)` returns `fraction · f*`. **Critical framing (PITFALLS #5):** Kelly on a −70% binary is *tiny*; the tool must return the small number honestly and the caller must never scale it up toward the 1%/week target. Pure arithmetic. Source: PITFALLS.md #5, standard Kelly theory.

### 4. Risk-of-ruin — `pp` (deterministic, no Monte Carlo)
The PITFALLS ask: "simulate strings of losses at the intended size." Do it **deterministically**, not with a seeded RNG:
- `prob_n_consecutive_losses(p_loss, n) = p_loss ** n` — exact.
- `max_survivable_consecutive_losses(size_pct, gap=0.70, ruin_drawdown=0.5)` — how many −70%-of-position hits at `size_pct` before cumulative drawdown ≥ `ruin_drawdown`. Closed-form/iterative arithmetic.
- `risk_of_ruin(p_loss, size_pct, gap, ruin_drawdown, n_trades)` — combine the two: P(a run long enough to ruin occurs within N trades). Prefer an exact recurrence / binomial enumeration over Monte Carlo so results are reproducible and testable (QUANT-03 + OPS-04).
- **This is the sizing that keeps you solvent — the −70%-gap downside, NOT the 1% target.** Source: PITFALLS.md #5, #2, #10.

### 5. Cointegration — `sm` (the one heavy tool)
```python
from statsmodels.tsa.stattools import coint                    # Engle-Granger 2-step
from statsmodels.tsa.vector_ar.vecm import coint_johansen      # Johansen
import numpy as np
# Engle-Granger: t_stat, p_value, crit = coint(price_a, price_b)
# Hedge ratio (β): OLS slope of a on b -> np.polyfit(price_b, price_a, 1)[0]
```
`cointegration(price_a, price_b, method="engle_granger")` → `ToolResult(value=p_value, detail={"t_stat":..., "crit_values":[...], "hedge_ratio":..., "cointegrated": p_value < 0.05})`. Johansen for the trace-statistic path. **Validation caveat (FEATURES.md A5, PITFALLS #1):** cointegration is *necessary but not sufficient* — the peer must also be catalyst-clean and the pair must be modeled conditional on the catalyst (tool 7). Requires ≥ ~30 aligned observations; guard short series. Source: FEATURES.md A5, statsmodels docs (API stable across 0.14.x — HIGH).

### 6. Correlation / β — `np`
`correlation = np.corrcoef(a, b)[0,1]`; `beta = np.polyfit(market_returns, asset_returns, 1)[0]` (or `cov(a,m)/var(m)`). Guard: equal-length, ≥2 points, non-zero variance (else corr/β undefined → raise). Source: standard.

### 7. Conditional-payoff matrix — `pp`
The honest replacement for "0.7 correlated = hedged" (PITFALLS #1). Given target and peer moves under each catalyst branch:
```
             peer ↑        peer ↓
target ↑   (+T↑, +P↑)   (+T↑, −P↓)
target ↓   (−T↓, +P↑)   (−T↓, −P↓)
```
`conditional_payoff(target_up, target_down, peer_up, peer_down, w_target, w_peer)` → 2×2 (or 4-cell) portfolio-return matrix in `detail`, plus `value = worst_cell` (the combined worst-case, un-netted). Feeds sizing. Inputs come from **historical analog gaps** (the agent supplies them; KB analogs from Phase 2). Pure arithmetic. Source: PITFALLS.md #1 ("model the pair's payoff conditional on the catalyst outcome... target −70% / peer +X%").

### 8. Options-implied move — `pp`
Straddle method (preferred, model-free): `implied_move_pct = (call_mid + put_mid) / underlying_price`. IV method: `implied_move_pct = iv · sqrt(days_to_event / 365)`. `implied_move(...)` supports both; return the % move as `value`. Use as a **magnitude prior for the downside gap in sizing**, never as a directional signal (PITFALLS #10). Pure arithmetic. Source: FEATURES.md A3, PITFALLS.md #10.

### 9. IV-crush estimate — `pp`
`crush = pre_event_iv − post_event_iv` (or `expected_post_iv ≈ baseline_iv`, so `crush ≈ pre_event_iv − baseline_iv`). You trade equities, so this is a **context/sizing input, not P&L** (PITFALLS #10) — the tool estimates the magnitude of the vol collapse to sanity-check the implied move. Pure arithmetic. Source: PITFALLS.md #10 (150–300% pre-event IV normal for biotech binaries).

### 10. Sharpe / Sortino / returns / attribution — `np` (HAND-ROLLED, freq explicit)
```python
def sharpe(returns, periods_per_year, risk_free=0.0):   # periods_per_year REQUIRED
    r = np.asarray(returns, float)
    excess = r - risk_free / periods_per_year
    sd = excess.std(ddof=1)
    if sd == 0: raise ValueError("zero volatility — Sharpe undefined")
    return float(excess.mean() / sd * np.sqrt(periods_per_year))
```
- **Sortino:** same but denominator = downside deviation (std of `min(r,0)` or below-MAR returns).
- **cumulative_return:** `np.prod(1 + r) - 1`.
- **attribution:** decompose realized P&L into catalyst-outcome / market-beta drift / hedge-leg / sizing contributions (FEATURES.md A1 "EOD P&L + attribution") — a weighted decomposition over supplied per-component returns; pure arithmetic.
- **The freq footgun is now a required argument** (`periods_per_year`) — the deliberate cure for vectorbt/quantstats silent-annualization corruption noted in CLAUDE.md. Weekly book → `periods_per_year=52`. Test both a weekly and daily case so the factor is exercised.
- Source: CLAUDE.md STACK (freq footgun), FEATURES.md A4/A1.

### 11. SL/TP levels — `pp`
`stop_loss = entry · (1 − sl_pct)`, `take_profit = entry · (1 + tp_pct)`, `reward_risk = tp_pct / sl_pct`. **Critical labeling (PITFALLS #2):** when the hold window contains a binary catalyst, the SL is **advisory only** — the gap jumps it. The tool must accept a `holds_through_catalyst: bool` and set `detail={"advisory": True, "reason": "gap jumps stop on binary event — size for -70%, not stop distance"}` so the dossier/dashboard never displays a fictitious bounded loss. Pure arithmetic. Source: PITFALLS.md #2.

### 12. Portfolio concentration / exposure — `pp`
`concentration` = Herfindahl `Σ wᵢ²` (or max single-name weight); `gross_exposure = Σ|wᵢ|`, `net_exposure = Σ wᵢ`. **Long/long framing (PITFALLS #1):** two longs = 2× gross long, NOT netted — expose gross explicitly so the PM/Risk agent sees real directional risk. Pure arithmetic. Source: FEATURES.md A1 (PM portfolio-fit), PITFALLS.md #1.

## Reproducible Output Record (QUANT-03)

`ToolResult` (shown in Pattern 1) is the reproducibility contract:
- `inputs: dict` — the **verbatim** parameters the tool was called with. Because signatures take plain types (Pattern 3), this is JSON-serializable and can be persisted to the KB or the dossier for audit.
- `tool` + `tool_version` — identify *which* formula produced the number; bump `tool_version` on any formula change so an old audited number is traceable to old logic.
- `frozen=True` + `extra="forbid"` — the result is immutable and cannot silently carry stray fields, exactly like the `contracts` models.
- **Test (QUANT-03):** `test_quant_result.py` asserts every tool populates `inputs` with the exact call args, that mutation raises, and that `ToolResult(...).model_dump()` round-trips through JSON. A parametrized test over *every* tool asserting `result.inputs` matches the call is the cheapest way to enforce this library-wide.

## Rubric as Tunable Config (FRAME-01 / FRAME-02)

The 8 factors + weights (verbatim from FEATURES.md A2 — these ARE the data):

| # | Factor | Weight |
|---|--------|--------|
| 1 | Probability of Success (PoS) at the catalyst gate | 0.20 |
| 2 | Cash runway | 0.15 |
| 3 | Trial design quality | 0.15 |
| 4 | Endpoint credibility | 0.12 |
| 5 | Regulatory precedent | 0.12 |
| 6 | Pipeline value / asset concentration | 0.10 |
| 7 | Management & sponsor track record | 0.08 |
| 8 | Competitive / commercial context | 0.08 |
(Σ = 1.00)

**Storage — `data/rubric_weights.json`:**
```json
{
  "version": 1,
  "weights": {
    "pos": 0.20, "cash_runway": 0.15, "trial_design": 0.15, "endpoint_credibility": 0.12,
    "regulatory_precedent": 0.12, "pipeline_concentration": 0.10, "management": 0.08, "commercial": 0.08
  }
}
```
**Loader + scorer — `quant/rubric.py`:**
- `load_weights(path=...) -> dict` — reads JSON, **validates Σweights ≈ 1.0** (raise otherwise) and that every factor key is present.
- `score_rubric(factor_scores: dict[str,float], weights: dict) -> ToolResult` — `factor_scores` each 0–10; `composite = Σ(scoreᵢ · weightᵢ) · 10` → 0–100. Surface the **PoS factor separately** in `detail` (FEATURES.md: it's the dominant driver of a binary). Reject unknown/missing factor keys and out-of-range scores (extra="forbid" discipline).
- **Tunability (FRAME-02):** weights are read from the file at call time, so the Phase-10 learning loop just rewrites the JSON (bumping `version`) — no code change. `json.dump` is why JSON beats stdlib-read-only `tomllib`.
- **Upgrade path (note for planner):** if the learning loop needs A/B/versioned weight sets (PITFALLS #13 warns against free-mutating configs), move to a `rubric_weights` DB table keyed by version. JSON file is the lazy-correct start; DB is the escalation.

## Base-Rate Table (FRAME-03)

The numbers (verbatim from FEATURES.md A3 — HIGH confidence, sourced):

| Metric | Value | Source |
|--------|-------|--------|
| Overall LoA from Phase I, all indications (2011–2020) | 7.9% | BIO/Biomedtracker |
| Phase II → Phase III advancement (biggest hurdle) | 28.9% | BIO 2011–2020 |
| Phase PoS rule-of-thumb | Ph1 ~10–15%, Ph2 ~25–35%, Ph3 ~50–65%, Filed ~85–90% | Healthcare IB guide |
| Oncology LoA from Phase I (lowest) | ~3.4% | Oxford Biostatistics |
| Large-pharma oncology transitions | Ph1→2 76.8%, Ph2→3 59.4%, Ph3→appr 57.1% | Oxford Biostatistics |
| Prior CRL on the asset | reduces approval prob ~28% (−0.28) | BiopharmaWatch |
| Positive AdCom vote | ~90% of AdCom-supported apps approved (FDA follow-through) | RTTNews |
| Biomarker-selected programs | higher LoA at every phase | BIO 2011–2020 |

**Storage — `data/base_rates.csv`** (matches existing `data/pdufa_curated.csv` convention which already carries `source_name,source_url,source_type`):
```
metric,phase,indication,value,source_name,source_url,quote
loa,I,all,0.079,BIO/Biomedtracker 2011-2020,https://www.readkong.com/page/...,"7.9% overall LoA from Phase I"
transition,II,all,0.289,BIO 2011-2020,https://...,"28.9% Phase II to Phase III"
loa,I,oncology,0.034,Oxford Biostatistics,https://academic.oup.com/...,"~3.4% oncology LoA from Phase I"
crl_penalty,,all,-0.28,BiopharmaWatch,https://www.biopharmawatch.com/...,"prior CRL reduces approval ~28%"
adcom_followthrough,,all,0.90,RTTNews,https://www.rttnews.com/...,"~90% of AdCom-supported approved"
...
```
**Loader — `quant/base_rates.py`:**
- `load_base_rates(path=...) -> list[dict]` and `base_rate(metric, phase=None, indication=None) -> dict` → returns `{value, source_name, source_url, quote}` so any agent citing it gets the citation **with** the number (the anti-hallucination discipline: no number without a source, exactly like `KeyFinding.evidence_ref`).
- **Citability:** the source columns ARE the citation. An agent reads the value and the `source_url`+`quote` together.
- **KB seeding (OPTIONAL, deferable):** these could also be seeded into the KB as `insert_claim(KBNode(kind=...), [EvidenceSource(url=..., quote=...)])` so they're queryable alongside scenario analogs. **Recommendation: don't, this phase.** Base rates are static reference data, not scenario claims; a CSV + loader is simpler and matches convention. Seed into the KB only if/when an agent needs base rates *inside* an analog query (Phase 10). Note for planner: the KB path is a clean escalation because `insert_claim` already enforces the citation invariant these rows carry.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cointegration (ADF unit-root, Johansen trace) | Custom ADF regression + critical-value tables | `statsmodels.tsa.stattools.coint`, `coint_johansen` | Critical values + lag selection are a bug farm; this is money-critical |
| Correlation / β / std / mean over arrays | Manual loops | `numpy` (already in-tree) | Correct, fast, readable one-liners |

**Key insight — the inversion:** In *this* library the usual "don't hand-roll metrics" advice is **wrong**. Sharpe/Sortino/rNPV/Kelly/risk-of-ruin are short, exact, well-specified formulas. The libraries that "provide" them (quantstats, empyrical, vectorbt) are heavyweight and — worse — hide the annualization factor that silently corrupts Sharpe (the documented `freq` footgun). Hand-rolling with an **explicit, required `periods_per_year`** is simpler, lighter, and *more correct*. Hand-roll the arithmetic; only import statsmodels for the genuinely hard statistical test (cointegration).

## Common Pitfalls (money-critical — these are the OPS-04 test targets)

### Pitfall 1: Division-by-zero / undefined-metric emitted as inf or NaN
**What goes wrong:** `cash/0`, Sharpe with zero volatility, β with zero market variance, Kelly with zero loss fraction → `inf`/`NaN` flows into a position size.
**How to avoid:** Raise `ValueError` at the boundary (Pattern 2). Never return `inf`/`NaN` from a money tool.
**Warning sign:** a test that passes with `float('inf')` in the result.

### Pitfall 2: Silent annualization (the freq footgun)
**What goes wrong:** Sharpe computed without a periods factor, or with a wrong default (daily vs weekly), silently 7×/√7 off.
**How to avoid:** `periods_per_year` is a **required** argument; test a weekly (52) and a daily (252) case.

### Pitfall 3: Short/empty series into cointegration or metrics
**What goes wrong:** `coint` on 3 points, Sharpe on `[]`, corr on 1 point → garbage or crash.
**How to avoid:** Guard minimum lengths (cointegration needs ≥ ~30; corr/β ≥ 2 with non-zero variance); raise a clear error.

### Pitfall 4: Kelly/risk-of-ruin scaled to the return target, not survival
**What goes wrong (PITFALLS #5):** treating the tiny −70%-gap Kelly output as "too small" and scaling up toward 1%/week = ruin.
**How to avoid:** The tools return the honest small number and expose risk-of-ruin explicitly. Tests assert Kelly on a −70% binary is small and that `risk_of_ruin` rises sharply with size — the arithmetic itself is the guardrail.

### Pitfall 5: SL displayed as bounded loss on a held-through binary
**What goes wrong (PITFALLS #2):** dashboard shows "max loss = stop distance" for a position spanning the catalyst; the gap jumps the stop.
**How to avoid:** `sl_tp_levels(..., holds_through_catalyst=True)` flags `advisory=True` in `detail`; a test asserts the flag is set.

### Pitfall 6: Reproducibility hole — a tool returns a bare number
**What goes wrong (QUANT-03):** an output without its inputs snapshot can't be audited.
**How to avoid:** library-wide parametrized test asserting every tool returns a `ToolResult` whose `inputs` equals the call args.

## Exhaustive Edge-Case TDD (OPS-04) — the biggest quality lever

**Write these tests FIRST (RED), then the logic.** Existing test style to mirror: descriptive snake_case names (e.g. `test_uncited_claim_rejected_leaves_no_orphan`), `pytest.raises(ValueError)`, `@pytest.mark.parametrize`, in-memory `db` fixture from `conftest.py` (only base-rate/rubric-persistence tests need it; pure math tools need no DB). No given/when/then required in this repo.

Per-tool edge-case matrix (every ✅ is a required test case):

| Tool | div-by-zero / undefined | negative input | empty/short series | NaN / inf input | extreme value | happy path |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| rNPV | discount rate −100% (÷0) ✅ | negative cashflow ✅ | empty cashflow list ✅ | NaN PoS ✅ | 40% discount, 20yr ✅ | ✅ |
| cash_runway | burn=0 ✅ | negative cash ✅ | — | NaN ✅ | burn≫cash → ~0 mo ✅ | ✅ |
| kelly | loss frac=0 ✅ | negative edge → 0 ✅ | — | NaN prob ✅ | p=1 → clamp ✅ | ✅ |
| risk_of_ruin | — | negative size ✅ | n_trades=0 ✅ | — | size=100% → ruin=1 ✅ | ✅ |
| cointegration | — | — | <30 obs ✅ / mismatched len ✅ | NaN in series ✅ | perfectly cointegrated ✅ | ✅ |
| correlation_beta | zero variance ✅ | — | 1 point ✅ / mismatched len ✅ | NaN ✅ | corr=±1 ✅ | ✅ |
| conditional_payoff | — | — | — | — | target −70%/peer +40% ✅ | ✅ |
| implied_move | price=0 ✅ | negative IV ✅ | — | NaN ✅ | 300% IV ✅ | ✅ |
| iv_crush | — | negative IV ✅ | — | NaN ✅ | pre 300→post 50 ✅ | ✅ |
| sharpe / sortino | zero vol ✅ | — | empty ✅ / 1 point ✅ | NaN ✅ | freq 52 vs 252 ✅ | ✅ |
| cumulative_return | — | −100% return (÷0 next) ✅ | empty ✅ | NaN ✅ | −100% wipeout ✅ | ✅ |
| attribution | components ≠ total ✅ | — | — | NaN ✅ | — | ✅ |
| sl_tp | sl_pct=0 (÷0 R:R) ✅ | negative pct ✅ | — | — | held-through → advisory ✅ | ✅ |
| concentration/exposure | weights sum=0 ✅ | negative weight ✅ | empty book ✅ | NaN ✅ | single-name=1.0 ✅ | ✅ |
| rubric | Σweights≠1 ✅ | negative weight ✅ | missing factor ✅ | — | score>10 rejected ✅ | ✅ |
| base_rates | unknown key → None/raise ✅ | — | — | — | — | loads+cites ✅ |
| ToolResult | — | — | — | — | mutation raises ✅ | inputs snapshot round-trips ✅ |

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| quantstats/empyrical for all metrics | Hand-roll Sharpe/Sortino in numpy with explicit `periods_per_year` | Fewer deps, no freq footgun, readable |
| DCF/P/E on biotech | rNPV (probability-weighted, risk in the PoS not the discount rate) | The only defensible pre-revenue method (FEATURES.md A2) |
| "0.7 correlated = hedged" | conditional-payoff matrix on catalyst branches | Honest hedge accounting (PITFALLS #1) |
| Monte-Carlo risk-of-ruin | deterministic recurrence / consecutive-loss arithmetic | Reproducible + testable (no RNG seed) |

**Deprecated/outdated:** none relevant — statsmodels `coint`/`coint_johansen` APIs are stable across 0.14.x.

## Open Questions

1. **Exact requirement text for each tool's expected signature.** — What we know: QUANT-02 lists all 12 tools. What's unclear: no per-tool signature spec beyond the formulas here. Recommendation: planner defines signatures from the Tool Catalog; keep them plain-typed (Pattern 3).
2. **Does the Phase-10 learning loop need versioned/A-B weight sets now?** — What we know: FRAME-02 says "tunable"; PITFALLS #13 warns against free-mutating configs. Recommendation: ship the JSON file now (satisfies FRAME-02); note the DB-table upgrade path. Don't build A/B versioning this phase (YAGNI).
3. **Should base rates seed the KB now?** — Recommendation: no (CSV + loader satisfies FRAME-03); seed the KB only when an agent needs base rates inside an analog query.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | everything | ✓ | 3.14.6 | — |
| pydantic | ToolResult, models | ✓ | 2.13.4 | — |
| sqlite-vec / sqlite | base-rate/rubric persistence tests (if any) | ✓ | installed | — |
| statsmodels | cointegration | ✗ (not yet installed) | 0.14.6 available, cp314 wheel verified | numpy-only ADF is NOT an acceptable fallback — must install |
| numpy | corr/β/Sharpe | ✗ (arrives with statsmodels) | 2.5.2 cp314 | — |
| scipy/pandas/patsy | transitive | ✗ (arrive with statsmodels) | 1.18.0 / 3.0.5 / 1.0.2 cp314 | — |
| pytest / freezegun / pytest-cov | TDD, coverage gate | ✓ | 9.1.1 / 1.5.5 / installed | — |

**Missing dependencies with no fallback:** `statsmodels` — must be `pip install`ed and pinned in `pyproject.toml`. It is the only new dependency; its transitive chain (numpy/scipy/pandas/patsy) all have verified cp314 wheels (dry-run confirmed 2026-08-14, no source build).

**Missing dependencies with fallback:** none — everything else is stdlib/pure-python.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 (+ pytest-cov, freezegun 1.5.5) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths=["tests"]`, `addopts="-ra"`) |
| Quick run command | `.venv/bin/pytest tests/test_<file>.py -x -q` |
| Full suite command | `.venv/bin/pytest -q` |
| Coverage command | `.venv/bin/pytest --cov=catalyst_trader.quant --cov-report=term-missing` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| QUANT-01 | Every tool callable, importable from `quant`, versioned | unit | `.venv/bin/pytest tests/test_quant_result.py -x` | ❌ Wave 0 |
| QUANT-02 | Each of the 12 tools computes the correct formula | unit | `.venv/bin/pytest tests/test_valuation.py tests/test_sizing.py tests/test_pairs.py tests/test_options.py tests/test_performance.py tests/test_portfolio.py -x` | ❌ Wave 0 |
| QUANT-03 | Every tool output snapshots its inputs; result immutable | unit | `.venv/bin/pytest tests/test_quant_result.py -k inputs -x` | ❌ Wave 0 |
| FRAME-01 | 8-factor rubric present + composite score 0–100 | unit | `.venv/bin/pytest tests/test_rubric.py -x` | ❌ Wave 0 |
| FRAME-02 | Weights load from file; Σ≈1 enforced; editing file changes score | unit | `.venv/bin/pytest tests/test_rubric.py -k tunable -x` | ❌ Wave 0 |
| FRAME-03 | Base rates load + return value WITH citation; unknown key handled | unit | `.venv/bin/pytest tests/test_base_rates.py -x` | ❌ Wave 0 |
| OPS-04 | Exhaustive edge cases (div-0, negative, empty/short, NaN, extreme) per tool | unit | `.venv/bin/pytest tests/ -q && .venv/bin/pytest --cov=catalyst_trader.quant --cov-report=term-missing` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/pytest tests/test_<module>.py -x -q` (the module just touched)
- **Per wave merge:** `.venv/bin/pytest -q` (full suite)
- **Phase gate:** full suite green + coverage on `catalyst_trader.quant` at/above the project bar (OPS-04) before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_quant_result.py` — QUANT-01, QUANT-03 (ToolResult + library-wide inputs-snapshot parametrized test)
- [ ] `tests/test_valuation.py` — QUANT-02 (rNPV, cash_runway)
- [ ] `tests/test_sizing.py` — QUANT-02 (kelly, fractional_kelly, risk_of_ruin, sl_tp)
- [ ] `tests/test_pairs.py` — QUANT-02 (cointegration, correlation_beta, conditional_payoff)
- [ ] `tests/test_options.py` — QUANT-02 (implied_move, iv_crush)
- [ ] `tests/test_performance.py` — QUANT-02 (sharpe, sortino, cumulative_return, attribution — freq cases)
- [ ] `tests/test_portfolio.py` — QUANT-02 (concentration, exposure)
- [ ] `tests/test_rubric.py` — FRAME-01, FRAME-02
- [ ] `tests/test_base_rates.py` — FRAME-03
- [ ] Framework install: `pip install statsmodels==0.14.6` (pins numpy/scipy/pandas/patsy) + add to `pyproject.toml [project.dependencies]`
- [ ] Data files: `data/rubric_weights.json`, `data/base_rates.csv`

*(conftest.py already provides `db`, `load_fixture`, `embed`, `frozen_now` fixtures — reuse; pure-math tests need no fixtures.)*

## Sources

### Primary (HIGH confidence)
- Local codebase via Graphify (`graphify explain models|insert_claim`; read `contracts/__init__.py`, `kb.py`, `db.py`, `models.py`, `conftest.py`, `pyproject.toml`, `migrations/003_kb.sql`) — existing pydantic/atomic-write/TDD patterns to mirror
- `pip install --dry-run` on the project venv (2026-08-14) — verified cp314 wheels for statsmodels 0.14.6, numpy 2.5.2, scipy 1.18.0, pandas 3.0.5, and the quantstats/empyrical dependency chains that justify rejecting them
- `.planning/research/FEATURES.md` A2/A3 — rNPV rubric (8 factors + weights) + base-rate numbers, with their own cited sources (BIO/Biomedtracker, Oxford Biostatistics, RTTNews, BiopharmaWatch)
- `.planning/research/PITFALLS.md` #1,#2,#5,#10 — risk-of-ruin sizing, conditional hedge payoff, SL-advisory, implied-move-as-magnitude-prior
- `CLAUDE.md` STACK — quantstats/empyrical/vectorbt guidance + freq footgun; minimal-deps + TDD constraints

### Secondary (MEDIUM confidence)
- statsmodels `tsa.stattools.coint` / `tsa.vector_ar.vecm.coint_johansen` API (stable across 0.14.x — training + consistent with dry-run metadata; not re-fetched from docs this session)

### Tertiary (LOW confidence)
- None load-bearing. Kelly/risk-of-ruin/Sharpe formulas are standard finance (no single URL).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — dependency availability + cp314 wheels verified by dry-run on the actual venv
- Architecture: HIGH — patterns lifted directly from existing `contracts`/`kb`/`store` code
- Formulas: HIGH — standard, well-specified; only cointegration delegates to a library
- Base-rate numbers: HIGH — verbatim from FEATURES.md's sourced table
- Pitfalls/edge cases: HIGH — driven by PITFALLS.md + universal money-math failure modes

**Research date:** 2026-08-14
**Valid until:** ~2026-09-14 (stable; re-verify statsmodels/numpy versions if the venv Python changes)
