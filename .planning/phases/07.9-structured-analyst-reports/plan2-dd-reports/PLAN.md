---
phase: 07.9-structured-analyst-reports
plan: 2
type: tdd
wave: 1
depends_on: ["01", "1.5"]   # both SHIPPED — 01 gives AnalystReportBase + reusable section sub-models; 1.5 gives the bundle + the C5 qualitative/fact split. Listed for traceability.
files_modified:
  - src/catalyst_trader/contracts/__init__.py
  - src/catalyst_trader/desk/diligence.py
  - tests/test_contracts.py
  - tests/test_desk_diligence.py
  - tests/fixtures/agent_responses/dd_trial_stats_signal.json
  - tests/fixtures/agent_responses/dd_regulatory_signal.json
  - tests/fixtures/agent_responses/dd_financials_signal.json
  - tests/fixtures/agent_responses/dd_ownership_flow_signal.json
  - tests/fixtures/agent_responses/dd_options_move_signal.json
  - tests/fixtures/agent_responses/dd_hedge_revalidation_signal.json
  - tests/fixtures/agent_responses/dd_liquidity_signal.json
  - tests/fixtures/agent_responses/dd_historical_analog_signal.json
autonomous: true
requirements: [CALL-01]
must_haves:
  truths:
    - "Each of the 8 locked DD dimensions (trial_stats/regulatory/financials/ownership_flow/options_move/hedge_revalidation/liquidity/historical_analog) emits a dimension-specific structured report carrying an adversarial subset of the guideline's ordered sections + nullable data-point fields, instead of the bare AnalystSignal."
    - "A number the DD dimension could not source is null (default None), never fabricated; each dimension's ONE headline verdict number, when non-null, carries a non-empty paired _source string (model_validator)."
    - "Each DD report still carries the base interface (dimension/thesis/score/confidence/key_findings/unknowns), so synthesize_verdict / dimension_passed / assemble_dossier / _narrative / enforce_dossier / md.py consume it unchanged — the money go/no-go math is byte-identical."
    - "No DD headline number depends on a QUALITATIVE fact the bundle does not carry (rNPV, prior-CRL narrative, AdCom outcome, MoA, label risk) — those slots exist but are nullable, agent/KB-sourced (C5); every headline anchors on a deterministic free-source fact."
    - "The FIREWALL stays a TYPE invariant: run_dimension is still assembled ONLY from DiligenceInput; no desk conclusion is representable on the input. The 4 lens reports + generic runtime seam are untouched (schema split preserved). The whole suite runs offline and is green."
  artifacts:
    - path: "src/catalyst_trader/contracts/__init__.py"
      provides: "8 DD dimension report classes subclassing AnalystReportBase + 2 new sections (Tradeability + hedge fields); REUSES the Plan-1 section sub-models; AnalystSignal kept for the generic seam."
      contains: "class TrialStatsReport"
    - path: "src/catalyst_trader/desk/diligence.py"
      provides: "DD_REPORT_FOR mapping + run_dimension bound per-dim to its report class + plain-language/section HARD RULES in build_dimension_prompt + widened type hints; money math (synthesize_verdict/dimension_passed) body UNCHANGED."
      contains: "DD_REPORT_FOR"
    - path: "tests/fixtures/agent_responses/dd_trial_stats_signal.json"
      provides: "A schema-valid TrialStatsReport fixture in the new richer shape (base fields + sections + headline+source)."
      contains: "trial_stats"
  key_links:
    - from: "src/catalyst_trader/desk/diligence.py::run_dimension"
      to: "src/catalyst_trader/desk/runtime.py::run_structured"
      via: "binds the per-dimension DD report class (DD_REPORT_FOR[dimension]) as the output schema, NOT AnalystSignal"
      pattern: "run_structured\\(.*DD_REPORT_FOR|run_structured\\(.*report_cls"
    - from: "src/catalyst_trader/desk/diligence.py::synthesize_verdict"
      to: "the 8 DD reports"
      via: "duck-reads .dimension/.score/.confidence/.key_findings (AnalystReportBase interface preserved) — money math body unchanged"
      pattern: "s\\.dimension in MONEY_TOUCHING|sig\\.key_findings"
    - from: "src/catalyst_trader/desk/md.py::reconcile"
      to: "DiligenceDossier.per_dimension"
      via: "reads d['catalyst_id'] from the (now richer) per_dimension dicts — additive, still present"
      pattern: "per_dimension"
---

<objective>
Give each of the 8 LOCKED diligence dimensions its own structured, plain-language report — the DD
mirror of Plan 1's 4 lens reports. Today all 8 DD dims emit the thin shared `AnalystSignal`
(`diligence.run_dimension` binds it). This plan gives each dim a richer `AnalystReportBase` subclass
(adversarial subset of the guideline sections + nullable data-point slots + ONE headline verdict
number gated by a paired `_source`), rewrites the 8 prompts to the plain-language standard, and
re-points `run_dimension` — while the go/no-go money math, the firewall, and the whole downstream
duck-typed interface stay byte-identical.

The hard constraints that shape every choice:
- **Firewall = TYPE invariant (LOCKED #1).** DD reads the SAME cited facts as the desk (the Plan-1.5
  Research Bundle), but forms its verdict adversarially/independently. There is NO independent re-pull
  cross-check — independence lives purely in judgment. `run_dimension` is still assembled ONLY from
  `DiligenceInput`; no desk conclusion is representable.
- **Keys FROZEN (LOCKED #2).** The 8 dimension keys/order are unchanged: `trial_stats, regulatory,
  financials, ownership_flow, options_move, hedge_revalidation, liquidity, historical_analog`.
- **C5 (Plan 1.5).** The bundle carries ONLY deterministic free-source facts. The QUALITATIVE reads
  (rNPV, prior-CRL narrative, AdCom outcome, MoA, label risk, efficacy/safety detail) are NOT in the
  substrate — they stay agent/KB-sourced and nullable. **No headline number may depend on them.**
- **Money math UNTOUCHED.** `synthesize_verdict` / `dimension_passed` / `assemble_dossier` bodies do
  not change — only their type hints widen. The reports subclass `AnalystReportBase` (same duck-typed
  interface the money code reads), so consumers flow unchanged — exactly how the 4 lens reports did.
- **NO DUPLICATION.** REUSE the Plan-1 section sub-models (TrialDesign, Endpoints, Efficacy, Safety,
  Application, Division, PriorCrl, AdCom, LabelRisk, Poa, Runway, CapitalStructure, Insiders,
  ShortInterest, Ownership, ExpectedMove, ImpliedProb, Analog) verbatim. Add ONLY the 2 sections that
  have no lens equivalent (DD liquidity is *tradeability*, NOT the balance-sheet `Liquidity` section).

**OPEN DECISION — RESOLVED: CONSOLIDATION (2026-11-10).** DD reads the shared Plan-1.5 Research
Bundle ONLY (via `make_diligence_inputs` → `market_data`); there is NO independent belt-and-suspenders
re-pull. Rationale: frugality (each free source hit once) + identical ground truth, so a DD-vs-desk
disagreement is pure judgment, never a data artifact. The firewall is unaffected: the bundle carries
cited FACTS only, never desk interpretations, and `run_diligence` still takes only `DiligenceInput`.

**REVISIONS from plan-check (2026-11-10) — these OVERRIDE the task text below where they conflict:**
- R1 NO DUPLICATION: `trial_stats` binds the Plan-1 `ClinicalReport` and `regulatory` binds the Plan-1
  `RegulatoryReport` directly (the drafted TrialStatsReport/DDRegulatoryReport were field-for-field
  copies; extra lens slots like moa/disease just stay null). Only 6 new DD classes.
- R2 Headline = the reused SECTION field (no second copy of the same number): financials
  `runway.runway_months`, ownership `short_interest.si_pct_float`, options `expected_move.expected_move_pct`
  — each paired with a report-level `*_source`. Hedge/analog keep report-level headlines (no section).
- R3 `Tradeability` is TARGET-LEG only (`bid/volume/oi` + `volume_source`; headline = `volume`):
  `liquidity_quote` carries one leg, so peer/spread fields would be always-null fiction.
- R4 The liquidity dim got NO data in its prompt — add `liquidity_context(liquidity_quote)` (prompt
  text only; `zero_liquidity`/`ungrounded_money`/`synthesize_verdict` unchanged).
- R5 The real-boundary uncited-finding test does not exist — ADD it (fake only SDK `query`).
- R6 Test router routes on the bound schema (`{cls: d}`), not on the first quoted dim token.
- R7 Section headers / plain-language rules must not contain "direction" (firewall leak-word test).

Purpose: legible, deep, plain-language DD output for the CEO and the downstream MD.
Output: 8 DD report contracts, 8 rewritten adversarial one-pager prompts, `run_dimension` bound
per-dim, every DD construction/fixture/seam-assertion site migrated, and a green offline suite with
the analyst half + generic seam provably untouched.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/research/analyst-report-guideline.md
@.planning/phases/07.9-structured-analyst-reports/plan1.5-research-bundle/07.9-1.5-SUMMARY.md
@.planning/phases/07.9-structured-analyst-reports/plan1-researchers/07.9-01-SUMMARY.md
@CLAUDE.md

<dd_report_schema_design>
<!-- The per-dim contract. Each DD report SUBCLASSES AnalystReportBase (base interface:
     dimension/ticker/catalyst_id/thesis[=BOTTOM LINE]/score/confidence/key_findings[>=1 cited]/
     kb_analogs_queried/unknowns + the _at_least_one_sourced_finding validator). Each adds an
     ADVERSARIAL subset of guideline sections + ONE headline number gated by a paired _source
     (a @model_validator(mode="after") mirroring Plan-1's `_headline_sourced`). REUSED = a Plan-1
     section sub-model imported/reused verbatim (no duplication). Report-level headline placement
     mirrors ClinicalReport.pos_estimate (already report-level in Plan 1). -->

| DD dim (frozen key) | Report class | Sections (REUSE from Plan 1 unless NEW) | Headline number + _source | Grounding (C5) |
|---|---|---|---|---|
| trial_stats | `TrialStatsReport` | REUSE TrialDesign, Endpoints, Efficacy, Safety + `prior_consistency: str\|None`, `key_scientific_risk: str\|None` | `pos_estimate` / `pos_estimate_source` | Bundle: trial (CT.gov phase/status/primary_endpoint/enrollment), base_rates(pos), analogs. QUALITATIVE-nullable (agent/KB): efficacy point-estimate/CI/HR/ARR/NNT, safety tables, endpoint-change — NOT in bundle. Headline anchors on base_rate(pos)+phase (deterministic). |
| regulatory | `DDRegulatoryReport` | REUSE Application, Division, PriorCrl, AdCom, LabelRisk, Poa + `regulatory_question: str\|None`, `precedent: str\|None` | `poa.point` / `poa.point_source` (reuse Poa's own pair) | Bundle: base_rates(crl_penalty, adcom_followthrough), analogs. QUALITATIVE-nullable: prior-CRL narrative, AdCom scheduling/outcome, label risk, division posture — agent/KB. Headline anchors on base_rate (deterministic); qualitative reads are MODIFIERS the agent notes, never the number's source. |
| financials | `DDFinancialsReport` | REUSE Runway, CapitalStructure, Insiders (solvency/dilution subset) | `runway_months` / `runway_months_source` (report-level) | Bundle: financials (cash/burn/shares via edgar.fundamentals) → cash_runway tool. **rNPV EXCLUDED (C5 — qualitative, not in bundle).** Headline = runway-vs-catalyst (deterministic). |
| ownership_flow | `OwnershipFlowReport` | REUSE ShortInterest, Ownership, Insiders | `short_interest_pct_float` / `short_interest_pct_float_source` (report-level) | Bundle: ownership (short_interest_pct, days_to_cover, insider_net). All deterministic. |
| options_move | `OptionsMoveReport` | REUSE ExpectedMove, ImpliedProb | `expected_move_pct` / `expected_move_pct_source` (report-level) | Bundle: options (CBOE quote) + implied_move. Headline is the straddle-implied move; **None/abstain when illiquid** (honest null — the historical-gap fallback narrative goes in thesis/findings). Deterministic. |
| hedge_revalidation | `HedgeRevalidationReport` | NEW report-level fields: `validated: bool\|None`, `covers: str\|None`, `mechanism: str\|None` | `conditional_worst` / `conditional_worst_source` (report-level) | Bundle: hedge_inputs (analog_gaps), prices → `risk.validate_hedge` (deterministic prep re-run in hedge_context). Headline = un-netted worst cell of the validated inverse hedge (or null if no valid hedge). |
| liquidity | `LiquidityReport` | NEW section `Tradeability` (extra=forbid, frozen): `target_bid/target_volume/target_oi/peer_bid/peer_volume/peer_oi/spread_pct` all `float\|None` | `worst_leg_volume` / `worst_leg_volume_source` (report-level) | Bundle: options underlying_quote → the `liquidity_quote` {bid, volume, oi}. Headline = the tighter leg's tradeable volume (0 = the `zero_liquidity` hard fail). **Do NOT reuse the `Liquidity` section — that is balance-sheet cash, a different domain.** Deterministic. |
| historical_analog | `HistoricalAnalogReport` | REUSE Analog (`analogs: list[Analog] = []`) | `analog_realized_move_pct` / `analog_realized_move_pct_source` (report-level) | Bundle: analogs (kb.analog_query realized-move precedents). Headline = median realized move of the closest DISCONFIRMING analogs. Deterministic. |

House rules (identical to Plan 1): every section sub-model `ConfigDict(extra="forbid", frozen=True)`;
every numeric/string leaf `Optional`-default-`None`; sections default-construct so an empty report is
buildable (the agent fills what it can source, leaves the rest null — "an empty slot is a finding");
each report's headline validator raises iff headline non-null AND paired `_source` empty/None.

Name-collision guard: the DD `regulatory`/`financials`/`liquidity` reports MUST be
`DDRegulatoryReport`/`DDFinancialsReport`/`LiquidityReport` — the Plan-1 `RegulatoryReport`/
`FinancialReport` names are taken (lens reports) and the `Liquidity` name is a section sub-model.
</dd_report_schema_design>

<construction_site_map>
<!-- EXHAUSTIVE. `grep 'AnalystSignal('` finds only ONE in-code DD constructor (_sig, test only);
     the real DD surface is ~13 sites (module hints + a seam router + schema-identity asserts +
     8 fixtures). Split MIGRATE (DD side) vs UNTOUCHED (analyst side / generic seam / downstream). -->

MIGRATE (DD side -> 8 new dimension reports):
- src/catalyst_trader/contracts/__init__.py            ADD 8 DD report classes + Tradeability section (AnalystSignal stays)
- src/catalyst_trader/desk/diligence.py                DD_REPORT_FOR + run_dimension bind + widen hints (run_dimension:163,
                                                        gather_dimensions:180, dimension_passed:327, synthesize_verdict:339,
                                                        _narrative_prompt:387, _narrative:403, assemble_dossier:410,
                                                        run_diligence findings) + import swap + prompt rewrites (DILIGENCE_PROMPTS +
                                                        build_dimension_prompt HARD RULES). BODY of money fns unchanged.
- tests/test_contracts.py                              ADD 8 DD-report tests (AnalystSignal tests stay)
- tests/test_desk_diligence.py                         _dd_router:74/82 (validate+route per-dim class), test_dd_fixtures:106,
                                                        _sig:311 (per-dim report), count assert:588 (schema-identity -> class membership)
- tests/fixtures/agent_responses/dd_trial_stats_signal.json         -> TrialStatsReport shape
- tests/fixtures/agent_responses/dd_regulatory_signal.json          -> DDRegulatoryReport shape
- tests/fixtures/agent_responses/dd_financials_signal.json          -> DDFinancialsReport shape
- tests/fixtures/agent_responses/dd_ownership_flow_signal.json      -> OwnershipFlowReport shape
- tests/fixtures/agent_responses/dd_options_move_signal.json        -> OptionsMoveReport shape
- tests/fixtures/agent_responses/dd_hedge_revalidation_signal.json  -> HedgeRevalidationReport shape
- tests/fixtures/agent_responses/dd_liquidity_signal.json           -> LiquidityReport shape
- tests/fixtures/agent_responses/dd_historical_analog_signal.json   -> HistoricalAnalogReport shape

UNTOUCHED (must stay green, DO NOT edit) — these PROVE the split + firewall:
- src/catalyst_trader/desk/analysts.py + the 4 lens reports (ClinicalReport/…/MarketReport) + their tests   (Plan 1 — analyst half)
- src/catalyst_trader/desk/research_bundle.py, desk/diligence_inputs.py                                       (Plan 1.5 substrate — no re-source)
- src/catalyst_trader/desk/md.py                        (reads per_dimension dicts by key — richer dicts are additive)
- src/catalyst_trader/desk/live_desk.py                 (consumes the DiligenceDossier — per_dimension stays list[dict])
- tests/test_live_desk_decision.py, tests/test_desk_md.py, tests/test_company_scan.py   (build per_dimension as raw dicts + stub run_diligence — NOT AnalystSignal; stay green)
- tests/test_desk_runtime.py + tests/fixtures/agent_responses/sample_analyst_signal.json (generic run_structured seam — AnalystSignal kept, unaffected)
- contracts.AnalystSignal + KeyFinding + their boundary tests    (AnalystSignal KEPT as the generic seam's representative contract — deleting it touches out-of-scope test_desk_runtime; ponytail: harmless, leave it)
</construction_site_map>

<tool_backing_recommendation>
STAGED analyst tool-backing (backing `build_quant_tools` with the bundle via `fact_for`) belongs in
**Plan 3, NOT Plan 2.** Justification:
- It touches the ANALYSTS' quant tools (`desk/tools.py::build_quant_tools`), an orthogonal concern to
  the DD *reports* this plan ships — mixing them violates single-concern + blows the 2-3 task budget.
- It is NOT a genuine one-liner despite `fact_for` existing: `build_quant_tools` wires 7 tool closures
  (base_rate/analog_query/query_playbooks/rnpv/cash_runway/implied_move/correlation_beta), each
  needing a `fact_for` cache-lookup + a live-compute fallback + a test proving cache-hit AND
  cite-preservation. That is its own TDD slice.
- Plan 2 stays focused: the 8 DD *reports* + wiring. DD dims already read the same free-source facts
  today (via the quant server + the bundle-backed market_data); tool-backing only changes precomputed-
  vs-live, not the report shape. Fold it into Plan 3 alongside the roll-up + consumer rewrite.
</tool_backing_recommendation>

<interfaces>
<!-- The exact contracts/consumers the executor works against. No codebase exploration needed. -->

Plan-1 base + REUSABLE sections (contracts/__init__.py) — import + subclass/reuse, do NOT re-declare:
```python
class AnalystReportBase(BaseModel):          # the debate/verifier/DD money-code interface
    model_config = ConfigDict(extra="forbid")
    dimension: str; ticker: str; catalyst_id: str
    thesis: str = Field(min_length=1)         # BOTTOM LINE, grounded in key_findings
    score: float = Field(ge=-1.0, le=1.0); confidence: float = Field(ge=0.0, le=1.0)
    key_findings: list[KeyFinding]            # >=1 sourced finding enforced by validator
    kb_analogs_queried: list[str] = []; unknowns: list[str] = []

_SECTION = ConfigDict(extra="forbid", frozen=True)   # the house config for every section sub-model
# REUSE verbatim (already defined by Plan 1): TrialDesign, Endpoints, Efficacy, Safety, Application,
#   Division, PriorCrl, AdCom, LabelRisk, Poa (point/point_source/clean_approve/approve_restricted/crl),
#   Runway, CapitalStructure, Insiders, ShortInterest, Ownership, ExpectedMove, ImpliedProb, Analog.
# Headline pattern (report-level, from ClinicalReport): pos_estimate: float|None + pos_estimate_source:
#   str|None + @model_validator(mode="after") raising if number set & source empty.
```

DD money code the reports must flow through UNCHANGED (bodies not edited — hints widen only):
```python
MONEY_TOUCHING = frozenset({"financials","ownership_flow","options_move","hedge_revalidation","liquidity"})
def dimension_passed(sig, *, params) -> bool:   # reads sig.key_findings, sig.score, sig.confidence
def synthesize_verdict(findings, *, liquidity_zero, params) -> "go"|"no_go":  # reads s.dimension, dimension_passed
def assemble_dossier(findings, verdict, narrative, *, liquidity_zero, params): # s.model_dump() -> per_dimension dict
```
`md.py::reconcile` reads `d["catalyst_id"]` from `dossier.per_dimension` (list[dict]) — the richer
`model_dump()` is additive; catalyst_id stays present. No md.py change.

run_structured seam (runtime.py) — binds ONE schema per call:
```python
async def run_structured(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet") -> BaseModel
```

run_dimension today (to migrate — currently binds AnalystSignal):
```python
async def run_dimension(dimension, input, *, mcp_servers=None, allowed_tools=None, extra_context="", model="sonnet") -> AnalystSignal:
    return await run_structured(build_dimension_prompt(dimension, input, extra_context=extra_context),
                                AnalystSignal, mcp_servers=..., allowed_tools=..., model=model)
```

test_desk_diligence.py seam router today (to migrate — routes on `schema is AnalystSignal`):
```python
signals = {d: AnalystSignal.model_validate(load_fixture(f"agent_responses/dd_{d}_signal")) for d in DD_DIMENSIONS}
async def _fake(prompt, schema, ...):
    if schema is AnalystSignal:
        for d in DD_DIMENSIONS:
            if f'"{d}"' in prompt: return signals[d]
    if schema.__name__ == "SupportCheck": return schema(supported=True, reason="ok")
    return schema.model_validate(narrative or load_fixture("agent_responses/dd_narrative"))
# _sig(dimension, ...) builds AnalystSignal(...); count assert at :588 `schema is AnalystSignal` == 8
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Define the 8 DD dimension report contracts (reuse Plan-1 sections; no duplication)</name>
  <files>src/catalyst_trader/contracts/__init__.py, tests/test_contracts.py</files>
  <behavior>
    Tests-first in tests/test_contracts.py (offline pydantic, no seam), parametrized over the 8 DD reports:
    - Each DD report validates a FULLY populated payload (its sections filled) — one representative test per dim.
    - Nullable defaults: a report built with ONLY the base interface fields (dimension/ticker/
      catalyst_id/thesis/score/confidence/key_findings/unknowns) validates, and every section numeric
      leaf reads None (never 0/fabricated). Sections default-construct.
    - extra="forbid": a hallucinated key on a DD report OR any nested section rejects.
    - Base spine preserved (inherited): empty thesis rejects (min_length=1); empty key_findings rejects
      (>=1 sourced finding); score outside [-1,1] and confidence outside [0,1] reject.
    - Headline no-fabrication (one enforceable pair per dim): headline number set + source empty ->
      reject; number null -> source may be empty; both set -> validate. The 8 pairs:
        trial_stats: pos_estimate <-> pos_estimate_source
        regulatory:  poa.point    <-> poa.point_source   (reuses Poa's own pair)
        financials:  runway_months <-> runway_months_source
        ownership_flow: short_interest_pct_float <-> short_interest_pct_float_source
        options_move: expected_move_pct <-> expected_move_pct_source
        hedge_revalidation: conditional_worst <-> conditional_worst_source
        liquidity: worst_leg_volume <-> worst_leg_volume_source
        historical_analog: analog_realized_move_pct <-> analog_realized_move_pct_source
    - C5 no-bundle-assumption (explicit test): each DD report validates with ALL qualitative fields null
      — TrialStatsReport with efficacy/safety all None, DDRegulatoryReport with prior_crl/adcom/
      label_risk all None, DDFinancialsReport carries NO rNPV field at all (assert `"rnpv" not in
      DDFinancialsReport.model_fields` and no rnpv_* leaf) — proving no headline leans on a qualitative slot.
    - Section reuse (no duplication): assert the DD reports reference the SAME class objects as Plan 1,
      e.g. `TrialStatsReport.model_fields["trial_design"].annotation is TrialDesign`,
      `DDRegulatoryReport.model_fields["poa"].annotation is Poa`,
      `HistoricalAnalogReport` analogs element type is `Analog`. (Locks NO-DUPLICATION as a test.)
    - Liquidity domain guard: assert LiquidityReport does NOT carry the balance-sheet `Liquidity`
      section (it's tradeability) — `Liquidity` is not among its section annotations.
    - AnalystSignal's + the 4 lens reports' OWN existing tests still pass unchanged (regression guard).
  </behavior>
  <action>
    In contracts/__init__.py, ADD (do NOT modify/delete AnalystSignal, KeyFinding, AnalystReportBase,
    or the 4 lens reports + their sections — REUSE the sections):

    1. ONE new section sub-model (no lens equivalent):
       `class Tradeability(BaseModel)` with `model_config = _SECTION` and leaves
       `target_bid/target_volume/target_oi/peer_bid/peer_volume/peer_oi/spread_pct: float | None = None`.
       (The DD `Liquidity` section — balance-sheet cash — must NOT be reused here; different domain.)

    2. The 8 DD dimension reports, each subclassing AnalystReportBase, REUSING the Plan-1 sections
       (see the schema table in <dd_report_schema_design>), each defaulting its sections construct-empty,
       each with ONE report-level headline number + paired *_source + a `@model_validator(mode="after")`
       named `_headline_sourced` (copy the Plan-1 shape) that raises iff the headline is non-null while
       its paired source is empty/None. Exact shapes:
         class TrialStatsReport(AnalystReportBase):
             trial_design: TrialDesign = TrialDesign(); endpoints: Endpoints = Endpoints()
             efficacy: Efficacy = Efficacy(); safety: Safety = Safety()
             prior_consistency: str | None = None; key_scientific_risk: str | None = None
             pos_estimate: float | None = None; pos_estimate_source: str | None = None
         class DDRegulatoryReport(AnalystReportBase):
             application: Application = Application(); division: Division = Division()
             prior_crl: PriorCrl = PriorCrl(); adcom: AdCom = AdCom(); label_risk: LabelRisk = LabelRisk()
             poa: Poa = Poa(); regulatory_question: str | None = None; precedent: str | None = None
             # headline = poa.point / poa.point_source (reuse Poa's own pair in the validator)
         class DDFinancialsReport(AnalystReportBase):
             runway: Runway = Runway(); capital_structure: CapitalStructure = CapitalStructure()
             insiders: Insiders = Insiders()
             runway_months: float | None = None; runway_months_source: str | None = None
             # NO rnpv field — C5 (rNPV is qualitative, not in the bundle)
         class OwnershipFlowReport(AnalystReportBase):
             short_interest: ShortInterest = ShortInterest(); ownership: Ownership = Ownership()
             insiders: Insiders = Insiders()
             short_interest_pct_float: float | None = None; short_interest_pct_float_source: str | None = None
         class OptionsMoveReport(AnalystReportBase):
             expected_move: ExpectedMove = ExpectedMove(); implied_prob: ImpliedProb = ImpliedProb()
             expected_move_pct: float | None = None; expected_move_pct_source: str | None = None
         class HedgeRevalidationReport(AnalystReportBase):
             validated: bool | None = None; covers: str | None = None; mechanism: str | None = None
             conditional_worst: float | None = None; conditional_worst_source: str | None = None
         class LiquidityReport(AnalystReportBase):
             tradeability: Tradeability = Tradeability()
             worst_leg_volume: float | None = None; worst_leg_volume_source: str | None = None
         class HistoricalAnalogReport(AnalystReportBase):
             analogs: list[Analog] = []
             analog_realized_move_pct: float | None = None; analog_realized_move_pct_source: str | None = None

    # ponytail: 8 plain subclasses reusing existing sections + 1 new Tradeability + 1 tiny validator each.
    #           NO builder/factory/registry; nullable-default IS the "empty slot is a finding" rule.
    #           rNPV is ABSENT (not None) on DDFinancialsReport — C5, so a bundle-less headline is impossible.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_contracts.py -x -q</automated>
  </verify>
  <done>All 8 DD reports validate full + empty payloads, default section numerics to None, reject
  extras/bad base fields, enforce the headline paired-source, reuse the Plan-1 section classes (asserted
  by identity), carry NO rNPV (C5), and keep the balance-sheet Liquidity section out of the DD liquidity
  report; AnalystSignal + the 4 lens reports remain green.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Rewrite the 8 adversarial one-pager prompts + bind run_dimension per-dim + migrate fixtures</name>
  <files>src/catalyst_trader/desk/diligence.py, tests/test_desk_diligence.py, tests/fixtures/agent_responses/dd_trial_stats_signal.json, tests/fixtures/agent_responses/dd_regulatory_signal.json, tests/fixtures/agent_responses/dd_financials_signal.json, tests/fixtures/agent_responses/dd_ownership_flow_signal.json, tests/fixtures/agent_responses/dd_options_move_signal.json, tests/fixtures/agent_responses/dd_hedge_revalidation_signal.json, tests/fixtures/agent_responses/dd_liquidity_signal.json, tests/fixtures/agent_responses/dd_historical_analog_signal.json</files>
  <behavior>
    Tests-first in tests/test_desk_diligence.py (seam faked to return the migrated per-dim fixture):
    - run_dimension(dim) returns an INSTANCE of the correct DD report class (TrialStatsReport for
      "trial_stats", DDRegulatoryReport for "regulatory", … LiquidityReport for "liquidity"), and the
      seam is bound to THAT class (captured["schema"] is that class, not AnalystSignal) — the DD schema split.
    - Base interface intact on every returned report: .dimension == dim, >=1 cited key_finding, non-empty
      adversarial thesis, unknowns surfaced.
    - build_dimension_prompt(dim) contains, per dim, the guideline's ORDERED section headers for that
      dim's adversarial subset (e.g. trial_stats: "Trial Design","Endpoints","Efficacy","Safety","Key
      Scientific Risk"; regulatory: "Application","AdCom","Label","Probability of Approval"; financials:
      "Runway","Dilution"/"Capital","Insider"; ownership_flow: "Short Interest","Insider"; options_move:
      "Expected Move","Implied"; hedge_revalidation: "Hedge"; liquidity: "Tradeab"/"Volume"; historical_analog: "Analog").
    - build_dimension_prompt carries the Plain-Language Standard (§5) as HARD RULES: assert "define"
      every term inline, every number "gets context" vs a benchmark, "lead with the bottom line", and
      "leave" unavailable numbers "null" / never fabricate.
    - PRESERVED (keep these assertions passing): the ADVERSARIAL framing ("assume the promoting desk is
      wrong"/"KILL"), "mcp__quant__", cite-or-drop (exact evidence_ref), the dimension-token mandate
      (dim emitted EXACTLY), grounded thesis (SYNTHESIS of cited findings, no new uncited claim), fill unknowns.
    - Firewall regression: build_dimension_prompt for every dim references ONLY DiligenceInput-derived
      fields — assert no desk-conclusion word leaks (reuse/extend any existing firewall assertion; a
      DebateVerdict/TradeProposal/StrategyDossier is not representable on DiligenceInput anyway).
    - The uncited-finding-rejected test still holds through the REAL run_structured (only SDK query
      faked): a payload with zero key_findings raises ValidationError at the DD report boundary.
  </behavior>
  <action>
    1. In diligence.py, rewrite each entry of DILIGENCE_PROMPTS into a full ADVERSARIAL one-pager
       TEMPLATE for its dim: keep the existing "find why this FAILS / assume the desk is wrong" persona,
       then list the guideline section headers the dim must fill (adversarial subset per the schema
       table), cue the data-point checklist ("fill each with a tool-cited number or leave it null"),
       and the dim's framework heuristic (trial_stats: statistical-vs-clinically-meaningful, HR/CI/ARR/
       NNT context, base-rate-anchored PoS; regulatory: 3-outcome PoA + AdCom concordance; financials:
       runway-vs-catalyst + dilution + insider signal, NO rNPV; ownership_flow: crowding/squeeze +
       insider direction; options_move: straddle-implied move + IV-crush, abstain-if-illiquid;
       hedge_revalidation: validated-inverse-only, conditional_worst; liquidity: tradeable-at-size,
       zero-liquidity is the only hard fail; historical_analog: disconfirming realized moves).
    2. In build_dimension_prompt, ADD the Plain-Language Standard (§5) as HARD RULES alongside the
       existing cite-or-drop / grounded-thesis / dimension-token rules (do NOT remove those): (a) define
       every technical term inline the first time; (b) every number gets context vs which benchmark,
       never bare; (c) lead with the bottom line then evidence; and restate unavailable numbers are left
       null, never fabricated. Keep the existing adversarial HARD RULES 1-5 verbatim.
    3. Add `DD_REPORT_FOR = {"trial_stats": TrialStatsReport, "regulatory": DDRegulatoryReport,
       "financials": DDFinancialsReport, "ownership_flow": OwnershipFlowReport,
       "options_move": OptionsMoveReport, "hedge_revalidation": HedgeRevalidationReport,
       "liquidity": LiquidityReport, "historical_analog": HistoricalAnalogReport}` and bind
       run_dimension: `report_cls = DD_REPORT_FOR[dimension]` then `return await run_structured(...,
       report_cls, ...)`. Change run_dimension's return annotation to AnalystReportBase. Import the 8
       report classes + AnalystReportBase from ..contracts. (Type-hint widening of the other fns is
       Task 3 — do only the run_dimension bind here so this task's tests pass.)
    4. Migrate the 8 dd_*_signal.json fixtures to the new per-dim shapes: keep their existing base fields
       (dimension/ticker/catalyst_id/thesis/score/confidence/key_findings/unknowns) VERBATIM (the money
       tests depend on score/conf/findings) and ADD each dim's section objects with a realistic mix of
       tool-cited numbers and null slots. Set each headline + its paired source consistently (e.g.
       trial_stats pos_estimate + pos_estimate_source cited to a base_rate tool ref; financials
       runway_months + source cited to cash_runway; leave qualitative slots null to demonstrate C5).
    5. Migrate test_desk_diligence.py: the `_dd_router` builds `signals` by validating each fixture
       against `DD_REPORT_FOR[d]` (not AnalystSignal) and routes on `schema in set(DD_REPORT_FOR.values())`
       (not `schema is AnalystSignal`); `test_dd_fixtures_are_valid_signals` validates against the per-dim
       class; the `_sig(dimension, ...)` builder returns `DD_REPORT_FOR[dimension](...)` (same base
       fields, add default sections); the `:588` count assert becomes membership-in-the-8-classes == 8.

    # ponytail: still a dict of 8 job strings + one f-string builder + one seam call; the only new
    #           moving part is DD_REPORT_FOR. No per-dim class hierarchy in diligence.py.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_desk_diligence.py -x -q</automated>
  </verify>
  <done>Each DD dim returns + binds its report class; the 8 prompts carry the section headers +
  Plain-Language HARD RULES while preserving adversarial framing/cite-or-drop/token/grounded-thesis;
  the 8 fixtures validate in the new shape with base fields intact; the real-boundary uncited-finding
  test still rejects; the money go/no-go tests (one-money-dim-fails, all-pass GO, zero-liquidity) stay green.</done>
</task>

<task type="auto">
  <name>Task 3: Widen remaining diligence.py hints; prove full suite green + analyst/seam/downstream untouched</name>
  <files>src/catalyst_trader/desk/diligence.py, tests/test_desk_diligence.py</files>
  <action>
    Honest typing pass + full-suite verification (the money-fn BODIES do not change).

    1. diligence.py: widen the type hints that read `list[AnalystSignal]` / `AnalystSignal` to
       `list[AnalystReportBase]` / `AnalystReportBase` in: dimension_passed (sig param),
       synthesize_verdict (findings), _narrative_prompt (findings), _narrative (findings),
       assemble_dossier (findings), gather_dimensions (return), run_diligence (findings local). These
       are duck-typed bodies — NO logic change (Money/sizing math UNTOUCHED). Drop the now-unused
       `AnalystSignal` import from diligence.py (mirrors analysts.py dropping it in Plan 1); keep the
       AnalystReportBase + 8 report-class imports from Task 2.
    2. Update the diligence.py module docstring line(s) that say "Returns 8 cited AnalystSignals" to
       "8 cited per-dimension reports" (doc honesty; no behavior).
    3. Run the FULL offline suite. Fix only genuine breakage introduced by the migration (expected: any
       remaining test_desk_diligence.py reference to AnalystSignal for a DD dim). DO NOT touch:
       analysts.py + the 4 lens reports + their tests; research_bundle.py / diligence_inputs.py;
       md.py / live_desk.py; test_live_desk_decision.py / test_desk_md.py / test_company_scan.py
       (they build per_dimension as raw dicts + stub run_diligence — must stay green as-is);
       test_desk_runtime.py + sample_analyst_signal.json; the AnalystSignal/KeyFinding contracts.
    4. Prove the split + firewall (record in SUMMARY):
       - `grep -n AnalystSignal src/catalyst_trader/desk/diligence.py` returns NOTHING (DD fully off the shared contract).
       - `git diff --stat` shows NO changes under analysts.py, research_bundle.py, diligence_inputs.py,
         md.py, live_desk.py, test_desk_runtime.py, sample_analyst_signal.json, or the 4 lens-report tests.
       - run_diligence still takes ONLY `input: DiligenceInput` for trade facts (firewall signature intact).
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/ -q</automated>
  </verify>
  <done>Full offline suite green. The 8 DD dims run end-to-end on their per-dim reports (gather ->
  synthesize_verdict -> narrative -> assemble -> enforce -> md); the money math is byte-unchanged; the
  4 lens reports + generic runtime seam + the bundle substrate + downstream md/live_desk are provably
  untouched; the firewall signature (DiligenceInput-only) holds.</done>
</task>

</tasks>

<verification>
- `.venv/bin/python -m pytest tests/ -q` is green (offline; run_structured/query monkeypatched, zero live LLM).
- `grep -n AnalystSignal src/catalyst_trader/desk/diligence.py` returns nothing (DD off the shared contract).
- `grep -n AnalystSignal src/catalyst_trader/desk/analysts.py` still returns nothing (Plan 1 state intact).
- `git diff --stat` shows NO changes under analysts.py, research_bundle.py, diligence_inputs.py, md.py,
  live_desk.py, test_desk_runtime.py, sample_analyst_signal.json, or the 4 lens-report tests/fixtures.
- Each of the 8 DD reports validates a full payload, defaults every unsourced number to None, enforces
  its headline paired-source, reuses the Plan-1 section classes (identity-asserted), and carries no rNPV (C5).
- `synthesize_verdict` / `dimension_passed` bodies are byte-unchanged (only hints widened) — the
  one-money-dim-fails, all-pass-GO, and zero-liquidity money tests stay green.
</verification>

<success_criteria>
- The 8 locked DD dimensions emit dimension-specific structured one-pagers (adversarial guideline
  subset + §5 Plain-Language enforced as HARD RULES + numbers null-by-default, never fabricated).
- The schema split is clean: new DD report contracts added by REUSING the Plan-1 sections (no
  duplication), run_dimension bound per-dim, every DD construction/fixture/seam-assertion site migrated.
- The firewall is preserved as a TYPE invariant (run_dimension assembled ONLY from DiligenceInput; no
  independent re-pull — LOCKED #1); DD reads the bundle's cited facts and forms its verdict independently.
- C5 honored: no DD headline number depends on a qualitative fact; rNPV is ABSENT from DDFinancialsReport;
  qualitative slots (prior-CRL/AdCom/label/efficacy/safety) exist but are nullable, agent/KB-sourced.
- Money/sizing math untouched; the downstream duck-typed interface (dimension/thesis/score/confidence/
  key_findings/unknowns) and per_dimension dicts flow unchanged (md/live_desk green).
- CALL-01 advanced for the DD dims (Plan 3 = roll-up + consumer rewrite + analyst tool-backing).
</success_criteria>

<output>
After completion, create `.planning/phases/07.9-structured-analyst-reports/plan2-dd-reports/07.9-2-SUMMARY.md`
</output>
