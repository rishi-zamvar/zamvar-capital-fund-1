# Phase 7: Verifier/Guardrails + Backtest Harness - Research

**Researched:** 2026-08-15
**Domain:** Deterministic backtest harness (Layer A mechanical + Layer B guarded-agentic) + point-in-time event set + runtime guardrail gate, over ~1yr history, before any capital.
**Confidence:** HIGH (reuse verdict is against actual read signatures; two load-bearing reuse assumptions in CONTEXT were checked and one was FALSE — see Standard Stack)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
1. **Backtest measures the CORRECTED strategy** — Layer A runs the actual shipped mechanics (weekly build/exit cadence, target-within-survival-cap sizing, no-zero-trade defensive fallback, universe-wide `thesis_scan`, honest hedge/single-leg selection). MECHANICAL replay (deterministic pair/leg selection + sizing + entry 1-2d pre-event + SL/TP + 1-week exit) with **NO LLM**.
2. **Pessimistic fill model (money-honesty)** — fill at historical price with a tunable slippage haircut; on a **held-through binary event, fill at the GAP-OPEN (far-side), NOT the stop level** (a stop can't fill inside the gap). Skip an event only if halted/delisted/zero-volume/zero-quote (volume caps ignored by design). Tunable slippage knob.
3. **DATA-GATHERING TIMING simulation (operator directive)** — replay ONLY data that would ACTUALLY have been available at decision time given free-source lag + fetch cadence (delayed options, bi-monthly short interest, EOD). Add a tunable **DATA-LATENCY knob** alongside the slippage knob. Reuse the point-in-time discipline already in `bars_asof`/`card_asof`/`universe_as_of`.
4. **Point-in-time event set (BACK-01)** — ~1yr of universe earnings calendars (dense, precisely-dated) + dateable biotech catalysts, point-in-time, INCLUDING delisted names (survivorship-free). Reuse `universe_as_of` + the catalyst store.
5. **Layer B guarded-agentic replay (BACK-03) — labeled biased-optimistic** — run the REAL pipeline (run_desk/run_portfolio/run_diligence/reconcile) on historical catalysts with look-ahead GUARDRAILS (web blocked/archived-only, point-in-time fundamentals, outcome-blind prompts). Results explicitly LABELED biased-optimistic. Expensive → run on a SAMPLE, log what was sampled/dropped (**no silent caps**).
6. **Runtime guardrails/monitors (OPS-03)** — active + enforced on the live pipeline: catalyst-date freshness, fact-check, provenance, the Workflow-3 firewall, net-long/concentration caps, NO PATH from scraped/raw content to an order. Many already exist as invariants — this phase makes them a runtime GATE, tested.
7. **The go/no-go gate (BACK-05)** — baseline (win rate, avg win/loss, Sharpe, Sortino, max DD, hedge-effectiveness) unlocks config tuning and produces an explicit, **SAMPLE-BASED** go/no-go gate before paper trading (never calendar-based).
8. **Reuse + discipline** — reuse quant performance tools, `run_weekly`/`thesis_scan`/`select_book`/sizing, the desk pipeline, the stores. Layer A is pure deterministic Python; Layer B reuses the real desk behind guardrails. Full TDD (`.venv/bin/python -m pytest`, bare python NOT on PATH), fully offline (synthetic history fixtures; Layer B mocks `run_structured`). Graphify graph-first.

### Claude's Discretion
- Whether the mechanical catalyst-leg direction proxy comes from the KB base-rate P(positive) prior vs a fixed long-the-run-up rule (Layer A has no LLM verdict — see Pitfall 1).
- Weekly-bar vs daily-bar granularity for the fill model (the store is weekly today — see Pitfall 2).
- The exact `backtest/` module decomposition and the shape of the latency-knob config.
- The sampling strategy for Layer B (how many catalysts, stratified vs random) — as long as dropped events are logged, not silently capped.

### Deferred Ideas (OUT OF SCOPE)
- The paper ledger (Layer C, forward out-of-sample) — **Phase 8**.
- Live free-data fetchers — data-layer component (backtest uses historical fixtures + the latency knob to simulate lag).
- Config auto-tuning from the baseline — the gate UNLOCKS it; the actual refit loop is **Phase 10**.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BACK-01 | Historical event set from ~1yr earnings + dateable biotech catalysts (point-in-time, survivorship-free) | REUSE `universe_as_of` + `bars_asof` (both carry the `<= as_of` guard) + `tradeable_catalysts` (WARNING: status-only, NO date guard — the event-set builder MUST post-filter its output on `last_verified_at <= effective_asof`, else a catalyst verified after the simulated week leaks in). NEW: an event-set builder that assembles per-week `(as_of, universe, catalysts, bars)` tuples. Offline via synthetic fixtures (`upsert_bars` + `insert_catalyst` + universe snapshots). Real 1yr data = documented carry-forward. |
| BACK-02 | Layer A mechanical backtest (no LLM) → baseline distribution + hedge effectiveness | NEW `backtest/` engine loop that re-expresses the weekly mechanics deterministically (does NOT call `run_desk` — that's the LLM). REUSE `thesis_scan`, `classify_drop`, `weekly_base_rate`, `size_for_survival`, `validate_hedge`, `select_book`, `bars_asof`. Baseline metrics: REUSE `sharpe`/`sortino`/`cumulative_return`/`attribution`; **NEW `max_drawdown` + `win_rate` + `avg_win_loss` + `hedge_effectiveness`** (do NOT exist — see Standard Stack). |
| BACK-03 | Layer B guarded agentic replay, labeled biased-optimistic | REUSE `run_desk`/`run_portfolio`/`run_diligence`/`reconcile`; the desk is ALREADY web-free (`ALLOWED_TOOLS = mcp__quant__*` only — free seam). NEW: point-in-time feeding + outcome-blind catalyst dict + `biased_optimistic` label + sampling/drop-log wrapper. Offline: mock `desk.runtime.run_structured`. |
| BACK-04 | Fill model: historical price + tunable slippage; skip only halted/delisted/zero-vol/zero-quote | NEW fill module: pessimistic far-side + gap-open on held-through binaries (NOT the SL), slippage knob, skip-guard. REUSE `bars_asof` as the price source. |
| BACK-05 | Baseline unlocks config tuning + sample-based go/no-go gate | NEW small deterministic gate fn (baseline dist + N → go/no-go, sample-based never calendar). |
| OPS-03 | Runtime guardrails/monitors made a tested runtime GATE | REUSE `is_tradeable`, `verifier.enforce`, `enforce_dossier`, `enforce_estimate`, `DiligenceInput` firewall, `select_book` heat_cap + `concentration`. NEW: a thin `guardrails` aggregator that asserts these hold at runtime + tests. (Live-position SL/TP + paper P&L monitors listed in OPS-03 belong to Phase 8/8.5 — scope note below.) |
</phase_requirements>

## Summary

Phase 7 is **~70% reuse, ~30% new deterministic plumbing**. The shipped codebase already contains every hard part: the point-in-time price/universe/catalyst stores (all with `<= as_of` no-look-ahead guards), the deterministic weekly mechanics (`thesis_scan`, `size_for_survival`, `validate_hedge`, `select_book`), the performance math, and — critically — a desk that is **already web-free** (analysts call `mcp__quant__*` only, never a web tool). That last fact makes the Layer-B "web blocked" guardrail a **free seam** (the same class of finding that made Phase 6.8 cheap).

Two CONTEXT reuse assumptions were checked against actual signatures. One held, one did **not**: `quant/performance.py` ships `sharpe`, `sortino`, `cumulative_return`, `attribution` — but **there is no `max_drawdown`, no `win_rate`, no `avg_win/loss`, and no `hedge_effectiveness`**. The go/no-go baseline in BACK-05/Decision 7 explicitly requires max-DD and hedge-effectiveness, so these are NEW money-critical deterministic tools (TDD, exhaustive edge cases), not reuse. Likewise, **quantstats/empyrical are not installed** (deps: httpx, pydantic, sqlite-vec, statsmodels, claude-agent-sdk) — do NOT add them; the four missing metrics are ~5-15 lines of numpy each and belong beside the existing four in `performance.py`.

**Primary recommendation:** Build a new `backtest/` package (event-set builder, mechanical engine loop, fill model with slippage+latency knobs, Layer-B guarded wrapper, go/no-go gate) + a thin `desk/guardrails.py` runtime gate + 4 new `performance.py` metrics. Layer A re-expresses the weekly loop deterministically (it must NOT call `run_desk`, which is the LLM); Layer B calls the real desk with `run_structured` mocked in tests. Zero new dependencies, fully offline via synthetic-history fixtures.

## Standard Stack

### Core (all already installed — no new deps)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| numpy (via statsmodels dep) | shipped | The 4 new metric functions | Already the substrate of `performance.py`; no new dep |
| pydantic | 2.13.4 | Backtest result contracts (baseline distribution, gate verdict, Layer-B label) | Project-wide money-boundary discipline; `extra="forbid"` makes leaks a ValidationError |
| pytest + pytest-asyncio | 9.1.1 / auto | TDD, async desk tests | `asyncio_mode=auto` already set |

### Alternatives Considered (REJECTED — do not add)
| Instead of | Could Use | Verdict |
|------------|-----------|---------|
| in-house `performance.py` + 4 new fns | quantstats | **Reject.** Not installed; adds a heavy dep + the `freq` footgun the project already cured (`periods_per_year` is a required arg on `sharpe`/`sortino`). |
| custom mechanical loop | vectorbt / backtrader | **Reject.** Vectorized param-sweep / bar-by-bar order engines are wrong for a weekly 20-name book; the strategy already lives in deterministic tools we replay directly. |

**Installation:** none. `pyproject.toml` unchanged.

**Version verification:** no new packages, so nothing to verify against a registry. The 4 new metric fns use numpy already pulled in transitively by `statsmodels==0.14.6`.

## Architecture Patterns

### Recommended Structure
```
src/catalyst_trader/
├── backtest/
│   ├── __init__.py
│   ├── events.py        # BACK-01: point-in-time event-set builder (reuses *_asof)
│   ├── fill.py          # BACK-04: pessimistic far-side + gap-open fill, slippage + latency knobs
│   ├── engine.py        # BACK-02: Layer A mechanical loop (NO LLM) -> baseline distribution
│   ├── layerb.py        # BACK-03: guarded agentic replay wrapper + biased-optimistic label + sampling
│   └── gate.py          # BACK-05: sample-based go/no-go gate
├── desk/
│   └── guardrails.py    # OPS-03: thin runtime gate aggregating existing invariants
└── quant/
    └── performance.py   # EXTEND: + max_drawdown, win_rate, avg_win_loss, hedge_effectiveness
```

### Pattern 1: Layer A re-expresses the mechanics; it does NOT call `run_desk`
**What:** `run_weekly(conn, embed, as_of, open_book, *, params=None, target_weekly=0.01, catalyst_context=None, closing_legs=None)` is a THIN composition that, for catalyst names, calls `await run_desk(...)` — i.e. the **LLM Workflow-1 debate**. Decision 1 requires Layer A to be **NO LLM**. So Layer A cannot reuse `run_weekly` wholesale for the catalyst legs.
**Why:** `run_weekly` with `catalyst_context=None` already produces a deterministic book — but it DROPS the catalyst legs (`if ... catalyst_context is None: continue`), leaving only the statistical + defensive sleeves. That omits the core of the strategy.
**How:** Layer A re-implements the weekly loop deterministically, reusing the deterministic tools and supplying a **deterministic direction proxy** for the catalyst leg (Claude's discretion — recommended: the KB base-rate `P(positive)` prior already used everywhere as "the assumption," so Layer A measures the strategy-as-configured, not an LLM). It reuses:
```
thesis_scan(universe, as_of, store, conn, params)        # every name, deterministic, row schema below
classify_drop(ticker, as_of, store, conn, params)
weekly_base_rate(...)                                     # P(positive) prior for the catalyst leg
size_for_survival(p_loss, gap, target_return, expected_move).value   # cap-safe sizing
validate_hedge(...)                                       # deterministic honest-hedge (returns None if fake)
select_book(candidates, open_book, weekly_budget, heat_cap, target_weekly, ...)
bars_asof(conn, ticker, as_of, lookback_weeks=...)       # the price source
```
`thesis_scan` returns `ToolResult(detail={"rows": [...]})`; each row: `{ticker, thesis_type, trigger, p, mean_next, n_effective, eligible, veto_reasons, drop_class?}`. Catalyst names come back `thesis_type="catalyst"` with nulls (Workflow-1 owns them) — Layer A fills the catalyst leg itself.

### Pattern 2: Point-in-time by construction (reuse the `<= as_of` guard)
**What:** `bars_asof` (`week_end <= as_of`) and `universe_as_of` (latest cohort `<= as_of`, append-only, delisted retained) already enforce no-look-ahead and survivorship-freeness. **`tradeable_catalysts` does NOT** — it filters `status='verified'` only (store.py L166), with no date bound, so on a historical replay it returns catalysts verified AFTER the simulated week. The event-set builder MUST post-filter its output on `Catalyst.last_verified_at <= effective_asof` (models.py L76) — the one point-in-time guard the store does not provide for itself. `is_tradeable` is likewise status-only, not a date gate.
**How:** the event-set builder walks a weekly `as_of` cursor across ~1yr; at each step it reads universe/bars strictly through the `_asof` functions and catalysts through `tradeable_catalysts` THEN the mandatory `last_verified_at <= effective_asof` post-filter. **Never** read a raw table with a `>` or unbounded date, and **never** treat `tradeable_catalysts` output as point-in-time without the verification filter.

### Pattern 3: Data-latency knob = an as-of transform per data class
**What:** free sources lag (options delayed, short interest bi-monthly, EOD calibration). Look-ahead sneaks in when a decision at date D reads a datum only *published* after D.
**How:** a pure function `effective_asof(data_class, decision_date, latency_cfg) -> as_of_str` that subtracts the per-class lag, and ALL reads for that class go through `bars_asof(..., effective_asof(...))`. The knob sits in `params`/config beside the slippage knob. This reuses the existing guard — it just shifts the argument. Test: inject a bar/card dated between `effective_asof` and `decision_date`, assert the engine never returns it (the same property `test_bars_asof_never_returns_a_future_bar` proves for the base guard).

### Pattern 4: Layer B guardrails — mostly free, then label + sample
**What:** the desk is ALREADY web-free (`ALLOWED_TOOLS` in `orchestrator.py`/`diligence.py` = `mcp__quant__*` only). `run_desk`/`run_diligence` take a `catalyst`/`DiligenceInput` and reach the model only via `desk.runtime.run_structured` (the single SDK seam every test monkeypatches).
**How:**
- **Web blocked:** assert `ALLOWED_TOOLS` contains no web tool (a guardrail test), not new plumbing.
- **Point-in-time fundamentals:** feed the desk's market context through the same `effective_asof`/`bars_asof` path.
- **Outcome-blind prompts:** the catalyst dict handed to `run_desk` must NOT carry the realized outcome (assert disjoint fields — same `extra="forbid"` firewall technique as `DiligenceInput`).
- **Label biased-optimistic:** every Layer-B result carries a `biased_optimistic=True` field on its contract (structural, not a comment).
- **Sample + log dropped:** the wrapper records `{sampled: [...], dropped: [...], reason}` — a zero-silent-truncation record, mirroring 6.7's `logged_flags`.
- **Offline:** monkeypatch `run_structured` (see `tests/test_desk_orchestrator.py::_patch_seam` and `test_weekly_runner.py`).

### Anti-Patterns to Avoid
- **Reusing `run_weekly` for Layer A catalyst legs.** It calls `run_desk` (LLM) — violates the no-LLM decision. Re-express the loop.
- **Filling a held-through binary at the SL level.** The whole point (Pitfall 2): the stop is jumped by the gap; fill at the gap-open far-side.
- **Adding quantstats/empyrical.** Not installed; four numpy fns beside the existing four are the lazy correct call.
- **A silent `[:N]` cap on Layer-B sampling.** Decision 5 forbids it — log every dropped catalyst.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Point-in-time price read | a new query | `store.bars_asof` | Already carries the money-critical `week_end <= as_of` guard + delisted retention |
| Survivorship-free universe | a screen | `universe.build.universe_as_of` | Append-only cohorts, delisted names retained |
| Cap-safe sizing | new Kelly math | `desk.risk.size_for_survival` | No return-target coupling; ruin cap structurally un-crossable |
| Honest hedge | a correlation check | `desk.risk.validate_hedge` | Returns `None` unless a true inverse peer passes conditional-payoff + cointegration + catalyst-clean |
| Weekly thesis rows | re-derive base rates | `quant.weekly.thesis_scan` | Deterministic, every-name, catalyst-precedence + falling-knife veto baked in |
| Sharpe/Sortino/return/attribution | reimplement | `quant.performance.*` | `periods_per_year` required (freq footgun cured); attribution reconciles to total |
| Fact-check / provenance / firewall gates | new checks | `verifier.enforce`, `enforce_dossier`, `enforce_estimate`, `DiligenceInput` | These ARE the OPS-03 invariants; the gate aggregates them |

**Key insight:** the only genuinely new *logic* is the fill model (pessimistic gap-open), the four missing metrics, the latency transform, and the sample-based gate. Everything else is wiring existing deterministic tools into a weekly replay loop.

## Common Pitfalls

### Pitfall 1: Layer A has no directional verdict (the LLM is gone)
**What goes wrong:** the mechanical replay needs a long/short/skip direction for each catalyst leg, but the production direction comes from the LLM bull/bear debate that Layer A must not run.
**How to avoid:** use a deterministic proxy — recommended the KB base-rate `P(positive)` prior (`weekly_base_rate` / analog gaps), which is exactly "the assumptions are the moat" the strategy is configured on. Document that Layer A measures *the configured strategy*, not the LLM's incremental edge (that's Layer B). Make the proxy a named, swappable knob so the planner/operator can compare "always long the run-up" vs "base-rate-gated."
**Warning sign:** a hard-coded "always long" that quietly makes the baseline a beta bet.

### Pitfall 2: The price store is WEEKLY — the gap-open fill needs care
**What goes wrong:** `bars_asof` returns weekly OHLCV (`week_end`, open/high/low/close). "Entry 1-2d pre-event" and an intraday gap-open aren't directly representable at weekly resolution.
**How to avoid:** two honest options (Claude's discretion): (a) model at weekly granularity — enter at the prior week's close/anchor, the "gap" is the hold-week OPEN vs prior close, exit at the hold-week close; pessimistic held-through fill = the worse of far-side and the hold-week open (down leg) / low. This matches the one-week horizon and needs no new data. (b) add a daily-bar seam if finer fills matter — heavier, deferred-worthy. Recommend (a) with a `# ponytail:` note naming the ceiling; the weekly horizon makes daily granularity low-value for the baseline.
**Warning sign:** a fill model that assumes intraday prints the weekly store doesn't have.

### Pitfall 3: Silent look-ahead through the non-price data classes
**What goes wrong:** bars are guarded, but a naively-fed "current" short interest / options quote at decision date D is really post-D data.
**How to avoid:** route EVERY data class through `effective_asof(class, D)`; property-test that no datum newer than the class's effective as-of is ever read.

### Pitfall 4: Layer-B outcome leakage
**What goes wrong:** the realized outcome rides along in the catalyst dict or the analog set and the model "predicts" what it can already see → the baseline looks great and is a lie.
**How to avoid:** outcome-blind contract (`extra="forbid"`, no outcome field), point-in-time analog set (`<= as_of`), and the honest `biased_optimistic=True` label regardless — memorization leaks through parametric memory even with a clean prompt (this is why Layer B is labeled, not trusted).

## Code Examples

### Reuse: point-in-time price read (the backtest's price source)
```python
# Source: src/catalyst_trader/store.py:224
bars = store.bars_asof(conn, ticker, as_of, lookback_weeks=None)  # week_end <= as_of, delisted retained
```

### Reuse: cap-safe sizing (identical call to run_weekly's statistical sleeve)
```python
# Source: src/catalyst_trader/desk/weekly.py:121
size = size_for_survival(p_loss=1.0 - p, gap=stat_gap,
                         target_return=target_weekly, expected_move=mean_next).value
```

### Reuse: the offline mock seam for Layer B
```python
# Source: tests/test_desk_orchestrator.py:65
def _patch_seam(monkeypatch, fake):
    for mod in (...): monkeypatch.setattr(mod, "run_structured", fake)  # zero live API in pytest
```

### New: shape of the four missing metrics (build in performance.py, TDD)
```python
# NEW — do NOT reuse (max_drawdown/win_rate/avg_win_loss/hedge_effectiveness do not exist)
def max_drawdown(returns: list[float]) -> ToolResult: ...   # min peak-to-trough on compounded equity
def win_rate(trade_returns: list[float]) -> ToolResult: ... # frac > 0, empty -> raise (no silent 0)
def avg_win_loss(trade_returns: list[float]) -> ToolResult: ...
def hedge_effectiveness(target_legs: list[float], hedge_legs: list[float]) -> ToolResult: ...
# hedge-eff = how often the peer leg actually offset the target leg on the down days (Decision 2/7)
```

## Runtime State Inventory

Not applicable — greenfield backtest package + code-only additions. No rename/refactor/migration. (No stored data re-keyed, no live-service config, no OS-registered state, no secret renames, no build-artifact churn beyond a normal package add.)

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `.venv/bin/python` | all tests | ✓ | project venv | — |
| pytest / pytest-asyncio | TDD | ✓ | 9.1.1 / auto | — |
| numpy (via statsmodels) | new metrics | ✓ | shipped | — |
| Graphify graph | navigation | ✓ | 2593 nodes | read files graph points to |
| Live FMP historical (1yr bars/earnings) | REAL baseline run | ✗ | — | **Synthetic-history fixtures** for all offline tests; real data curation is a documented carry-forward (Decision 8 / STATE carry-forwards) before the operator runs the true baseline |

**Missing dependencies with no fallback:** none for the code/tests. The only gap is real 1yr historical data for an *actual* baseline number — a data-curation carry-forward, not a build blocker (tests run fully offline on synthetic fixtures).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 + pytest-asyncio (`asyncio_mode=auto`) |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, `testpaths=["tests"]`) |
| Quick run command | `.venv/bin/python -m pytest tests/test_backtest_*.py -x -q` |
| Full suite command | `.venv/bin/python -m pytest -q` |

> Bare `python` is NOT on PATH — always `.venv/bin/python -m pytest`.

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BACK-01 | Event set is point-in-time + survivorship-free (delisted names present; no future catalyst/bar) | unit | `.venv/bin/python -m pytest tests/test_backtest_events.py -x` | ❌ Wave 0 |
| BACK-02 | Layer A mechanical loop (no LLM) produces a baseline distribution + hedge-effectiveness; never calls `run_desk` | unit | `.venv/bin/python -m pytest tests/test_backtest_engine.py -x` | ❌ Wave 0 |
| BACK-02 | New metrics: `max_drawdown`/`win_rate`/`avg_win_loss`/`hedge_effectiveness` (edge cases: empty→raise, -100% wipeout, all-wins) | unit | `.venv/bin/python -m pytest tests/test_performance.py -x` | ⚠️ extend existing |
| BACK-03 | Layer B runs the real desk with `run_structured` mocked; result carries `biased_optimistic=True`; sampled/dropped both logged (no silent cap); web tools absent | unit | `.venv/bin/python -m pytest tests/test_backtest_layerb.py -x` | ❌ Wave 0 |
| BACK-04 | Fill model: far-side + slippage; held-through binary fills at gap-open NOT SL; skip only halted/delisted/zero-vol/zero-quote | unit | `.venv/bin/python -m pytest tests/test_backtest_fill.py -x` | ❌ Wave 0 |
| DATA-LATENCY | Latency knob shifts as-of per data class; look-ahead is impossible (future-dated datum never read) | unit | `.venv/bin/python -m pytest tests/test_backtest_latency.py -x` | ❌ Wave 0 |
| BACK-05 | Go/no-go gate is sample-based (N-driven), never calendar; emits explicit verdict from the baseline dist | unit | `.venv/bin/python -m pytest tests/test_backtest_gate.py -x` | ❌ Wave 0 |
| OPS-03 | Runtime gate asserts each existing invariant (catalyst freshness, cite-or-drop verifier, DD firewall, concentration/heat cap, no scrape→order); fails closed on violation | unit | `.venv/bin/python -m pytest tests/test_guardrails.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest tests/test_backtest_*.py tests/test_guardrails.py tests/test_performance.py -x -q`
- **Per wave merge:** `.venv/bin/python -m pytest -q` (full suite — 831+ existing tests must stay green)
- **Phase gate:** full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_backtest_events.py` — BACK-01 (point-in-time + survivorship; synthetic fixtures)
- [ ] `tests/test_backtest_engine.py` — BACK-02 Layer A loop (assert no `run_desk` call)
- [ ] `tests/test_backtest_fill.py` — BACK-04 pessimistic gap-open + slippage + skip-guard
- [ ] `tests/test_backtest_latency.py` — DATA-LATENCY no-look-ahead property test
- [ ] `tests/test_backtest_layerb.py` — BACK-03 guarded replay + label + sample/drop-log (mock `run_structured`)
- [ ] `tests/test_backtest_gate.py` — BACK-05 sample-based gate
- [ ] `tests/test_guardrails.py` — OPS-03 runtime gate
- [ ] extend `tests/test_performance.py` — 4 new metrics with exhaustive edge cases (money-critical)
- [ ] synthetic-history fixture helper (reuse `tests/test_price_store.py::_series` seed pattern; extend for multi-week + delisted + catalyst-dated series)

## State of the Art

| Old Assumption (CONTEXT) | Actual State (verified) | Impact |
|--------------------------|-------------------------|--------|
| Reuse Phase-3 `max-DD` from `performance.py` | **No `max_drawdown` exists** — only sharpe/sortino/cumulative_return/attribution | max-DD + win-rate + avg-win/loss + hedge-eff are NEW money tools (TDD) |
| quantstats available for tearsheets (STACK.md) | **Not installed**; in-house numpy perf tools | Add 4 fns beside the existing 4; no new dependency |
| Layer-B "web blocked" is new guardrail work | Desk is **already web-free** (`ALLOWED_TOOLS=mcp__quant__*`) | Free seam — guardrail is an assertion, not plumbing |
| Reuse `run_weekly` for Layer A | `run_weekly` calls `run_desk` (the LLM) | Layer A must re-express the loop; can reuse the deterministic tools it composes, not the composition |

## Open Questions

1. **Catalyst-leg direction proxy for Layer A (no LLM).**
   - Known: production direction is the LLM debate verdict; Layer A can't run it.
   - Unclear: base-rate `P(positive)` prior vs fixed long-the-run-up.
   - Recommendation: base-rate prior (measures the configured strategy), as a named swappable knob; planner locks the default.

2. **Fill granularity (weekly vs daily bars).**
   - Known: store is weekly; horizon is one week.
   - Unclear: whether weekly-open gap proxy is honest enough for the baseline.
   - Recommendation: weekly granularity with a `# ponytail:` ceiling note; daily-bar seam deferred unless the gate is granularity-sensitive.

3. **OPS-03 live-position monitors (SL/TP, countdown, paper P&L).**
   - Known: OPS-03's text also lists live-position monitors, but those need a ledger.
   - Unclear: scope boundary vs Phase 8/8.5.
   - Recommendation: Phase 7 delivers the *pipeline* guardrail gate (freshness/fact-check/provenance/firewall/concentration/no-scrape-to-order); live-position monitors ride with the paper ledger (Phase 8) / intra-week monitor (Phase 8.5). Flag for the planner to confirm the split.

## Sources

### Primary (HIGH confidence — read directly this session)
- `src/catalyst_trader/quant/performance.py` — confirmed ONLY sharpe/sortino/cumulative_return/attribution (no max-DD)
- `src/catalyst_trader/desk/weekly.py::run_weekly` (L77-151) — thin composition; calls `run_desk` (LLM) for catalyst legs
- `src/catalyst_trader/store.py::bars_asof` (L224) + `upsert_bars` — weekly OHLCV, `week_end <= as_of` guard, delisted retained
- `src/catalyst_trader/universe/build.py::universe_as_of` (L133) — latest cohort `<= as_of`
- `src/catalyst_trader/desk/orchestrator.py::run_desk`/`run_portfolio` (L44/L81) — web-free `ALLOWED_TOOLS`; `run_portfolio` work-item contract
- `src/catalyst_trader/quant/weekly.py::thesis_scan`/`_thesis_row` (L313/L343) — row schema + catalyst precedence
- `src/catalyst_trader/desk/risk.py::size_for_survival` (L36) / `validate_hedge` (L101)
- `src/catalyst_trader/desk/md.py::reconcile` (L283); `desk/verifier.py::enforce`/`enforce_estimate`; `desk/diligence.py::enforce_dossier`/`synthesize_verdict`; `calendar/verify.py::is_tradeable`; `desk/portfolio.py::select_book` + `quant/portfolio.py::concentration`
- `src/catalyst_trader/desk/runtime.py::run_structured` (L29) — the single SDK seam
- `tests/conftest.py`, `tests/test_price_store.py`, `tests/test_desk_orchestrator.py` — offline fixture + `run_structured` mock patterns
- `pyproject.toml` — deps (no quantstats/empyrical), pytest config

### Secondary (project research, settled — not re-derived)
- `.planning/research/PITFALLS.md` #1 (peer-long ≠ hedge), #2 (stop jumped by gap), #7 (pessimistic fills), #8 (look-ahead/survivorship), #13 (learning-loop overfit)
- `.planning/research/STACK.md` (quantstats/vectorbt tradeoffs — confirms reject-new-dep)

## Metadata

**Confidence breakdown:**
- Reuse-vs-new verdict: HIGH — read actual signatures; both CONTEXT reuse assumptions checked (one falsified)
- Architecture (Layer A/B split, latency transform): HIGH — grounded in the shipped `run_weekly`/`run_desk` seam + existing `*_asof` guards
- Fill-model granularity: MEDIUM — weekly store is a real constraint; two honest options presented for planner to lock

**Research date:** 2026-08-15
**Valid until:** ~2026-09-15 (stable in-house codebase; re-check only if the desk gains a web tool or `performance.py` changes)
