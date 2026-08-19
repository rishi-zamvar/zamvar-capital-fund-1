"""Pydantic v2 inter-layer contracts — the enforceable boundaries between every agent
layer. `extra="forbid"` + bounded score/confidence + a required non-empty evidence_ref
are the anti-hallucination spine at the message boundary: an LLM that hallucinates a key,
omits a citation, or emits an out-of-range score is rejected by model_validate, not
trusted. This mirrors Phase-1's `_at_least_one_source` no-uncited-claim discipline at the
contract boundary (the DB-write half of KB-02 lives in kb.py).

# ponytail: field lists straight from ARCHITECTURE.md; extend a model when a layer needs a
#           field, don't pre-add speculative ones.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class KeyFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim: str
    evidence_ref: str = Field(min_length=1)  # no source -> reject (anti-hallucination)
    source_url: str | None = None


class AnalystSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dimension: str
    ticker: str
    catalyst_id: str
    score: float = Field(ge=-1.0, le=1.0)  # bearish..bullish
    confidence: float = Field(ge=0.0, le=1.0)
    key_findings: list[KeyFinding]
    kb_analogs_queried: list[str] = []
    unknowns: list[str] = []

    @field_validator("key_findings")
    @classmethod
    def _at_least_one_sourced_finding(cls, v: list[KeyFinding]) -> list[KeyFinding]:
        if not v:
            raise ValueError(
                "an AnalystSignal must carry at least one sourced key_finding"
            )
        return v


class DebateVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    thesis: str
    direction: Literal["positive", "negative"]  # binary catalyst verdict (CALL-03)
    confidence: float = Field(ge=0.0, le=1.0)
    bull_strongest_point: str
    bear_strongest_point: str
    unresolved_dissent: list[str] = []
    evidence_refs: list[str] = []
    kill_criteria: list[str]  # explicit falsification criteria — required, non-empty

    @field_validator("kill_criteria")
    @classmethod
    def _at_least_one_kill_criterion(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError(
                "a DebateVerdict must carry at least one kill/falsification criterion"
            )
        return v


class Hedge(BaseModel):
    """The honest-hedge abstraction. `validated` + `covers` make a fake idiosyncratic
    hedge UNREPRESENTABLE — a peer may claim to cover the idiosyncratic binary only if it
    validated as an inverse peer THIS catalyst. `instrument` is options-ready: put_option
    is a legal enum member but is refused at promotion in v1 (architected, not executed).
    """

    model_config = ConfigDict(extra="forbid")
    instrument: Literal["equity_peer", "inverse_etf", "put_option"]  # put_option reserved; NOT executed in v1
    ticker: str
    payoff_direction: int  # +1 co-move, -1 inverse (from kb.hedge_peers)
    validated: bool  # passed conditional_payoff + cointegration + catalyst-clean THIS catalyst
    covers: Literal["idiosyncratic", "sector_beta", "none"]
    mechanism: str
    conditional_worst: float  # quant.conditional_payoff value (un-netted worst cell)

    @field_validator("covers")
    @classmethod
    def _honest_coverage(cls, v: str, info) -> str:
        # instrument/payoff_direction/validated are declared above covers, so they are
        # already in info.data when this runs (pydantic v2 field-declaration order).
        if v == "idiosyncratic" and not (
            info.data.get("validated") and info.data.get("payoff_direction") == -1
        ):
            raise ValueError(
                "only a validated inverse peer may claim to cover idiosyncratic risk (HEDGE-01/04)"
            )
        if info.data.get("instrument") == "inverse_etf" and v == "idiosyncratic":
            raise ValueError(
                "an inverse_etf (LABD) covers sector_beta only, never the idiosyncratic binary (locked decision #4)"
            )
        if info.data.get("instrument") == "put_option":
            raise ValueError(
                "put_option hedges are architected but not executable in v1 (deferred)"
            )
        return v


class EstimateVetting(BaseModel):
    """The estimate-gate verdict (§7). A promoted trade always carries verdict="endorse"
    — a reject blocks finalize upstream before promotion."""

    model_config = ConfigDict(extra="forbid")
    verdict: Literal["endorse", "reject"]
    input_refs: list[str]  # vetted (surviving) estimator input refs
    dropped_inputs: list[str] = []  # uncited/unresolvable inputs dropped structurally
    reasons: list[str]  # per-check findings (comparability, consistency, cold-start)
    uncertainty_widened: bool = False  # cold-start shrink-to-base-rate applied


class ScenarioRow(BaseModel):
    """One row of the pre-committed exit scenario table (Tier-3 Exit Plan). `target` is the
    football-field price for the branch; `action` is the deterministic pre-decided response."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    scenario: Literal["approval", "rejection", "mixed", "delay"]
    probability: float
    target: float  # football-field target PRICE for this branch
    action: Literal["hold_and_trail", "exit_on_open", "exit_half", "lean_hedge"]


class ThesisInvalidation(BaseModel):
    """The typed thesis-invalidation leg: the branch that FALSIFIES the thesis, the down-move
    magnitude floor it must clear, and the disqualifying news (verdict kill_criteria)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    outcome: str  # the falsifying branch ("rejection" for a positive trade, "approval" for negative)
    magnitude_floor: float
    disqualifying_news: list[str]


class EvFlipGuard(BaseModel):
    """Stored EV-flip inputs so the reflex can recompute remaining_upside*p - downside*(1-p)
    against `threshold` at the CURRENT price (a flip => trim-or-exit)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    upside: float
    downside: float
    p: float
    threshold: float


class ExitPlan(BaseModel):
    """The deterministic Exit Plan authored at ENTRY (no agent in the hot path): a no-stop
    expectation band, a pre-committed scenario table, a typed thesis-invalidation, a hard TIME
    barrier, and the EV-flip guard inputs — all computed from the football-field/verdict numbers
    the desk already produced. The intraweek reflex + the exit review both read it."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    expectation_band: tuple[float, float]  # (entry*(1-down_move), entry*(1+up_move)) — the no-stop zone
    scenario_table: list[ScenarioRow]
    thesis_invalidation: ThesisInvalidation
    time_barrier: str  # hard triple-barrier TIME leg (== exit_by_date)
    ev_flip: EvFlipGuard


class TradeProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_long: str
    hedge: Hedge | None  # None => fallback (size-tiny / exit-before-event), HEDGE-04
    pair_rationale: str
    entry: float
    exit_by_date: str
    stop_loss: float  # ADVISORY when sl_advisory is True (held-through gap risk, PITFALLS #2)
    take_profit: float  # ADVISORY when sl_advisory is True
    size_pct: float
    expected_return_pct: float
    kb_analogs: list[str] = []
    holds_through_catalyst: bool  # False = exit-before-event default (HEDGE-04)
    catalyst_id: str
    direction: Literal["positive", "negative"]  # carried from DebateVerdict
    estimate_vetting: EstimateVetting  # §7 — endorse required before promote
    sl_advisory: bool  # True whenever holds_through_catalyst (mirrors sl_tp_levels advisory)
    expected_move_field: dict | None = None  # FF-05 field detail (point_estimate/dispersion/agreement/refs); None when < min_methods
    retrieval_confidence: str | None = None  # analog retrieval confidence label ("thin"/"ok") surfaced for field weighting
    exit_plan: ExitPlan | None = None  # Tier-3 deterministic Exit Plan authored at entry; None => pre-Tier-3 constructions stay valid
    hedge_profile: dict | None = None  # out-of-band hedge facts (HEDGE-CORR-1c); CONTEXT only, never a ranking signal — attached at construction, absent from every scoring/sizing path


class RiskAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    downside_stress_scenarios: list[str]
    hedge_correlation_estimate: float
    correlation_source: str
    liquidity_check: str
    event_vol_estimate: float
    aggressive_view: str
    conservative_view: str
    neutral_view: str
    residual_risks: list[str] = []
    conditional_payoff_matrix: dict  # quant.conditional_payoff detail.matrix (HEDGE-02)
    conditional_worst: float  # un-netted worst cell sized against
    hedge: Hedge | None  # the ACTUAL validated Hedge object (or None) — 05-07 reconciles it onto the promoted TradeProposal (BLOCKER-1); the OBJECT, not just a bool
    hedge_valid: bool  # mirror = (hedge is not None and hedge.validated) — inverse held THIS catalyst? (HEDGE-01/04)
    recommended_size_pct: float  # from size_for_survival — the quant number, not the LLM's
    ruin_at_size: float  # risk_of_ruin at the chosen size (audit)


class PortfolioContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    concentration: float
    corr_to_open_positions: list[float]
    weekly_budget_remaining: float


class StrategyDossier(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["promote", "kill"]
    trade: TradeProposal
    portfolio_context: PortfolioContext
    verdict_summary: str
    dissent_log: list[str] = []
    all_evidence_refs: list[str] = []
    residual_net_long: float  # exposure().detail.net over the promoted book (HEDGE-05)
    which_risk_covered: Literal["idiosyncratic", "sector_beta", "none"]  # HEDGE-05
    position_memo: str  # OPS-01 (authored separately, before the decision)
    pre_mortem: list[str]  # OPS-02 ("assume it lost — why")
    kill_criteria: list[str]  # carried from DebateVerdict, required non-empty

    @field_validator("kill_criteria")
    @classmethod
    def _at_least_one_kill_criterion(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError(
                "a StrategyDossier must carry at least one kill/falsification criterion"
            )
        return v


class DiligenceInput(BaseModel):
    """The firewall boundary (DILIG-01). extra='forbid' makes any Workflow-1/2 field
    UNREPRESENTABLE, so run_diligence accepts ONLY this type — a leaked DebateVerdict/
    TradeProposal/thesis is a type error at model_validate, not a policy violation (the
    Hedge.covers move applied to the input). `catalyst` stays a raw `dict` (minimal facts:
    {catalyst_id, catalyst_type, event_date, ...}) to keep the boundary minimal; `pair` is
    the hedge peer TICKER only — never a Hedge object or its rationale."""

    model_config = ConfigDict(extra="forbid")
    ticker: str
    catalyst: dict
    pair: str | None = None


class DiligenceDossier(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["go", "no_go"]
    per_dimension: list[dict]
    red_flags: list[str] = []
    strongest_disconfirming_evidence: str
    all_evidence_refs: list[str] = []
    residual_risks: list[str] = []  # mirrors RiskAssessment.residual_risks
    dd_expected_move: float | None = None  # FF-05 independent straddle/iv-implied move; None when options illiquid/absent (abstain)


class RetriggerFlag(BaseModel):
    """Re-trigger payload into WF-1/2. extra='forbid' + the ABSENCE of any answer-shaped
    field makes handing the debate a conclusion UNREPRESENTABLE (mirrors DiligenceInput
    inbound). Carries a FACT + why it's material, never a direction/confidence/size/verdict."""
    model_config = ConfigDict(extra="forbid")
    target: Literal["catalyst_call", "portfolio_build"]
    finding: str        # the specific fact DD/weekly-refresh surfaced that the workflow left out
    evidence_ref: str   # kb:<id> / tool:<fn>#<hash> — non-empty; ALSO the oscillation key
    why_material: str   # why it changes verdict direction / sizing bucket / structure

    @field_validator("finding", "why_material", "evidence_ref")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("RetriggerFlag needs a non-empty finding/why_material/evidence_ref")
        return v


class WeeklyFlag(BaseModel):
    """A flag emitted by the weekly per-name REFRESH (WEEK-06) that routes UP to the MD
    (RECON-08). quant = a metric tripped vs baseline; qual = an analyst noted a material change.
    Carries the GAP, not the answer, and has NO target — the MD decides route-or-log and, if
    routing, picks the target (→ RetriggerFlag). extra='forbid' + no action/answer field."""
    model_config = ConfigDict(extra="forbid")
    ticker: str
    flag_type: Literal["quant", "qual"]
    finding: str        # the metric move / analyst note — a fact, never an action or verdict
    evidence_ref: str   # kb:<id> / tool:<fn>#<hash> — non-empty
    why_material: str

    @field_validator("ticker", "finding", "why_material", "evidence_ref")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("WeeklyFlag needs non-empty ticker/finding/why_material/evidence_ref")
        return v


class ReconciliationRound(BaseModel):
    model_config = ConfigDict(extra="forbid")
    round: int                               # 1..3
    md_flags: list[RetriggerFlag] = []        # actioned re-triggers routed this round (auditable proof the answer wasn't handed down)
    logged_flags: list[WeeklyFlag] = []       # incoming flags the MD chose NOT to action — logged, never forced (RECON-08/WEEK-06)
    response_delta: str                      # what changed vs prior, or "unmoved + rebuttal"
    convergence: dict                        # each convergence criterion -> pass/fail (deterministic)
    cross_check: dict                        # the cross_check() snapshot the MD reviewed
    disposition: Literal["continue", "converged", "cap_hit", "diverged_pass"]


class MDDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["enter", "pass", "escalate"]
    rationale: str
    accepted_residuals: list[str] = []       # each unresolved caveat + how it's priced (size/kill/hedge) — RECON-05
    overrides: list[str] = []                # any workflow recommendation the MD overrode + reason
    dissent_preserved: list[str] = []        # DebateVerdict.unresolved_dissent + DD.strongest_disconfirming_evidence, VERBATIM
    round_log: list[ReconciliationRound]     # the immutable per-round log
    blocker_class: Literal["mandate", "data_gap", "factual_conflict", "infra"] | None = None
    recommended_resolution: str | None = None

    @model_validator(mode="after")
    def _escalation_shape(self):
        if self.decision == "escalate":
            if not self.blocker_class or not (self.recommended_resolution or "").strip():
                raise ValueError("an escalation MUST carry blocker_class + recommended_resolution (completed-staff-work)")
        elif self.blocker_class or self.recommended_resolution:
            raise ValueError("blocker_class/recommended_resolution are escalation-only fields")
        return self


class ScanInput(BaseModel):
    """The Phase-6.8 scanner firewall (SCAN-04). ONLY the card pair + tripped flags cross the
    firewall into the Haiku pass — no desk verdict/thesis/position field is representable, so a
    leak is a ValidationError at model_validate, not a policy check (mirror of DiligenceInput).
    card_prev/card_cur stay raw dicts to keep the boundary minimal (the point-in-time cards from
    store.card_asof); tripped is the echo of the Stage-1 flags threaded in by Python."""

    model_config = ConfigDict(extra="forbid")
    ticker: str
    week_end: str
    card_prev: dict | None = None
    card_cur: dict
    tripped: list[dict] = []


class OpportunityFlag(BaseModel):
    """The Stage-2 Haiku scanner output + the scan_flag audit payload (SCAN-01). Rich by design;
    the WIRE format to the MD is the WeeklyFlag projection (Plan 03 to_weekly_flag). Gap-not-answer:
    NO direction/size/target field exists — it carries a falsifiable thesis + what must be verified
    + the unknowns, and the MD assigns the route (mirrors WeeklyFlag/RetriggerFlag discipline)."""

    model_config = ConfigDict(extra="forbid")
    ticker: str
    week_end: str
    opportunity_type: Literal["catalyst_vol", "squeeze_setup", "dilution_risk",
                              "technical_reversal", "continuation", "competitor_event",
                              "unknown_vol", "no_opportunity"]
    thesis_to_verify: str            # ONE falsifiable hypothesis, never a call/direction
    verification_needed: Literal["catalyst_call", "measured_edge", "mini_backtest", "diligence"]
    key_findings: list[KeyFinding]   # cite-or-drop enforced downstream (Plan 03)
    kb_analogs: list[str] = []       # analog_query evidence refs leaned on
    tripped_flags: list[str] = []    # echo of the Stage-1 flags (threaded by Python)
    unknowns: list[str] = []         # gap-not-answer payload
    confidence: float = Field(ge=0.0, le=1.0)
