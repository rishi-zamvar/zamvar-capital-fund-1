---
phase: 07.9-structured-analyst-reports
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - src/catalyst_trader/contracts/__init__.py
  - src/catalyst_trader/desk/analysts.py
  - src/catalyst_trader/desk/debate.py
  - tests/test_contracts.py
  - tests/test_desk_analysts.py
  - tests/test_desk_orchestrator.py
  - tests/test_desk_debate.py
  - tests/test_desk_verifier.py
  - tests/test_backtest_layerb.py
  - tests/fixtures/agent_responses/clinical_signal.json
  - tests/fixtures/agent_responses/regulatory_signal.json
  - tests/fixtures/agent_responses/financial_signal.json
  - tests/fixtures/agent_responses/market_sentiment_signal.json
autonomous: true
requirements: [CALL-01]
must_haves:
  truths:
    - "Each of the 4 catalyst-call analysts (clinical/regulatory/financial/market_sentiment) emits a lens-specific structured report carrying the guideline's ordered sections + nullable data-point fields."
    - "A number the analyst could not source is null (default None), never fabricated; the lens headline verdict number, when asserted non-null, carries a non-empty paired source string."
    - "Each lens report still carries thesis (the BOTTOM LINE), score, confidence, cited key_findings, and unknowns, so debate + verifier consume it unchanged."
    - "The 8 diligence dimensions still validate & run on the UNCHANGED AnalystSignal — diligence.py and every dd_*_signal fixture are untouched and green."
    - "The whole desk test suite runs offline (run_structured monkeypatched, zero live LLM) and is green."
  artifacts:
    - path: "src/catalyst_trader/contracts/__init__.py"
      provides: "AnalystReportBase + ClinicalReport/RegulatoryReport/FinancialReport/MarketReport + per-section sub-models (guideline §7); AnalystSignal kept intact for the DD dims."
      contains: "class ClinicalReport"
    - path: "src/catalyst_trader/desk/analysts.py"
      provides: "4 one-pager PROMPT templates + Plain-Language HARD RULES in build_prompt + run_analyst mapping dimension -> lens report class"
      contains: "REPORT_FOR"
    - path: "tests/fixtures/agent_responses/clinical_signal.json"
      provides: "A schema-valid ClinicalReport fixture in the new shape"
      contains: "clinical"
  key_links:
    - from: "src/catalyst_trader/desk/analysts.py::run_analyst"
      to: "src/catalyst_trader/desk/runtime.py::run_structured"
      via: "binds the per-dimension lens report class (NOT AnalystSignal) as the output schema"
      pattern: "run_structured\\(.*REPORT_FOR|run_structured\\(.*report_cls"
    - from: "src/catalyst_trader/desk/debate.py::_evidence_context"
      to: "the lens reports"
      via: "duck-reads .dimension/.thesis/.score/.confidence/.key_findings/.unknowns (base interface preserved)"
      pattern: "s\\.thesis|s\\.key_findings"
    - from: "src/catalyst_trader/desk/diligence.py::run_dimension"
      to: "src/catalyst_trader/contracts/__init__.py::AnalystSignal"
      via: "still binds AnalystSignal — decoupled import, UNTOUCHED this plan"
      pattern: "AnalystSignal"
---

<objective>
Restructure the 4 CATALYST-CALL analysts (clinical / regulatory / financial / market_sentiment)
to emit the structured, data-rich, plain-language one-pager defined in
`.planning/research/analyst-report-guideline.md` (§1-4 sections, §5 Plain-Language Standard,
§7 JSON schema) — replacing the thin shared `AnalystSignal` for these 4 analysts only.

The hard problem is the **schema split**: `AnalystSignal` is shared today by BOTH the 4 analysts
(`analysts.run_analyst`) AND the 8 DD dimensions (`diligence.run_dimension`). This plan gives the
4 analysts a NEW richer per-lens contract while the 8 DD dims KEEP `AnalystSignal` (Plan 2 migrates
them). The decoupling is already clean in the source: `diligence.py` imports and binds `AnalystSignal`
independently of `analysts.py`, so we ADD the new contracts + re-point ONLY `analysts.py` and its
consumers — `diligence.py` is not touched.

Purpose: legible, deeper, plain-language analyst output for the CEO and the downstream debate/DD/MD.
Output: 4 lens report contracts (guideline §7), 4 rewritten one-pager prompts, run_analyst bound to
the lens classes, every migrated analyst construction/fixture site, and a green offline suite with the
DD half provably untouched.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/research/analyst-report-guideline.md
@CLAUDE.md

<interfaces>
<!-- The exact contracts/consumers the executor works against. No codebase exploration needed. -->

CURRENT shared contract (contracts/__init__.py) — KEEP verbatim; DD dims still use it:
```python
class KeyFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim: str
    evidence_ref: str = Field(min_length=1)   # no source -> reject
    source_url: str | None = None

class AnalystSignal(BaseModel):               # UNCHANGED — Plan 2 migrates the DD dims off this
    model_config = ConfigDict(extra="forbid")
    dimension: str
    ticker: str
    catalyst_id: str
    thesis: str = Field(min_length=1)
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    key_findings: list[KeyFinding]            # >=1 sourced finding enforced by validator
    kb_analogs_queried: list[str] = []
    unknowns: list[str] = []
```

The DOWNSTREAM interface the new lens reports MUST preserve (why the base keeps these fields):
- debate.py `_evidence_context(signals)` reads: `s.dimension`, `s.thesis`, `s.score`, `s.confidence`,
  `s.key_findings` (each `.claim`, `.evidence_ref`), `s.unknowns`.
- verifier.py `_claim_for(ref, signals)` reads: `sig.key_findings` (each `.evidence_ref`, `.claim`).
- Both are DUCK-TYPED (type hints only, no runtime isinstance) — passing lens-report subclasses works.

run_structured seam (runtime.py) — binds ONE schema per call:
```python
async def run_structured(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet") -> BaseModel
```

analysts.run_analyst today (to migrate):
```python
async def run_analyst(dimension, catalyst, *, mcp_servers=None, allowed_tools=None, model="sonnet") -> AnalystSignal:
    prompt = build_prompt(dimension, catalyst)
    return await run_structured(prompt, AnalystSignal, mcp_servers=..., allowed_tools=..., model=model)
```

orchestrator.run_desk fans the 4 dims out and passes signals -> debate.run -> verifier.enforce.
DIMENSIONS = list(analysts.PROMPTS). No run_desk logic change is required (duck-typed) — but its
TESTS assert `schema is AnalystSignal`, which must be migrated (see Task 3).
</interfaces>

<construction_site_map>
<!-- EXHAUSTIVE. `grep 'AnalystSignal('` finds only 4 in-code constructors; the real analyst-side
     surface is ~15 sites because most are model_validate(fixture) + `schema is AnalystSignal`
     seam-router assertions. Split into MIGRATE (analyst side) vs UNTOUCHED (DD side / generic seam). -->

MIGRATE (analyst side -> new lens reports):
- src/catalyst_trader/contracts/__init__.py            ADD the lens contracts (AnalystSignal stays)
- src/catalyst_trader/desk/analysts.py                 rewrite PROMPTS + build_prompt + run_analyst
- src/catalyst_trader/desk/debate.py                   widen type hints base|lens (runtime already duck-typed)
- tests/test_contracts.py                              ADD lens-report tests (AnalystSignal tests stay)
- tests/test_desk_analysts.py                          isinstance/schema-identity + prompt-content assertions
- tests/test_desk_orchestrator.py:40,49,88,112         seam router keyed by dim + count==4 assertion
- tests/test_backtest_layerb.py:34,43                  seam router (schema is AnalystSignal)
- tests/test_desk_debate.py:24,30                       2 in-code AnalystSignal(...) -> lens reports
- tests/test_desk_verifier.py:38                        1 in-code AnalystSignal(...) -> a lens report
- tests/fixtures/agent_responses/clinical_signal.json          -> ClinicalReport shape
- tests/fixtures/agent_responses/regulatory_signal.json        -> RegulatoryReport shape
- tests/fixtures/agent_responses/financial_signal.json         -> FinancialReport shape
- tests/fixtures/agent_responses/market_sentiment_signal.json  -> MarketReport shape

UNTOUCHED (DD side + generic seam) — must stay green, DO NOT edit:
- src/catalyst_trader/desk/diligence.py                (imports+binds AnalystSignal independently)
- tests/test_desk_diligence.py:82,311,588             (DD seam router + 1 constructor + count==8)
- tests/fixtures/agent_responses/dd_*_signal.json (all 8)
- tests/test_desk_runtime.py + fixtures/agent_responses/sample_analyst_signal.json
  (generic run_structured seam test — AnalystSignal still exists, so this is unaffected)
- AnalystSignal + KeyFinding contracts and their existing test_contracts.py boundary tests
</construction_site_map>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Define the 4 lens report contracts (guideline §7) — the schema split</name>
  <files>src/catalyst_trader/contracts/__init__.py, tests/test_contracts.py</files>
  <behavior>
    Tests-first in tests/test_contracts.py (offline pydantic, no seam):
    - Each lens report (ClinicalReport/RegulatoryReport/FinancialReport/MarketReport) validates a
      FULLY populated payload (all §7 sections filled) — one representative test per lens.
    - Nullable numerics default to None when omitted: a report built with ONLY the base interface
      fields (dimension/ticker/catalyst_id/thesis/score/confidence/key_findings/unknowns) + empty
      section objects validates, and every numeric leaf reads None (never 0/fabricated).
    - extra="forbid": a hallucinated key on a lens report OR any nested section rejects.
    - Base interface preserved: missing/empty thesis rejects (min_length=1); empty key_findings
      rejects (>=1 sourced finding); score outside [-1,1] and confidence outside [0,1] reject —
      i.e. the same anti-hallucination spine as AnalystSignal, on the base class.
    - No-fabrication rule (the enforceable slice of §7 "a number carries a paired _source"):
      when a lens's HEADLINE verdict number is non-null it MUST carry a non-empty paired source
      string, else ValidationError. Headline pairs, one per lens:
        clinical: pos_estimate  <-> pos_estimate_source
        regulatory: poa.point   <-> poa.point_source
        financial: rnpv.rnpv_m  <-> rnpv.rnpv_source
        market: asymmetry.ev_pct<-> asymmetry.ev_source
      (Test: headline number set + source empty -> reject; number null -> source may be empty; both
      set -> validate.) Do NOT try to police all ~30 numbers — this one enforceable pair per lens is
      the "where enforceable" carve-out.
    - AnalystSignal's OWN existing tests still pass unchanged (regression guard that the split kept
      the shared contract intact for the DD dims).
  </behavior>
  <action>
    In contracts/__init__.py, ADD (do NOT modify or delete AnalystSignal / KeyFinding — the 8 DD
    dims still bind AnalystSignal until Plan 2):

    1. `class AnalystReportBase(BaseModel)` with model_config extra="forbid" carrying the DOWNSTREAM
       interface fields verbatim from AnalystSignal: dimension, ticker, catalyst_id,
       thesis: str = Field(min_length=1)  # the BOTTOM LINE, grounded in key_findings,
       score: float [-1,1], confidence: float [0,1], key_findings: list[KeyFinding],
       kb_analogs_queried: list[str] = [], unknowns: list[str] = [].
       Reuse AnalystSignal's `_at_least_one_sourced_finding` validator (copy it onto the base).
       This base IS the debate/verifier contract — those consumers read exactly these fields.

    2. Per-section sub-models faithful to guideline §7, each ConfigDict(extra="forbid", frozen=True),
       EVERY numeric leaf `Optional` (`int | None = None` / `float | None = None`) and string leaf
       `str | None = None` unless it is a base interface field. Faithful section maps:
         Clinical: DiseaseUnmetNeed, Moa, TrialDesign, Endpoints, Efficacy, Safety
           (+ prior_consistency: str|None, key_scientific_risk: str|None,
            pos_estimate: float|None, pos_estimate_source: str|None)
         Regulatory: Application, Division, PriorCrl, AdCom, LabelRisk, Poa(point/point_source
            + scenarios: clean_approve/approve_restricted/crl each float|None)
           (+ regulatory_question: str|None, precedent: str|None)
         Financial: Liquidity, Runway, CapitalStructure, FinancingRound (list[FinancingRound]=[]),
            Insiders, Rnpv(rnpv_m/rnpv_source + peak_sales_m/pos/net_price/addressable_pop/
            penetration_pct/loe_date/discount_rate)
           (+ signal_synthesis: str|None)
         Market: RunUp, ExpectedMove, ImpliedProb, ShortInterest, Ownership, Sentiment,
            Analog (list[Analog]=[]), Asymmetry(ev_pct/ev_source + position_size_pct/driver/expression)
       Populate the leaf fields from the §7 JSON sketch (implement per fields, not verbatim). Keep
       section objects themselves REQUIRED on the report but default-constructible (each section is a
       sub-model whose fields all default None) so an empty report is buildable — analysts fill what
       they can source, leave the rest null.

    3. The 4 lens reports subclass AnalystReportBase, each adding its typed sections:
         class ClinicalReport(AnalystReportBase):   clinical sections ...
         class RegulatoryReport(AnalystReportBase):  regulatory sections ...
         class FinancialReport(AnalystReportBase):   financial sections ...
         class MarketReport(AnalystReportBase):      market sections ...

    4. The headline no-fabrication invariant: on each lens report add a `@model_validator(mode="after")`
       that raises if its headline number (list above) is not None while its paired *_source string is
       empty/None. One tiny validator per lens; message names the pair. (This is the machine-enforceable
       reflection of §7's "every number carries a paired _source" — applied to the load-bearing verdict
       number only, per the "where enforceable" scope.)

    # ponytail: plain pydantic sub-models straight from §7 — no builder, no factory, no registry.
    #           Nullable-by-default IS the "empty slot is a finding" rule; no runtime null-filling code.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_contracts.py -x -q</automated>
  </verify>
  <done>All 4 lens reports validate a full payload, default numerics to None, reject extras / bad
  base fields / a non-null headline number with an empty source; AnalystSignal's own tests remain
  green (the DD-shared contract is intact).</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Rewrite the 4 one-pager prompts + bind run_analyst to the lens classes</name>
  <files>src/catalyst_trader/desk/analysts.py, tests/test_desk_analysts.py, tests/fixtures/agent_responses/clinical_signal.json, tests/fixtures/agent_responses/regulatory_signal.json, tests/fixtures/agent_responses/financial_signal.json, tests/fixtures/agent_responses/market_sentiment_signal.json</files>
  <behavior>
    Tests-first in tests/test_desk_analysts.py (seam faked to return the migrated lens fixture):
    - run_analyst(dim) returns an INSTANCE of the correct lens report class (ClinicalReport for
      "clinical", etc.), and the seam is bound to THAT class (captured["schema"] is ClinicalReport,
      not AnalystSignal) — proves the schema split at the seam.
    - Each returned report keeps the base interface: .dimension == dim, >=1 cited key_finding,
      non-empty thesis (bottom line), unknowns surfaced.
    - build_prompt(dim) contains, per lens, the guideline's ORDERED section headers (e.g. clinical:
      "Bottom Line", "Trial Design", "Efficacy", "Safety", "Key Scientific Risk"; regulatory:
      "Application", "AdCom", "Label", "Probability of Approval"; financial: "Runway", "rNPV",
      "Insider"; market: "Expected Move", "Implied", "Short Interest", "Asymmetry").
    - build_prompt contains the Plain-Language Standard as HARD RULES: assert the three rules are
      present — "define" every term inline the first time, every number "gets context" vs a benchmark,
      and "lead with the bottom line". Also assert "leave" unavailable numbers "null" / never fabricate.
    - PRESERVED from the current prompt (keep these assertions passing): "mcp__quant__", the persona
      keyword per dim (clinically meaningful / regulatory counsel / CFO / microstructure), grounded
      thesis ("cited key_findings"), cite-or-drop, and the depth directive ("one level deeper",
      "second-order", "no new uncited claim", evidence_ref + dropped).
    - The uncited-finding-rejected test still holds through the REAL run_structured (only SDK query
      faked): a payload with zero key_findings raises ValidationError at the lens-report boundary.
  </behavior>
  <action>
    1. In analysts.py, rewrite each entry of PROMPTS into the full one-pager TEMPLATE for its lens:
       list the guideline §1-4 (A) ordered section headers the analyst must fill, cue the (B) data-point
       checklist ("fill each with a tool-cited number or leave it null"), and the (C) framework heuristic
       (clinical: statistical vs clinically-meaningful, HR/CI/ARR/NNT context; regulatory: 3-outcome
       PoA + AdCom concordance; financial: runway-vs-catalyst + rNPV + financing/insider signal;
       market: expected move / IV-crush / implied-prob / asymmetry). Keep each persona's distinctive
       named voice + keyword.
    2. In build_prompt, ADD the Plain-Language Standard (§5) as HARD RULES alongside the existing
       cite-or-drop / grounded-thesis / depth rules (do not remove those): (a) define every technical
       term inline the first time; (b) every number gets context — good/bad vs which benchmark, never a
       bare number; (c) lead with the bottom line then the evidence; and restate that unavailable numbers
       are left null and never fabricated (an empty slot is a finding). Keep the existing HARD RULES 1-6
       verbatim.
    3. Map dimension -> lens report class and bind it:
         REPORT_FOR = {"clinical": ClinicalReport, "regulatory": RegulatoryReport,
                       "financial": FinancialReport, "market_sentiment": MarketReport}
       run_analyst: `report_cls = REPORT_FOR[dimension]` then
       `return await run_structured(prompt, report_cls, mcp_servers=..., allowed_tools=..., model=model)`.
       Change the return annotation to AnalystReportBase. Import the lens classes from ..contracts;
       DROP the AnalystSignal import from analysts.py (it no longer binds it).
    4. Migrate the 4 fixtures (clinical/regulatory/financial/market_sentiment_signal.json) to the new
       lens shapes: keep their existing base fields (dimension/ticker/catalyst_id/thesis/score/
       confidence/key_findings/unknowns) and ADD each lens's section objects with a realistic mix of
       tool-cited numbers and null slots (demonstrating "empty slot = finding"). Set the headline
       number + its paired source consistently (e.g. clinical pos_estimate + pos_estimate_source cited
       to a base_rate tool ref).

    # ponytail: still a dict of 4 job strings + one f-string builder + one seam call — the only new
    #           moving part is REPORT_FOR. No per-lens class hierarchy in analysts.py.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_desk_analysts.py -x -q</automated>
  </verify>
  <done>Each analyst returns + binds its lens report class; the prompts carry the section headers +
  Plain-Language HARD RULES while preserving cite-or-drop/persona/depth/grounded-thesis; the 4
  fixtures validate in the new shape; the real-boundary uncited-finding test still rejects.</done>
</task>

<task type="auto">
  <name>Task 3: Migrate the remaining consumer sites; prove desk green + DD untouched</name>
  <files>src/catalyst_trader/desk/debate.py, tests/test_desk_debate.py, tests/test_desk_verifier.py, tests/test_desk_orchestrator.py, tests/test_backtest_layerb.py</files>
  <action>
    Re-point every remaining analyst-side construction/validation site so the full desk stays green,
    and CONFIRM the DD side + generic seam are untouched.

    1. debate.py: widen the type hints that read `list[AnalystSignal]` to
       `list[AnalystReportBase]` (in `run`, `_evidence_context`, `_side_prompt` where applicable) and
       import AnalystReportBase — purely honest typing; the body is already duck-typed so no logic
       changes. (Do NOT change debate's logic — Plan 3 does the deep debate rework; Plan 1 only keeps
       it green.)
    2. tests/test_desk_debate.py:24,30 — replace the 2 in-code `AnalystSignal(...)` in SIGNALS with a
       ClinicalReport and a FinancialReport carrying the same base fields (add empty/default sections).
       Update the import.
    3. tests/test_desk_verifier.py:38 — replace the single `AnalystSignal(...)` ref->claim signal with
       a lens report (ClinicalReport) carrying the same key_findings map. Update the import.
    4. tests/test_desk_orchestrator.py — the seam router (line ~40/49) keys per dimension: route each
       dim to its lens report class + migrated `{dim}_signal` fixture, and change the count assertion
       (line ~88) + prompt filter (line ~112) from `schema is AnalystSignal` to membership in the 4
       lens classes (e.g. `schema in {ClinicalReport, RegulatoryReport, FinancialReport, MarketReport}`).
       Assert 4 analyst-schema calls as before.
    5. tests/test_backtest_layerb.py:34,43 — same seam-router migration: per-dim lens class + fixture;
       `schema is AnalystSignal` -> lens-class membership.
    6. DO NOT touch: diligence.py, test_desk_diligence.py (its AnalystSignal constructor/router/
       count==8 stay), the 8 dd_*_signal.json fixtures, test_desk_runtime.py + sample_analyst_signal.json,
       or AnalystSignal/KeyFinding. These prove the split: the DD half still rides the unchanged
       AnalystSignal.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/ -q</automated>
  </verify>
  <done>Full offline suite green. Analyst path runs on the 4 lens reports end-to-end (analysts ->
  debate -> verifier -> orchestrator -> backtest layer B); the 8 DD dims + their fixtures + the generic
  runtime seam remain on the unchanged AnalystSignal and are green — the schema split is proven by the
  DD half being untouched while the analyst half moved.</done>
</task>

</tasks>

<verification>
- `.venv/bin/python -m pytest tests/ -q` is green (offline; run_structured/query monkeypatched, zero live LLM).
- `grep -n AnalystSignal src/catalyst_trader/desk/analysts.py` returns nothing (analysts fully off the shared contract).
- `grep -n AnalystSignal src/catalyst_trader/desk/diligence.py` still binds AnalystSignal (DD untouched — Plan 2).
- `git diff --stat` shows NO changes under diligence.py, test_desk_diligence.py, dd_*_signal.json, test_desk_runtime.py, sample_analyst_signal.json.
- Each lens report validates a full guideline-§7 payload and defaults every unsourced number to None.
</verification>

<success_criteria>
- The 4 catalyst-call analysts emit lens-specific structured one-pagers (guideline §1-4 + §7), with the
  Plain-Language Standard enforced as HARD RULES in the prompt and numbers null-by-default (never fabricated).
- The schema split is clean: new lens contracts added, AnalystSignal kept intact, only analysts.py + its
  consumers re-pointed; the 8 DD dims still validate/run on AnalystSignal with zero edits.
- debate + verifier consume the richer reports unchanged (base interface preserved) and stay green.
- Every analyst-side construction/fixture/seam-assertion site is migrated; full suite green offline.
- CALL-01 satisfied for the researcher lens reports (Plan 2 = DD dims, Plan 3 = roll-up + consumers).
</success_criteria>

<output>
After completion, create `.planning/phases/07.9-structured-analyst-reports/plan1-researchers/07.9-01-SUMMARY.md`
</output>
