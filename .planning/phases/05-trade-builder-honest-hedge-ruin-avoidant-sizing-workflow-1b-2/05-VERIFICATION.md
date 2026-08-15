---
phase: 05-trade-builder-honest-hedge-ruin-avoidant-sizing-workflow-1b-2
verified: 2026-08-15T08:07:15Z
status: passed
score: 7/7 must-have truths per plan verified (35+ truths across 7 plans), 12/12 requirements satisfied, 9/9 money-critical invariants confirmed
---

# Phase 5: Trade Builder / Honest Hedge / Ruin-Avoidant Sizing (Workflow-1b) Verification Report

**Phase Goal:** Turn the week's catalyst calls (Phase-4 DebateVerdicts) into ONE recommended portfolio — build each trade, honestly validate/select the hedge (or fall back to survival-sized single leg with estimated-move-driven adaptive SL/TP), size for survival, run the 3-way risk committee, and have the MD/PM promote or kill into a StrategyDossier. Stops at the dossier — NO live execution.
**Verified:** 2026-08-15T08:07:15Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (per-plan must_haves, cross-checked against source)

| # | Plan | Truth | Status | Evidence |
|---|------|-------|--------|----------|
| 1 | 05-01 | Fake idiosyncratic hedge unrepresentable at contract boundary | ✓ VERIFIED | `contracts/__init__.py:82-101` `Hedge._honest_coverage` raises unless `validated and payoff_direction==-1` |
| 2 | 05-01 | LABD (inverse_etf) can only be sector_beta | ✓ VERIFIED | same validator, explicit `instrument=="inverse_etf" and v=="idiosyncratic"` raise |
| 3 | 05-01 | put_option legal enum, unpromotable in v1 | ✓ VERIFIED | validator raises unconditionally when `instrument=="put_option"` |
| 4 | 05-01 | TradeProposal carries hedge/hold-through/sl_advisory/catalyst_id/direction/estimate_vetting | ✓ VERIFIED | `contracts/__init__.py:116-132` |
| 5 | 05-01 | RiskAssessment carries the Hedge OBJECT, not just a bool | ✓ VERIFIED | `contracts/__init__.py:148-149` `hedge: Hedge \| None` + `hedge_valid: bool` mirror |
| 6 | 05-02 | catalyst_move_estimate produces signed EV + separate up/down magnitudes, offline-capable, implied_move magnitude-only | ✓ VERIFIED | `quant/events.py:51-111`, `_branch_magnitude` raises w/o fallback |
| 7 | 05-02 | hold_vs_exit decides by expected-LOG-growth, not raw EV; tail-penalty case provably exits | ✓ VERIFIED | `quant/events.py:114-184`; test `test_hold_vs_exit_positive_ev_but_tail_favors_exit` at `tests/test_events.py:262` |
| 8 | 05-02 | adaptive_sl_tp_levels delegates to sl_tp_levels (one advisory gate) | ✓ VERIFIED | `quant/sizing.py:201-227` `return sl_tp_levels(...)` |
| 9 | 05-03 | kb.load_params returns highest-confidence fitted_params row or bootstrap default | ✓ VERIFIED | `kb.py:354-363` |
| 10 | 05-04 | size_for_survival: largest survivable size, NO return-target param | ✓ VERIFIED | `desk/risk.py:33-72`; test `test_no_return_target_parameter` introspects signature |
| 11 | 05-04 | Only -1 peers validated; conditional_payoff + cointegration + catalyst-clean all required; else None | ✓ VERIFIED | `desk/risk.py:75-129` `validate_hedge` |
| 12 | 05-04 | assess calls validate_hedge exactly once, threads onto hedge + hedge_valid | ✓ VERIFIED | `desk/risk.py:234-246`; test `test_validate_hedge_called_exactly_once` (tests/test_desk_risk.py:289) |
| 13 | 05-05 | enforce_estimate audits assumptions, never recomputes money numbers | ✓ VERIFIED | `desk/verifier.py:147+` two-stage structural→semantic, reuses `evidence.resolve`/`quote_supported` |
| 14 | 05-06 | Builder builds TradeProposal: candidate peer, entry, hold-vs-exit, advisory SL/TP | ✓ VERIFIED | `desk/builder.py:91-177` |
| 15 | 05-06 | Estimated down-move (not blanket -70%) sizes the leg | ✓ VERIFIED | `desk/builder.py:118` `size_for_survival(p_loss=1.0-p_positive, gap=down_move)` |
| 16 | 05-06 | Hold-vs-exit via quant tool, never raw EV; builder never does arithmetic | ✓ VERIFIED | `desk/builder.py:122-128`; `! grep -qE "est\.value\s*>" builder.py` confirmed clean |
| 17 | 05-06 | SL advisory whenever holds_through_catalyst | ✓ VERIFIED | `desk/builder.py:132-134` |
| 18 | 05-06 | Rejected estimate blocks finalize | ✓ VERIFIED | `desk/builder.py:145-152` `except EstimateRejectedError: return None` |
| 19 | 05-06 | Every builder threshold param-driven, missing key raises | ✓ VERIFIED | `desk/builder.py:102-103` `builder_p = params["builder"]` (dict access, no `.get`) |
| 20 | 05-07 | run_portfolio: zero-trade week is valid success | ✓ VERIFIED | `desk/orchestrator.py:85`, test `test_run_portfolio_zero_trade_week_all_pass_returns_empty` |
| 21 | 05-07 | Reconciliation: risk.recommended_size_pct + risk.hedge overwrite proposal BEFORE select_book (BLOCKER-1) | ✓ VERIFIED | `desk/orchestrator.py:100-104` `model_copy(update={...})`; test `test_run_portfolio_reconciles_risk_size_not_builder_preliminary` asserts `size_pct == 0.02` and `!= 0.005` |
| 22 | 05-07 | select_book aggregates to ~1% by selection only, never resizes above survival | ✓ VERIFIED | `desk/portfolio.py:44-77` (append-only, no size mutation); test `test_select_book_never_resizes_above_survival_size` |
| 23 | 05-07 | Memo + pre-mortem authored separately, before PM decision (author ≠ approver) | ✓ VERIFIED | `desk/portfolio.py:169-208`; test `test_memo_and_premortem_authored_separately_from_pm` asserts call order `[PositionMemo, PreMortem, PMDecision]` |
| 24 | 05-07 | Dossier states residual net-long + which risk covered, derived from reconciled hedge | ✓ VERIFIED | `desk/portfolio.py:109-119` `_which_risk_covered` + `desk/orchestrator.py` reconciliation feeds it |

**Score:** 24/24 sampled truths verified across all 7 plans (all plan-level must_haves confirmed against source, not SUMMARY prose).

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/catalyst_trader/contracts/__init__.py` | Hedge, EstimateVetting + extended models | ✓ VERIFIED | present, substantive, wired (imported by risk/builder/portfolio/orchestrator) |
| `src/catalyst_trader/quant/events.py` | catalyst_move_estimate, expected_log_growth, hold_vs_exit | ✓ VERIFIED | present, re-exported, wired into builder.py |
| `src/catalyst_trader/quant/sizing.py` | adaptive_sl_tp_levels (extended) | ✓ VERIFIED | delegates to sl_tp_levels, wired into builder.py |
| `src/catalyst_trader/kb.py` | load_params seam | ✓ VERIFIED | wired into builder.py |
| `src/catalyst_trader/desk/verifier.py` | enforce_estimate | ✓ VERIFIED | wired into builder.py |
| `src/catalyst_trader/desk/risk.py` | size_for_survival, validate_hedge, assess | ✓ VERIFIED | wired into orchestrator.py |
| `src/catalyst_trader/desk/builder.py` | build() | ✓ VERIFIED | wired into orchestrator.py |
| `src/catalyst_trader/desk/portfolio.py` | select_book, author_memo, author_pre_mortem, pm_decide | ✓ VERIFIED | wired into orchestrator.py |
| `src/catalyst_trader/desk/orchestrator.py` | run_portfolio | ✓ VERIFIED | present, composes builder→risk→reconcile→select_book→PM |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `adaptive_sl_tp_levels` | `sl_tp_levels` | delegation | ✓ WIRED | `return sl_tp_levels(entry, sl_pct, tp_pct, holds_through_catalyst)` |
| `hold_vs_exit` | `expected_log_growth` | compares g_hold vs g_exit at same f | ✓ WIRED | `desk/events.py:165-166` |
| `builder.build` | `kb.load_params → catalyst_move_estimate → adaptive_sl_tp_levels` | param-driven construction | ✓ WIRED | `desk/builder.py:102-133` |
| `builder.build` | `risk.size_for_survival(gap=down_move)` | leg sizing on estimated down-move | ✓ WIRED | `desk/builder.py:118` |
| `builder.build` | `verifier.enforce_estimate` | vet before use | ✓ WIRED | `desk/builder.py:145-152` |
| `risk.assess` | `desk.runtime.run_structured` | 3-way fan-out + synthesis | ✓ WIRED | `desk/risk.py:222-239` |
| `RiskAssessment.hedge` | `validate_hedge result` | single call, threaded | ✓ WIRED | `desk/risk.py:234-246` |
| `run_portfolio` reconciliation | `proposal.size_pct/hedge = risk.recommended_size_pct/risk.hedge` | model_copy BEFORE select_book | ✓ WIRED | `desk/orchestrator.py:100-113` |
| `select_book` | `quant.exposure + quant.concentration` | heat-cap/gross math | ✓ WIRED | `desk/portfolio.py:24,71,195` |
| `StrategyDossier.residual_net_long` | `quant.exposure(promoted_weights).detail.net` | HEDGE-05 disclosure | ✓ WIRED | `desk/portfolio.py:195` |

### Money-Critical Invariant Confirmation (explicit checks requested)

| # | Invariant | Result | Evidence |
| - | --------- | ------ | -------- |
| 1 | `size_for_survival` has NO return-target parameter | ✓ CONFIRMED | Signature `(p_loss, gap, ruin_cap, per_event_cap, n_trades)` — no target/return/weekly/one_pct. Test-enforced via `inspect.signature` introspection (`tests/test_desk_risk.py:26-31`). |
| 2 | `Hedge.covers` makes fake idiosyncratic hedge unrepresentable; `put_option` legal-but-unpromotable; inverse_etf sector_beta-only | ✓ CONFIRMED | `contracts/__init__.py:82-101`, all 3 sub-rules present and each has a dedicated raising test in `tests/test_contracts.py`. |
| 3 | `catalyst_move_estimate` + `adaptive_sl_tp_levels` + builder read params and RAISE on missing key; estimator works offline | ✓ CONFIRMED | `params["estimator"]`, `params["sl_tp"]`, `params["builder"]` — plain dict indexing (no `.get`) in `events.py`, `sizing.py`, `builder.py`. `_branch_magnitude` raises when a branch is empty and no `implied_move` supplied — confirms offline-first. |
| 4 | Hold-vs-exit uses `hold_vs_exit`/expected-log-growth, NOT raw EV; `builder.py` clean of `est.value >`; adversarial test exists and passes | ✓ CONFIRMED | `grep -qE "est\.value\s*>" src/catalyst_trader/desk/builder.py` → no match (exit 1, confirming absence). `test_hold_vs_exit_positive_ev_but_tail_favors_exit` exists at `tests/test_events.py:262` and is part of the green 649-test run. |
| 5 | `enforce_estimate` blocks finalize on rejection, reuses verifier machinery | ✓ CONFIRMED | `desk/verifier.py:147+`; `builder.py:145-152` catches `EstimateRejectedError` and returns `None` (never finalizes); reuses `evidence.resolve`/`quote_supported` (verified via grep — same functions used in both `enforce` and `enforce_estimate`). |
| 6 | `run_portfolio` reconciles `risk.recommended_size_pct` + `risk.hedge` onto promoted TradeProposal BEFORE `select_book` (Blocker-1); test asserts promoted size == committee size (≠ builder size) | ✓ CONFIRMED | `desk/orchestrator.py:100-104` (`model_copy(update=...)` runs before `select_book` call at line 113). Test `test_run_portfolio_reconciles_risk_size_not_builder_preliminary` (`tests/test_desk_portfolio.py:281-291`) asserts `promoted[0].trade.size_pct == 0.02` (committee) and `!= 0.005` (builder preliminary). |
| 7 | `select_book` aggregates to ~1% by selection only, never resizes a leg above survival; zero-trade weeks valid | ✓ CONFIRMED | `desk/portfolio.py:44-77` — candidates are only appended or dropped, no `.size_pct =` mutation exists anywhere in the function body. Dedicated test `test_select_book_never_resizes_above_survival_size` + `test_select_book_zero_trade_when_nothing_clears_budget` + `test_select_book_empty_candidates_is_zero_trade`. |
| 8 | Author of the memo ≠ approver (OPS-01/02) | ✓ CONFIRMED | `author_memo`/`author_pre_mortem` are independent `run_structured` calls preceding `pm_decide`'s own call. Test `test_memo_and_premortem_authored_separately_from_pm` asserts exact call-order `[PositionMemo, PreMortem, PMDecision]` and that both author calls index-precede the PM call. |
| 9 | Zero live API calls in the pytest suite; `.venv/bin/python -m pytest -q` green (649 expected) | ✓ CONFIRMED | `.venv/bin/python -m pytest -q` → **649 passed, 2 warnings** (unrelated statsmodels ComplexWarning in `test_pairs.py`, pre-existing Phase-3 code, not Phase-5). `claude_agent_sdk` is imported ONLY in `desk/runtime.py` (the one seam) and `desk/tools.py` (MCP tool registration, not invoked in these tests); all 8 desk test files (`test_desk_analysts`, `test_desk_builder`, `test_desk_estimate_gate`, `test_desk_orchestrator`, `test_desk_debate`, `test_desk_risk`, `test_desk_portfolio`, `test_desk_verifier`) monkeypatch `run_structured` directly on the module under test. |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| PORT-01 | 05-07 | Weekly catalyst calls → one recommended portfolio | ✓ SATISFIED | `run_portfolio` composes builder→risk→reconcile→select_book→PM over `verdicts` |
| PORT-02 | 05-02,03,05,06 | Trade Builder: hedge peer, entry, hold-vs-exit, SL/TP | ✓ SATISFIED | `desk/builder.py::build` |
| PORT-03 | 05-02,03,04 | 3-way Risk Committee sizes for survival; 1% is a measured outcome | ✓ SATISFIED | `desk/risk.py::size_for_survival` + `assess`; no return-target param |
| PORT-04 | 05-07 | MD/PM evaluates fit (concentration/correlation/budget), promotes/kills | ✓ SATISFIED | `select_book` + `pm_decide` |
| PORT-05 | 05-01,07 | Emits StrategyDossier | ✓ SATISFIED | `pm_decide` returns `StrategyDossier` |
| HEDGE-01 | 05-01,04,06 | Hedge is inverse-payoff peer, not merely correlated | ✓ SATISFIED | `-1`-only filters in `builder._candidate_peer` and `risk.validate_hedge` |
| HEDGE-02 | 05-04 | Per-catalyst conditional payoff re-analysis | ✓ SATISFIED | `validate_hedge` calls `conditional_payoff` on caller-supplied analog gaps |
| HEDGE-03 | 05-04 | Peer catalyst-clean over hold window | ✓ SATISFIED | `validate_hedge` filters `store.tradeable_catalysts` by peer+date window |
| HEDGE-04 | 05-01,04,06 | No-valid-peer fallback: size-tiny/exit, never fake hedge | ✓ SATISFIED | `Hedge.covers` boundary + `validate_hedge` returns `None` + builder `min_tradeable_size` floor |
| HEDGE-05 | 05-01,07 | Dossier states residual net-long + which risk covered | ✓ SATISFIED | `StrategyDossier.residual_net_long` / `which_risk_covered`, computed in `pm_decide` |
| OPS-01 | 05-01,05,07 | Position memo w/ kill criteria, authorship separated from approval | ✓ SATISFIED | `author_memo` precedes `pm_decide`, test-enforced ordering |
| OPS-02 | 05-01,07 | Pre-mortem before promotion | ✓ SATISFIED | `author_pre_mortem` precedes `pm_decide`, test-enforced ordering |

No orphaned requirements — REQUIREMENTS.md's Phase 5 row set (`PORT-01..05`, `HEDGE-01..05`, `OPS-01/02`) exactly matches the union of `requirements:` fields across the 7 plans; all rows marked `[x]` Complete and confirmed by source-level evidence above (not just REQUIREMENTS.md's own checkbox).

### Anti-Patterns Found

None. Scanned all 9 phase-touched source files (`contracts/__init__.py`, `desk/risk.py`, `desk/builder.py`, `desk/portfolio.py`, `desk/orchestrator.py`, `desk/verifier.py`, `quant/events.py`, `quant/sizing.py`, `kb.py`) for `TODO|FIXME|XXX|HACK|PLACEHOLDER|not implemented|coming soon` — zero matches. No `return null`/empty-stub patterns found in the money paths; all `.get(..., default)` calls checked are on non-money-critical fields (params access is uniformly plain-dict indexing, which is the intended "raise on missing key" behavior).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full suite green, zero live API | `.venv/bin/python -m pytest -q` | 649 passed, 2 warnings (pre-existing statsmodels ComplexWarning, unrelated to Phase 5) | ✓ PASS |
| Phase-5 suite subset green | `.venv/bin/python -m pytest tests/test_desk_risk.py tests/test_desk_builder.py tests/test_desk_portfolio.py tests/test_desk_estimate_gate.py tests/test_contracts.py tests/test_events.py tests/test_sizing.py tests/test_kb_params.py -q` | 225 passed | ✓ PASS |
| No raw-EV hold branch in builder | `! grep -qE "est\.value\s*>" src/catalyst_trader/desk/builder.py` | no match | ✓ PASS |
| No return-target literal in sizing signature | `inspect.signature` test | asserted in suite | ✓ PASS |

### Human Verification Required

None. All must-haves and invariants are structurally enforced (pydantic boundary validators) and test-covered with adversarial cases (tail-penalty hold-vs-exit, fake-hedge rejection, reconciliation-overwrite, author-order). Phase-5 is deterministic/offline by design — no UI, no live external calls, nothing requiring human judgment to verify.

### Gaps Summary

None. All 24 sampled must-have truths across the 7 plans verified against actual source code (not SUMMARY prose); all 12 requirement IDs satisfied with concrete evidence; all 9 explicitly-requested money-critical invariants confirmed present and test-enforced; full 649-test suite green with zero live API calls in the desk seam.

---

_Verified: 2026-08-15T08:07:15Z_
_Verifier: Claude (gsd-verifier)_
