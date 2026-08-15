---
phase: 07-verifier-guardrails-backtest-harness
plan: 04
subsystem: backtest
tags: [backtest, layer-a, no-llm, base-rate-direction-proxy, blocker-2, survival-sizing, gap-open-fill, baseline-distribution, hedge-effectiveness, offline]

# Dependency graph
requires:
  - phase: 07-verifier-guardrails-backtest-harness
    provides: "07-01 win_rate/avg_win_loss/sharpe/sortino/max_drawdown/hedge_effectiveness; 07-02 build_event_set (last_verified_at-filtered) + fill_price (gap-open) + effective_asof + seed_history"
  - phase: 06.5-weekly-strategy-correction
    provides: "quant/weekly.py thesis_scan/classify_drop/_match_trigger/weekly_base_rate; desk/weekly.py L116-119 statistical-leg derivation (mirrored); desk/risk.py size_for_survival/validate_hedge; desk/portfolio.py select_book/Candidate (defensive_book)"
provides:
  - "backtest/engine.py::run_layer_a — the deterministic weekly mechanical backtest (NO LLM) -> (list[BacktestResult], BaselineDistribution)"
  - "the named swappable direction_proxy registry (DIRECTION_PROXIES / resolve_direction_proxy), default base_rate — the catalyst-leg P(positive) COMPUTED via classify_drop->_match_trigger->weekly_base_rate (BLOCKER-2 closed)"
  - "baseline_distribution — the honest baseline (win rate / avg win-loss / Sharpe / Sortino / max-DD / hedge-effectiveness) the go/no-go gate (07-05) consumes"
  - "frozen extra=forbid contracts BacktestResult / LegOutcome / BaselineDistribution"
affects: [07-05, go-no-go-gate, backtest-harness]

# Tech tracking
tech-stack:
  added: []  # reuses the shipped deterministic tools + 07-01/07-02 modules; NO new dependency
  patterns:
    - "Layer A RE-EXPRESSES the weekly cadence deterministically — it never imports or calls the LLM desk (grep-gate returns nothing + a monkeypatch-to-raise regression test); every money number comes from the shipped tools, none re-derived"
    - "The catalyst-leg direction is a base-rate P(positive) proxy that COMPUTES its inputs (classify_drop -> _match_trigger -> weekly_base_rate) rather than reading trigger/drop_class/p off the null-bearing catalyst thesis row (BLOCKER-2); exposed as a named swappable knob, never a coin-flip/None fallback"
    - "Catalyst legs are sourced from the 07-02 point-in-time (last_verified_at<=as_of) event set, NOT thesis_scan's unguarded _catalyst_in_hold_window -> engine-level verification look-ahead is impossible"
    - "quant.weekly is referenced through the module (qw.classify_drop / qw.weekly_base_rate) so the reuse/computed-direction tests can monkeypatch the shipped tools and prove Layer A used them"

key-files:
  created:
    - src/catalyst_trader/backtest/engine.py
    - tests/test_backtest_engine.py
  modified: []

key-decisions:
  - "run_layer_a is SYNC (deterministic, no LLM) and returns (results, baseline_distribution(results)) so callers get both the per-leg audit trail and the summary the gate consumes"
  - "base_rate proxy returns (None, None) — an honest SKIP — when the recent move matches no trigger cell; it is never a 0.5/None coin-flip default. long_runup is the ('long', 0.5) beta-bet comparison knob only"
  - "catalyst-leg sizing expected_move = the base-rate mean_next (one extra deterministic read via _base_rate_ev), falling back to target_weekly when no cell exists so a leg is never sized to the tiny FLOOR"
  - "the defensive book is INLINED (not imported from desk.weekly) so the NO-LLM Layer A module never pulls in the agentic orchestrator import chain"
  - "Sharpe/Sortino run on the SIZE-WEIGHTED compounded weekly equity at an explicit periods_per_year=52 (freq footgun cured); they return None when undefined (too few weeks / no downside); max-DD on the same weekly equity; win-rate/avg-win-loss over every leg's realized return; hedge-effectiveness over the hedged pairs; empty results RAISE"

patterns-established:
  - "Layer A is the trustworthy baseline (the honest number, before the biased-optimistic Layer B) — the base-rate ASSUMPTIONS are what it measures, not any LLM edge"

requirements-completed: [BACK-02]

# Metrics
duration: 16min
completed: 2026-08-15
---

# Phase 7 Plan 04: Layer A Mechanical Backtest Engine Summary

**The trustworthy, fully-offline, NO-LLM backtest of the corrected weekly strategy — it re-expresses the shipped cadence deterministically over the 07-02 point-in-time event set, computes each catalyst leg's direction as a base-rate P(positive) (BLOCKER-2 closed: never off the null catalyst row), fills held-through binaries at the pessimistic gap-open, and rolls the per-leg outcomes into a baseline distribution (win rate / avg win-loss / Sharpe / Sortino / max-DD / hedge-effectiveness) with zero new dependencies.**

## Performance
- **Duration:** ~16 min
- **Started:** 2026-08-15T23:41:04Z
- **Completed:** 2026-08-15T23:57:38Z
- **Tasks:** 3
- **Files created:** 2

## Accomplishments
- **Contracts + the direction_proxy knob (Task 1)** — frozen `extra=forbid` `LegOutcome` / `BacktestResult` / `BaselineDistribution`; a `DIRECTION_PROXIES` registry (`base_rate` default + `long_runup` comparison) with `resolve_direction_proxy`. `base_rate` COMPUTES P(positive) via `classify_drop -> _match_trigger -> weekly_base_rate` — it never reads trigger/drop_class/p off the catalyst thesis row (which carries `trigger=None/p=None` and no `drop_class`), and never returns a 0.5/None coin-flip default.
- **`run_layer_a` — the deterministic weekly loop (Task 2)** — iterates `build_event_set`; per week: catalyst legs from the last_verified_at-filtered event record (direction via the proxy, target-within-survival-cap `size_for_survival`, honest `validate_hedge` -> single-leg fallback), the statistical sleeve mirrored from `thesis_scan` (top-k eligible, single-leg, one-week exit), a defensive fallback so no week is zero-trade, `select_book` aggregation, entry pre-event -> `fill_price` pessimistic gap-open exit. Provably NO-LLM (grep-clean + a monkeypatch-`run_desk`/`run_weekly`-to-raise test still completes).
- **`baseline_distribution` (Task 3)** — trade-level win-rate/avg-win-loss over every leg; Sharpe/Sortino/max-DD over the size-weighted compounded weekly equity at explicit `periods_per_year=52`; hedge-effectiveness over the hedged pairs; empty results raise (no silent zero baseline). `run_layer_a` returns `(results, distribution)`.

## Task Commits
Each task committed atomically on `main` (TDD RED confirmed before each GREEN):
1. **Task 1: contracts + swappable direction_proxy knob** — `0351ccc` (feat)
2. **Task 2: run_layer_a — deterministic weekly mechanical loop (NO LLM)** — `932fcb5` (feat)
3. **Task 3: baseline distribution assembly (metrics + hedge-effectiveness)** — `d7f042c` (feat)

## Files Created
- `src/catalyst_trader/backtest/engine.py` (329 lines) — `run_layer_a` + `baseline_distribution` + the `DIRECTION_PROXIES` registry + the three frozen contracts
- `tests/test_backtest_engine.py` — 14 tests: contract-forbids-extra, the four direction-proxy tests, the six loop tests (never-calls-run_desk, no-zero-trade, gap-open, reuses-tools, computed-base-rate, verified-after-as_of), and the four baseline tests

## Decisions Made
- `run_layer_a` is sync and returns `(results, distribution)`; base_rate returns an honest `(None, None)` skip when no trigger cell matches (never a coin-flip); defensive book inlined to keep Layer A free of the LLM orchestrator import; Sharpe/Sortino/max-DD on the size-weighted weekly equity at explicit `periods_per_year=52`.

## Deviations from Plan
None material. Three clarifications within the plan's stated intent:
- **[Rule 3 - blocking] `quant.weekly` referenced through the module (`qw.classify_drop` / `qw.weekly_base_rate`), not direct name imports.** The plan's reuse/computed-direction tests monkeypatch `quant.weekly.weekly_base_rate`; a direct `from ..quant.weekly import weekly_base_rate` would bind a name the patch can't reach. Module-qualified calls make the monkeypatch (and the "reuses the shipped tool" proof) actually bite. Files: `engine.py`. Folded into commits `0351ccc`/`932fcb5`.
- **catalyst-leg sizing `expected_move`** uses one extra deterministic `_base_rate_ev` read (base-rate `mean_next`, target fallback) — the proxy's uniform `(side, p)` contract doesn't carry `mean_next`, so the EV for `size_for_survival` is read alongside it. Negligible offline; documented with a `# ponytail:` note.
- **defensive legs park flat (`realized_ret=0.0`)** — the cash-like anchor's honest one-week outcome; mirrors `build_weekly_leg_dossier`'s treatment. Documented in `_cash_leg`.

## Issues Encountered
- Initial test used a `from .synth_history` relative import which fails outside a package; switched to `from tests.synth_history import ...` (the established pattern in the other backtest suites).

## User Setup Required
None — fully offline, zero new dependencies, zero external configuration.

## Next Phase Readiness
- Layer A's `(results, BaselineDistribution)` is the trustworthy baseline the go/no-go gate (07-05) consumes, and the `long_runup` knob gives it the beta-bet comparison. Real ~1yr earnings/PDUFA calendar ingestion into the store remains a documented carry-forward (tests run on the synthetic fixture).
- Full suite green: **906 passed** (892 prior + 14 new). 2 pre-existing statsmodels ComplexWarnings (out of scope).

---
*Phase: 07-verifier-guardrails-backtest-harness*
*Completed: 2026-08-15*

## Self-Check: PASSED

Both created files exist on disk; all three task commits (`0351ccc`, `932fcb5`, `d7f042c`) are in history. `grep run_desk|run_weekly engine.py` returns nothing (NO-LLM invariant); the computed-direction (`classify_drop`/`_match_trigger`/`weekly_base_rate`) reuse is present. Full suite: 906 passed.
