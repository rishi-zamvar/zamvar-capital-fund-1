---
phase: 07.9-structured-analyst-reports
plan: 1.5
type: tdd
wave: 1
depends_on: []
files_modified:
  - src/catalyst_trader/contracts/__init__.py
  - src/catalyst_trader/desk/research_bundle.py
  - src/catalyst_trader/desk/diligence_inputs.py
  - tests/test_desk_research_bundle.py
  - tests/test_desk_diligence_inputs.py
autonomous: true
requirements: [CALL-01]
# CALL-01 = the shared cited-fact substrate feeding the analyst desk + DD. This plan lays the
# input-layer (the bundle + one proven consumer); full analyst tool-backing is staged to Plan 2 /
# a follow-on per the phase brief ("CALL-01 NOT closed — spans Plan 2/3").

must_haves:
  truths:
    - "A CatalystResearchBundle can be built for one catalyst with every populated fact carrying a resolvable evidence_ref (tool:… or an inline base-rate citation)."
    - "Each free/cited source is invoked EXACTLY ONCE per catalyst regardless of how many facts or downstream consumers read from it."
    - "The bundle carries FACTS ONLY — the contract has NO field for any desk interpretation (analyst score/confidence/thesis, debate verdict, builder dossier); a leaked interpretation field is a type error (extra='forbid'), not a policy check."
    - "A missing/degraded source yields a null fact (value=None) + a degraded flag — never a fabricated number."
    - "The bundle reads point-in-time through serving.asof(cutoff) — a future/unknowable read never leaks into the facts."
    - "make_diligence_inputs (the DD feed) sources its market_data FROM the bundle — one consumer proven — while returning the SAME (DiligenceInput, market_data, degraded) contract (existing DD suite stays green)."
  artifacts:
    - path: "src/catalyst_trader/contracts/__init__.py"
      provides: "CatalystResearchBundle + Fact wrapper (nullable-default-None, evidence_ref per fact, extra='forbid', FACTS ONLY)"
      contains: "class CatalystResearchBundle"
    - path: "src/catalyst_trader/desk/research_bundle.py"
      provides: "build_research_bundle(conn, ticker, catalyst, as_of, *, <injected sources>) — deterministic, cache-first, computed-once, honest-degrade, point-in-time, evidence-tagged"
      contains: "def build_research_bundle"
    - path: "src/catalyst_trader/desk/diligence_inputs.py"
      provides: "make_diligence_inputs refactored to consume the bundle (delegates sourcing; no independent re-fetch); same return contract"
      contains: "build_research_bundle"
    - path: "tests/test_desk_research_bundle.py"
      provides: "offline TDD: computed-once (call-count spies), facts-only (firewall assertion), honest-degrade, point-in-time, resolvable evidence_ref"
      contains: "def test_"
  key_links:
    - from: "src/catalyst_trader/desk/research_bundle.py"
      to: "kb.analog_query / quant.base_rate / edgar.fundamentals / clinicaltrials / options_cboe.fetch / finra.fetch / edgar.insider_net / serving.asof(cutoff).bars"
      via: "injected source callables (production defaults = the real free/cached readers), each called once"
      pattern: "analog_query|base_rate|fundamentals|options_cboe|finra|insider_net|serving.asof"
    - from: "src/catalyst_trader/desk/diligence_inputs.py"
      to: "build_research_bundle"
      via: "make_diligence_inputs builds the bundle once, then maps bundle facts -> market_data"
      pattern: "build_research_bundle"
    - from: "each populated Fact.evidence_ref"
      to: "desk.evidence.resolve"
      via: "tool_ref_for-minted refs are resolvable-by-construction"
      pattern: "tool:.*#|citation"
---

<objective>
Build the **Catalyst Research Bundle**: ONE deterministic research pass that computes every cited
fact once per catalyst (KB analogs, base rates, financials/runway, trial stats, options-implied move,
ownership/insider, price/positioning, hedge inputs) into a structured, evidence_ref-tagged substrate —
then prove it can FEED a consumer by refactoring `make_diligence_inputs` (the DD firewall's data feed)
to source its `market_data` FROM the bundle instead of re-fetching.

Today the same facts are re-derived many times: `analog_query` runs ~6× per catalyst (4 analysts +
`catalyst_context` risk sizing + `builder`), `base_rate` runs per-analyst, and `make_diligence_inputs`
re-sources options/financials/ownership/trial for DD. The bundle computes each free source ONCE and
hands the identical ground truth everywhere.

**FIREWALL LINE (non-negotiable, a TESTED invariant):** the bundle carries ONLY cited FACTS. It has
NO field for any desk interpretation (analyst score/thesis, debate verdict, builder dossier). DD reads
the same FACTS but forms its verdict INDEPENDENTLY. `extra='forbid'` makes a leaked interpretation a
type error, not a policy violation.

Purpose: frugality (each free source hit once — cache-first) + consistency (identical ground truth) +
a strengthened independent-diligence firewall (a DD-vs-desk disagreement becomes pure judgment, not a
data artifact).

Output: `CatalystResearchBundle` contract, `build_research_bundle` builder, a bundle-backed
`make_diligence_inputs`, and an offline TDD suite proving computed-once / facts-only / honest-degrade /
point-in-time / resolvable-refs.

SCOPE (1.5 only): build the bundle + ONE proven consumer (DD via make_diligence_inputs). Do NOT build
the DD structured reports (Plan 2), the roll-up (Plan 3), or the full analyst tool-backing (staged —
see "Staged: analyst consumption" below).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/07.9-structured-analyst-reports/PHASE-BRIEF.md
@.planning/research/analyst-report-guideline.md

# The two sourcing functions the bundle GENERALIZES + ABSORBS (study their honest-degrade patterns):
@src/catalyst_trader/desk/diligence_inputs.py
@src/catalyst_trader/desk/catalyst_context.py

# The single orchestration seam where analysts + builder + DD all pull facts today:
@src/catalyst_trader/desk/live_desk.py

# The analyst tool surface + citation model (why cite-or-drop drives the consumption mechanism):
@src/catalyst_trader/desk/tools.py
@src/catalyst_trader/desk/evidence.py

# The DD contract the consumer must keep intact:
@tests/test_desk_diligence_inputs.py

<interfaces>
<!-- The real source functions the bundle ORCHESTRATES. Do NOT re-implement any of these — inject them
     (production defaults) and call each ONCE. Signatures verified against the codebase. -->

# KB analogs — nearest past catalysts of the same type + realized moves
kb.analog_query(conn, embed, context: str, filters: dict, k: int = 5, as_of: str | None = None) -> list[dict]
kb.default_embedder()                                   # offline via CT_EMBEDDER=hash
desk.builder._split_moves(analogs) -> tuple[list[float], list[float]]   # up_moves, down_moves

# Base rates — cited clinical priors (raises ValueError on no-match / ambiguous — NEVER returns None)
quant.base_rate(metric: str, phase=None, indication=None) -> {"value","source_name","source_url","quote"}

# Financials/runway + ownership shares — ONE fetch reused for BOTH (mirror make_diligence_inputs)
providers.edgar.fundamentals(ticker) -> {"shares_outstanding","cash_usd","monthly_burn_usd","cash_runway_months","provenance"} | None
providers.edgar.insider_net(ticker, *, since: str, until: str) -> float | None   # 0.0 = quiet tape, GROUNDS

# Trial stats (non-money; None is fine, no NO-GO)
providers.clinicaltrials.fetch_trial_readouts(...)      # a CT.gov record | None

# Options-implied move — quote (CBOE) is a SOURCE; implied_move is a deterministic quant DERIVATION (cited, not an interpretation)
providers.options_cboe.fetch(ticker) -> {"options_quote": {...}|None, "underlying_quote": {...}, "underlying_price": ...} | None
quant.implied_move(underlying_price, *, call_mid=None, put_mid=None, iv=None, days_to_event=None) -> ToolResult

# Ownership — FINRA short interest (production default binds as_of via registry.recent_si_settlement)
providers.finra.fetch(ticker, settlement_date=None) -> {"short_interest","days_to_cover","si_settlement_date"} | None
providers.registry.recent_si_settlement(as_of)

# Price / positioning — point-in-time close series through the serving gateway (cache-first)
serving.asof(conn, cutoff) -> Databook ; Databook.bars(ticker, as_of, *, lookback_weeks=None) -> list[dict]  # raises LookAheadDenied on future

# Evidence refs (how each fact gets a resolvable citation):
desk.evidence.tool_ref_for(name: str, inputs: dict) -> "tool:<name>#<hash>"   # resolvable-by-construction
desk.evidence.tool_ref(result) -> str                                         # for quant ToolResults
desk.evidence.resolve(conn, ref) -> dict | None                              # tool:… always resolves; base_rate carries an INLINE citation dict instead
</interfaces>
</context>

<staged_decision>
## Analyst-consumption mechanism — RECOMMENDATION (built path vs staged path)

The parent asked which mechanism feeds the bundle to the 4 analysts. Two options:

1. **Prompt-context** — pass the bundle slice into each analyst's prompt as `extra_context`.
   ❌ REJECTED: the analyst HARD RULES (analysts.py rule 1-2) require every number to come from a
   `mcp__quant__*` tool call and be cited by the `evidence_ref` the tool returns. Facts arriving via
   prose have no tool ref → cite-or-drop silently drops them → the whole one-pager degrades.

2. **Tool-backing (cache)** — back the in-process quant MCP server (`build_quant_tools`) with the
   bundle, so `analog_query` / `base_rate` / `implied_move` / `cash_runway` return the PRECOMPUTED
   cited fact (still emitting a resolvable `evidence_ref`).
   ✅ RECOMMENDED: preserves cite-or-drop verbatim (the tool still returns a resolvable ref), delivers
   the frugality win (source hit once, cached), and requires ZERO change to analyst prompts/contracts.

**This plan builds the bundle + proves the DD consumer** (make_diligence_inputs — a pure deterministic
fact-sourcer, offline-testable, the cleanest seam to prove DD reads the bundle). The analyst
tool-backing (option 2) is STAGED to Plan 2 / a follow-on, but the builder is SHAPED for it now: the
bundle exposes facts keyed so a thin `build_quant_tools` cache-lookup adapter is trivial later (e.g. a
`bundle.fact_for(tool_name, inputs)` accessor, or facts keyed by the same tool-ref inputs hash the
tools already mint). Do NOT wire the analyst tools in this plan.
</staged_decision>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: The CatalystResearchBundle contract + firewall invariant (facts-only)</name>
  <files>src/catalyst_trader/contracts/__init__.py, tests/test_desk_research_bundle.py</files>
  <behavior>
    Tests FIRST (RED), in tests/test_desk_research_bundle.py:
    - test_bundle_is_facts_only_no_interpretation_fields: assert CatalystResearchBundle.model_fields
      contains NONE of {score, confidence, thesis, verdict, dossier, recommendation, decision,
      key_findings} — the firewall line, at the type level.
    - test_bundle_forbids_extra: constructing with a stray interpretation field (e.g. score=0.7)
      raises pydantic.ValidationError (extra='forbid').
    - test_bundle_facts_default_null: an empty CatalystResearchBundle(ticker=…, catalyst=…) validates
      with every numeric fact value defaulting to None (an empty slot is an honest finding).
    - test_fact_carries_ref: a populated Fact validates with value + evidence_ref; a Fact may instead
      carry an inline `citation` dict (the base-rate shape {source_name, source_url, quote}); a Fact
      with a value but neither a ref nor a citation is REJECTED (cite-or-drop at the contract).
  </behavior>
  <action>
    Add to contracts/__init__.py (mirror the existing lens-report sub-model style, pydantic v2,
    ConfigDict(extra='forbid')):
    - `class Fact(BaseModel)`: `value: <nullable> = None`, `evidence_ref: str | None = None`,
      `citation: dict | None = None`, `context: str | None = None`. A model_validator: if `value is
      not None`, exactly one of {evidence_ref, citation} MUST be present (cite-or-drop at the contract).
      Keep it generic (value typed loosely — float/str/list/dict/None — this is a substrate, not a lens).
    - `class CatalystResearchBundle(BaseModel)` with `model_config = ConfigDict(extra='forbid')`:
        ticker: str ; catalyst: dict ; as_of: str
        analogs: Fact       (list of realized-move analog dicts, from kb.analog_query)
        base_rates: list[Fact] = []   (each an inline-citation Fact from quant.base_rate)
        financials: Fact    (cash_usd/monthly_burn_usd/shares_outstanding/cash_runway_months bundle)
        trial: Fact         (CT.gov record; non-money)
        options: Fact       (CBOE quote + underlying_price + days_to_event)
        implied_move: Fact  (quant.implied_move derivation over the options quote)
        ownership: Fact     (short_interest_pct/days_to_cover/insider_net)
        prices: Fact        (target close series + positioning)
        hedge_inputs: Fact  (analog_gaps split from analogs — the catalyst_context single-leg shape)
        degraded: list[str] = []   (honest-degrade flags, mirrors make_diligence_inputs' `degraded`)
      FACTS ONLY — add NO score/thesis/verdict/dossier field. Field names/leaves may follow the
      guideline §7 checklist categories; the invariant is: nullable-default-None + a Fact ref/citation
      per populated fact + no interpretation field.
    Run the tests → GREEN. Commit: `feat(07.9): CatalystResearchBundle contract (facts-only substrate)`.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_desk_research_bundle.py -x -q</automated>
  </verify>
  <done>The 4 contract tests pass; CatalystResearchBundle has no interpretation field and extra='forbid'; Fact enforces cite-or-drop for any populated value.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: build_research_bundle — deterministic, computed-once, honest-degrade, point-in-time</name>
  <files>src/catalyst_trader/desk/research_bundle.py, tests/test_desk_research_bundle.py</files>
  <behavior>
    Tests FIRST (RED), extending tests/test_desk_research_bundle.py with fake injected sources
    (offline — NO network, NO LLM, NO real embedder; mirror test_desk_diligence_inputs.py fakes):
    - test_computed_once: wrap each injected source in a call-counting spy; build the bundle; assert
      EACH source was called EXACTLY once (analog_source, financials_source reused for financials +
      ownership shares → still one fetch, base_rate_source per distinct metric, options/finra/insider/
      price each once). This is the frugality proof.
    - test_every_populated_fact_has_resolvable_ref: for each populated Fact, either evidence.resolve(
      conn, fact.evidence_ref) is not None (tool:… refs) OR fact.citation carries source_name/url/quote.
    - test_honest_degrade_missing_source: inject financials_source -> None (and finra -> None); assert
      bundle.financials.value is None AND bundle.ownership.value is None AND a matching flag is in
      bundle.degraded — and NO fabricated number anywhere (assert the values are None, not 0/guessed).
    - test_insider_zero_grounds: insider_source -> 0.0 (quiet tape) with finra+shares present GROUNDS
      ownership (0.0 is a real datum → `is not None`), not a degrade.
    - test_point_in_time: inject a price_source that records the `as_of`/cutoff it was called with;
      assert the builder passes the point-in-time cutoff through (no future read). Optionally: a fake
      that raises serving.LookAheadDenied on a future date is never triggered for a knowable as_of.
    - test_facts_only_output: assert the returned object is a CatalystResearchBundle and (belt-and-
      suspenders) has no interpretation attribute set.
  </behavior>
  <action>
    Create desk/research_bundle.py. Mirror make_diligence_inputs + catalyst_context patterns EXACTLY
    (injectable sources with free/cache-first production defaults; honest-degrade whole-dict-or-omit;
    source-or-omit; the ONE fundamentals fetch reused for financials cash/burn AND ownership shares).

    `def build_research_bundle(conn, ticker, catalyst, as_of, *, cutoff=None, embed=None,
        analog_source=None, base_rate_source=None, financials_source=None, trial_source=None,
        options_source=None, finra_source=None, insider_source=None, price_source=None,
        params=None) -> CatalystResearchBundle`

    Production defaults (bind lazily; each called ONCE):
      analog_source     -> kb.analog_query(conn, embed or kb.default_embedder(), f"{ticker} {ctype}", {"type": ctype}, as_of=as_of)
      base_rate_source  -> quant.base_rate (wrap in try/except ValueError -> degrade, per its raise-on-miss contract)
      financials_source -> edgar.fundamentals   (reused for financials + ownership shares — do NOT fetch twice)
      trial_source      -> clinicaltrials reader (None is fine, non-money)
      options_source    -> options_cboe.fetch   (nested options_quote|None -> honest sentinel like diligence_inputs)
      finra_source      -> finra.fetch(t, registry.recent_si_settlement(as_of))  (resolve INSIDE where as_of is bound — see diligence_inputs C1)
      insider_source    -> edgar.insider_net (0.0 grounds)
      price_source      -> serving.asof(conn, cutoff).bars(ticker, as_of, lookback_weeks=…) close series (cache-first, point-in-time)

    Each populated Fact carries its ref: provider/quant facts -> evidence.tool_ref_for(name, inputs)
    (resolvable-by-construction); base_rate facts -> the INLINE citation dict {source_name,source_url,
    quote} (matches tools.py). Numbers default None; a missing/ValueError/None source -> value=None +
    a `degraded` flag, NEVER a fabricated figure. hedge_inputs = analog_gaps split via
    builder._split_moves (single-leg honest default, exactly as catalyst_context does — reuse, don't
    reinvent). Point-in-time: thread `cutoff` (== as_of for knowable/backtest, None=now/live) into
    serving.asof, mirroring live_desk.

    # ponytail: one function + injected sources + honest field builders. No provider class, no
    #           registry, no cache class — serving.asof IS the cache; reuse the ONE fundamentals fetch.
    Run tests iteratively (RED->GREEN). Commit: `feat(07.9): build_research_bundle (computed-once cited substrate)`.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_desk_research_bundle.py -x -q</automated>
  </verify>
  <done>All bundle-builder tests pass: each source called exactly once, every populated fact has a resolvable ref/citation, a missing source degrades to null+flag (never fabricated), insider 0.0 grounds ownership, the point-in-time cutoff is threaded through.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Wire the proven consumer — make_diligence_inputs sources from the bundle</name>
  <files>src/catalyst_trader/desk/diligence_inputs.py, tests/test_desk_diligence_inputs.py</files>
  <behavior>
    Tests FIRST (RED), extending tests/test_desk_diligence_inputs.py:
    - test_diligence_inputs_reads_bundle: inject a fake `bundle_fn` (or the real build_research_bundle
      with fake sources) and assert make_diligence_inputs maps bundle FACTS -> the SAME market_data
      shape {options, liquidity_quote, hedge, trial, financials, ownership} it produced before — i.e.
      the DD contract is byte-compatible.
    - test_no_double_sourcing: assert make_diligence_inputs no longer calls edgar/finra/options
      directly a second time — it consumes the bundle's already-sourced facts (the frugality win at
      the DD seam). Verify via call-count spies or by asserting the bundle_fn is the only source path.
    - The EXISTING test_desk_diligence_inputs.py cases (B2 sentinel, C1 None-bid->0, S2.5 financials/
      ownership whole-dict-or-omit + degrade flags) MUST still pass unchanged (backward-compat).
  </behavior>
  <action>
    Refactor make_diligence_inputs to DELEGATE sourcing to the bundle (no independent re-fetch):
    - Add an injectable `bundle_fn=None` (production default = build_research_bundle) to the factory.
    - Inside the closure: build the bundle ONCE for (conn, ticker, catalyst, as_of, cutoff=as_of),
      then MAP its facts into the existing market_data dict:
        options       <- bundle.options.value (keep the nested-quote/sentinel + days_to_event logic;
                          if the sentinel construction now lives in the bundle, map it through)
        liquidity_quote <- bundle.options.value underlying (None-bid -> 0 coercion preserved, C1)
        financials    <- bundle.financials.value (whole-dict-or-omit + the same degrade flag string)
        ownership     <- bundle.ownership.value  (whole-dict-or-omit + the same degrade flag string)
        trial         <- bundle.trial.value
        hedge         <- REUSE risk_inputs {entry, exit_by_date, analog_gaps, prices} verbatim (unchanged)
      Preserve the EXACT return contract: (DiligenceInput, market_data, degraded: list[str]). The
      `degraded` list now comes from bundle.degraded (same honest-NO-GO strings the DD dims expect).
    - Keep make_diligence_inputs's public signature backward-compatible: the old per-source injection
      kwargs (options_source/financials_source/…) may either be threaded INTO the bundle builder or
      deprecated in favor of `bundle_fn`; whichever keeps the existing tests green with the smallest
      diff. Do NOT change run_diligence or live_desk in this plan (live_desk already calls
      make_diligence_inputs() — the seam stays; the bundle now backs it).

    # ponytail: the bundle becomes the single source; make_diligence_inputs shrinks to a fact->
    #           market_data mapper. Smaller diff, one source of truth, firewall unchanged (still FACTS).
    Run BOTH suites (RED->GREEN). Commit: `refactor(07.9): make_diligence_inputs sources from the research bundle`.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_desk_diligence_inputs.py tests/test_desk_research_bundle.py -x -q</automated>
  </verify>
  <done>make_diligence_inputs sources market_data from the bundle (DD reads the bundle — one consumer proven), no double-sourcing, and the full existing diligence-inputs suite stays green (backward-compat + firewall FACTS-ONLY intact).</done>
</task>

</tasks>

<verification>
Whole-suite regression (the bundle is additive; every prior suite must stay green — analysts, DD,
catalyst_context, live_desk, builder, orchestrator):

```bash
.venv/bin/python -m pytest -q
```

Firewall assertion is a TEST, not a review note: `test_bundle_is_facts_only_no_interpretation_fields`
+ `test_bundle_forbids_extra` must both pass. Frugality is a TEST: `test_computed_once` +
`test_no_double_sourcing`. Honest-degrade is a TEST: `test_honest_degrade_missing_source`.
</verification>

<success_criteria>
- CatalystResearchBundle exists, FACTS ONLY (no interpretation field, extra='forbid'), every populated
  fact carries a resolvable evidence_ref or an inline citation, numbers default None.
- build_research_bundle computes each free source ONCE per catalyst, cache-first, point-in-time
  (serving.asof cutoff), honest-degrade (missing -> null + flag, never fabricated).
- make_diligence_inputs sources DD's market_data FROM the bundle (one consumer proven), same contract,
  existing DD suite green.
- Recommended analyst-consumption mechanism (tool-backing via a bundle cache) is documented and the
  builder is shaped for it; the actual analyst rewiring is staged (NOT built here).
- `.venv/bin/python -m pytest -q` is green (additive change, no regressions).
</success_criteria>

<output>
After completion, create `.planning/phases/07.9-structured-analyst-reports/plan1.5-research-bundle/07.9-1.5-SUMMARY.md`
capturing: the bundle contract shape, which real source functions it orchestrates (enumerated), the
computed-once/honest-degrade/point-in-time proofs, the DD consumer seam, and the STAGED analyst
tool-backing plan (for Plan 2 to pick up).
</output>
