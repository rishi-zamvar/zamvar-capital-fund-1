
## DATA-03 amendment (2026-08-16) — out-of-scope pre-existing failure
- `tests/test_refresh.py::test_refresh_full_pipeline_httpx` FAILS on baseline (before this change) — `fmp.py:66 TypeError: string indices must be integers` when parsing the FMP earnings-calendar fixture. Unrelated to the DATA-03 single-authoritative verify change (confirmed via `git stash` isolation). Not touched.
