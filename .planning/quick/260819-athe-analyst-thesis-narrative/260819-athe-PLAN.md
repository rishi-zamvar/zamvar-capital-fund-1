---
phase: quick-260819-athe
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - src/catalyst_trader/contracts/__init__.py
  - src/catalyst_trader/desk/analysts.py
  - src/catalyst_trader/desk/diligence.py
  - src/catalyst_trader/desk/debate.py
  - tests/test_contracts.py
  - tests/test_desk_analysts.py
  - tests/test_desk_debate.py
  - tests/test_desk_verifier.py
  - tests/test_desk_diligence.py
  - tests/fixtures/agent_responses/clinical_signal.json
  - tests/fixtures/agent_responses/regulatory_signal.json
  - tests/fixtures/agent_responses/financial_signal.json
  - tests/fixtures/agent_responses/market_sentiment_signal.json
  - tests/fixtures/agent_responses/sample_analyst_signal.json
  - tests/fixtures/agent_responses/dd_financials_signal.json
  - tests/fixtures/agent_responses/dd_hedge_revalidation_signal.json
  - tests/fixtures/agent_responses/dd_historical_analog_signal.json
  - tests/fixtures/agent_responses/dd_liquidity_signal.json
  - tests/fixtures/agent_responses/dd_options_move_signal.json
  - tests/fixtures/agent_responses/dd_ownership_flow_signal.json
  - tests/fixtures/agent_responses/dd_regulatory_signal.json
  - tests/fixtures/agent_responses/dd_trial_stats_signal.json
autonomous: true
requirements: [CALL-01, CALL-02]

must_haves:
  truths:
    - "Every AnalystSignal carries a non-empty synthesized `thesis` — a 1-3 sentence dimension-specific read of the catalyst — required at the schema boundary (a citation-free-of-thesis signal is rejected by model_validate)."
    - "Each of the 4 analyst prompts instructs the model to LEAD with a thesis that SYNTHESIZES its own cited key_findings and introduces no new uncited claim (cite-or-drop grounding inherited, not bypassed)."
    - "The bull/bear/moderator debate sees each analyst's stated thesis (not just the raw findings) so the debate argues coherent per-dimension views."
    - "The 8 diligence-dimension signals (shared AnalystSignal schema) also carry a grounded thesis, and the DD prompt requests it."
    - "All existing desk suites stay green offline (no live LLM): run_structured is monkeypatched everywhere; deterministic money math untouched."
  artifacts:
    - path: "src/catalyst_trader/contracts/__init__.py"
      provides: "AnalystSignal.thesis required str field"
      contains: "thesis"
    - path: "src/catalyst_trader/desk/analysts.py"
      provides: "thesis grounding rule in build_prompt"
      contains: "thesis"
    - path: "src/catalyst_trader/desk/debate.py"
      provides: "thesis surfaced in _evidence_context"
      contains: "thesis"
  key_links:
    - from: "desk/analysts.py::build_prompt"
      to: "contracts.AnalystSignal.thesis"
      via: "prompt instructs the required thesis field, grounded in own key_findings"
      pattern: "thesis"
    - from: "desk/debate.py::_evidence_context"
      to: "AnalystSignal.thesis"
      via: "s.thesis rendered as the lead line per dimension"
      pattern: "s\\.thesis"
---

<objective>
Add a synthesized `thesis` narrative to every analyst's output. Today an `AnalystSignal`
states its point-of-view IMPLICITLY (spread across cited `key_findings`). The CEO wants each
analyst to LEAD with an explicit 1-3 sentence dimension-specific "here's my read of this
catalyst" — stated with the signal's own score/confidence, and backed by (not replacing) the
cited findings.

Purpose: make each analyst's stance legible up front and make the bull/bear debate argue four
coherent stated theses instead of reconstructing a view from scattered findings.

Output: a required `thesis: str` on `AnalystSignal`; the 4 analyst prompts (and the shared
diligence prompt) instruct a findings-grounded thesis; the debate surfaces it; every existing
construction/fixture updated; all suites green offline.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md

<interfaces>
<!-- Exact contract + seam the executor works against. Use directly — no exploration needed. -->

contracts/__init__.py::AnalystSignal (Pydantic v2, model_config = ConfigDict(extra="forbid")):
```python
class AnalystSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dimension: str
    ticker: str
    catalyst_id: str
    score: float = Field(ge=-1.0, le=1.0)     # bearish..bullish
    confidence: float = Field(ge=0.0, le=1.0)
    key_findings: list[KeyFinding]            # validator: at least one; each has evidence_ref (min_length=1)
    kb_analogs_queried: list[str] = []
    unknowns: list[str] = []
    # ADD: thesis: str  (required, non-empty)
```
Note: `DebateVerdict` ALSO has a `thesis` field — distinct model, no collision.

analysts.py::build_prompt(dimension, catalyst) -> str  # 4 PROMPTS dict + shared HARD RULES f-string
diligence.py::build_dimension_prompt(dimension, input, *, extra_context="") -> str  # 8 DD dims, SAME AnalystSignal schema via run_structured
debate.py::_evidence_context(signals: list[AnalystSignal]) -> str  # flattens signals into shared bull/bear/moderator context

run_structured seam (monkeypatched in every desk test — NEVER hits a live LLM):
```python
async def _fake(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet"): ...
```
</interfaces>

<construction_sites>
<!-- EVERY place an AnalystSignal is built or validated. ALL need the new required field. -->
In-code (Python) — 4 sites:
  - tests/test_desk_debate.py:24  (SIGNALS[0], clinical)
  - tests/test_desk_debate.py:29  (SIGNALS[1], financial)
  - tests/test_desk_verifier.py:38  (_signal helper)
  - tests/test_desk_diligence.py:299 (_sig helper)

JSON fixtures validated via AnalystSignal.model_validate — 13 sites (all in tests/fixtures/agent_responses/):
  clinical_signal, regulatory_signal, financial_signal, market_sentiment_signal, sample_analyst_signal,
  dd_financials_signal, dd_hedge_revalidation_signal, dd_historical_analog_signal, dd_liquidity_signal,
  dd_options_move_signal, dd_ownership_flow_signal, dd_regulatory_signal, dd_trial_stats_signal
  (consumed by test_desk_analysts.py, test_desk_runtime.py, test_desk_diligence.py)
</construction_sites>

<design_decisions>
1. REQUIRED, not optional-with-default. Rationale: the CEO wants a thesis on EVERY signal; a
   `thesis: str = ""` default lets structured-output silently skip it. `extra="forbid"` + required
   forces the model to emit it. Backward-compat risk is LOW and fully contained: no AnalystSignal is
   persisted to the DB or serialized to disk outside tests — every consumer (orchestrator -> debate ->
   verifier) passes it in-memory. The blast radius is exactly the 4 code sites + 13 fixtures above.

2. GROUNDING = inheritance, not a new verification pass. The thesis is a SYNTHESIS of the analyst's
   OWN key_findings, which are already cite-or-drop (schema requires >=1 finding, each with a non-empty
   evidence_ref). The prompt rule: "your thesis must restate what your cited findings already say —
   introduce NO claim that is not in a cited key_finding." Because it adds no new evidence_ref, it
   inherits the findings' grounding. => The VERIFIER NEEDS NO CHANGE. verifier.enforce gates
   DebateVerdict.evidence_refs (not the analyst thesis); treating the analyst thesis as an independently
   verifiable claim would be redundant work on evidence its findings already carry. Do NOT add a thesis
   verification pass.

3. DEBATE change is ADDITIVE. _evidence_context already renders each signal; prepend the thesis as the
   lead line per dimension. _side_prompt/_moderator_prompt read the same `evidence` string, so bull, bear,
   and moderator all inherit it with no signature change and no new call.
</design_decisions>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add required AnalystSignal.thesis + grounded-thesis prompts + update all constructions/fixtures</name>
  <files>src/catalyst_trader/contracts/__init__.py, src/catalyst_trader/desk/analysts.py, src/catalyst_trader/desk/diligence.py, tests/test_contracts.py, tests/test_desk_analysts.py, tests/test_desk_verifier.py, tests/test_desk_diligence.py, tests/test_desk_debate.py, tests/fixtures/agent_responses/*_signal.json</files>
  <behavior>
    - RED (contract): AnalystSignal WITHOUT a `thesis` fails model_validate (missing required field);
      WITH `thesis=""` fails (must be non-empty); WITH a real thesis validates. Add these to test_contracts.py.
    - RED (prompt): analysts.build_prompt(dimension, catalyst) contains an instruction to emit a `thesis`
      that synthesizes the signal's own cited findings (assert the word "thesis" + a grounding phrase appears,
      for each of the 4 dimensions). Add to test_desk_analysts.py. Same one-line assertion for
      diligence.build_dimension_prompt in test_desk_diligence.py.
    - GREEN then keeps the whole affected suite green once fixtures/constructions carry the field.
  </behavior>
  <action>
    Implement CALL-01 thesis output. Steps:

    1. contracts/__init__.py — add to AnalystSignal, immediately after `catalyst_id`:
       `thesis: str = Field(min_length=1)  # synthesized dimension-specific read; grounded in key_findings (CALL-01)`
       (min_length=1 mirrors KeyFinding.evidence_ref — a required, non-empty synthesis, no default that lets
       the model skip it. Per design decision #1.)

    2. analysts.py::build_prompt — add ONE numbered HARD RULE (grounding rule, decision #2). Insert as a new
       rule (renumber is unnecessary — append as rule 5), worded exactly to enforce inheritance:
       "5. Emit a `thesis`: 1-3 sentences stating your dimension-specific read of this catalyst ("here is my
        read"), consistent with your score/confidence. It MUST be a SYNTHESIS of your own cited key_findings —
        do NOT introduce any claim that is not already in a cited finding (the thesis inherits their grounding;
        it is not a new uncited assertion)."

    3. diligence.py::build_dimension_prompt — add the SAME rule 5 text (the DD dimensions share the AnalystSignal
       schema via run_structured, so the field is required for them too; without the instruction the model gets an
       unexplained required field). Adversarial framing already lives in DILIGENCE_PROMPTS — no other change.

    4. Update the 4 in-code constructions (add a plausible, findings-consistent thesis string):
       - test_desk_debate.py SIGNALS[0] (clinical, score=0.5): e.g. thesis="The science supports a positive
         readout: the pivotal endpoint was met with strong significance."
       - test_desk_debate.py SIGNALS[1] (financial, score=-0.3): e.g. thesis="Financially fragile into the event:
         cash runway lapses just after the PDUFA, raising dilution risk."
       - test_desk_verifier.py::_signal helper (clinical): add a thesis kwarg (a short synthesis line).
       - test_desk_diligence.py::_sig helper: add a generic thesis kwarg so every dimension gets one.

    5. Update all 13 AnalystSignal JSON fixtures in tests/fixtures/agent_responses/ (listed in
       <construction_sites>) — add a `"thesis": "..."` key to each, a 1-3 sentence line coherent with that
       fixture's dimension/score/findings. Keep them short and grounded in the fixture's existing findings.

    Do NOT touch verifier.py (decision #2) or any deterministic money/sizing path (narrative-output change only).
    No new magic numbers. Reuse the min_length=1 pattern already in the file (no new constant).
  </action>
  <verify>
    <automated>cd "/Users/rishizamvar/Documents/Projects/Zamvar Capital/Fund 1 Strategy" && .venv/bin/python -m pytest tests/test_contracts.py tests/test_desk_analysts.py tests/test_desk_diligence.py tests/test_desk_runtime.py tests/test_desk_verifier.py -q</automated>
  </verify>
  <done>AnalystSignal requires a non-empty thesis; the 4 analyst prompts + the DD prompt instruct a
  findings-grounded thesis; all 4 code constructions + 13 fixtures carry it; the listed suites pass offline.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Surface each analyst's thesis in the bull/bear/moderator debate (additive)</name>
  <files>src/catalyst_trader/desk/debate.py, tests/test_desk_debate.py</files>
  <behavior>
    - RED: after debate.run(SIGNALS, ...), the bull prompt AND the bear prompt AND the moderator prompt each
      contain each signal's thesis text (assert `SIGNALS[0].thesis in prompt` for a captured bull/bear/moderator
      prompt). The seam already records prompts via `calls` — reuse that pattern.
    - Confirm the change is ADDITIVE: the existing context-isolation assertions (scratchpad never crosses) still pass.
  </behavior>
  <action>
    In debate.py::_evidence_context, prepend the thesis as the lead line for each signal so bull/bear/moderator
    argue the STATED per-dimension view, not just raw findings. Change the per-signal block from:
      `lines.append(f"[{s.dimension}] score={s.score:+.2f} confidence={s.confidence:.2f}")`
    to lead with the thesis, e.g.:
      `lines.append(f"[{s.dimension}] THESIS: {s.thesis}")`
      `lines.append(f"  score={s.score:+.2f} confidence={s.confidence:.2f}")`
    (keep findings + unknowns lines as-is). This is the only change — `evidence` flows unchanged into
    _side_prompt and _moderator_prompt, so all three consumers inherit the thesis with no signature change.

    VERIFIER: no change (design decision #2). The analyst thesis is a synthesis of already-cited findings and
    introduces no evidence_ref; verifier.enforce gates DebateVerdict.evidence_refs and is unaffected. Confirm by
    keeping test_desk_verifier green.

    Add the RED test to test_desk_debate.py using the existing `_seam`/`calls` capture pattern.
    Offline only — run_structured stays monkeypatched. No money math touched.
  </action>
  <verify>
    <automated>cd "/Users/rishizamvar/Documents/Projects/Zamvar Capital/Fund 1 Strategy" && .venv/bin/python -m pytest tests/test_desk_debate.py tests/test_desk_verifier.py -q</automated>
  </verify>
  <done>Each analyst's thesis appears in the bull, bear, and moderator prompts; context-isolation and
  verifier suites remain green; verifier code unchanged.</done>
</task>

</tasks>

<verification>
Full offline suite passes (no live LLM anywhere — run_structured monkeypatched):
`cd "/Users/rishizamvar/Documents/Projects/Zamvar Capital/Fund 1 Strategy" && .venv/bin/python -m pytest tests/ -q`
Focus suites: test_contracts, test_desk_analysts, test_desk_debate, test_desk_verifier, test_desk_diligence,
test_desk_runtime, test_desk_orchestrator, test_company_scan.
</verification>

<success_criteria>
- AnalystSignal.thesis is required + non-empty (missing or "" rejected at model_validate).
- The 4 analyst prompts + the DD prompt instruct a 1-3 sentence, findings-grounded thesis (no new uncited claim).
- The debate surfaces each analyst's thesis to bull, bear, and moderator.
- All 17 constructions (4 code + 13 fixtures) updated; entire test suite green offline.
- verifier.py and all deterministic money/sizing code unchanged.
</success_criteria>

<output>
After completion, create `.planning/quick/260819-athe-analyst-thesis-narrative/260819-athe-SUMMARY.md`.
</output>
