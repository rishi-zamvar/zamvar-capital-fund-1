---
phase: quick-260819-pers
plan: 01
type: tdd
wave: 1
depends_on: []
files_modified:
  - src/catalyst_trader/desk/analysts.py
  - tests/test_desk_analysts.py
autonomous: true
requirements: [CALL-01]
must_haves:
  truths:
    - "Each of the 4 analyst prompts reads as a distinct named expert (physician-scientist / FDA regulatory counsel / CFO / buy-side PM), not a generic job label"
    - "build_prompt carries a shared DEPTH DIRECTIVE mandating one-level-deeper WHY + a non-obvious second-order insight"
    - "The DEPTH DIRECTIVE is explicitly subordinate to cite-or-drop: a novel insight with no tool evidence_ref is dropped"
    - "The pre-existing cite-or-drop HARD RULE (rule 2) and grounded-thesis rule (rule 5) are preserved verbatim"
    - "build_prompt still emits the dimension token, ticker, catalyst_id and mcp__quant__ tool mandate"
    - "All change is prompt-string only; AnalystSignal schema and money/sizing paths are untouched; the 8 DD dimensions (diligence.build_dimension_prompt) are NOT touched"
  artifacts:
    - path: src/catalyst_trader/desk/analysts.py
      provides: "4 expert-persona PROMPTS + shared DEPTH DIRECTIVE in build_prompt HARD RULES"
      contains: "DEPTH"
    - path: tests/test_desk_analysts.py
      provides: "offline asserts: per-dim persona keyword + depth directive + cite-or-drop subordination + preserved invariants"
  key_links:
    - from: "build_prompt DEPTH DIRECTIVE"
      to: "cite-or-drop HARD RULE (rule 2)"
      via: "explicit subordination clause ('an insight without a supporting tool evidence_ref is dropped')"
      pattern: "evidence_ref.*dropped|no new uncited"
---

<objective>
Deepen the 4 analyst agents from generic job strings into distinct top-expert personas that
reason to the WHY — a deeper INTERPRETATION of tool-cited facts, never a new uncited claim.

- clinical -> physician-scientist (MD/PhD): mechanism, trial-design validity, clinically
  (not just statistically) meaningful endpoint, causal plausibility of the efficacy signal.
- regulatory -> FDA regulatory counsel (lawyer): the actual FDA deficiency/ask, review-pathway
  + precedent, AdCom voting dynamics and what a panel vote does/doesn't legally bind, guidance
  interpretation — the procedural WHY.
- financial -> CFO: balance-sheet + runway mechanics, dilution/financing STRUCTURE, and what
  capital-markets moves (raises, ATM, insider activity) SIGNAL about management conviction.
- market_sentiment -> buy-side PM / microstructure: what's priced in, options skew + short-interest
  mechanics, who is on the other side of the trade and why.

Plus a shared DEPTH DIRECTIVE in build_prompt's HARD RULES, made EXPLICITLY subordinate to
cite-or-drop.

Purpose: richer, non-consensus, second-order insight in the `thesis`/key_findings without
opening a fabrication vector.
Output: prompt-string changes to analysts.py (PROMPTS + build_prompt), asserted offline.

SCOPE GUARDRAIL: touch ONLY the 4 analyst PROMPTS + build_prompt in desk/analysts.py. Do NOT
touch diligence.build_dimension_prompt (the 8 DD dims), the AnalystSignal schema, the already-
shipped `thesis` field/rule, or any money/sizing math.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
</execution_context>

<context>
@src/catalyst_trader/desk/analysts.py
@tests/test_desk_analysts.py

<interfaces>
build_prompt(dimension: str, catalyst) -> str  # analysts.py:52
PROMPTS: dict[str, str]  # analysts.py:21 — the 4 job strings being rewritten

Existing HARD RULES in build_prompt (analysts.py:72-88) that MUST survive the edit:
  rule 1 — mandates `mcp__quant__*` tool calls (asserted: "mcp__quant__" in prompt)
  rule 2 — cite-or-drop: "Every key_finding MUST carry the exact evidence_ref ... (cite-or-drop)"
  rule 4 — 'Emit `dimension` EXACTLY as "{dimension}"' (double-quoted token; orchestrator test
           test_desk_orchestrator.py:51 matches f'"{d}"' against the prompt — keep it)
  rule 5 — grounded thesis, contains literal phrase "cited key_findings"
           (asserted: test_prompt_mandates_grounded_thesis)
</interfaces>

<test_surface>
Enumerated — every test that asserts on the analyst prompt STRING (so none break silently):
  - tests/test_desk_analysts.py::test_prompt_mandates_quant_tools_and_dimension_token
      asserts "mcp__quant__", "clinical", "ACME"  -> PRESERVED by rules 1/4 + ticker
  - tests/test_desk_analysts.py::test_prompt_mandates_grounded_thesis
      asserts "thesis", "cited key_findings"  -> PRESERVED by rule 5 (keep phrase verbatim)
  - tests/test_desk_orchestrator.py:51
      matches f'"{d}"' (dimension in double quotes) -> PRESERVED by rule 4
  - tests/test_desk_debate.py / test_desk_verifier.py
      assert on BULL/BEAR markers + the thesis FIELD VALUE, NOT the analyst job strings -> UNAFFECTED
  No existing test asserts the OLD generic wording ("CLINICAL/SCIENTIFIC analyst", etc.),
  so rewriting PROMPTS breaks nothing silently.
</test_surface>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Expert-persona PROMPTS + subordinate DEPTH DIRECTIVE (TDD)</name>
  <files>tests/test_desk_analysts.py, src/catalyst_trader/desk/analysts.py</files>
  <behavior>
    New offline asserts on build_prompt(dimension, CATALYST) (RED first, no live LLM):
    - Per-dimension persona keyword (parametrized), each distinctive to that expert:
        clinical         -> "clinically meaningful"   (physician-scientist: clinical vs statistical significance)
        regulatory       -> "regulatory counsel"      (the lawyer voice)
        financial        -> "CFO"                     (the CFO voice)
        market_sentiment -> "microstructure"          (buy-side / microstructure voice)
      (Pick the exact literal you write into each PROMPT; assert that literal.)
    - Depth directive present in EVERY dimension's prompt (it lives in shared build_prompt):
        assert "second-order" in prompt  AND  "one level deeper" (or your literal) in prompt
    - Cite-or-drop SUBORDINATION present and unambiguous:
        assert a literal like "no new uncited claim" in prompt
        assert "evidence_ref" appears in the same directive with "dropped"  (novel insight w/o ref -> dropped)
    - Preserved invariants (regression guards, keep existing tests too):
        "cite-or-drop" still in prompt; "cited key_findings" still in prompt (rule 5);
        'dimension` EXACTLY as' / the double-quoted dimension token still present (rule 4).
  </behavior>
  <action>
    Step 1 (RED): Extend tests/test_desk_analysts.py. Add a parametrized
    test_prompt_has_expert_persona (dim -> keyword table above) and a
    test_depth_directive_is_cite_or_drop_subordinate asserting the depth text AND its
    subordination clause AND that cite-or-drop/rule-5 phrasing survives. Run -> must FAIL.

    Step 2 (GREEN): Edit src/catalyst_trader/desk/analysts.py ONLY.
    (a) Rewrite the 4 PROMPTS entries into rich, distinct expert voices per <objective>. Each
        opens by naming the persona (physician-scientist MD/PhD; FDA regulatory counsel; CFO;
        buy-side PM / market-microstructure specialist) and carries a dimension-specific
        "reason to the WHY / surface the non-obvious second-order insight" mandate:
          clinical: mechanism + trial-design validity + is the endpoint CLINICALLY MEANINGFUL
                    (not just statistically significant) + causal plausibility of the signal.
          regulatory: the FDA's ACTUAL deficiency/ask + review-pathway & precedent + AdCom voting
                    dynamics and what a panel vote legally does/doesn't bind + guidance/statutory read.
          financial: runway mechanics + dilution/financing STRUCTURE + what raises/ATM/insider
                    activity SIGNAL about management conviction.
          market_sentiment: what's priced in + options skew & short-interest MECHANICS + who is on
                    the other side and why.
        Include each test's asserted persona keyword verbatim.
    (b) Add ONE shared DEPTH DIRECTIVE as a new HARD RULE in build_prompt (e.g. rule 6), worded
        so depth is a deeper INTERPRETATION of tool-cited evidence and EXPLICITLY subordinate to
        cite-or-drop. Suggested literal (keep the asserted substrings):
          "6. DEPTH: reason one level deeper than consensus — every finding states the WHY
              (mechanism / precedent / cause), and surface at least one non-obvious second-order
              insight a generalist would miss. This depth is a deeper INTERPRETATION of your
              tool-cited evidence: introduce NO new uncited claim — an insight without a supporting
              tool evidence_ref is DROPPED. This directive is subordinate to cite-or-drop (rule 2)."
        Do NOT alter rules 1-5. Keep the "# ponytail:" note honest (still a dict + one f-string).
    Run -> must PASS.

    Do NOT touch diligence.py, contracts.py, or any sizing/money module. No new magic numbers,
    no new dependency, no new function — edit the two existing string sites only.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_desk_analysts.py tests/test_desk_orchestrator.py tests/test_desk_debate.py tests/test_desk_verifier.py -q</automated>
  </verify>
  <done>
    New persona + depth + subordination asserts pass; all pre-existing analyst/orchestrator/
    debate/verifier tests stay green; change is confined to PROMPTS + build_prompt in analysts.py.
  </done>
</task>

</tasks>

<verification>
- `.venv/bin/python -m pytest tests/test_desk_analysts.py tests/test_desk_orchestrator.py tests/test_desk_debate.py tests/test_desk_verifier.py -q` all green.
- `git diff --name-only` shows ONLY src/catalyst_trader/desk/analysts.py + tests/test_desk_analysts.py.
- Manual read: each PROMPT names a distinct expert; build_prompt rule 6 subordination clause present; rules 1-5 unchanged.
</verification>

<success_criteria>
- 4 PROMPTS are distinct expert personas reasoning to the WHY.
- Shared DEPTH DIRECTIVE present in every dimension prompt, explicitly subordinate to cite-or-drop.
- cite-or-drop (rule 2) + grounded-thesis (rule 5) + dimension token (rule 4) + tool mandate (rule 1) preserved.
- DD dims, AnalystSignal schema, thesis field, and money math untouched.
- Full targeted suite green, offline (no live LLM).
</success_criteria>

<output>
After completion, create `.planning/quick/260819-pers-analyst-expert-personas/260819-pers-SUMMARY.md`
</output>
