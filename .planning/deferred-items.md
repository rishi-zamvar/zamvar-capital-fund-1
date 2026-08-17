
## DATA-03 amendment (2026-08-16) — out-of-scope pre-existing failure
- `tests/test_refresh.py::test_refresh_full_pipeline_httpx` FAILS on baseline (before this change) — `fmp.py:66 TypeError: string indices must be integers` when parsing the FMP earnings-calendar fixture. Unrelated to the DATA-03 single-authoritative verify change (confirmed via `git stash` isolation). Not touched.

## Catalyst-pipeline consolidation (refresh.py → run_cycle) — DEFERRED 2026-08-17
Operator decided (2026-08-16): one canonical catalyst pipeline, archive the legacy path. RTTNews drop is DONE. The refresh.py→run_cycle consolidation is NOT done — two executor attempts stalled on transient infra (600s watchdog; also an ENOTFOUND on /compact same window). Mapped by hand instead:
- **refresh.py** = the launchd production daily job (DATA-01/03/05): curated-PDUFA load + FMP/CT.gov fetch + verify + **48h re-verify** + **T-2 trigger**, ~180-day FORWARD catalyst window.
- **scripts/daemon.py::run_cycle** = the 6.10 data daemon: prices + cards + all providers incl. pdufa_edgar, ~52-week BACKWARD window.
- The reusable DATA-03/05 logic already lives in shared modules: **T-2 trigger → calendar/triggers.py**, **48h re-verify → calendar/verify.py**. refresh.py only composes them.
- **The delicate bit:** the two use opposite time windows by design (catalysts forward, prices backward) — a real behavioral merge, not just moving calls. Must keep run_cycle's backward price window AND add a forward catalyst pass that fires triggers.py + verify.py re-verify + the curated loader, then repoint launchd at the unified entrypoint and archive refresh.py.
- **Preserve on the canonical path (tests):** DATA-01 calendar, DATA-03 48h re-verify, DATA-05 T-2 trigger, curated-PDUFA loader, verify gate, point-in-time last_verified_at.
- **Risk if rushed:** a wrong/lost catalyst date = total loss (project's #1 principle). Do with TDD + explicit DATA-03/05 preservation tests, not under infra flakiness.
- **Not blocking:** both pipelines work today; run_cycle+ingest (the canonical data path the backtest uses) is unaffected. This is hygiene/dedup, off the critical path to the backtest.
