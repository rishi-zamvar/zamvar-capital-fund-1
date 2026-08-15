# Phase 5: Trade Builder, Honest Hedge & Ruin-Avoidant Sizing (Workflow 1b/2) — Research

**Researched:** 2026-08-15
**Domain:** Turning per-catalyst DebateVerdicts into ONE survival-sized, honestly-hedged weekly portfolio + StrategyDossier, on Claude Agent SDK subagents over deterministic quant/KB tools.
**Confidence:** HIGH (stack settled; every reused symbol read from source, not training data)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (LOCKED USER DECISION 2026-08-15 — "Both: survival-size now, options-ready")
1. **Survival-first sizing is the backbone** — risk-of-ruin / fractional-Kelly on a −70% binary gap; the ~1%/week target is a MEASURED outcome, NEVER a sizing input; zero-trade weeks are allowed.
2. **Pair ONLY where mechanism AND data both validate the inverse** — the Risk agent runs `quant.conditional_payoff` (+ cointegration + catalyst-clean check) PER TRADE against KB analogs. NO hardcoded/assumed pairs (PHVS/BCRX proved same-disease ≠ hedge). If the peer doesn't reliably rise when the target falls on THIS catalyst → reject the hedge.
3. **No-valid-hedge is the DEFAULT, not the exception** — fall back to size-tiny or exit-before-event. Never a fake hedge.
4. **LABD (inverse biotech ETF) only as a sector-beta damper** for event-week, explicitly labeled as NOT hedging the idiosyncratic binary.
5. **Options-ready architecture** — model the hedge as an abstraction (a `Hedge` protocol / instrument type) so a put-option hedge slots in later WITHOUT a rewrite, even though v1 is equities-only. Do NOT build options execution now; just don't foreclose it.

### Claude's Discretion
Follow ROADMAP criteria + PROJECT.md + CLAUDE.md. Reuse Phase-3 quant tools (conditional_payoff, risk_of_ruin, fractional_kelly, cointegration, sl_tp, concentration, exposure — all return ToolResult), the Phase-2 KB hedge-relationship store + analog query, the Phase-4 DebateVerdict as input, and the contracts (TradeProposal, RiskAssessment, StrategyDossier — extend if a field is missing, mirroring the Phase-4 DebateVerdict extension). Agents interpret; the quant tools compute. Full TDD, offline (mock the run_structured seam; no live API). SL/TP is ADVISORY only.

### Deferred Ideas (OUT OF SCOPE)
- Options/put-hedge EXECUTION (architect for it, don't build it) — v2.
- Live order placement — Phase 11.
- Independent diligence on the built portfolio — Phase 6.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PORT-01 | Take the week's catalyst calls, build ONE recommended portfolio | Orchestrator-level `run_portfolio(verdicts[])`: build each trade → risk-size each → one PM pass over all candidates + open book (concentration/exposure/budget). §Architecture Pattern 1, 6 |
| PORT-02 | Trade Builder selects inverse-hedge peer, entry, hold-vs-exit, SL/TP | `desk/builder.py`: DebateVerdict → TradeProposal; peer from `kb.hedge_peers` (candidates, re-validated in Risk), `quant.sl_tp_levels(holds_through_catalyst=)`. §Trade Builder |
| PORT-03 | 3-way Risk Committee sizes for survival via risk-of-ruin; 1% is measured, never an input | `desk/risk.py` mirrors `debate.py`; deterministic `size_for_survival()` sweep over `risk_of_ruin` — no return-target param anywhere. §Sizing, §Structural Invariants |
| PORT-04 | MD/PM evaluates portfolio fit (concentration, corr to open book, budget), promote/kill | PM `run_structured` (opus) over `quant.concentration`/`exposure` on the combined book. §Portfolio Manager |
| PORT-05 | Emit a StrategyDossier | Extend `contracts.StrategyDossier`. §Contract Extensions |
| HEDGE-01 | Hedge is an inverse-payoff peer (rises when target falls), not merely correlated | `kb.hedge_peers` stores `payoff_direction` (+1/−1); builder only proposes `-1` peers as idiosyncratic hedges. §Honest Hedge |
| HEDGE-02 | Risk agent re-analyzes the hedge conditional on THIS catalyst → conditional payoff matrix | `quant.conditional_payoff` on analog gaps + `quant.cointegration` per trade. §Honest Hedge Validation |
| HEDGE-03 | Peer must be catalyst-clean over the hold window | Deterministic check against the catalyst calendar (Phase-1 store) for the peer over `[entry, exit_by_date]`. §Honest Hedge Validation |
| HEDGE-04 | No-valid-inverse-peer fallback: size-tiny or exit-before-event, never fake | `Hedge=None` path → `holds_through_catalyst=False` (exit-before) or tiny `size_pct`. Structural: unvalidated hedge cannot claim `covers="idiosyncratic"`. §Fallback |
| HEDGE-05 | Dossier states residual net-long risk + which risk is covered | `exposure().detail.net` → `residual_net_long`; `which_risk_covered ∈ {idiosyncratic, sector_beta, none}`. §Contract Extensions |
| OPS-01 | Position memo per trade with kill criteria, authorship separated from approval | Distinct `run_structured` call producing the memo BEFORE the PM decision; kill_criteria carried from DebateVerdict. §Memo & Pre-mortem |
| OPS-02 | Pre-mortem step ("assume this lost — why?") before promotion | Distinct `run_structured` call, separate from PM. §Memo & Pre-mortem |

</phase_requirements>

## Project Constraints (from CLAUDE.md / PROJECT.md / CONVENTIONS.md)

- **GSD workflow gate:** no direct edits outside a GSD command. This phase runs under `/gsd:execute-phase`.
- **TDD, exhaustive edge cases on money-critical tools (OPS-04):** tests before logic; the sizing/hedge path is money-critical → exhaustive suite.
- **Simplest codebase that works, boring over clever, minimal deps:** no new runtime dependencies needed for this phase (all math is Phase-3 quant; all orchestration is the existing `run_structured` seam). Do NOT add libraries.
- **Env-first secrets:** N/A this phase (fully offline, no API/keys).
- **Graphify:** re-index after this code-producing phase (`/graphify`).
- **Phase-completion HTML report (MANDATORY):** `docs/phase-reports/phase-05-report.html`, terminal/brass design language of `docs/architecture-workflows.html`, favicon 🧬, sections: What's done / Needs review / Going well / Next steps / Project state.
- **TOKEN-NOTES (MANDATORY):** update `.planning/TOKEN-NOTES.md` tally + carry the Directives section forward into every subagent prompt. Current directives: query the graph not the tree; reuse settled research; trim `files_to_read`; prefer the codebase map; right-size models.

## Summary

Everything this phase needs already exists and is tested — the phase is **wiring, two new desk modules, and three lean contract extensions**, not new math. The Phase-3 quant library already encodes the two locked invariants *structurally*: `risk_of_ruin` has **no return-target parameter** (so sizing can never chase 1%/week) and `conditional_payoff` returns the **un-netted worst cell** over a 2×2 catalyst branch (the honest replacement for "0.7 correlated = hedged"). `exposure()` reports **gross with abs**, so two longs can never net away their directional risk. The Phase-2 KB already stores hedge relationships with an explicit **`payoff_direction` sign (+1 co-move / −1 inverse)** and citations. The Phase-4 `DebateVerdict` already carries **`kill_criteria`** (required, non-empty). The desk already has a proven **bounded-fan-out-over-one-seam** pattern (`debate.py`) and a single monkeypatchable SDK seam (`desk.runtime.run_structured`) that makes the whole suite offline.

The work: (1) `desk/builder.py` turns a `DebateVerdict` → `TradeProposal`, selecting a candidate `-1` peer from `kb.hedge_peers`, setting entry / hold-vs-exit / advisory SL/TP; (2) `desk/risk.py` mirrors `debate.py` for a 3-way aggressive/conservative/neutral committee whose *interpretation* is LLM but whose *size* comes from a deterministic `size_for_survival()` sweep over `risk_of_ruin`; the committee re-validates the hedge per-catalyst via `conditional_payoff` + `cointegration` + a catalyst-clean calendar check, defaulting to size-tiny/exit when the inverse doesn't hold; (3) a PM pass over the week's candidates + the open book (`concentration`/`exposure`/budget) emitting `StrategyDossier`; (4) a position memo + pre-mortem authored in **separate `run_structured` calls from the approver** (OPS-01/02).

**Primary recommendation:** Build `desk/builder.py` + `desk/risk.py` + `desk/portfolio.py` mirroring `desk/debate.py`'s exact shape (flat async fan-out over `run_structured`, schema-dispatched). Extend `TradeProposal`/`RiskAssessment`/`StrategyDossier` with a `Hedge` model and the residual/coverage/memo/pre-mortem fields. Make sizing and hedge-honesty *structural* (invariant in the type/function signature, not in a prompt) exactly as Phase-3 did.

## Reused Building Blocks (verified from source — do NOT re-read the tree)

### Quant tools (`src/catalyst_trader/quant/`, all return `ToolResult`, all RAISE on bad input)

| Symbol | Signature | What it gives this phase |
|--------|-----------|--------------------------|
| `conditional_payoff` | `(target_up, target_down, peer_up, peer_down, w_target, w_peer)` | `value` = **worst 2×2 cell (un-netted)**; `detail.matrix` = all 4 branches. The catalyst-conditional hedge test (HEDGE-02). Branch moves are the **caller's** analog gaps. |
| `cointegration` | `(price_a, price_b, method="engle_granger", significance=0.05)` | `detail.cointegrated: bool`, `detail.hedge_ratio` (β). Necessary-not-sufficient for a hedge (docstring says so). ≥30 obs or raises. |
| `correlation_beta` | `(asset_returns, market_returns)` | `value`=corr, `detail.beta`. Sector-beta context only; NOT a hedge justification. |
| `risk_of_ruin` | `(p_loss, size_pct, gap=0.70, ruin_drawdown=0.5, n_trades=52)` | Exact DP (no RNG), reproducible. **NO return-target parameter — this is the structural anti-1%-coupling.** `detail.max_survivable_consecutive_losses`. |
| `kelly` | `(p_win, win_frac, loss_frac)` | `f*`, clamped ≥0 (no edge = no bet). |
| `fractional_kelly` | `(kelly_fraction, fraction=0.25)` | quarter-Kelly scale-down. |
| `sl_tp_levels` | `(entry, sl_pct, tp_pct, holds_through_catalyst=False)` | `detail.stop/target`, `value`=R:R. When `holds_through_catalyst=True` sets `detail.advisory=True` + reason (PITFALLS #2). |
| `concentration` | `(weights)` | Herfindahl Σwᵢ²; `detail.max_weight` (abs). |
| `exposure` | `(weights)` | **Gross Σ|wᵢ| (abs)**; `detail.net` = signed Σwᵢ → residual net-long (HEDGE-05). |

Import surface: `from catalyst_trader.quant import ...` (all re-exported in `quant/__init__.py`).

### KB (`src/catalyst_trader/kb.py`)

- `hedge_peers(conn, name) -> list[{peer, mechanism, payoff_direction, weight, evidence}]` — **candidate** peers with a stored `payoff_direction` sign. **Validate, don't trust:** the stored sign is a prior; HEDGE-02 requires re-validating the inverse PER catalyst.
- `analog_query(conn, embed, context, filters, k=5) -> list[{catalyst, outcome, distance}]` — nearest past scenarios (structural SQL filter → semantic KNN), each with realized Outcome. Source the **branch gaps** for `conditional_payoff` from analog outcomes.
- `insert_hedge_peer(conn, name, peer, mechanism, payoff_direction, weight, evidence)` — `payoff_direction ∈ {+1, −1}` (0 raises); citation required. Use if the phase writes back a validated relationship.
- Offline embedder: `kb.default_embedder()` / `kb.hash_embed` (tests inject `hash_embed` via the `embed` fixture).

### Contracts (`src/catalyst_trader/contracts/__init__.py`, pydantic v2, `extra="forbid"`)

- `DebateVerdict` (Phase-4 input) — carries `direction: "positive"|"negative"`, `confidence`, `bull_strongest_point`, `bear_strongest_point`, `unresolved_dissent[]`, `evidence_refs[]`, **`kill_criteria[]` (required non-empty)**. The kill criteria flow into the position memo (OPS-01) for free.
- `TradeProposal`, `RiskAssessment`, `PortfolioContext`, `StrategyDossier` — exist but are **thin**; extend them (see §Contract Extensions). The module comment already licenses this: *"extend a model when a layer needs a field, don't pre-add speculative ones."*

### Desk machinery (`src/catalyst_trader/desk/`)

- **`runtime.run_structured(prompt, schema, *, mcp_servers, allowed_tools, model="sonnet")`** — the ONE SDK seam. Binds `schema.model_json_schema()` to `output_format`, `model_validate`s the return, retries once on `ValidationError`. **Every new role call routes through this** → whole phase tests offline via one monkeypatch.
- **`debate.run(signals, catalyst, rounds=MAX_ROUNDS)`** — the pattern to mirror for the risk committee: bounded loop of isolated `run_structured` calls (bull/bear), then a synthesis call (moderator, `model="opus"`) → validated contract. `MAX_ROUNDS = 2`.
- **`verifier.enforce(conn, verdict, signals=)`** — two-stage source-quote-or-drop gate. The dossier's evidence_refs can be gated the same way before finalize (reuse, don't rebuild).
- **`orchestrator.run_desk(conn, catalyst)`** — composition example (`gather` analysts → `debate.run` → `verifier.enforce`). Workflow-1b's entry (`run_portfolio`) is the analogous thin composition.
- **`tools.build_quant_server(conn)` / `build_quant_tools(conn)`** — wraps quant/KB as ONE in-process MCP server named `"quant"`; every tool is `mcp__quant__<name>`. If the risk/builder agents need to CALL tools (vs. the Python layer computing), extend the wrapped subset here (the comment flags `cointegration` as "add here when a desk role needs it").
- **`evidence.tool_ref(result)` / `tool_ref_for(name, inputs)`** — mint resolvable `tool:<name>#<hash>` citations for quant-derived numbers (the sizing/payoff numbers in the dossier).

## Architecture Patterns

### Recommended module layout (mirror the org chart, one file per role — as ARCHITECTURE.md prescribes)
```
src/catalyst_trader/desk/
├── builder.py      # DebateVerdict -> TradeProposal (peer pick, entry, hold-vs-exit, advisory SL/TP)   [PORT-02, HEDGE-01]
├── risk.py         # 3-way committee (mirror debate.py) + deterministic size_for_survival()            [PORT-03, HEDGE-02..04]
├── portfolio.py    # PM: week's candidates + open book -> StrategyDossier; memo + pre-mortem           [PORT-01,04,05, OPS-01,02, HEDGE-05]
└── (runtime.py, debate.py, tools.py, evidence.py, verifier.py — REUSE)
```
`ponytail: three files, each a thin fan-out over run_structured + deterministic quant calls. No config object, no strategy registry, no base "Layer" class — debate.py has none of those and does the same job.`

### Pattern 1: Deterministic sizing, LLM interpretation (the load-bearing separation)
**What:** The 3-way committee agents *argue* p_loss, gap magnitude, and hedge validity from analogs; a **deterministic `size_for_survival()`** turns those into `size_pct`. The size is ALWAYS a quant-tool output, never an LLM number.
**Shape:**
```python
# desk/risk.py — deterministic, no return-target anywhere (mirrors risk_of_ruin's own design)
def size_for_survival(p_loss: float, gap: float = 0.70,
                      ruin_cap: float = 0.02, per_event_cap: float = 0.03,
                      n_trades: int = 52) -> ToolResult:
    """Largest size_pct whose risk_of_ruin(p_loss, size_pct, gap) <= ruin_cap,
    also clamped to per_event_cap. Sweep size downward; NO 1%/return-target input.
    Returns the chosen size + the risk_of_ruin snapshot as its citation."""
```
**Why structural:** the function *cannot* take a return target — there is no parameter for one, exactly like `risk_of_ruin` deliberately omits it. A test asserts the signature has no `target`/`return` param (see §Structural Invariants).

### Pattern 2: Honest hedge as a validated abstraction (options-ready)
**What:** A `Hedge` model with an `instrument` discriminator so a put slots in later with zero rewrite; `validated` + `covers` make fake hedges *unrepresentable*.
```python
# contracts/__init__.py
class Hedge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instrument: Literal["equity_peer", "inverse_etf", "put_option"]  # put_option reserved; NOT executed in v1
    ticker: str
    payoff_direction: int                       # +1 co-move, -1 inverse (from kb.hedge_peers)
    validated: bool                             # passed conditional_payoff + cointegration + catalyst-clean THIS catalyst
    covers: Literal["idiosyncratic", "sector_beta", "none"]
    mechanism: str
    conditional_worst: float                    # quant.conditional_payoff value (un-netted worst cell)

    @field_validator("covers")
    @classmethod
    def _honest_coverage(cls, v, info):
        # a hedge may claim to cover the idiosyncratic binary ONLY if it validated as inverse this catalyst
        if v == "idiosyncratic" and not (info.data.get("validated") and info.data.get("payoff_direction") == -1):
            raise ValueError("only a validated inverse peer may claim to cover idiosyncratic risk (HEDGE-01/04)")
        if info.data.get("instrument") == "put_option":
            raise ValueError("put_option hedges are architected but not executable in v1 (deferred)")
        return v
```
- `equity_peer` + `validated=True` + `payoff_direction=-1` → `covers="idiosyncratic"`.
- `inverse_etf` (LABD) → `covers="sector_beta"` ALWAYS, never idiosyncratic (locked decision #4). Enforce in the builder, and the validator blocks the illegal claim.
- No valid hedge → `Hedge=None` on the proposal → fallback (HEDGE-04).
- `put_option` is a legal enum value (options-ready) but the validator refuses to *execute/promote* it in v1 — the shape exists, the path is closed. `ponytail: enum member + one guard = the whole "abstraction", no protocol class, no factory.`

### Pattern 3: Authorship separated from approval (OPS-01/02)
**What:** The position memo and the pre-mortem are produced by `run_structured` calls **distinct from** the PM promote/kill call. Separation is structural: different call, different prompt, produced *before* the decision and fed *into* it.
**Test:** count/label the seam calls — assert memo+pre-mortem calls precede and are separate from the PM decision call.

### Pattern 4: Portfolio-level pass over the WEEK (PORT-01)
`run_portfolio(conn, verdicts: list[DebateVerdict], open_book) -> list[StrategyDossier]`:
1. `builder.build(v)` for each verdict → candidate `TradeProposal[]`.
2. `risk.assess(proposal, catalyst, conn)` for each → `RiskAssessment` (+ size + hedge validity).
3. ONE PM pass sees ALL candidates + the open book: `concentration(all_weights)`, `exposure(all_weights).detail.net`, weekly budget remaining → promote a subset, kill the rest → `StrategyDossier[]`.
Zero-trade weeks are a valid output (empty promote set) — assert that's not an error (PITFALLS #5).

### Anti-patterns to avoid (from PITFALLS.md — these are total-loss-capable)
- **Peer long counted as a hedge without conditional re-validation** (Pitfall 1). Enforce via `Hedge.validated` + `conditional_payoff`.
- **Sizing coupled to the 1% target** (Pitfall 5). Enforce via `size_for_survival` having no target param.
- **Stop shown as bounded loss on a held-through position** (Pitfall 2). `sl_tp_levels(holds_through_catalyst=True)` marks it advisory; dossier must display `-70%` gap risk, not stop distance.
- **Netting two longs to hide gross** (Pitfall 1). Always report `exposure()` gross + `.detail.net` residual.
- **Over-trading to fill a weekly quota** (Pitfall 5). PM may promote zero.

## Contract Extensions

Mirror the Phase-4 `DebateVerdict` extension (it gained `kill_criteria` + a validator). Add only fields a specific req needs.

**`TradeProposal`** — replace `hedge_long: str` with the structured hedge; add hold/exit + catalyst id:
```
+ hedge: Hedge | None            # None => fallback (size-tiny/exit), HEDGE-04
+ holds_through_catalyst: bool    # False = exit-before-event default (PITFALLS #2, HEDGE-04)
+ catalyst_id: str
+ direction: Literal["positive","negative"]   # carried from DebateVerdict
  (keep: target_long, pair_rationale, entry, exit_by_date, stop_loss, take_profit, size_pct, expected_return_pct, kb_analogs)
  stop_loss/take_profit stay but are ADVISORY when holds_through_catalyst — note in field docs.
```
`ponytail: hedge_long:str -> hedge:Hedge|None is the one real change; the rest are 3 scalar adds.`

**`RiskAssessment`** — add the conditional-payoff evidence + the survival size:
```
+ conditional_payoff_matrix: dict     # quant.conditional_payoff detail.matrix (HEDGE-02)
+ conditional_worst: float            # the un-netted worst cell that sizing sized against
+ hedge_valid: bool                   # inverse held THIS catalyst? (HEDGE-01/04)
+ recommended_size_pct: float         # from size_for_survival — the quant number, not the LLM's
+ ruin_at_size: float                 # risk_of_ruin at the chosen size (audit)
  (keep the existing aggressive/conservative/neutral views + residual_risks)
```

**`StrategyDossier`** — add the OPS + HEDGE-05 disclosures:
```
+ residual_net_long: float            # exposure().detail.net over the promoted book (HEDGE-05)
+ which_risk_covered: Literal["idiosyncratic","sector_beta","none"]   # HEDGE-05
+ position_memo: str                  # OPS-01 (authored in a separate call)
+ pre_mortem: list[str]               # OPS-02 ("assume it lost — why")
+ kill_criteria: list[str]            # carried from DebateVerdict, required non-empty
```

## Honest Hedge Validation (the crux — HEDGE-01..05)

Per candidate trade, the Risk committee runs a deterministic gate (LLM interprets, tools decide):
1. **Candidate peers:** `kb.hedge_peers(conn, target)` → keep only `payoff_direction == -1` for idiosyncratic-hedge consideration. (`+1` peers are conviction longs, never hedges — PITFALLS #1.)
2. **Inverse holds THIS catalyst (HEDGE-02):** pull branch gaps from `kb.analog_query` (target's analog outcomes + the peer's read-through), feed `conditional_payoff(target_up, target_down, peer_up, peer_down, w_target, w_peer)`. The **worst cell** must be materially better than the un-hedged target-alone worst case, AND the peer must fall (`peer_down < 0`) in the `target_down` branch. If not → not a hedge.
3. **Cointegration (necessary, not sufficient):** `cointegration(price_a, price_b)` → `detail.cointegrated` must be True and `hedge_ratio` sane. Cointegration alone never qualifies a hedge (docstring is explicit) — it's a gate, conditional_payoff is the decider.
4. **Catalyst-clean over the hold (HEDGE-03):** query the Phase-1 catalyst calendar/store for the peer over `[entry, exit_by_date]`; any own PDUFA/readout/earnings/M&A → peer disqualified (its own binary contaminates the hedge).
5. **Set `Hedge.validated`** = (2 ∧ 3 ∧ 4). `covers` follows: validated inverse peer → `idiosyncratic`; LABD inverse-ETF → `sector_beta` (never idiosyncratic); else the trade takes the **fallback**.

### Fallback (HEDGE-04 — the DEFAULT, not the exception)
No validated inverse peer → `TradeProposal.hedge = None` and either:
- **Exit-before-event** (`holds_through_catalyst=False`) — converts binary-gap risk to drift risk (PITFALLS #2 preferred default), or
- **Size-tiny** (`size_for_survival` with a low `per_event_cap`) if holding through is chosen.
Never fabricate a hedge. The `Hedge.covers` validator makes a fake idiosyncratic claim raise at the contract boundary — the fallback is structurally the path of least resistance.

### Residual disclosure (HEDGE-05)
`exposure(promoted_weights).detail.net` → `residual_net_long`; `which_risk_covered` is `idiosyncratic` only if a validated inverse peer is in the trade, `sector_beta` if only LABD, else `none`. Dossier states both explicitly.

## Sizing for Survival (PORT-03)

- Drive size ENTIRELY from `size_for_survival()` → `risk_of_ruin` (no return target). `p_loss` from base rates / analog outcomes (cite it); `gap` default 0.70 (worse for illiquid names — take the analog's actual downside gap when available, or the options-implied move as a magnitude prior per PITFALLS #10).
- Hard caps: `per_event_cap` (e.g. ≤2–3% of account, PITFALLS #5) and a portfolio heat cap enforced at the PM pass via `concentration`.
- **1% is a MEASURED outcome:** compute `expected_return_pct` for display only; it must never feed back into `size_pct`. Structural: `size_for_survival` doesn't accept it.
- Zero-trade weeks allowed: if no size clears the ruin cap at any acceptable edge, size = fallback-tiny or the PM kills it.

## Memo & Pre-mortem (OPS-01/02)

- **Position memo** (`run_structured`, its own call): thesis + entry/exit + advisory SL/TP + **kill_criteria carried from the DebateVerdict** + which risk is covered / residual net-long. Authored BEFORE and SEPARATELY from the PM decision (author ≠ approver).
- **Pre-mortem** (`run_structured`, its own call): "assume this position lost — enumerate why" → `pre_mortem: list[str]`. Feeds the PM but is not the PM.
- **PM promote/kill** (`run_structured`, `model="opus"`): reads the memo + pre-mortem + RiskAssessment + portfolio context → `StrategyDossier.decision`. Distinctness is the OPS-01/02 guarantee; test by asserting the memo/pre-mortem seam calls are separate from and precede the PM call.

## Deterministic Offline Testing (mock the run_structured seam)

Exactly the established pattern (verified in `tests/test_desk_debate.py`, `test_desk_orchestrator.py`):
- **Monkeypatch `run_structured`** on the module under test with a fake that dispatches on `schema` (and/or role text in `prompt`) and returns fixtures. `monkeypatch.setattr(risk, "run_structured", _fake)`.
- **Quant tools run for real** — they're deterministic and already tested in Phase 3; assert the size/matrix numbers exactly.
- **KB uses the in-memory `db` fixture + `hash_embed`** (the `embed` fixture) — offline, no ML dep.
- **Agent-response fixtures** live in `tests/fixtures/agent_responses/*.json` (add `trade_builder_proposal`, `risk_aggressive`, `risk_conservative`, `risk_neutral`, `risk_synthesis`, `position_memo`, `pre_mortem`, `pm_dossier`).
- pytest 9.1.1, `asyncio_mode=auto` (async tests need no decorator). Run under `.venv`.

## Structural Invariants (TDD — must be enforced in types/signatures, like Phase-3)

These are the "no return-target param" class of guarantee — the reason the design is trustworthy without reading a prompt:

1. **Sizing cannot chase a return target.** `size_for_survival` signature has no `target`/`return`/`weekly` parameter. `test_size_for_survival_has_no_return_target_param` (introspect `inspect.signature`). Mirrors the existing `risk_of_ruin` guarantee.
2. **A fake hedge is unrepresentable.** `Hedge(covers="idiosyncratic", validated=False)` raises. `test_unvalidated_hedge_cannot_claim_idiosyncratic`.
3. **LABD is never an idiosyncratic hedge.** `Hedge(instrument="inverse_etf", covers="idiosyncratic")` raises (or builder forces `sector_beta`). `test_inverse_etf_is_sector_beta_only`.
4. **Two longs never net away.** `exposure` gross uses abs; `residual_net_long` = `.detail.net`; dossier shows gross ≥ |net|. `test_dossier_reports_gross_not_netted`.
5. **Options are architected, not executed.** `put_option` is a valid enum member but promoting it raises in v1. `test_put_option_hedge_reserved_not_promotable`.
6. **Held-through stop is advisory.** `sl_tp_levels(holds_through_catalyst=True).detail.advisory is True`; dossier never shows stop distance as max loss. `test_held_through_stop_is_advisory`.
7. **Zero-trade week is valid.** `run_portfolio` returning all-kill is success, not error. `test_zero_trade_week_allowed`.
8. **Author ≠ approver.** memo + pre-mortem seam calls are separate from and precede the PM call. `test_memo_and_premortem_authored_separately_from_pm`.

## Validation Architecture (Nyquist)

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 + pytest-asyncio (`asyncio_mode=auto`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`testpaths=["tests"]`, `addopts="-ra"`) |
| Quick run command | `.venv/bin/python -m pytest tests/test_desk_builder.py tests/test_desk_risk.py -x -q` |
| Full suite command | `.venv/bin/python -m pytest -q` (currently 498 tests green) |

### Phase Requirements → Test Map
| Req | Behavior | Type | Automated Command | File |
|-----|----------|------|-------------------|------|
| PORT-01 | Week's verdicts → one portfolio; zero-trade allowed | unit | `.venv/bin/python -m pytest tests/test_desk_portfolio.py -k "week or zero_trade" -x` | ❌ Wave 0 |
| PORT-02 | Verdict → TradeProposal (peer, entry, hold-vs-exit, advisory SL/TP) | unit | `.venv/bin/python -m pytest tests/test_desk_builder.py -x` | ❌ Wave 0 |
| PORT-03 | Committee sizes via risk-of-ruin; no return-target coupling | unit | `.venv/bin/python -m pytest tests/test_desk_risk.py -k "size or ruin or no_return_target" -x` | ❌ Wave 0 |
| PORT-04 | PM promote/kill on concentration/exposure/budget | unit | `.venv/bin/python -m pytest tests/test_desk_portfolio.py -k "promote or concentration" -x` | ❌ Wave 0 |
| PORT-05 | Emits validated StrategyDossier | unit | `.venv/bin/python -m pytest tests/test_contracts.py -k "dossier" -x` | ⚠️ extend existing |
| HEDGE-01 | Only `-1` inverse peer is an idiosyncratic hedge | unit | `.venv/bin/python -m pytest tests/test_desk_risk.py -k "inverse or hedge_peer" -x` | ❌ Wave 0 |
| HEDGE-02 | Per-catalyst conditional_payoff matrix computed | unit | `.venv/bin/python -m pytest tests/test_desk_risk.py -k "conditional" -x` | ❌ Wave 0 |
| HEDGE-03 | Peer catalyst-clean over hold window | unit | `.venv/bin/python -m pytest tests/test_desk_risk.py -k "catalyst_clean" -x` | ❌ Wave 0 |
| HEDGE-04 | No-valid-hedge → size-tiny/exit, never fake | unit | `.venv/bin/python -m pytest tests/test_desk_risk.py -k "fallback or fake" -x` | ❌ Wave 0 |
| HEDGE-05 | Dossier states residual net-long + which risk covered | unit | `.venv/bin/python -m pytest tests/test_desk_portfolio.py -k "residual or covered" -x` | ❌ Wave 0 |
| OPS-01 | Memo w/ kill criteria, authored separately | unit | `.venv/bin/python -m pytest tests/test_desk_portfolio.py -k "memo" -x` | ❌ Wave 0 |
| OPS-02 | Pre-mortem before promotion | unit | `.venv/bin/python -m pytest tests/test_desk_portfolio.py -k "premortem or pre_mortem" -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** the quick run command for the touched module.
- **Per wave merge:** `.venv/bin/python -m pytest tests/test_desk_*.py tests/test_contracts.py -q`.
- **Phase gate:** full suite green before `/gsd:verify-work`.

### Wave 0 Gaps
- [ ] `tests/test_desk_builder.py` — PORT-02, HEDGE-01
- [ ] `tests/test_desk_risk.py` — PORT-03, HEDGE-02/03/04 + structural sizing invariant
- [ ] `tests/test_desk_portfolio.py` — PORT-01/04/05, HEDGE-05, OPS-01/02
- [ ] Extend `tests/test_contracts.py` — `Hedge` model + extended TradeProposal/RiskAssessment/StrategyDossier validators
- [ ] Fixtures: `tests/fixtures/agent_responses/{trade_builder_proposal,risk_aggressive,risk_conservative,risk_neutral,risk_synthesis,position_memo,pre_mortem,pm_dossier}.json`
- Framework install: none — pytest/pytest-asyncio already in `.venv`.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| pytest + pytest-asyncio | test suite | ✓ | 9.1.1 | — |
| pydantic | contracts | ✓ | 2.13.4 | — |
| statsmodels | `cointegration` (already used) | ✓ | 0.14.6 | — |
| sqlite-vec | KB analog query | ✓ | ≥0.1.9 | — |
| claude-agent-sdk | `run_structured` seam | ✓ | 0.2.139 | mocked in tests (offline) |
| `.venv` interpreter | all | ✓ | py≥3.10 | `python`/`python3` NOT on bare PATH — MUST use `.venv/bin/python` |

No external network/API/services this phase (fully offline). No new dependencies to add.

## Common Pitfalls (phase-specific, from PITFALLS.md)

### Pitfall A: Trusting the KB's stored `payoff_direction` as proof of hedge
**Wrong:** `kb.hedge_peers` returns `-1` → treat as validated hedge.
**Why:** the stored sign is a prior claim, not a per-catalyst validation; PHVS/BCRX was stored/assumed and was an anti-hedge.
**Avoid:** always re-run `conditional_payoff` + cointegration + catalyst-clean for THIS catalyst; `Hedge.validated` gates it.

### Pitfall B: LLM emits the size number
**Wrong:** the risk agent returns `size_pct` in its structured output and the code trusts it.
**Avoid:** the agent supplies *inputs* (p_loss estimate, chosen gap, hedge validity) with citations; `size_for_survival` computes the number. Test that the dossier size equals the quant output, not the agent's.

### Pitfall C: Netting the pair to size bigger
**Avoid:** size to the combined un-netted worst case (`conditional_payoff.value`); report `exposure` gross. Two longs = 2× gross, structurally.

### Pitfall D: Displaying stop distance as bounded loss on a held-through binary
**Avoid:** `holds_through_catalyst=True` → advisory stop; dossier max-loss = `-gap` sized loss, not stop distance.

## Open Questions

1. **Where does the "week's calls" batch come from (PORT-01 input)?**
   - Known: Phase-4 produces one `DebateVerdict` per catalyst; the orchestrator sequences per-catalyst runs.
   - Unclear: whether Phase-5 receives a pre-collected `list[DebateVerdict]` or pulls the week's verified catalysts itself.
   - Recommendation: `run_portfolio(conn, verdicts: list[DebateVerdict], open_book)` takes the list explicitly (caller collects). Keeps the module a pure transform, testable with fixtures. Confirm the collection seam at plan time.

2. **Open-book / positions ledger shape for the PM (PORT-04).**
   - Known: ARCHITECTURE.md calls for a positions ledger; the paper ledger is Phase-8.
   - Unclear: does a ledger exist yet, or is it a stub this phase?
   - Recommendation: accept `open_book` as a simple list of `{ticker, weight, catalyst_id}` (a stub), so PM concentration/exposure math is real now and the real ledger plugs in at Phase-8. `ponytail: stub the ledger as a list, don't build Phase-8's ledger early.`

3. **Do the risk/builder agents CALL quant tools via MCP, or does the Python layer compute and pass numbers in?**
   - Known: analysts call `mcp__quant__*`; the sizing math is deterministic and money-critical.
   - Recommendation: **Python layer computes** the sizing/payoff/cointegration numbers and passes them into the agent prompts (agents interpret, don't compute) — this makes the money numbers deterministic and the structural invariants enforceable. Only expose a tool via MCP if an agent genuinely needs to explore. Confirm at plan time.

## State of the Art

No moving-target external tech this phase — all internal, stack locked. The only "current-vs-old" note: the project-wide correction that **long/long correlated pairs are NOT hedges** (PITFALLS #1, and the user's own PHVS/BCRX finding) is fully absorbed into this design via `conditional_payoff` + `Hedge.validated`. Do not reintroduce unconditional-correlation hedging.

## Sources

### Primary (HIGH confidence — read from source this session)
- `src/catalyst_trader/quant/{sizing.py,pairs.py,portfolio.py,__init__.py}` — tool signatures, invariants (no return-target; un-netted worst cell; gross-abs exposure)
- `src/catalyst_trader/contracts/__init__.py` — existing contracts + extension license
- `src/catalyst_trader/kb.py` — `hedge_peers`/`analog_query`/`insert_hedge_peer` (payoff_direction sign, citation invariant)
- `src/catalyst_trader/desk/{runtime.py,debate.py,orchestrator.py,verifier.py,tools.py,evidence.py,analysts.py}` — the seam + patterns to mirror
- `tests/{conftest.py,test_desk_debate.py,test_desk_orchestrator.py,test_kb_hedge.py}` — offline test pattern, fixtures, monkeypatch seam
- `.planning/{REQUIREMENTS.md,ROADMAP.md,config.json,TOKEN-NOTES.md}` — reqs, success criteria, directives
- `graphify explain` on `conditional_payoff`, `risk_of_ruin`, `fractional_kelly`, `cointegration` — call/test graph

### Secondary (project research, settled)
- `.planning/research/ARCHITECTURE.md` — org chart, contracts, build order, ledger/PM design
- `.planning/research/PITFALLS.md` — hedge/stop/sizing pitfalls this phase must structurally prevent (#1, #2, #5, #10)
- `.planning/phases/05-.../05-CONTEXT.md` — the locked hedging decision

## Metadata

**Confidence breakdown:**
- Reused building blocks: HIGH — every symbol read from source, not training data.
- Architecture / patterns: HIGH — mirrors the existing, tested `debate.py` shape.
- Contract extensions: HIGH — mechanical, licensed by the module comment + Phase-4 precedent.
- Structural invariants: HIGH — Phase-3 already proves the technique works here.
- Open questions (batch input, ledger shape, tool-call vs compute): MEDIUM — resolvable at plan time, recommendations given.

**Research date:** 2026-08-15
**Valid until:** stable — internal code, no fast-moving external deps (~30 days; re-check only if Phase-3/4 code changes).

## Single-Leg Estimated-Move Construction (no-hedge default)

> LOCKED SCOPE ADDITION (PM, 2026-08-15). Since validated hedges keep proving rare, the **no-hedge case is the DEFAULT**, and it is NOT "size tiny and pray" — it is estimated-move-driven single-leg construction. This section specifies the tooling. Discipline unchanged: agents interpret, tools compute + return `ToolResult`; reuse over rebuild.

### Reuse-vs-new verdict (headline)

| Capability | Verdict | Why (from the actual signatures I read) |
|------------|---------|------------------------------------------|
| **Catalyst move estimator** (prob-weighted expected move + separate up/down magnitudes) | **NEW tool needed** — `catalyst_move_estimate` in a new `quant/events.py` | No existing tool combines P(positive) + base rates + per-type analog gaps. `implied_move` gives ONE magnitude (unsigned, market-implied); `conditional_payoff` needs the up/down gaps **handed to it** (it doesn't derive them); `base_rate` returns a single cited scalar. The estimator is the missing piece that *produces* the up/down gaps the other tools consume. It **composes** `implied_move` (prior/cross-check) + `kb.analog_query` outcome `move`s (empirical per-type distribution) + a P(positive). |
| **Adaptive SL/TP** | **EXTEND `sizing.sl_tp_levels`, do NOT duplicate** | `sl_tp_levels(entry, sl_pct, tp_pct, holds_through_catalyst=False)` takes **fixed pcts** — it does NOT take a vol/implied-move input and does NOT derive levels. It already owns the advisory-labeling logic. Add a thin `adaptive_sl_tp_levels(...)` that DERIVES `sl_pct`/`tp_pct` from the estimate then **delegates to `sl_tp_levels`** so the advisory gate stays in one place. |
| **Down-move sizing** | **REUSE `risk_of_ruin`/`fractional_kelly` as-is** — zero new code | `risk_of_ruin(p_loss, size_pct, gap=0.70, ...)` **already takes `gap`**. Pass the estimator's `down_move` as `gap` instead of the generic 0.70. That is the entire change. |
| **Hold-through vs exit-before** | **NO new tool** — a builder branch over estimator + `risk_of_ruin` outputs | It's a deterministic comparison of numbers the two tools already return; sets the existing `holds_through_catalyst` bool. |
| **Book-level 1% aggregation** | **Mostly REUSE `exposure`/`concentration`; add a thin selector helper** | `exposure`/`concentration` give gross/net/heat but do NOT compute aggregate expected return or pick legs. A small deterministic `select_book(...)` aggregates Σ(size·expected_move) and greedily includes survivable legs toward ~1% under the heat cap. |

### 1. Catalyst move estimator — NEW tool `quant/events.py::catalyst_move_estimate`

**Data source for per-type gap distributions (defensible, in-house, citable):** the KB's own realized `Outcome` nodes. Verified: `kb.analog_query(conn, embed, context, filters={"type": "pdufa"}, k)` returns analogs each carrying `.outcome` attrs with a **signed `move`** (the realized % gap) — confirmed in `tests/test_kb_analog.py` (`outcome_attrs={"move": +0.2 / -0.1 ...}`) and `kb._with_outcome`. Filtering by catalyst `type` (`pdufa` / `ph3_readout` / `conference` / `earnings`) yields the empirical per-type gap distribution, and each analog carries its evidence for citation. This is the honest source; it **grows via the Phase-10 iteration loop**. No external gap-distribution feed exists cleanly (same landscape as PITFALLS.md PDUFA-data note) — do not scrape one.

**Methodology (robust, fat-tail-aware):**
- Split the analog `move`s into the **positive branch** (move > 0) and **negative branch** (move < 0).
- `up_move` = a robust central estimate of the positive branch (median, not mean — biotech gaps are fat-tailed); `down_move` = robust central estimate of the |negative branch| (magnitude).
- Cross-check/clamp against `implied_move` as a **magnitude prior** (PITFALLS #10: implied move is a sizing magnitude prior, never directional). If the KB branch is sparse (cold start, < N analogs), fall back to `implied_move` for the magnitude and widen uncertainty.
- `p_positive` comes from the **Phase-4 `DebateVerdict`** (`direction=="positive"` calibrated `confidence`), optionally anchored to a `base_rate` — supplied by the caller (agent-interpreted, cited), NOT recomputed here.
- `expected_move` = `p_positive * up_move − (1 − p_positive) * down_move` (signed EV of the leg).

**Signature + ToolResult shape** (pure-python, `math` only; mirrors `conditional_payoff`'s "caller supplies the gaps" contract so it stays offline + reproducible):
```python
# quant/events.py
def catalyst_move_estimate(
    p_positive: float,                 # from DebateVerdict confidence (+ base_rate anchor), caller-supplied
    up_moves: list[float],             # positive-branch analog gaps (from kb.analog_query outcomes)
    down_moves: list[float],           # negative-branch analog gaps (magnitudes)
    implied_move: float | None = None, # quant.implied_move value — prior/clamp, optional
    method: str = "median",            # robust central estimator; raises on unknown
) -> ToolResult:
    """Probability-weighted expected move + separate up/down magnitudes for one catalyst leg.
    value = expected_move (signed EV); detail = {up_move, down_move, p_positive, n_up, n_down,
    implied_move, source: 'analogs'|'implied_fallback'}. RAISES on empty branches with no
    implied_move fallback, non-finite inputs, or p_positive outside [0,1] (Pattern 2)."""
```
- `value` = `expected_move`; `detail.down_move` is the number that feeds sizing (`risk_of_ruin(gap=down_move)`); `detail.up_move` feeds the TP anchor.
- Citation: the `inputs` snapshot (the analog gaps) IS the reproducibility record, minted as a `tool:` ref by `evidence.tool_ref` like every other quant result.
- `ponytail: caller passes the branch lists (already pulled via analog_query in the risk layer), estimator does robust stats + EV. No DB handle inside the tool → stays pure + trivially testable, same pattern as conditional_payoff.`

### 2. Adaptive SL/TP — EXTEND `quant/sizing.py`

`sl_tp_levels` as-read: `(entry, sl_pct, tp_pct, holds_through_catalyst=False)` → `detail.stop/target`, `value`=R:R, and when `holds_through_catalyst=True` it sets `detail.advisory=True` + a reason string. It does **not** derive levels from volatility. Add a thin wrapper that derives the pcts from the estimate and **delegates** (advisory logic stays in one place):
```python
def adaptive_sl_tp_levels(
    entry: float,
    up_move: float,             # estimator detail.up_move → TP anchor
    vol_move: float,            # estimator detail.down_move OR implied_move → SL scale (vol proxy)
    holds_through_catalyst: bool = False,
    sl_vol_mult: float = 1.0,   # SL at sl_vol_mult × vol_move (ATR-style, but implied/estimated vol — no OHLC needed)
    tp_frac: float = 0.8,       # TP anchored near tp_frac × up_move (don't assume the full gap)
) -> ToolResult:
    """Derive sl_pct = sl_vol_mult·vol_move, tp_pct = tp_frac·up_move, then delegate to
    sl_tp_levels(entry, sl_pct, tp_pct, holds_through_catalyst) so the advisory gate is shared."""
```
- **Vol source:** the estimator's `down_move` (or `implied_move`) IS the volatility proxy — avoids needing intraday OHLC/ATR data we don't have this phase. `ponytail: implied/estimated vol as the ATR stand-in; add true ATR only if OHLC history lands (Phase-8).`
- **CRITICAL gap-exposed invariant + where the label lives:** on a **hold-through-binary** leg the stop is gap-exposed — it cannot fill inside the overnight gap, it executes at the gapped open. So SL/TP is a REAL control ONLY for **(a) exit-before-event** and **(b) continuous post-gap drift**. The label already lives in the `ToolResult.detail` (`advisory=True` + reason) set by `sl_tp_levels(holds_through_catalyst=True)` — `adaptive_sl_tp_levels` inherits it by delegation. It must ALSO surface on the contract: **`TradeProposal.stop_loss`/`take_profit` are advisory whenever `holds_through_catalyst=True`** (already an added field per §Contract Extensions), and the `StrategyDossier` must render max-loss as the `-down_move`-sized loss, NOT the stop distance (PITFALLS #2, Pitfall D above). Recommend a `sl_advisory: bool` field on `TradeProposal` mirroring the tool's flag so the dashboard can't accidentally show a fictitious bounded loss.

### 3. Hold-through vs exit-before — ties estimator → existing `holds_through_catalyst`

Deterministic branch in `desk/builder.py` (no new tool):
```
est = catalyst_move_estimate(...)                       # value = expected_move (signed EV)
size = size_for_survival(p_loss=1-p_positive, gap=est.detail["down_move"], ...)   # survival size on the ESTIMATED down-move
hold_through = (est.value > EV_MIN) and (size.value >= MIN_TRADEABLE_SIZE)
# hold_through True  -> holds_through_catalyst=True,  SL advisory, size = survival size on down_move
# hold_through False -> holds_through_catalyst=False -> exit-before-event (trade the run-up, SL is a real control),
#                        or PASS entirely if even the run-up has no edge (zero-trade weeks OK)
```
- Positive EV **and** a survivable down-move at a tradeable size → may hold through. Else exit-before-event (converts binary-gap risk to drift risk, PITFALLS #2) or pass.
- The down-move that sizes the leg is the **estimated** `down_move`, not a blanket −70% (the −70% remains the conservative default only when the estimator has no data).

### 4. Book-level 1% aggregation — thin selector in `desk/portfolio.py`

**1% is a book-level construction/selection target, NEVER a leg sizing input.** Each leg is sized survival-first by `size_for_survival` on its own estimated down-move (that function has no target param — the structural guarantee). The ~1% only enters at **selection/aggregation across the week's legs**:
```python
def select_book(candidates, open_book, weekly_budget, heat_cap, target_weekly=0.01):
    """Greedily include survivable legs (best expected_move/risk first) toward ~target_weekly
    aggregate expected return, subject to weekly_budget + concentration heat_cap. Never resizes
    a leg to hit the target: if survivable legs can't reach 1%, the book stays below 1%
    (zero-trade weeks allowed). Returns the promoted subset + aggregate expected return."""
```
- Aggregate expected return = `Σ over legs (size_pct · expected_move)` (leg `expected_move` = estimator `value`).
- **`exposure`/`concentration` cover the *constraint* math** (gross/net/heat cap on the combined book) but do NOT compute aggregate expected return or pick legs — hence the thin `select_book` selector. It's the only genuinely new portfolio-level code; it composes the existing tools.
- Structural invariant: `select_book` may reorder/drop legs but MUST NOT increase any leg's `size_pct` above its `size_for_survival` output. Test it.

### 5. Validation Architecture additions (Nyquist)

| Item | Behavior | Type | Automated Command | File |
|------|----------|------|-------------------|------|
| `catalyst_move_estimate` | prob-weighted EV + up/down magnitudes from analog branches; implied-move fallback; robust median; raises on empty+no-fallback / bad p | unit | `.venv/bin/python -m pytest tests/test_events.py -x` | ❌ Wave 0 |
| estimator no-directional-signal | implied_move used as magnitude prior only, never as direction | unit | `.venv/bin/python -m pytest tests/test_events.py -k "prior or magnitude" -x` | ❌ Wave 0 |
| `adaptive_sl_tp_levels` | derives sl/tp from vol_move/up_move, delegates to sl_tp_levels | unit | `.venv/bin/python -m pytest tests/test_sizing.py -k "adaptive" -x` | ⚠️ extend existing |
| **gap-exposed SL invariant** | hold-through → `detail.advisory=True`; TradeProposal `sl_advisory` set; dossier max-loss = −down_move, not stop distance | unit | `.venv/bin/python -m pytest tests/test_sizing.py -k "advisory" tests/test_desk_builder.py -k "advisory" -x` | ❌ Wave 0 |
| down-move sizing wiring | `size_for_survival` receives estimator `down_move` as `gap`, not 0.70 | unit | `.venv/bin/python -m pytest tests/test_desk_builder.py -k "down_move or gap" -x` | ❌ Wave 0 |
| hold-through decision | positive EV + survivable size → holds_through_catalyst=True; else exit/pass | unit | `.venv/bin/python -m pytest tests/test_desk_builder.py -k "hold_through or exit_before" -x` | ❌ Wave 0 |
| `select_book` 1% aggregation | aggregates toward ~1% via selection; never resizes a leg above its survival size; zero-trade allowed | unit | `.venv/bin/python -m pytest tests/test_desk_portfolio.py -k "select_book or aggregate or one_pct" -x` | ❌ Wave 0 |

**New Wave-0 files:** `tests/test_events.py` (+ new `src/catalyst_trader/quant/events.py`, re-export in `quant/__init__.py`); extend `tests/test_sizing.py` for `adaptive_sl_tp_levels`; extend `tests/test_desk_builder.py` / `test_desk_portfolio.py`.

**Net new code proposed (kept minimal):** ONE new quant tool (`catalyst_move_estimate`), ONE extension (`adaptive_sl_tp_levels` delegating to `sl_tp_levels`), ONE thin selector (`select_book`). Everything else — down-move sizing (`risk_of_ruin(gap=)`), hold-through bool, gross/net/heat — is pure reuse.

### 6. Model-fit & playbook-parameterized tools — NO magic numbers (LOCKED, PM 2026-08-15)

The estimator + adaptive-SL/TP tools must be **fitted-parameter driven and grow over time**, not static heuristics with hardcoded constants. Mirror the options-ready-`Hedge` discipline: build the *seam* now so the Phase-9 refit loop slots in with **no rewrite**; do NOT build the refit loop this phase.

#### Does Phase-2's KB already have a home for fitted params + realized outcomes? — YES. No new table/node type.

Verified against `src/catalyst_trader/kb.py` + `tests/test_kb_playbook.py` / `test_kb_analog.py`:

| Need | Existing home | Evidence |
|------|---------------|----------|
| **Realized outcomes** (the refit target) | `Outcome` node kind, signed `move` in attrs, linked `catalyst -[RESULTED_IN]-> outcome` | `_NODE_KINDS` includes `outcome`; `test_kb_analog.py` seeds `outcome_attrs={"move": ...}`; `analog_query` returns each analog's outcome. Grows every week via realized events. |
| **Fitted parameter sets** (per catalyst type, versioned, cited) | `playbook` node kind via `insert_playbook(conn, scenario_type, scenario, strategy, confidence, evidence)` | `strategy` is stored in `attrs_json` through `json.dumps` → **round-trips an arbitrary dict** (existing tests use strings, but the column is JSON). `scenario_type` is exact-match filterable; `query_playbooks` returns confidence-desc. |
| **Versioning of a param set** | first-class `confidence` column + `created_at`; multiple rows per `scenario_type` | `query_playbooks` orders confidence-desc; Phase-9 refit just `insert_playbook`s a newer, better-confidence row — the reader picks it up automatically. |
| **Provenance of a param set** (which data/model produced it) | mandatory `CITES -> EvidenceSource` on every playbook (routed through `insert_claim`) | `insert_playbook` raises without `evidence`; `test_kb_playbook.py` asserts the citation requirement. A fitted param set is itself a cited claim — consistent with cite-or-drop. |

**Conclusion:** store each catalyst type's fitted params as ONE `playbook` node, namespaced `scenario_type=f"fitted_params:{catalyst_type}"` (exact-match, so no collision with real scenario playbooks), whose `strategy` dict carries both param groups:
```python
strategy = {
  "estimator": {"method": "median", "min_analogs": 5, "implied_blend": 0.5, "default_down_move": 0.70},
  "sl_tp":     {"sl_vol_mult": 1.0, "tp_frac": 0.8, "drift_coef": 0.0},
  "fit_source": "bootstrap: base_rates.csv + BIO/Wong Ph3 gap study",   # MODEL/method attribution
}
```
The `CITES` edge attributes the **data**; `strategy.fit_source` attributes the **model/method**. `ponytail: reuse the playbook node — it is already a cited, versioned, per-type, confidence-ranked key/value store. A new "params" table would duplicate it exactly.`

#### The param seam (pure tool + DB-reading loader — split for determinism)

- **Tools take `params` IN, stay pure + offline** (frozen `ToolResult` out; tests pin params explicitly): `catalyst_move_estimate(..., params: dict)` and `adaptive_sl_tp_levels(..., params: dict)`. **No numeric literal in the tool body** — every threshold (per-type gap defaults, drift coef, vol multiplier, TP/SL bands) reads from `params`; a missing key raises (no silent hardcoded fallback inside the tool).
- **The DB-reading seam lives in `kb.py`** (next to `query_playbooks`), so the pure quant tool never touches a connection:
  ```python
  def load_params(conn, catalyst_type: str) -> dict:
      """Top (highest-confidence) fitted_params:<type> playbook's strategy dict, or the bootstrap
      default if none. The ONE seam Phase-9's refit loop replaces the SOURCE of — signature frozen."""
  ```
- **Flow:** `desk/builder.py` calls `kb.load_params(conn, catalyst_type)` → passes the dict into the pure tools. Only the *source* of params changes over time; the tool math is fixed + reproducible.

#### Bootstrap params (works from trade #1)

Seed one `fitted_params:<type>` playbook per catalyst type at seed time (same convention as `data/base_rates.csv` / `data/pdufa_curated.csv`), derived from base rates + published historical per-type gaps, **cited** to those sources. So the tools are parameterized from the very first trade with an honest, traceable param set — the refit loop only *improves* it later. `ponytail: a seed script + a data/fitted_params_bootstrap.csv (or inline in a migration seed), cited — not a fitting pipeline. The fitter is Phase 9.`

#### Explicitly deferred to Phase 9 (LEARN) — build the seam, not the loop
- The refit/fitting pipeline (fit new params from accumulated `Outcome` nodes, score, gate, insert a higher-confidence playbook row). Phase 5 delivers: the two `params`-taking tools + `kb.load_params` seam + the bootstrap playbook rows + the (already-existing) playbook/outcome schema they refit against. `ponytail: exactly the Hedge-abstraction move — the put-option enum exists but isn't executed; here the param seam + playbook schema exist but aren't refit yet.`

#### Validation Architecture additions (param seam + provenance)

| Item | Behavior | Type | Automated Command | File |
|------|----------|------|-------------------|------|
| No magic numbers | estimator/SL-TP tools raise on a missing `params` key — no numeric literal fallback in the body | unit | `.venv/bin/python -m pytest tests/test_events.py tests/test_sizing.py -k "params_required or no_magic" -x` | ❌ Wave 0 |
| Deterministic w/ pinned params | same `params` in → identical frozen `ToolResult` out (offline, no DB) | unit | `.venv/bin/python -m pytest tests/test_events.py tests/test_sizing.py -k "deterministic or pinned" -x` | ❌ Wave 0 |
| `kb.load_params` seam | returns top-confidence `fitted_params:<type>` strategy dict; bootstrap default when none | unit | `.venv/bin/python -m pytest tests/test_kb_params.py -x` | ❌ Wave 0 |
| Newer fit wins | higher-confidence playbook row shadows the older (versioning) | unit | `.venv/bin/python -m pytest tests/test_kb_params.py -k "version or newer" -x` | ❌ Wave 0 |
| Param provenance (cite-or-drop) | a fitted param set has a `CITES->EvidenceSource` edge + `strategy.fit_source`; uncited insert raises | unit | `.venv/bin/python -m pytest tests/test_kb_params.py -k "provenance or cited" -x` | ❌ Wave 0 |
| Bootstrap present | one cited `fitted_params:<type>` seed exists per catalyst type after seed | unit | `.venv/bin/python -m pytest tests/test_kb_params.py -k "bootstrap" -x` | ❌ Wave 0 |

**New Wave-0 file:** `tests/test_kb_params.py` (loader + versioning + provenance + bootstrap). No new node/table type — reuses `playbook` + `Outcome`. No schema migration needed.

### 7. Estimate vetting gate — the builder audits estimator/SL-TP ASSUMPTIONS before consuming them (LOCKED, PM 2026-08-15)

The builder must VET `catalyst_move_estimate` + `adaptive_sl_tp_levels` outputs before it uses them. The gate audits the **assumptions/inputs behind** the model outputs — NOT the arithmetic (the tools own the math and are unit-tested; agents never recompute money numbers). This is the estimate-layer mirror of `desk/verifier.py`'s source-quote-or-drop, and it **reuses that machinery directly**.

#### Reuse vs new (exact, against `desk/verifier.py` as read)

| Piece | Reused verbatim | New |
|-------|-----------------|-----|
| Two-stage **structural (deterministic) → semantic (LLM, gated)** shape | ✅ same shape as `verifier.enforce` | — |
| `evidence.resolve(conn, ref)` + `evidence.quote_supported(source, claim)` | ✅ the deterministic structural half — every estimator INPUT must carry a resolvable ref; `kb:` refs pass the quote gate; `tool:` refs resolved-by-construction; uncited/unresolvable → dropped | — |
| `run_structured(prompt, schema, model="opus")` seam | ✅ the semantic half (offline-testable via monkeypatch, exactly like `verifier`) | new prompt + new check schema (below) |
| Raise-to-block-finalize (`VerdictUnsupportedError`) | ✅ same pattern | new `EstimateRejectedError` |
| Home | ✅ **add `enforce_estimate(...)` as a sibling of `enforce(...)` in `desk/verifier.py`** (colocates the pattern, max reuse) | the function body |
| The input-assembly + the specific checks | — | `estimate → [{input, ref, value}]`; the deterministic consistency checks; the comparability/cold-start LLM judgment |

`ponytail: it's verifier.enforce with a different subject (an estimate's inputs, not a verdict's evidence_refs). Same resolve+quote+run_structured+raise; only the checklist and the schema are new.`

#### The five checks (deterministic where possible, LLM only where judgment is needed)

1. **Input provenance (STRUCTURAL, deterministic):** every estimator input carries a resolvable `evidence_ref` — P(positive) (from the Phase-4 `DebateVerdict`, cited), the `analog_query` analog set (`tool:analog_query#…`, resolved-by-construction), the `implied_move` value (`tool:implied_move#…`), the catalyst-**type** classification (from the cited catalyst record), the vol proxy (`tool:` ref). Uncited/unresolvable input → **dropped**, same as an uncited claim in Phase-4.
2. **Analog comparability (SEMANTIC, LLM):** are the KB analogs actually comparable to THIS catalyst — same type, similar phase/indication/drug class? Off-type or cherry-picked analogs feeding the gap distribution → reject. (This is the one that genuinely needs the LLM; the structural filter in `analog_query` already enforces `type`, so the LLM judges the finer phase/indication/class match.)
3. **Consistency (mostly DETERMINISTIC):**
   - P(positive) matches the Phase-4 verdict direction + is within tolerance of its `confidence` — pure numeric check.
   - estimated down-move consistent with the type's `base_rate` — numeric sanity band.
   - **hold-through leg with a NON-advisory SL is a rejectable inconsistency** — pure boolean: `holds_through_catalyst and not sl_advisory` → reject (ties to §2's gap-exposed invariant).
   These are cheap comparisons; do them in the structural stage, no LLM.
4. **Cold-start / small-n (DETERMINISTIC flag → SEMANTIC handling):** thin analog set (`n_analogs < params["estimator"]["min_analogs"]`) → flag implied-move-fallback reliance and require **widened uncertainty / shrink-to-base-rate** rather than overclaim (`EstimateVetting.uncertainty_widened=True`). Reject if the estimate overclaims precision on thin data.
5. **Blocking:** a rejected estimate **blocks finalize** (raises `EstimateRejectedError`, mirroring Phase-4 blocking unsupported verdicts) → the builder re-derives with vetted inputs or passes the trade. The endorse/reject verdict is recorded (audit).

#### Which contract carries the vetting verdict

New model + one field on `TradeProposal` (the builder produces it; **it is on the dossier by containment** since `StrategyDossier.trade` IS a `TradeProposal`):
```python
class EstimateVetting(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["endorse", "reject"]
    input_refs: list[str]              # vetted (surviving) estimator input refs
    dropped_inputs: list[str] = []     # uncited/unresolvable inputs dropped in the structural stage
    reasons: list[str]                 # per-check findings (comparability, consistency, cold-start)
    uncertainty_widened: bool = False  # cold-start shrink-to-base-rate applied

# TradeProposal += estimate_vetting: EstimateVetting
```
- **Carrier = `TradeProposal.estimate_vetting`.** A promoted trade always carries `verdict="endorse"` (reject blocks finalize before promotion). Reachable on the dossier via `dossier.trade.estimate_vetting` — no duplication.
- `ponytail: one field on TradeProposal, surfaced on the dossier by containment. Add a top-level StrategyDossier mirror ONLY if the PM must restate it at dossier top-level — default: don't duplicate. Need the top-level flag? Say so.`

#### Validation Architecture additions (gate: endorse, each rejection reason, blocking) — all offline via the `run_structured` seam

| Item | Behavior | Type | Automated Command | File |
|------|----------|------|-------------------|------|
| Endorse path | fully-cited, comparable, consistent estimate → `verdict="endorse"`, all input_refs survive | unit | `.venv/bin/python -m pytest tests/test_desk_estimate_gate.py -k "endorse" -x` | ❌ Wave 0 |
| Reject: uncited input | an estimator input with an unresolvable/absent ref is dropped; estimate rejected/blocked | unit | `.venv/bin/python -m pytest tests/test_desk_estimate_gate.py -k "uncited or dropped" -x` | ❌ Wave 0 |
| Reject: off-type/cherry-picked analogs | non-comparable analogs (LLM judged) → reject | unit | `.venv/bin/python -m pytest tests/test_desk_estimate_gate.py -k "comparab or off_type" -x` | ❌ Wave 0 |
| Reject: P(positive) vs verdict | P(positive) contradicts Phase-4 direction/confidence → reject (deterministic) | unit | `.venv/bin/python -m pytest tests/test_desk_estimate_gate.py -k "consistency or p_positive" -x` | ❌ Wave 0 |
| Reject: hold-through + non-advisory SL | `holds_through_catalyst and not sl_advisory` → reject (deterministic) | unit | `.venv/bin/python -m pytest tests/test_desk_estimate_gate.py -k "advisory_inconsistency" -x` | ❌ Wave 0 |
| Reject: down-move vs base rate | estimated down-move outside the type's base-rate sanity band → reject | unit | `.venv/bin/python -m pytest tests/test_desk_estimate_gate.py -k "base_rate_band" -x` | ❌ Wave 0 |
| Cold-start widening | thin analog set → `uncertainty_widened=True` / shrink-to-base-rate, not overclaim | unit | `.venv/bin/python -m pytest tests/test_desk_estimate_gate.py -k "cold_start or small_n" -x` | ❌ Wave 0 |
| Blocking finalize | a `reject` raises `EstimateRejectedError` → trade does not finalize (mirrors verifier) | unit | `.venv/bin/python -m pytest tests/test_desk_estimate_gate.py -k "block or raises" -x` | ❌ Wave 0 |

**New Wave-0 file:** `tests/test_desk_estimate_gate.py`; extend `tests/test_contracts.py` for `EstimateVetting` + `TradeProposal.estimate_vetting`. Reuses `evidence.resolve`/`quote_supported` + the `run_structured` monkeypatch pattern from `tests/test_desk_verifier.py` — fully offline.
