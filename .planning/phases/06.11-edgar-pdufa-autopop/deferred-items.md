## Deferred (out-of-scope, pre-existing)

- **test_refresh.py::test_refresh_full_pipeline_httpx** — fails with
  `TypeError: string indices must be integers` at `fmp.py:66` (`row["symbol"]`).
  Pre-existing at phase-start commit a8e8981; zero `pdufa_edgar` references in
  `test_refresh.py`/`fmp.py`. NOT caused by Plan 06.11-01 (additive provider only).
  Owner: whoever touches the FMP earnings calendar provider next.

## Pre-existing (out of scope for 06.11-03)
- `tests/test_refresh.py::test_refresh_full_pipeline_httpx` — TypeError at `src/catalyst_trader/providers/fmp.py:66`. Fails on a clean tree BEFORE any 06.11-03 change (verified via git stash). Unrelated to the RH adapter/registry/ingest edits. Not fixed here (scope boundary).
