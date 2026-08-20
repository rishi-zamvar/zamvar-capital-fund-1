# Recorded agent responses (offline replay)

One JSON file per recorded role response. Each file is the exact structured
payload a role's `query()` would emit — a schema-valid instance of that role's
contract. The 4 catalyst-call analysts each emit a lens report
(`{clinical,regulatory,financial,market_sentiment}_signal.json` ->
`ClinicalReport`/`RegulatoryReport`/`FinancialReport`/`MarketReport`, guideline §7);
the 8 DD dims + the generic seam sample still ride the shared `AnalystSignal`
(`dd_*_signal.json`, `sample_analyst_signal.json`). Debate/verdict/etc. as before
(`DebateVerdict`, ...).

The whole desk test suite runs **offline**. There are two mock points, both
against the single SDK seam in `catalyst_trader.desk.runtime`:

- **`run_structured`** — monkeypatch this when the test only cares about the
  parsed model a caller receives (analyst/debate/verifier logic). Return
  `schema.model_validate(load_fixture("agent_responses/<name>"))`.
- **`query`** — monkeypatch the lower-level SDK call when the test needs to
  exercise `run_structured` itself (validation, retry, options passthrough).
  Yield a message whose `.result` is the JSON *text* of the fixture.

No test ever performs a live Anthropic call. Load fixtures via the
`load_fixture` conftest helper (it accepts subpaths, e.g.
`load_fixture("agent_responses/sample_analyst_signal")`).

## Files

- `sample_analyst_signal.json` — schema-valid `AnalystSignal` (clinical
  dimension, one sourced key_finding) proving the replay pattern.
