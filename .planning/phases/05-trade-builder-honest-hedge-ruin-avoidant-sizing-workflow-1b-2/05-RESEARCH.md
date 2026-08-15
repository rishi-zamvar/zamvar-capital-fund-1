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
