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

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
