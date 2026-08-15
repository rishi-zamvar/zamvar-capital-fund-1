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


class TradeProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_long: str
    hedge_long: str
    pair_rationale: str
    entry: float
    exit_by_date: str
    stop_loss: float
    take_profit: float
    size_pct: float
    expected_return_pct: float
    kb_analogs: list[str] = []


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


class DiligenceDossier(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["go", "no_go"]
    per_dimension: list[dict]
    red_flags: list[str] = []
    strongest_disconfirming_evidence: str
    all_evidence_refs: list[str] = []
