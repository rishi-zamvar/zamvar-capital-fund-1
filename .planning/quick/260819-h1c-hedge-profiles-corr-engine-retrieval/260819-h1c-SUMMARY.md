---
phase: quick-260819-h1c
plan: 01
subsystem: quant/kb/desk
tags: [correlations, hedge-profiles, out-of-band-retrieval, week-alignment]
requires:
  - quant/pairs.py::correlation_beta
  - quant/weekly.py::_weekly_returns
  - kb.py::_get_or_create_company
  - playbook/store.py::stamp_axes (pattern)
  - providers/prices.py::get_weekly_bars
provides:
  - quant/correlations.py (compute_hedge_profile / compute_xbi_stats / compute_pair_corr)
  - kb.stamp_hedge_profile / kb.hedge_profile
  - contracts.TradeProposal.hedge_profile (optional)
  - scripts/build_hedge_profiles.py (--dry-run / --self-check / live)
affects:
  - desk/builder.py (out-of-band attach)
key-files:
  created:
    - src/catalyst_trader/quant/correlations.py
    - tests/test_correlations.py
    - tests/test_hedge_profile_store.py
    - tests/test_desk_builder_hedge_profile.py
    - scripts/build_hedge_profiles.py
  modified:
    - src/catalyst_trader/kb.py
    - src/catalyst_trader/contracts/__init__.py
    - src/catalyst_trader/desk/builder.py
decisions: [C1-ex-event-observation-strip, C2-symmetric-peer-union, C3-signed-value-plus-direction]
metrics:
  duration: ~25min
  completed: 2026-08-19
  tests_added: 21
  commits: 4
requirements: [HEDGE-CORR-1a, HEDGE-CORR-1b, HEDGE-CORR-1c, HEDGE-CORR-1d]
---

# Phase quick-260819-h1c Plan 01: Correlation Engine + Explicit Hedge-Profiles + Out-of-Band Retrieval (Wave 1) Summary

DB-aware correlation engine that gives the desk explicit, always-available per-name hedge facts
(XBI corr/beta/R2 + same-group peer pairwise corr, full-window AND ex-event-week, each with a signed
value + strength verdict + explicit co-move/inverse direction), stored on KB company nodes, pulled
out-of-band with retrieval onto `TradeProposal` but provably never scored, plus a frugal populate CLI.

## What shipped (per task)

**Task 1 — `quant/correlations.py` (NEW module).** `compute_hedge_profile(conn, ticker, as_of=)`
assembles the explicit blob: `xbi.{full,ex_event}` each with `{corr, beta, r2, verdict, direction,
window}`, `peers[]` (same disease_area OR mechanism_class, from catalyst nodes) each with
`{corr_full, corr_ex_event, verdict, direction}`, `systematic_frac == R2`, `idiosyncratic_frac ==
1-R2`, `suggested_hedge` (`xbi_overlay@beta X` when XBI verdict ∈ {strong,moderate} else
`sizing_only`), and a `note`. Reuses `pairs.correlation_beta` (R2 == corr**2) and
`weekly._weekly_returns` — no hand-rolled math. All thresholds in module `PARAMS`
(`verdict_bands`/`ex_event_window_weeks`/`min_obs`/`hedge_verdicts`), read by direct subscript so a
missing key raises. 12 offline tests. Decision: NEW module (not extend `pairs.py`) to keep
`pairs.py` pure-numpy/DB-free — mixing DB reads would break its purity + test contract.

**Task 2 — `kb.stamp_hedge_profile` / `kb.hedge_profile`.** Writer mirrors `stamp_axes` discipline:
`_get_or_create_company` → SELECT attrs_json → json.loads → overwrite `attrs["hedge_profile"]` →
UPDATE → commit. Idempotent overwrite, exactly one company node per ticker, preserves the existing
`ticker` key, no re-embed, no migration. Reader mirrors `hedge_peers`. content_sha-safe by using the
UPDATE writer, never the catalyst-record path. 6 offline tests.

**Task 3 — out-of-band wiring.** `contracts.TradeProposal.hedge_profile: dict | None = None` (optional,
`extra="forbid"` clean). `builder.build` pulls `hp = kb.hedge_profile(conn, target)` right after the
`analog_query_v2` capture and threads it into the `TradeProposal(...)` constructor ONLY. 3 new tests
incl. the byte-for-byte proof; existing `test_desk_builder` + `test_contracts` green.

**Task 4 — `scripts/build_hedge_profiles.py`.** Enumerates real universe tickers from catalyst nodes
(synthetic `AAA/BBB/...` + `XBI` excluded → **158 real tickers**). `--dry-run` prints the plan naming
the single XBI network call, reads the DB, writes nothing, touches no network (provider import is
lazy). Live run: one Friday-anchored `get_weekly_bars('XBI', '2020-01-01', <today>)` re-pull that
clean-overwrites the Monday rows (`DELETE` then `upsert_bars`), then compute+stamp each ticker off
cached `price_bar`, abstaining (skip) on insufficient obs. `--self-check` is the offline ponytail
one-check (in-memory seed → universe filtering + compute+stamp round-trip + dry-run-writes-nothing
asserts).

## C1–C3 methodology choices (made + documented)

- **C1 — ex-event stripping granularity:** strip the RETURN-OBSERVATION whose *destination*
  `week_end` ∈ the ex-event set, **post-computation** — not the raw bar. `_aligned_returns` computes
  returns on the full aligned series first, then drops observations whose `bars[i+1].week_end` is in
  the set. Dropping the bar would fuse two weeks into a spurious multi-week return; dropping the
  observation keeps every remaining return a true single-week move and keeps both legs aligned.
  Proven by `test_givenExEvent_whenStripping_thenDropsReturnObservationNotRawBar`
  (`len(ex) == len(full) - len(ex_ends)`).
- **C2 — peer-pair ex-event union:** `compute_pair_corr(..., ex_event=True)` strips the **symmetric
  union** of BOTH names' event weeks (`_ex_event_week_ends(a) | _ex_event_week_ends(b)`) so the number
  is well-defined regardless of order. XBI stats strip only the ticker's own events (XBI has no
  catalysts).
- **C3 — verdict sign:** the SIGNED corr/beta is ALWAYS stored; `_verdict` bands on `|corr|`
  (strong ≥0.6 / moderate ≥0.4 / weak ≥0.2 / none), and `_direction` labels `"co-move"` (≥0) vs
  `"inverse"` (<0) explicitly. A strong negative is `verdict="strong", direction="inverse"` — a real
  inverse relationship, never "none". Proven by the `_verdict(-0.75) == "strong"` +
  `_direction(-0.6) == "inverse"` assertions.

## Out-of-band byte-for-byte proof

`test_givenProfileVsNoProfile_whenBuild_thenScoringFieldsByteForByteIdentical`: builds the SAME
catalyst with vs without a stamped `hedge_profile` and asserts `size_pct`, `expected_return_pct`,
`expected_move_field`, `kb_analogs`, and `retrieval_confidence` are all identical, while
`hedge_profile` is `None` in one and the stored dict in the other. The profile attaches ONLY at the
`TradeProposal(...)` constructor — it is never referenced by `_split_moves`, the `methods[]` football
field, `size_for_survival`, or any score/estimate path. Confirms it is context, not a ranking signal
(design decision 4).

## Simple- vs log-returns note

The engine reuses `weekly._weekly_returns`, which computes **simple** close-to-close returns, while
spec 1a phrases it as "log-return". At the weekly scale the two are near-identical for correlation
purposes (weekly moves are small, log(1+r) ≈ r), and the reuse-map explicitly directs reusing this
helper rather than hand-rolling a log variant (which would duplicate money-path math and risk a new
bug). Decision: reuse the simple-return helper; do not fork a log variant. Documented here per the
plan interface note. Upgrade path: if a log variant is ever needed, add it to `weekly.py` and both
`classify_drop` and this engine adopt it together.

## Backward-compat proof

`TradeProposal.hedge_profile` is an optional field defaulting `None`. Fresh `:memory:` DB → no
stamped company node → `hedge_profile()` returns `None` on both sides → `out_default == out_explicit`
on every money field. Full suites green: `test_desk_builder`, `test_contracts`, `test_pairs`,
`test_kb_hedge` — **158 passed** across the combined run (2 warnings are pre-existing statsmodels
`ComplexWarning`s in `test_pairs`, unrelated to this change).

## Live populate — NOT run (operator step)

`scripts/build_hedge_profiles.py` was executed ONLY with `--dry-run` and `--self-check`. The live
populate (network XBI re-pull + profile writes to the live `catalyst.db`) is left un-run pending
operator vet, per the task constraint. Dry-run call plan:
`get_weekly_bars('XBI', '2020-01-01', '2026-08-19')` — the single external call — followed by
compute+stamp of the 158 real tickers off cached `price_bar`.

## Test counts

- `tests/test_correlations.py`: 12
- `tests/test_hedge_profile_store.py`: 6
- `tests/test_desk_builder_hedge_profile.py`: 3
- New total: **21**. Backward-compat suites (builder/contracts/pairs/kb_hedge) all green.

## Deviations from Plan

None — plan executed as written. The C1–C3 methodology choices were resolved as directed and are
documented above. Out-of-scope note: `test_pairs` emits 2 pre-existing statsmodels `ComplexWarning`s
(Johansen path) that predate this plan; not touched (scope boundary).

## Self-Check: PASSED
- Files created: correlations.py, test_correlations.py, test_hedge_profile_store.py,
  test_desk_builder_hedge_profile.py, build_hedge_profiles.py — all present.
- Commits: 3f17abb, 40b4c5e, e484db8, 5579d19 — all present in git log.
