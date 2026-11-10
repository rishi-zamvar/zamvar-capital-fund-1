"""Pydantic v2 inter-layer contracts — the enforceable boundaries between every agent
layer. `extra="forbid"` + bounded score/confidence + a required non-empty evidence_ref
are the anti-hallucination spine at the message boundary: an LLM that hallucinates a key,
omits a citation, or emits an out-of-range score is rejected by model_validate, not
trusted. This mirrors Phase-1's `_at_least_one_source` no-uncited-claim discipline at the
contract boundary (the DB-write half of KB-02 lives in kb.py).

# ponytail: field lists straight from ARCHITECTURE.md; extend a model when a layer needs a
#           field, don't pre-add speculative ones.
"""

from typing import Any, Literal

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
    thesis: str = Field(min_length=1)  # synthesized dimension-specific read; grounded in key_findings (CALL-01)
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


# ---------------------------------------------------------------------------------------
# 07.9 — the 4 CATALYST-CALL lens reports (schema split). AnalystSignal above stays intact
# for the 8 DD dims (Plan 2 migrates them). Each lens report subclasses AnalystReportBase —
# so it carries the SAME downstream interface (dimension/thesis/score/confidence/
# key_findings/unknowns) debate + verifier read, plus its guideline-§7 sections.
#
# House rules for every section sub-model: extra="forbid" (a hallucinated leaf rejects),
# frozen=True, and EVERY numeric/string leaf Optional-default-None — an empty slot is a
# finding, never a fabricated 0. The ONE headline verdict number per lens carries a paired
# `_source` enforced by a model_validator (the machine-enforceable slice of §7's
# "every number carries a paired _source").
# ponytail: plain pydantic sub-models straight from §7 — no builder/factory/registry; the
#           nullable-by-default field IS the "empty slot is a finding" rule (no null-fill code).
# ---------------------------------------------------------------------------------------

_SECTION = ConfigDict(extra="forbid", frozen=True)


class AnalystReportBase(BaseModel):
    """The downstream interface (debate `_evidence_context` + verifier `_claim_for` read
    exactly these fields) — identical spine to AnalystSignal, so lens subclasses flow through
    the duck-typed consumers unchanged. `thesis` is the BOTTOM LINE, grounded in key_findings."""

    model_config = ConfigDict(extra="forbid")
    dimension: str
    ticker: str
    catalyst_id: str
    thesis: str = Field(min_length=1)  # the BOTTOM LINE — synthesis of the cited key_findings (CALL-01)
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    key_findings: list[KeyFinding]
    kb_analogs_queried: list[str] = []
    unknowns: list[str] = []

    @field_validator("key_findings")
    @classmethod
    def _at_least_one_sourced_finding(cls, v: list[KeyFinding]) -> list[KeyFinding]:
        if not v:
            raise ValueError(
                "an analyst report must carry at least one sourced key_finding"
            )
        return v


# --- Clinical sections (guideline §1 / §7) ---------------------------------------------


class DiseaseUnmetNeed(BaseModel):
    model_config = _SECTION
    prevalence: int | None = None
    soc: str | None = None
    unmet_need_severity: str | None = None


class Moa(BaseModel):
    model_config = _SECTION
    target: str | None = None
    modality: str | None = None
    genetically_validated: bool | None = None
    selection_biomarker: bool | None = None


class TrialDesign(BaseModel):
    model_config = _SECTION
    n: int | None = None
    randomization: str | None = None
    control: str | None = None
    blinding: str | None = None
    alpha: float | None = None
    power: float | None = None
    powered_effect: str | None = None


class Endpoints(BaseModel):
    model_config = _SECTION
    primary: str | None = None
    ladder_rung: str | None = None
    surrogate_status: str | None = None
    endpoint_changed_vs_registration: bool | None = None
    key_secondaries: list[str] = []


class Efficacy(BaseModel):
    model_config = _SECTION
    point_estimate: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    p_value: float | None = None
    hr: float | None = None
    absolute_gain: str | None = None
    arr: float | None = None
    rrr: float | None = None
    nnt: float | None = None
    context_vs_benchmark: str | None = None


class Safety(BaseModel):
    model_config = _SECTION
    ae_discontinuation_pct: float | None = None
    sae_pct: float | None = None
    deaths: int | None = None
    grade34_pct: float | None = None
    boxed_warning_risk: str | None = None


class ClinicalReport(AnalystReportBase):
    disease_unmet_need: DiseaseUnmetNeed = DiseaseUnmetNeed()
    moa: Moa = Moa()
    trial_design: TrialDesign = TrialDesign()
    endpoints: Endpoints = Endpoints()
    efficacy: Efficacy = Efficacy()
    safety: Safety = Safety()
    prior_consistency: str | None = None
    key_scientific_risk: str | None = None
    pos_estimate: float | None = None  # HEADLINE verdict number
    pos_estimate_source: str | None = None

    @model_validator(mode="after")
    def _headline_sourced(self):
        if self.pos_estimate is not None and not (self.pos_estimate_source or "").strip():
            raise ValueError("clinical pos_estimate requires a non-empty pos_estimate_source (no-fabrication)")
        return self


# --- Regulatory sections (guideline §2 / §7) -------------------------------------------


class Application(BaseModel):
    model_config = _SECTION
    type: str | None = None
    review: str | None = None
    clock_months: int | None = None
    pdufa_date: str | None = None
    resubmission_class: str | None = None
    expedited_tags: list[str] = []


class Division(BaseModel):
    model_config = _SECTION
    name: str | None = None
    posture: str | None = None


class PriorCrl(BaseModel):
    model_config = _SECTION
    exists: bool | None = None
    deficiency_type: str | None = None
    addressed: bool | None = None


class AdCom(BaseModel):
    model_config = _SECTION
    scheduled: bool | None = None
    committee: str | None = None
    voting_question: str | None = None
    briefing_doc_tone: str | None = None


class LabelRisk(BaseModel):
    model_config = _SECTION
    boxed_warning: bool | None = None
    rems: bool | None = None
    narrow_label: bool | None = None
    confirmatory_trial: bool | None = None


class Poa(BaseModel):
    model_config = _SECTION
    point: float | None = None  # HEADLINE verdict number
    point_source: str | None = None
    clean_approve: float | None = None
    approve_restricted: float | None = None
    crl: float | None = None


class RegulatoryReport(AnalystReportBase):
    application: Application = Application()
    division: Division = Division()
    prior_crl: PriorCrl = PriorCrl()
    adcom: AdCom = AdCom()
    label_risk: LabelRisk = LabelRisk()
    poa: Poa = Poa()
    regulatory_question: str | None = None
    precedent: str | None = None

    @model_validator(mode="after")
    def _headline_sourced(self):
        if self.poa.point is not None and not (self.poa.point_source or "").strip():
            raise ValueError("regulatory poa.point requires a non-empty poa.point_source (no-fabrication)")
        return self


# --- Financial sections (guideline §3 / §7) --------------------------------------------


class Liquidity(BaseModel):
    model_config = _SECTION
    cash_m: float | None = None
    securities_m: float | None = None
    total_liquidity_m: float | None = None
    debt_m: float | None = None
    covenants: str | None = None


class Runway(BaseModel):
    model_config = _SECTION
    quarterly_burn_m: float | None = None
    runway_months: float | None = None
    clears_catalyst: bool | None = None
    cushion_months: float | None = None


class CapitalStructure(BaseModel):
    model_config = _SECTION
    shares_basic_m: float | None = None
    fully_diluted_m: float | None = None
    warrant_overhang: str | None = None
    annual_dilution_pct: float | None = None


class FinancingRound(BaseModel):
    model_config = _SECTION
    date: str | None = None
    vehicle: str | None = None
    gross_m: float | None = None
    discount_pct: float | None = None
    warrant_coverage: str | None = None
    investors: str | None = None


class Insiders(BaseModel):
    model_config = _SECTION
    net_direction: str | None = None
    discretionary_buys: list[str] = []
    scheduled_sales: list[str] = []  # §7 "10b5-1_sales" — pre-scheduled, low-signal
    specialist_13f_change: str | None = None


class Rnpv(BaseModel):
    model_config = _SECTION
    rnpv_m: float | None = None  # HEADLINE verdict number
    rnpv_source: str | None = None
    peak_sales_m: float | None = None
    pos: float | None = None
    net_price: float | None = None
    addressable_pop: int | None = None
    penetration_pct: float | None = None
    loe_date: str | None = None
    discount_rate: float | None = None


class FinancialReport(AnalystReportBase):
    liquidity: Liquidity = Liquidity()
    runway: Runway = Runway()
    capital_structure: CapitalStructure = CapitalStructure()
    financing_history: list[FinancingRound] = []
    insiders: Insiders = Insiders()
    rnpv: Rnpv = Rnpv()
    signal_synthesis: str | None = None

    @model_validator(mode="after")
    def _headline_sourced(self):
        if self.rnpv.rnpv_m is not None and not (self.rnpv.rnpv_source or "").strip():
            raise ValueError("financial rnpv.rnpv_m requires a non-empty rnpv.rnpv_source (no-fabrication)")
        return self


# --- Market sections (guideline §4 / §7) -----------------------------------------------


class RunUp(BaseModel):
    model_config = _SECTION
    move_4w_pct: float | None = None
    move_8w_pct: float | None = None
    vs_xbi_pct: float | None = None
    short_covering_component: str | None = None


class ExpectedMove(BaseModel):
    model_config = _SECTION
    atm_straddle: float | None = None
    expected_move_pct: float | None = None
    iv_current: float | None = None
    iv_post_event_est: float | None = None


class ImpliedProb(BaseModel):
    model_config = _SECTION
    x: float | None = None
    z: float | None = None
    y: float | None = None
    implied_p_approval: float | None = None


class ShortInterest(BaseModel):
    model_config = _SECTION
    si_pct_float: float | None = None
    days_to_cover: float | None = None
    cost_to_borrow_pct: float | None = None
    squeeze_setup: bool | None = None


class Ownership(BaseModel):
    model_config = _SECTION
    float_pct: float | None = None
    institutional_pct: float | None = None
    top10_concentration_pct: float | None = None


class Sentiment(BaseModel):
    model_config = _SECTION
    buy: int | None = None
    hold: int | None = None
    sell: int | None = None
    target_dispersion: str | None = None
    revision_trend: str | None = None


class Analog(BaseModel):
    model_config = _SECTION
    name: str | None = None
    implied_move_pct: float | None = None
    realized_move_pct: float | None = None
    outcome: str | None = None


class Asymmetry(BaseModel):
    model_config = _SECTION
    ev_pct: float | None = None  # HEADLINE verdict number
    ev_source: str | None = None
    position_size_pct: float | None = None
    driver: str | None = None
    expression: str | None = None


class MarketReport(AnalystReportBase):
    run_up: RunUp = RunUp()
    expected_move: ExpectedMove = ExpectedMove()
    implied_prob: ImpliedProb = ImpliedProb()
    short_interest: ShortInterest = ShortInterest()
    ownership: Ownership = Ownership()
    sentiment: Sentiment = Sentiment()
    analogs: list[Analog] = []
    asymmetry: Asymmetry = Asymmetry()

    @model_validator(mode="after")
    def _headline_sourced(self):
        if self.asymmetry.ev_pct is not None and not (self.asymmetry.ev_source or "").strip():
            raise ValueError("market asymmetry.ev_pct requires a non-empty asymmetry.ev_source (no-fabrication)")
        return self


# --- DD dimension reports (07.9 Plan 2) -------------------------------------------------
# The 8 diligence dims' one-pagers. trial_stats / regulatory REUSE ClinicalReport /
# RegulatoryReport outright (desk/diligence.DD_REPORT_FOR). The 6 below reuse the Plan-1
# sections; each headline IS the reused section field, paired with a report-level `*_source`.
# C5: every headline anchors on a deterministic bundle fact — DDFinancialsReport has NO rNPV.


def _require_source(number, source, what: str) -> None:
    if number is not None and not (source or "").strip():
        raise ValueError(f"{what} requires a non-empty paired source (no-fabrication)")


class DDFinancialsReport(AnalystReportBase):
    runway: Runway = Runway()
    capital_structure: CapitalStructure = CapitalStructure()
    insiders: Insiders = Insiders()
    runway_months_source: str | None = None  # pairs runway.runway_months (HEADLINE)

    @model_validator(mode="after")
    def _headline_sourced(self):
        _require_source(self.runway.runway_months, self.runway_months_source, "financials runway.runway_months")
        return self


class OwnershipFlowReport(AnalystReportBase):
    short_interest: ShortInterest = ShortInterest()
    ownership: Ownership = Ownership()
    insiders: Insiders = Insiders()
    si_pct_float_source: str | None = None  # pairs short_interest.si_pct_float (HEADLINE)

    @model_validator(mode="after")
    def _headline_sourced(self):
        _require_source(self.short_interest.si_pct_float, self.si_pct_float_source, "ownership short_interest.si_pct_float")
        return self


class OptionsMoveReport(AnalystReportBase):
    expected_move: ExpectedMove = ExpectedMove()
    implied_prob: ImpliedProb = ImpliedProb()
    expected_move_pct_source: str | None = None  # pairs expected_move.expected_move_pct (HEADLINE; null when illiquid)

    @model_validator(mode="after")
    def _headline_sourced(self):
        _require_source(self.expected_move.expected_move_pct, self.expected_move_pct_source, "options expected_move.expected_move_pct")
        return self


class HedgeRevalidationReport(AnalystReportBase):
    validated: bool | None = None
    covers: str | None = None
    mechanism: str | None = None
    conditional_worst: float | None = None  # HEADLINE — un-netted worst cell of the validated inverse hedge
    conditional_worst_source: str | None = None

    @model_validator(mode="after")
    def _headline_sourced(self):
        _require_source(self.conditional_worst, self.conditional_worst_source, "hedge conditional_worst")
        return self


class Tradeability(BaseModel):
    """DD liquidity = can the TARGET leg trade at size (NOT the balance-sheet `Liquidity` section).
    Target leg only: liquidity_quote carries one leg."""

    model_config = _SECTION
    bid: float | None = None
    volume: float | None = None  # HEADLINE — 0 is the zero_liquidity hard fail
    oi: float | None = None
    volume_source: str | None = None


class LiquidityReport(AnalystReportBase):
    tradeability: Tradeability = Tradeability()

    @model_validator(mode="after")
    def _headline_sourced(self):
        _require_source(self.tradeability.volume, self.tradeability.volume_source, "liquidity tradeability.volume")
        return self


class HistoricalAnalogReport(AnalystReportBase):
    analogs: list[Analog] = []
    analog_realized_move_pct: float | None = None  # HEADLINE — realized move of the closest disconfirming analogs
    analog_realized_move_pct_source: str | None = None

    @model_validator(mode="after")
    def _headline_sourced(self):
        _require_source(self.analog_realized_move_pct, self.analog_realized_move_pct_source, "analog_realized_move_pct")
        return self


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
    portfolio_outcome: dict | None = None  # whole-book build_portfolio risk read (TARGET-LEG scope — the
    # long/long hedge peer carries no size this phase); None until attached post-select_book. Additive:
    # existing constructions omit it -> None (mirrors TradeProposal.hedge_profile optional-additive).


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


# ---------------------------------------------------------------------------------------
# 07.9-1.5 — the Catalyst Research Bundle: the shared cited-FACT substrate (CALL-01).
#
# ONE deterministic research pass computes every free/cited fact ONCE per catalyst, then hands the
# identical ground truth to every consumer (DD here; the 4 analysts via tool-backing in Plan 2). The
# FIREWALL is a TYPE invariant, not a policy pass: the bundle carries FACTS ONLY — it has NO field for
# any desk interpretation (analyst score/thesis, debate verdict, builder dossier). extra='forbid'
# makes a leaked interpretation a ValidationError. Each populated Fact is cite-or-drop AT THE CONTRACT:
# a value with neither a resolvable evidence_ref nor an inline citation is rejected.
# ponytail: one generic Fact wrapper + a flat facts container. No per-fact class, no builder — the
#           nullable-default value IS the "empty slot is a finding" rule (no null-fill code).
# ---------------------------------------------------------------------------------------


class Fact(BaseModel):
    """One cited datum in the substrate. `value` is loose (float/str/list/dict) — this is a raw-fact
    carrier, not a lens. Cite-or-drop: a populated value MUST carry a resolvable `evidence_ref`
    (tool:… minted by evidence.tool_ref_for) OR an inline `citation` (the base-rate
    {source_name, source_url, quote} shape). An empty Fact (value=None) needs neither — an empty slot
    is an honest finding, never a fabricated 0."""

    model_config = ConfigDict(extra="forbid")
    value: Any = None
    evidence_ref: str | None = None
    citation: dict | None = None
    context: str | None = None

    @model_validator(mode="after")
    def _cite_or_drop(self):
        if self.value is not None and self.evidence_ref is None and self.citation is None:
            raise ValueError("a populated Fact must carry an evidence_ref or an inline citation "
                             "(cite-or-drop at the contract)")
        return self


class CatalystResearchBundle(BaseModel):
    """The shared cited-fact substrate for one catalyst. FACTS ONLY (no interpretation field);
    extra='forbid'. Every fact defaults to an empty Fact (value=None) so an unsourced slot is a
    finding. `degraded` mirrors make_diligence_inputs' honest-degrade flags."""

    model_config = ConfigDict(extra="forbid")
    ticker: str
    catalyst: dict
    as_of: str | None = None
    analogs: Fact = Field(default_factory=Fact)          # kb.analog_query realized-move precedents
    base_rates: list[Fact] = []                          # inline-cited clinical priors (quant.base_rate)
    financials: Fact = Field(default_factory=Fact)       # edgar.fundamentals cash/burn/shares/runway
    trial: Fact = Field(default_factory=Fact)            # CT.gov record (non-money; None is fine)
    options: Fact = Field(default_factory=Fact)          # CBOE seam (quote + underlying)
    implied_move: Fact = Field(default_factory=Fact)     # quant.implied_move derivation over the quote
    ownership: Fact = Field(default_factory=Fact)        # FINRA SI + shares + Form-4 insider_net
    prices: Fact = Field(default_factory=Fact)           # point-in-time close series (serving.asof)
    hedge_inputs: Fact = Field(default_factory=Fact)     # analog_gaps split (catalyst_context shape)
    degraded: list[str] = []

    def fact_for(self, tool_name: str, inputs: dict) -> Fact | None:
        """Plan-2 tool-backing accessor: return the Fact whose evidence_ref == tool_ref_for(name,
        inputs), so a build_quant_tools cache-lookup is a one-liner. None if no fact was minted from
        that exact tool call."""
        from ..desk import evidence  # lazy: avoid a contracts->desk import cycle at module load

        ref = evidence.tool_ref_for(tool_name, inputs)
        for f in (self.analogs, self.financials, self.trial, self.options, self.implied_move,
                  self.ownership, self.prices, self.hedge_inputs, *self.base_rates):
            if f.evidence_ref == ref:
                return f
        return None
