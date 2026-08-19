# Deferred / out-of-scope items — 260819-bgap

## Pre-existing failure (NOT caused by BGAP, not fixed here)

- **`tests/test_weekly_cycle.py::test_module_contains_no_opener_or_broker_call`** FAILS.
  - Cause: `scripts/weekly_cycle.py` source contains one of the forbidden broker/opener
    strings (`approve_pending` / `_open_paper_position` / `place_equity_order`).
  - Verified pre-existing: fails with all BGAP changes stashed. Both `tests/test_weekly_cycle.py`
    and `scripts/weekly_cycle.py` are UNTRACKED files (uncommitted, from prior slice-5 work),
    entirely unrelated to the binary tail-gap change.
  - Scope: out of scope for BGAP (no overlap with sizing.py / kb.py / catalyst_context.py).
    Owner of the slice-5 weekly_cycle scaffolding should resolve.
