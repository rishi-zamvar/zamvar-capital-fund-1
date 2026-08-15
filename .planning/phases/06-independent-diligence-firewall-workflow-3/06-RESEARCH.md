# Phase 6: Independent Diligence Firewall (Workflow 3) - Research

**Researched:** 2026-08-15
**Domain:** Structurally-isolated adversarial due-diligence desk (a second, firewalled multi-agent framework) over the existing quant/provider/KB/desk foundations
**Confidence:** HIGH (all reuse targets read via Graphify at their actual signatures; no new external tech)

## Summary

Phase 6 builds a SECOND desk that tries to KILL a promoted trade from raw sources, receiving only `{ticker, catalyst, pair?}`. It is 90% reuse: the analyst fan-out pattern, the `run_structured` seam, the `AnalystSignal` contract, `desk.evidence` cite-or-drop primitives, the quant MCP server, `desk.risk.validate_hedge`, `kb.analog_query`, and the `DiligenceDossier` contract all already exist and were read at source. The genuinely-new surface is small and money-critical: `contracts.DiligenceInput` (the firewall boundary), `desk/diligence.py` (8 adversarial dimension prompts + a *deterministic* asymmetric synthesizer + an LLM narrative pass + a diligence cite-or-drop gate), and a `run_diligence` entry point.

Two structural facts dominate the plan. (1) **The firewall is a pydantic + type-signature property, not a runtime check** — exactly the Phase-5 `Hedge.covers` move. `DiligenceInput` with `extra="forbid"` carrying only `{ticker, catalyst, pair?}` makes any Workflow-1/2 field *unrepresentable*; `run_diligence(input: DiligenceInput)` accepting only that type makes a leak *uncompilable*. The test is a field-denylist-disjoint assertion + an `extra="forbid"` rejection test. (2) **The asymmetry is a deterministic function, not LLM judgment** — a frozenset of money-touching dimensions + "any money-touching dimension fails → NO-GO; GO requires all money dimensions data-backed" is a pure Python function the LLM can never override, mirroring how `size_for_survival`/`validate_hedge` own the money numbers while the committee only argues.

**Raw-source ingestion is NOT built this phase** (CONTEXT deferred → Phase 7 / data-layer). Every dimension consumes values passed in through a mockable seam / the quant MCP tools, so the whole suite runs offline exactly like `test_desk_orchestrator.py` (monkeypatch `run_structured` per module with a role-router).

**Primary recommendation:** Mirror `desk/orchestrator.py::run_desk` verbatim as `run_diligence` — build the one quant MCP server, fan out 8 adversarial dimension agents (each emitting a reused `AnalystSignal`), run a *deterministic* `synthesize_verdict()` for the go/no-go asymmetry, then one opus narrative pass, then a diligence cite-or-drop gate reusing `desk.evidence` primitives. New code: 1 contract + 1 contract extension + 1 module + 1 entry point.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
1. **The FIREWALL is the crux (DILIG-01) — enforced structurally, not by convention.**
   - `run_diligence` accepts ONLY a minimal `DiligenceInput` (e.g. `{ticker, catalyst, pair?}`) — a NEW contract that STRUCTURALLY CANNOT carry Workflow-1/2 reasoning (no DebateVerdict, no TradeProposal, no bull/bear notes, no thesis). Mirror the Phase-5 discipline where a fake hedge was made unrepresentable at the pydantic boundary: here the leak is made unrepresentable by the input type + the absence of any code path from the diligence desk to Workflow-1/2 artifacts.
   - Adversarial FRAMING in every dimension prompt: the diligence desk's job is to find reasons this trade FAILS, from scratch.
   - TEST-ENFORCED: a test proves the diligence agents never receive any Workflow-1/2 field (the input type can't hold it) — the "provably never passed in" success criterion.

2. **Multi-dimensional DD from RAW sources (DILIG-02) — reuse the desk pattern; agents interpret, tools compute.** Each dimension is an analyst-style agent producing a SOURCE-CITED signal (reuse `desk/analysts.py` flat async fan-out + the single `run_structured` seam; agents NEVER do money arithmetic — deterministic tools compute). Dimensions:
   - **Trial stats / endpoints** → ClinicalTrials.gov v2 provider (existing).
   - **Regulatory precedent** → base rates + KB analogs (existing) + FDA/Federal Register free sources (data-layer).
   - **Financials / runway** → FMP provider (existing) + `quant.cash_runway` / `pipeline_value`.
   - **Ownership / flow / short interest** → FINRA free Query API + SEC EDGAR (data-layer).
   - **Options-implied move** → CBOE free delayed-quotes feed behind the pluggable `implied_move` SOURCE SEAM (from Phase 5); DD dimension takes the value IN / via a mockable provider so it's offline-testable, degrades gracefully when a name has illiquid options.
   - **Hedge / correlation re-validation** → REUSE `desk/risk.validate_hedge` + `quant.conditional_payoff` / `cointegration` (independent re-run, not trusting Workflow-2's result).
   - **Liquidity** → quote/volume checks (only zero-liquidity is a hard fail, per Fund design).
   - **Historical analog** → `kb.analog_query` (existing).

3. **Adversarial synthesizer (DILIG-03) — asymmetric, rewards NO-GO.**
   - Combines the dimensions and is DELIBERATELY ASYMMETRIC: a SINGLE failing money-touching dimension forces NO-GO (easy to kill, hard to clear). GO requires data-backed confidence across all money dimensions.
   - Emits `DiligenceDossier {go_no_go, evidence, residual_risks}` (contract exists from Phase 2 — extend only if a field is missing, mirroring the Phase-4/5 contract-extension precedent).
   - Cite-or-drop enforced (REUSE `desk/verifier` machinery): an uncited diligence claim is dropped; a NO-GO or GO must be evidence-backed.

4. **Reuse discipline (biggest cost lever).** REUSE: `desk/analysts.py` pattern, `run_structured` seam, `desk/verifier` (cite-or-drop), quant tools (`cash_runway`, `pipeline_value`, `conditional_payoff`, `cointegration`, `implied_move`, liquidity), providers (clinicaltrials, fmp), `kb.analog_query`, `desk/risk.validate_hedge`, the `DiligenceDossier` contract. NEW: `contracts.DiligenceInput` (the firewall boundary), `desk/diligence.py` (dimensions + adversarial synthesizer), a `run_diligence` orchestrator entry point. Query the Graphify graph to locate reuse targets — do NOT re-read the src/ tree.

5. **Offline + money-safety.** Fully offline: monkeypatch `run_structured`; mock providers / pass raw data in; zero live API in pytest. No path from scraped/raw content to an order (no execution in this phase). Full TDD (tests before logic, `.venv/bin/python -m pytest` — bare python NOT on PATH).

### Claude's Discretion
- Exact prompt wording per dimension (adversarial framing).
- Whether the deterministic asymmetry lives as its own pure function or inline (recommendation: its own pure function — testable in isolation, matches `size_for_survival` precedent).
- How the pass/fail per dimension is derived from the `AnalystSignal` score/confidence (recommendation below).
- Whether liquidity zero-fail is an inline boolean vs a new tiny helper (recommendation: inline boolean; not a new quant tool).

### Deferred Ideas (OUT OF SCOPE)
- Runtime guardrails / monitors (catalyst freshness, provenance, firewall enforcement at runtime, net-long caps, no-scraped-to-order) — Phase 7 (OPS-03).
- The actual web-scraper / free-data fetcher build (CBOE, FINRA, Federal Register ingestion) — data-layer component; this phase consumes values behind seams and mocks them in tests.
- Live order placement — Phase 11.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DILIG-01 | Runs on the proposed portfolio, receiving only `{ticker, catalyst, pair}` — an enforced firewall from Workflow 1/2 reasoning | NEW `contracts.DiligenceInput` (`extra="forbid"`, 3 fields) + `run_diligence(input: DiligenceInput)` type signature. Firewall test = field-denylist-disjoint assertion vs DebateVerdict/TradeProposal/StrategyDossier fields + `extra="forbid"` rejection (mirrors `test_hedge_*` unrepresentable tests). |
| DILIG-02 | Multi-dimensional DD from raw sources (8 dimensions) | 8 adversarial dimension agents over the reused `run_structured` seam + `AnalystSignal` contract; each backed by an EXISTING quant/provider/KB call (mapping table below); raw values passed in / mocked (fetchers deferred to Phase 7). |
| DILIG-03 | Synthesizer adversarially combines dimensions, rewards "no-go", requires data-backed confidence → `DiligenceDossier {go/no-go, evidence, residual risks}`; a single failing money-touching dimension forces NO-GO | NEW deterministic `synthesize_verdict(findings)` (money-touching frozenset + asymmetric rule) + LLM narrative pass + diligence cite-or-drop gate reusing `desk.evidence`. `DiligenceDossier` EXISTS; needs a `residual_risks` field added (see extension note). |
</phase_requirements>

## Reuse-vs-New Verdict (the cost lever — decided against ACTUAL signatures)

### NEW (write these)
| Item | File | Why new | Size |
|------|------|---------|------|
| `DiligenceInput` | `contracts/__init__.py` | The firewall boundary type — does not exist (Graphify: "No node matching 'DiligenceInput'"). `extra="forbid"`, fields `{ticker: str, catalyst: dict, pair: str \| None = None}`. | ~10 lines + validators |
| `DiligenceDossier.residual_risks` | `contracts/__init__.py` | Success criterion says `{go/no-go, evidence, residual_risks}`; the existing model has verdict/per_dimension/red_flags/strongest_disconfirming_evidence/all_evidence_refs but **no `residual_risks`**. Add `residual_risks: list[str] = []` (mirrors `RiskAssessment.residual_risks` / `StrategyDossier`). | 1 line |
| `desk/diligence.py` | new module | 8 adversarial dimension PROMPTS + a `build_dimension_prompt` + a thin `run_dimension` (mirrors `analysts.run_analyst`) + `synthesize_verdict()` (deterministic asymmetry) + `_narrative` synthesis + `enforce_dossier` cite-or-drop gate. | the bulk |
| `run_diligence` entry point | `desk/diligence.py` (or `orchestrator.py`) | Mirrors `run_desk`: build quant server → gather 8 dimensions → deterministic synth → opus narrative → cite-or-drop gate → `DiligenceDossier`. | ~30 lines, thin composition |

### REUSE (do NOT rebuild — confirmed signatures)
| Symbol | Location | Signature (as read) | Role in Phase 6 |
|--------|----------|---------------------|-----------------|
| `run_structured` | `desk/runtime.py:29` | `async run_structured(prompt, schema, *, mcp_servers=None, allowed_tools=None, model="sonnet")` | The ONLY SDK seam — every dimension + narrative call routes through it (monkeypatched in tests). |
| `run_analyst` / `build_prompt` pattern | `desk/analysts.py:87/52` | analyst = PROMPTS dict + `build_prompt(dim, catalyst)` + `run_structured(prompt, AnalystSignal, ...)` | COPY the shape (new PROMPTS, adversarial). `run_analyst` hard-refs `analysts.PROMPTS` (4 dims) so it can't be called verbatim for 8 new dims — write a sibling `run_dimension`. |
| `AnalystSignal` | `contracts/__init__.py:24` | `dimension, ticker, catalyst_id, score∈[-1,1], confidence∈[0,1], key_findings: list[KeyFinding], unknowns` + `_at_least_one_sourced_finding` | REUSE verbatim as each dimension's output. score/confidence drive the deterministic pass/fail. |
| `desk.evidence.resolve` / `quote_supported` / `tool_ref` | `desk/evidence.py` | resolve(conn, ref) / quote_supported(source, claim) / tool_ref(result) | REUSE primitives inside the diligence cite-or-drop gate. |
| `verifier.enforce` (as a pattern) | `desk/verifier.py:63` | `async enforce(conn, verdict: DebateVerdict, *, signals=None)` | `enforce` is typed to `DebateVerdict` (uses `.thesis`/`.evidence_refs`), so it can't gate a `DiligenceDossier` directly. MIRROR its two-stage shape (structural cite-or-drop → gated opus) exactly as `enforce_estimate` did — reuse the evidence primitives, not the function. |
| `desk.risk.validate_hedge` | `desk/risk.py:75` | `validate_hedge(conn, embed, target, catalyst, entry, exit_by_date, analog_gaps, prices) -> Hedge \| None` | The hedge/correlation dimension = an INDEPENDENT `validate_hedge` re-run; its `Hedge \| None` result is passed into that dimension agent's context (pure/deterministic, no LLM inside). |
| `quant.conditional_payoff` / `cointegration` / `correlation_beta` | `quant/pairs.py:138/42/105` | see signatures below | Used *inside* `validate_hedge` (already) — no direct call needed; expose as MCP tools only if a dimension agent must call them (currently not required). |
| `quant.cash_runway` | `quant/valuation.py:67` | `cash_runway(cash_usd, monthly_burn_usd, months_to_catalyst=None)` | Financials dimension (already registered in the quant MCP server). |
| `quant.pipeline_value` | `quant/valuation.py:99` | `pipeline_value(results: list[ToolResult])` | Financials dimension (submodule-only; not MCP-exposed — see note). |
| `quant.implied_move` | `quant/options.py:27` | `implied_move(underlying_price, call_mid=None, put_mid=None, iv=None, days_to_event=None)` | Options-implied-move dimension (already registered in MCP). Straddle wins when both legs supplied. |
| `kb.analog_query` | `kb.py:173` | `analog_query(conn, embed, context, filters: dict, k=5) -> list[dict]` | Historical-analog + regulatory-precedent dimensions (already registered in MCP). |
| `providers.clinicaltrials.fetch_trial_readouts` | `providers/clinicaltrials.py:85` | `(tickers, date_from, date_to, *, client=None, sponsor_map=None) -> list[Catalyst]` | Trial-stats dimension source (offline: `client=` a mock or values passed in). |
| `desk.tools.build_quant_server` / `build_quant_tools` | `desk/tools.py:96/39` | `build_quant_server(conn)` wraps base_rate, analog_query, query_playbooks, rnpv, cash_runway, implied_move, correlation_beta | REUSE the same server for the diligence agents. Extend the registry ONLY if a dimension agent must directly call a currently-unregistered tool (see note). |

**Net-new code estimate:** 1 contract + 1 one-line extension + 1 module (prompts + 1 deterministic function + 1 thin runner + 1 narrative + 1 gate) + 1 entry point. This is the smallest surface that satisfies DILIG-01/02/03 — matches the Phase-5 "1 tool + 1 extension + N desk modules" cost profile.

## Firewall Enforcement (DILIG-01) — the money-critical crux

### The contract shape
```python
class DiligenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")   # a leaked Workflow-1/2 field -> ValidationError
    ticker: str
    catalyst: dict          # the minimal catalyst facts {ticker, catalyst_type, event_date, catalyst_id}
    pair: str | None = None # the hedge peer ticker ONLY — never a Hedge object, never a rationale
```
`catalyst: dict` intentionally carries only the raw facts the dimensions need (the same `_get`-able shape `analysts.build_prompt` already reads). Do NOT type it as `Catalyst` if `Catalyst` carries downstream reasoning — but `Catalyst` is a data model (dates/sources), so either is safe; `dict` keeps the boundary minimal and dodges any accidental attribute. **`pair` is a bare ticker string**, never the validated `Hedge` (that would smuggle Workflow-2's `conditional_worst`/`validated` verdict across the firewall).

### Why this is structural, not conventional
- `run_diligence(input: DiligenceInput)` accepts ONLY that type. There is no parameter through which a `DebateVerdict`, `TradeProposal`, or `StrategyDossier` can enter — a leak is a type error, not a policy violation. This is the exact `Hedge.covers` discipline: make the bad state unrepresentable.
- `extra="forbid"` rejects any stray field (e.g. `thesis`, `bull_strongest_point`) at `model_validate`.
- The diligence prompts are assembled ONLY from `DiligenceInput` fields (mirror `build_prompt`, which reads only catalyst facts). No verdict/thesis is in scope to interpolate.

### The cleanest test that proves isolation (mirror `test_hedge_unvalidated_cannot_claim_idiosyncratic`)
Two complementary tests:
1. **Field-denylist-disjoint (structural, no LLM).** Assert `set(DiligenceInput.model_fields)` is disjoint from the union of `DebateVerdict`, `TradeProposal`, `StrategyDossier`, `RiskAssessment` field names (the Workflow-1/2 artifacts). Regression-guards against a future field addition re-opening the firewall. Precedent: the Phase-4 debate "denylist-disjoint" isolation test.
2. **`extra="forbid"` rejection.** `pytest.raises(ValidationError)` on `DiligenceInput(ticker=..., catalyst=..., thesis="...")` and on passing a `pair=<Hedge object>` / a dict with verdict fields — proves the leaked reasoning can't be constructed.

Optional belt-and-suspenders: a test that `run_diligence`'s signature annotation is `DiligenceInput` (via `typing.get_type_hints`) — proves no second reasoning parameter exists.

## The 8 DD Dimensions (DILIG-02) — each mapped to an EXISTING call

Each dimension is an adversarial `AnalystSignal`-emitting agent (fan-out via `asyncio.gather`, same as `run_desk`). "Money-touching" flag drives the asymmetry (col 4).

| # | Dimension | Reuses (confirmed signature) | Raw/free source (Phase-7 fetcher; Phase-6 = value-in/mock) | Offline-testable via | Money-touching? |
|---|-----------|------------------------------|------------------------------------------------------------|----------------------|-----------------|
| 1 | Trial stats / endpoints | `providers.clinicaltrials.fetch_trial_readouts` + `kb.analog_query` | ClinicalTrials.gov v2 (§4.1 — GREEN, live) | mock `client=` / pass study dict in | No (informative) |
| 2 | Regulatory precedent | `quant.base_rate` + `kb.analog_query` (both MCP-registered) | RTTNews FDA cal + Federal Register API (§2.1/2.2) | monkeypatch `run_structured`; base_rate is deterministic | No |
| 3 | Financials / runway | `quant.cash_runway` (MCP) + `quant.pipeline_value` | FMP + SEC EDGAR XBRL (§3.3/3.4) | values passed into the agent's tool call; cash_runway pure | **Yes** |
| 4 | Ownership / flow / short interest | *(no existing tool)* — agent interprets values passed in | FINRA Query API + SEC EDGAR Form 4/13F (§3.1/3.3 — GREEN) | pass SI/ownership dict in; mocked | **Yes** |
| 5 | Options-implied move | `quant.implied_move` (MCP) behind the `implied_move` SOURCE SEAM | CBOE delayed-quotes JSON (§1.1 — primary); liquidity gate §1.9 | pass call_mid/put_mid (or iv) in; **degrade gracefully** (below) | **Yes** |
| 6 | Hedge / correlation re-validation | `desk.risk.validate_hedge` (deterministic, INDEPENDENT re-run) → `conditional_payoff`+`cointegration` inside it | analog gaps + prices (KB / passed in) | pass `analog_gaps`+`prices`; `Hedge \| None` fed to agent | **Yes** |
| 7 | Liquidity | inline zero-liquidity boolean (NOT a new tool) | CBOE / Nasdaq quote+volume (§1/§4.2) | pass `{bid, volume, oi}` in | **Yes (zero-only hard fail)** |
| 8 | Historical analog | `kb.analog_query` (MCP) | KB (existing) | in-memory `db` fixture + `embed` fixture | No |

### Genuinely-NEW helper vs pure reuse
- **Pure reuse (no new helper):** dimensions 1, 2, 3, 5, 6, 8 — all backed by an existing tool/provider/KB call already in the MCP server or callable deterministically.
- **New (tiny):** dimension 4 (ownership/short-interest) and 7 (liquidity) have **no quant tool**. Neither needs one:
  - #7 liquidity: a one-line boolean `zero_liquidity = bid <= 0 or volume == 0 or oi == 0` — inline in the synthesizer/dimension. Per Fund design, **only zero-liquidity is a hard fail** (a wide-but-live quote is not a fail). Do NOT build a liquidity quant tool (YAGNI).
  - #4 ownership/short-interest: the agent INTERPRETS values passed in (SI %, days-to-cover, insider net) and cites them; no arithmetic tool needed (ratios are supplied pre-computed by the deferred fetcher). If a computed ratio is ever needed, it's a Phase-7 concern.
- **MCP registry note:** the quant server currently registers `base_rate, analog_query, query_playbooks, rnpv, cash_runway, implied_move, correlation_beta`. Dimensions 1–8 need only tools already in that set (plus deterministic `validate_hedge` outside the LLM). **No MCP registry extension is required** unless a dimension agent must directly call `cointegration`/`conditional_payoff` — it does not, because `validate_hedge` runs them deterministically and the *result* is fed in.

### Options-implied move — graceful degradation (locked)
The dimension takes `call_mid`/`put_mid` (or `iv`+`days_to_event`) IN via the pluggable seam. Apply the §1.9 liquidity gate BEFORE trusting IV: `ATM bid > 0 both legs; spread/mid < ~60%; combined OI ≥ ~100; an expiry at/after the catalyst`. Fail → tag the dimension `options_data: none/illiquid`, fall back to the in-house historical-gap estimator (existing `catalyst_move_estimate` path), and the options dimension emits low-confidence rather than junk IV. `implied_move` prefers the model-free straddle when both legs are supplied. Illiquid ≠ hard fail (that's liquidity dim #7's zero-only rule).

## Adversarial Synthesizer (DILIG-03) — deterministic asymmetry

### Encode "money-touching" + the asymmetry as a pure function (NOT LLM judgment)
```python
MONEY_TOUCHING = frozenset({"financials", "ownership_flow", "options_move",
                            "hedge_revalidation", "liquidity"})   # dims 3,4,5,6,7

def dimension_passed(sig: AnalystSignal) -> bool:
    # data-backed confidence: cited finding present + not bearish-below-threshold + confident enough
    ...

def synthesize_verdict(findings: list[AnalystSignal], liquidity_zero: bool) -> Literal["go","no_go"]:
    if liquidity_zero:
        return "no_go"                                   # zero-liquidity = hard fail
    money_fail = any(not dimension_passed(s) for s in findings if s.dimension in MONEY_TOUCHING)
    if money_fail:
        return "no_go"                                   # ONE money dim fails -> NO-GO (easy to kill)
    all_money_backed = all(dimension_passed(s) for s in findings if s.dimension in MONEY_TOUCHING)
    return "go" if all_money_backed else "no_go"         # GO requires all money dims data-backed
```
This is the `size_for_survival`/`validate_hedge` precedent: the deterministic function owns the verdict; the LLM can never flip it. **Tie/uncertainty defaults to NO-GO** — the asymmetry ("rewards no-go") is baked into the default branch. The LLM does the NARRATIVE only (`strongest_disconfirming_evidence`, `red_flags` text, `residual_risks`) via a separate `run_structured` opus call — its output CANNOT change `verdict` (mirror how `risk.assess` overwrites the money fields with `model_copy(update=...)` after the LLM synthesis).

`dimension_passed` derivation (Claude's discretion — recommended): a dimension passes when it has ≥1 cited `key_finding` AND (`score` not strongly bearish, e.g. `score > -δ`) AND `confidence ≥ min_conf`. Read `δ`/`min_conf` from params (missing-key-raises, per the Phase-3/5 "every threshold from params" convention) — do NOT hard-code numeric literals in money code.

### `DiligenceDossier` contract — does it need extension?
EXISTS (`contracts/__init__.py:185`): `verdict: Literal["go","no_go"]`, `per_dimension: list[dict]`, `red_flags: list[str]`, `strongest_disconfirming_evidence: str`, `all_evidence_refs: list[str]`. **Missing: `residual_risks`** (the success criterion literally says `{go/no-go, evidence, residual_risks}`). ADD `residual_risks: list[str] = []` (one line; mirrors `RiskAssessment.residual_risks` and `StrategyDossier`). `per_dimension: list[dict]` already carries the per-dimension evidence (serialize each `AnalystSignal` + its pass/fail); `all_evidence_refs` is "evidence"; `verdict` is go/no-go. No other change needed. `extra="forbid"` is already set.

### Cite-or-drop (reuse the primitives, mirror the shape)
`verifier.enforce` is `DebateVerdict`-typed, so write `enforce_dossier(conn, dossier, *, signals)` mirroring `enforce`/`enforce_estimate`: (1) structural — `evidence.resolve` every ref in `all_evidence_refs`; `kb:` refs also pass `quote_supported`; `tool:` refs resolved-by-construction; (2) gated opus semantic support only on load-bearing survivors. An uncited diligence claim is dropped; if a NO-GO's disconfirming evidence loses all support, that's an audit flag (a NO-GO on unsupported evidence is itself suspect). Reuse `desk.evidence` verbatim.

## Common Pitfalls

### Pitfall 1: Reusing `verifier.enforce` directly on the dossier
**What goes wrong:** `enforce(conn, verdict, ...)` calls `verdict.thesis`/`verdict.evidence_refs`/`verdict.model_copy` — `DiligenceDossier` has none of those. **Avoid:** mirror the shape (like `enforce_estimate` did), reuse only `evidence.resolve`/`quote_supported`.

### Pitfall 2: Letting the LLM set the go/no-go
**What goes wrong:** an LLM synthesis prompt that emits `verdict` lets a confident narrative override a money-dimension failure. **Avoid:** `synthesize_verdict()` is deterministic and its result OVERWRITES any LLM field via `model_copy(update={"verdict": ...})` — exactly `risk.assess`'s money-overwrite pattern.

### Pitfall 3: `pair` as a `Hedge` object (firewall leak)
**What goes wrong:** passing the validated `Hedge` as `pair` smuggles Workflow-2's `validated`/`conditional_worst` verdict across the firewall. **Avoid:** `pair: str | None` — a bare ticker; the diligence hedge dimension re-runs `validate_hedge` independently.

### Pitfall 4: Symmetric verdict logic
**What goes wrong:** "majority of dimensions pass → GO" defeats the "rewards no-go" mandate. **Avoid:** any single money-touching failure → NO-GO; GO requires ALL money dims backed; ties → NO-GO.

### Pitfall 5: Building raw-source fetchers this phase
**What goes wrong:** scope-creep into CBOE/FINRA/Federal Register scrapers (deferred to Phase 7). **Avoid:** consume values behind seams; mock in tests. No live HTTP in pytest.

## Runtime State Inventory

Not applicable — greenfield additive phase (new contract + new module + new entry point). No rename/refactor/migration. No stored data, service config, OS registrations, secrets, or build artifacts change (the `catalyst_trader.egg-info` is editable-install metadata, unaffected by adding modules). Verified: no existing `diligence` symbol in `src/`/`tests/` except the `DiligenceDossier` contract (Graphify + grep).

## Environment Availability

SKIPPED for external services — Phase 6 has NO live external dependency (all raw-source ingestion deferred to Phase 7; tests are fully offline). In-repo toolchain confirmed present:

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `.venv/bin/python` | all test/exec | ✓ | (bare `python` NOT on PATH — use `.venv/bin/python`) | — |
| pytest + pytest-asyncio | test suite (`asyncio_mode="auto"`) | ✓ | pytest 9.1.1 | — |
| Graphify | graph navigation | ✓ | 0.9.43 | — |
| claude-agent-sdk | `run_structured` seam (monkeypatched in tests) | ✓ (reused) | — | tests never hit it live |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 + pytest-asyncio (`asyncio_mode = "auto"`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths=["tests"]`) |
| Quick run command | `.venv/bin/python -m pytest tests/test_desk_diligence.py -x` |
| Full suite command | `.venv/bin/python -m pytest -q` |
| Offline recipe | monkeypatch `run_structured` per module with a role-router (copy `tests/test_desk_orchestrator.py::_router`/`_patch_seam`); fixtures: `db`, `load_fixture`, `embed` (in `conftest.py`) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| DILIG-01 | `DiligenceInput` fields disjoint from Workflow-1/2 artifact fields (denylist-disjoint) | unit | `.venv/bin/python -m pytest tests/test_contracts.py::test_diligence_input_firewall_field_disjoint -x` | ❌ Wave 0 |
| DILIG-01 | `extra="forbid"` rejects a leaked field (`thesis`/verdict field/`pair` as Hedge) | unit | `.venv/bin/python -m pytest tests/test_contracts.py::test_diligence_input_rejects_workflow_reasoning -x` | ❌ Wave 0 |
| DILIG-01 | `run_diligence` signature accepts only `DiligenceInput` (no reasoning param) | unit | `.venv/bin/python -m pytest tests/test_desk_diligence.py::test_run_diligence_signature_is_firewalled -x` | ❌ Wave 0 |
| DILIG-02 | 8 dimensions fan out concurrently via one `asyncio.gather`, each emits a cited `AnalystSignal` | integration | `.venv/bin/python -m pytest tests/test_desk_diligence.py::test_eight_dimensions_run_concurrently -x` | ❌ Wave 0 |
| DILIG-02 | Options dimension degrades on illiquid options (tag `none/illiquid`, low confidence, no junk IV) | unit | `.venv/bin/python -m pytest tests/test_desk_diligence.py::test_options_dimension_degrades_on_illiquid -x` | ❌ Wave 0 |
| DILIG-02 | Hedge dimension INDEPENDENTLY re-runs `validate_hedge` (not Workflow-2's result) | unit | `.venv/bin/python -m pytest tests/test_desk_diligence.py::test_hedge_dimension_revalidates_independently -x` | ❌ Wave 0 |
| DILIG-03 | Single money-touching failure forces NO-GO (deterministic) | unit | `.venv/bin/python -m pytest tests/test_desk_diligence.py::test_one_money_dimension_failure_forces_no_go -x` | ❌ Wave 0 |
| DILIG-03 | GO requires ALL money dimensions data-backed; ties default NO-GO | unit | `.venv/bin/python -m pytest tests/test_desk_diligence.py::test_go_requires_all_money_dimensions_backed -x` | ❌ Wave 0 |
| DILIG-03 | Zero-liquidity is a hard NO-GO fail | unit | `.venv/bin/python -m pytest tests/test_desk_diligence.py::test_zero_liquidity_hard_fails -x` | ❌ Wave 0 |
| DILIG-03 | LLM narrative cannot flip the deterministic verdict | unit | `.venv/bin/python -m pytest tests/test_desk_diligence.py::test_llm_narrative_cannot_override_verdict -x` | ❌ Wave 0 |
| DILIG-03 | Cite-or-drop: uncited dossier claim dropped; go/no-go must be evidence-backed | integration | `.venv/bin/python -m pytest tests/test_desk_diligence.py::test_dossier_cite_or_drop -x` | ❌ Wave 0 |
| DILIG-03 | `DiligenceDossier` carries `residual_risks` | unit | `.venv/bin/python -m pytest tests/test_contracts.py::test_diligence_dossier_has_residual_risks -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest tests/test_desk_diligence.py tests/test_contracts.py -x`
- **Per wave merge:** `.venv/bin/python -m pytest -q`
- **Phase gate:** full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_desk_diligence.py` — covers DILIG-01/02/03 (firewall signature, 8-dim fan-out, deterministic asymmetry, cite-or-drop). New file; copy the `_router`/`_patch_seam` offline pattern from `tests/test_desk_orchestrator.py`.
- [ ] `tests/test_contracts.py` — ADD `DiligenceInput` firewall tests + `DiligenceDossier.residual_risks` test (file exists; add cases beside the `test_hedge_*` unrepresentable precedents).
- [ ] `tests/fixtures/agent_responses/` — add recorded `AnalystSignal` fixtures for the 8 diligence dimensions + a diligence narrative fixture (mirror existing `<dim>_signal.json`).
- [ ] Framework install: none — pytest + pytest-asyncio already present.

## Sources

### Primary (HIGH confidence — read at source this session)
- Graphify graph (`graphify explain`) — confirmed `DiligenceInput` absent, `DiligenceDossier` present; located all reuse targets.
- `src/catalyst_trader/desk/runtime.py`, `analysts.py`, `verifier.py`, `risk.py`, `orchestrator.py`, `tools.py` — actual signatures + patterns.
- `src/catalyst_trader/contracts/__init__.py` — `DiligenceDossier`, `AnalystSignal`, `Hedge` (unrepresentable-state precedent).
- `src/catalyst_trader/quant/{valuation,options,pairs}.py`, `kb.py`, `providers/{clinicaltrials,fmp}.py` — tool/provider signatures.
- `tests/test_desk_orchestrator.py`, `tests/test_contracts.py`, `pyproject.toml`, `tests/conftest.py` — offline test recipe + config.
- `.planning/research/free-data-sources.md` — verified free raw sources per dimension (CBOE, FINRA, Federal Register, EDGAR, CT.gov).

### Secondary
- `.planning/phases/06-.../06-CONTEXT.md`, `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `.planning/TOKEN-NOTES.md`, `CLAUDE.md`.

## Metadata

**Confidence breakdown:**
- Reuse-vs-new verdict: HIGH — every reused signature read at source; `DiligenceInput` absence and `DiligenceDossier` shape confirmed.
- Firewall approach: HIGH — direct application of the in-repo `Hedge.covers` / debate-isolation precedents.
- Dimension→source mapping: HIGH — each backed by an existing call or a verified free source; fetchers explicitly deferred.
- Synthesizer asymmetry: HIGH — deterministic-function-owns-money precedent (`size_for_survival`/`risk.assess`) is established and reused.

**Research date:** 2026-08-15
**Valid until:** 2026-09-15 (stable — internal codebase; no fast-moving external deps this phase)
