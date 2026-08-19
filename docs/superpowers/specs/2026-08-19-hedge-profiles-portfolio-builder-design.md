# Hedge Profiles + Portfolio-Builder Engine — Design (2026-08-19)

**Status:** Approved decisions locked (CEO 2026-08-19). Build in two GSD waves.

## Motivation
Pre-paper analysis found the strategy's names are ~90% idiosyncratic: same-group peer pairs correlate ~0.11 (median, max 0.44), and even XBI explains only ~10% of the median name's weekly variance (7 of 69 names corr ≥ 0.5). So the "long target + correlated peer long" hedge premise is largely unsupported — the desk needs (a) explicit, always-available correlation/hedge facts per name, and (b) a portfolio what-if engine so agents can construct and stress-test a weekly book like a real desk. Neither exists today (verified: `company`/`hedge_peer` node kinds exist but are empty; no covariance anywhere in sizing/allocation; no what-if tool).

## Locked decisions
1. **Portfolio builder is a stateless ENGINE**: inputs = positions + EXPLICIT assumptions; output = everything relevant for the week. The agent iterates (stress-test, adjust assumptions, re-run). Assumptions are inputs, never hardcoded.
2. **Hedge profile is EXPLICIT**: per stock-pair and per index, store the value AND a plain correlary verdict (yes/weak/no) + systematic-vs-idiosyncratic split. An agent must see instantly whether a hedge is real.
3. **Correlations computed BOTH full-window AND ex-event-week** (strip each name's own catalyst weeks to isolate systematic/hedgeable co-movement from idiosyncratic alpha).
4. Out-of-band: the hedge profile is ALWAYS pulled alongside retrieval for a ticker, but NEVER scored into the KNN vote.

## Wave 1 — Correlation engine + explicit hedge-profiles + out-of-band retrieval

### 1a. Correlation engine (new module `quant/correlations.py` or extend `quant/pairs.py`)
- Pure functions over cached weekly `price_bar` returns (Friday-anchored). Compute:
  - pairwise weekly log-return correlation within `disease_area` and `mechanism_class` groups;
  - each name's corr / beta / R² to XBI (the sector index);
  - BOTH full-window AND ex-event-week variants (strip weeks overlapping any of the ticker's catalyst `event_date`s ± a window).
- Reuse `quant/pairs.py::correlation_beta` for the numpy math; `store.bars_asof`/`price_bar` for series; `weekly` return helper.
- Explicit verdict banding (module-level params, no magic literals): e.g. strong ≥0.6 / moderate 0.4–0.6 / weak 0.2–0.4 / none <0.2 — bands in a params dict, missing key raises.
- **Data trap (confirmed live):** XBI in `price_bar` is Monday-anchored (mixed rows) vs the Friday universe. Re-pull XBI Friday-anchored via `get_weekly_bars` (one free call) and upsert clean, OR intersect on common `week_end` before computing. The engine must guarantee week alignment.

### 1b. hedge_profile storage + reader (KB)
- `stamp_hedge_profile(conn, ticker, profile)` — mirror `playbook/store.py::stamp_axes`: `_get_or_create_company` → idempotent UPDATE of `attrs_json["hedge_profile"]`. NO migration (attrs_json is free JSON). content_sha-safe (company nodes aren't sha-gated) — MUST use the UPDATE writer, never the catalyst-record path.
- `hedge_profile(conn, ticker) -> dict|None` reader — mirror `kb.py::hedge_peers`.
- Profile shape (explicit): `{ "as_of", "xbi": {corr, beta, r2, verdict, window}, "peers": [{peer, disease_or_mech, corr_full, corr_ex_event, verdict}], "systematic_frac", "idiosyncratic_frac", "suggested_hedge": "xbi_overlay@beta X" | "sizing_only", "note" }`. Every relationship carries a verdict string.

### 1c. Out-of-band retrieval wiring (`desk/builder.py`)
- Right after `res = kb.analog_query_v2(...)` (builder.py:155) and `res["analogs"]` capture: attach `hp = kb.hedge_profile(conn, target)`; thread it into the `TradeProposal` (a new optional `hedge_profile` field) and/or `PortfolioContext` (the currently-empty `corr_to_open_positions` stub is the typed home). MUST NOT enter `_split_moves` / `methods` / `score` — it is context, not a ranking signal. Backward-compat: optional field, default None.

### 1d. Populate + recompute CLI (`scripts/build_hedge_profiles.py`)
- Enumerate universe tickers (from catalyst nodes), compute profiles via 1a, stamp via 1b. `--dry-run` prints the plan (frugality: only the XBI re-pull touches network; everything else is the cached price_bar). Recompute-on-demand tool the desk calls.

## Wave 2 — Portfolio-builder what-if engine

### 2a. `desk/portfolio_builder.py` (new) — the stateless engine
- Signature (pure, no I/O beyond reading passed-in data): `build_portfolio(positions, assumptions) -> PortfolioOutcome`.
  - `positions`: `[{ticker, side, size_pct, hedge?}]`.
  - `assumptions` (EXPLICIT, agent-supplied — reuse the assumptions_provider concept): per-name `expected_move`, `p_positive`, scenario branch probabilities; a correlation/beta source (default = stored hedge_profiles, overridable); a `sector_shock` magnitude; `periods_per_year`.
- Returns everything relevant for the week:
  - gross/net exposure (`quant/portfolio.py::exposure`), Herfindahl concentration (`concentration`);
  - correlation-adjusted portfolio vol/variance from a covariance built off the assumption betas/corrs (genuinely new glue);
  - aggregate expected return = Σ size·expected_move (same as `select_book`);
  - scenario/stress P&L: per-catalyst-branch via `quant/pairs.py::conditional_payoff`; a sector-shock scenario via XBI beta; worst-case / expected / best-case book P&L;
  - portfolio risk metrics via `quant/performance.py` over the scenario return series (Sharpe/Sortino/maxDD shaped like `BaselineDistribution`), + portfolio-level risk-of-ruin.
- **Stateless + iterative:** the agent calls it repeatedly with adjusted assumptions to stress-test. No hidden state, no hardcoded assumptions.
- Reuse ONLY existing primitives (exposure, concentration, conditional_payoff, performance.py, size_for_survival, select_book for optional construction). No new deps (quantstats/empyrical stay rejected).

### 2b. Agent tool wiring (`desk/tools.py`)
- Expose `build_portfolio` as an analyst MCP tool so the desk agents can "play with" portfolios (construct, stress, re-run). Structured output (pydantic `PortfolioOutcome`).

## Testing (both waves)
- TDD, tests-before-logic, all offline/in-memory (`:memory:` + seeded price_bar/catalyst fixtures; injected assumptions). Money-path coverage on the covariance/vol math and scenario P&L. No live network in code-task tests (the XBI re-pull is the one vetted main-dir data step). No new magic numbers (verdict bands + any multipliers in a params dict, missing-key-raises). No duplication (reuse the mapped primitives). Backward-compat: builder/TradeProposal/PortfolioContext optional additions only; existing suites green.

## Explicitly out of scope (v1)
- Populating `hedge_peer` graph edges (no genuine inverse peers exist — the profile blob tells the honest story; the -1 consumers stay empty).
- Wiring the portfolio engine into `run_layer_a`/live allocation (that's a later step once the engine is proven).
- Tail/crisis correlation window (ex-event-week is v1; tail-corr is a documented follow-up).
