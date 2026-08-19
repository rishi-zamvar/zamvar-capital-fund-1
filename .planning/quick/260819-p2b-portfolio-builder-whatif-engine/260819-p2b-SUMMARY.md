---
phase: quick-260819-p2b
plan: 01
subsystem: desk / portfolio what-if engine
tags: [portfolio-builder, covariance, scenario-pnl, risk-of-ruin, analyst-tool, wave-2]
requires: [quant.exposure, quant.concentration, quant.conditional_payoff, quant.sharpe, quant.sortino, quant.max_drawdown, quant.risk_of_ruin, kb.hedge_profile]
provides: [desk.portfolio_builder.build_portfolio, desk.portfolio_builder.PortfolioOutcome, build_portfolio analyst tool]
affects: [desk/tools.py analyst tool surface]
tech-stack:
  added: []
  patterns: [stateless pure function, frozen extra-forbid pydantic contract, PARAMS-no-magic-literals, assumption-overridable corr source, None-when-undefined discipline]
key-files:
  created:
    - src/catalyst_trader/desk/portfolio_builder.py
    - tests/test_portfolio_builder.py
  modified:
    - src/catalyst_trader/desk/tools.py
    - tests/test_desk_tools.py
decisions:
  - "Portfolio-ruin maps size_pct=1.0, gap=|worst_case| (whole book is the stake) so the DP integrates the actual worst book-loss fraction — no gross double-count."
  - "O(2^n) joint enumeration capped at PARAMS['max_scenario_names']=8; beyond it degrades to an exact-by-linearity marginal roll-up with a visible truncated flag."
  - "Static metrics (exposure/concentration/vol/expected return) are over the primary position tickers; a hedged position's peer leg enters only the scenario P&L via conditional_payoff."
metrics:
  tasks: 3
  new_tests: 31
  full_suite: "1640 passed, 1 xfail"
  duration: "~1 session"
  completed: 2026-08-19
---

# Quick 260819-p2b: Portfolio-Builder What-If Engine (Wave 2) Summary

Stateless pure function `build_portfolio(positions, assumptions) -> PortfolioOutcome` that computes a full weekly-book what-if — signed gross/net exposure, Herfindahl concentration, aggregate expected return, correlation-adjusted portfolio vol/variance, per-position + book scenario P&L, an XBI sector-shock P&L, Sharpe/Sortino/maxDD over the scenario cross-section, and a portfolio-level risk-of-ruin — reusing the already-shipped quant primitives as pure glue, plus one `build_portfolio` analyst tool. No DB, no network, no hidden state; the desk iterates by re-calling with adjusted assumptions.

## What shipped

- **`desk/portfolio_builder.py`** — `PortfolioOutcome` (frozen, `extra="forbid"`, all fields incl `scenarios`/`risk` defined in Task 1 so Task 2 only populated), `PARAMS` (no magic literals; direct-subscript missing-key-raises), and the engine.
  - `_resolve_corr_source` — the correlation source is an ASSUMPTION: a `dict {ticker: profile}` OR a `callable ticker->profile|None`; absent → everything idiosyncratic.
  - `_covariance` — `σ_p² = ΣΣ wᵢwⱼσᵢσⱼρᵢⱼ`; off-diagonal precedence **mutual peer corr → single-factor XBI-implied `ρᵢⱼ=ρᵢ,xbi·ρⱼ,xbi` → 0**, ρ clamped to [-1,1], each pair's source recorded in `covariance_detail.rho_source`.
  - `_position_branches` / `_book_scenarios` / `_sector_shock_pnl` / `_risk_block` — scenario roll-up and risk, all delegating to the mapped primitives.
- **`desk/tools.py`** — `@tool("build_portfolio", …)` wired into `build_quant_tools`; `PortfolioOutcome.model_dump()` returned via `_content` (plain payload — a PortfolioOutcome is not a `ToolResult`, so it does NOT go through `_result_content`). Default `corr_source = lambda t: kb.hedge_profile(conn, t)` — the ONLY place `conn` binds; the engine itself stays pure.

## Tests: 31 new (all RED-first)

- `tests/test_portfolio_builder.py` — **28** (17 Task 1 + 11 Task 2): covariance money-path (single / independent / high-corr two-longs / long-short diversification / precedence / clamp), dict-vs-callable equivalence, missing-profile idiosyncratic, vol-proxy labels, frozen contract, empty/non-finite raises; per-position branches, asymmetric down-move, hedged plumbing, sector shock, joint roll-up, risk-metric equality + None-when-undefined, ruin magnitude, over-cap truncation, all-hedged book.
- `tests/test_desk_tools.py` — **3**: tool-surface membership, structured payload, offline stored-hedge-profile default (unstamped ticker degrades to idiosyncratic, no crash).
- Full suite: **1640 passed, 1 xfail** (pre-existing).

## Plan-check concerns — landed in the RED tests

**CONCERN 1 (risk_of_ruin economic correctness).** `worst_case = Σ signed_weightᵢ·moveᵢ` is already a bankroll-fraction book loss. The naive `size_pct=gross, gap=|worst_case|` double-counts exposure. Fixed: `size_pct=1.0` (whole book is the stake for a portfolio-level ruin calc), `gap=clamp(|worst_case|,(0,1])`, so `size_pct·gap == |worst_case|`. `p_loss = Σ prob of negative-return branches`. Labelled in `risk.ruin_mapping_note`.
  - **Magnitude proof** (`test_risk_of_ruin_loss_magnitude_equals_worst_case`): a gross-1.2 book asserts `risk.ruin_loss_fraction == |worst_case|` **and** `!= 1.2·|worst_case|` — the ruin DP integrates the true loss, not the gross-inflated one — and equals `quant.risk_of_ruin(p_loss, 1.0, gap=|worst_case|)`.

**CONCERN 2 (O(2ⁿ) cap).** Beyond `PARAMS['max_scenario_names']` names the engine does NOT enumerate 2ⁿ joint branches; it falls back to a marginal/independent roll-up (worst/best/expected are exact by linearity; per-name expected is the returns proxy) and sets `scenarios['truncated']=True` with a `note` naming the cap.
  - `test_over_cap_book_truncates_gracefully_without_dropping_positions`: a book exceeding the cap sets the flag, returns finite metrics, drops NO positions, does not hang.

**CONCERN 3 (short-side sign).** `test_expected_return_applies_side_sign` + `test_long_short_expected_return_sums_signed` pin the side sign applied to `size·expected_move`, locking the generalization beyond `select_book`'s longs-only convention.

**CONCERN 4 (hedged plumbing).** `test_hedged_position_worst_matches_conditional_payoff` pins that a hedged position's worst branch equals `quant.conditional_payoff(...).value` — `w_peer` + peer up/down moves come from the position's `hedge` + `assumptions[peer]`, no re-derived 2×2.

## Honesty labels in the outcome

- `covariance_detail.vol_proxy_names` — which names used the `σ=|expected_move|` proxy vs a supplied `sigma`.
- `covariance_detail.rho_source` — per off-diagonal pair: `"peer"` | `"xbi_implied"` | `"zero"`.
- `scenarios.sector_shock_missing_beta` — names with no β (contributed 0 to the shock).
- `scenarios.truncated` + `note` — when the joint enumeration degraded.
- `risk.ruin_mapping_note` + `ruin_size_pct`/`ruin_gap`/`ruin_loss_fraction` — the modelled portfolio-ruin mapping.
- `assumptions_echo` — verbatim assumptions snapshot (reproducibility, like `ToolResult.inputs`).

## Backward-compat proof

Purely additive: one new module, one new contract, one new tool appended to `build_quant_tools`'s returned list. No existing signature changed. Full suite **1640 passed** (all prior `test_desk_tools.py` tool-surface + citation assertions still green). Reuse verified: `grep -nE "def (sharpe|sortino|max_drawdown|risk_of_ruin|concentration|exposure|conditional_payoff)" src/catalyst_trader/desk/portfolio_builder.py` returns nothing — no primitive re-implemented.

## Worked example (the shape the desk sees)

A 2-position book: **AAA long 0.6**, **BBB short 0.4**; AAA/BBB mutual peer corr 0.7, XBI betas 1.2 / 0.8; AAA `expected_move 0.20 p 0.60`, BBB `expected_move 0.10 p 0.55`; `sector_shock -0.10`, `periods_per_year 52`.

```json
{
  "gross_exposure": 1.0, "net_exposure": 0.20, "concentration": 0.52, "max_weight": 0.6,
  "expected_return": 0.08,
  "portfolio_variance": 0.00928, "portfolio_vol": 0.0963,
  "covariance_detail": {
    "sigma_by_name": {"AAA": 0.2, "BBB": 0.1},
    "vol_proxy_names": ["AAA", "BBB"],
    "rho_source": {"AAA-BBB": "peer"}
  },
  "scenarios": {
    "worst_case": -0.16, "expected_case": 0.02, "best_case": 0.16,
    "sector_shock_pnl": -0.04, "sector_shock_missing_beta": [],
    "truncated": false, "n_branches": 4,
    "per_position": {"AAA": [{"return": 0.12, "prob": 0.6}, {"return": -0.12, "prob": 0.4}],
                     "BBB": [{"return": -0.04, "prob": 0.55}, {"return": 0.04, "prob": 0.45}]}
  },
  "risk": {
    "sharpe": 0.0, "sortino": 0.0, "max_drawdown": -0.2272,
    "risk_of_ruin": 0.559, "ruin_p_loss": 0.4,
    "ruin_size_pct": 1.0, "ruin_gap": 0.16, "ruin_loss_fraction": 0.16,
    "ruin_mapping_note": "portfolio-ruin assumption: size_pct=1 (whole book is the stake), gap=|worst_case| …"
  }
}
```

Note the C1 fix in the wild: `ruin_loss_fraction == 0.16 == |worst_case|`, and the peer corr (0.7) on a long+short book pulls `portfolio_variance` **below** the independence level via the negative cross term.

## Deviations from plan

**Execution-ordering note (not a scope change):** the engine is cohesive glue, so the full module was drafted at once, then split back to genuine RED-first per-task commits — Task 1 shipped the contract + static metrics with `scenarios={}`/`risk={}` placeholders (17 RED tests), Task 2's 11 scenario/risk tests were confirmed RED against those placeholders before the scenario logic was restored. Per-task commits are atomic and each was RED-before-green. No functional deviation from the plan's interfaces.

## Commits

- `fa78da9` feat(quick-260819-p2b): PortfolioOutcome contract + static what-if metrics
- `7dc1626` feat(quick-260819-p2b): scenario/stress P&L + portfolio risk in the engine
- `8d12e32` feat(quick-260819-p2b): register build_portfolio as an analyst tool
