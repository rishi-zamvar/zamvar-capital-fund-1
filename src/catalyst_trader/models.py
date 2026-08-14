"""Pydantic domain models. The no-LLM-date invariant is enforced here at the type boundary:
a Catalyst cannot exist without at least one named source row."""

from enum import Enum

from pydantic import BaseModel, field_validator


class CatalystType(str, Enum):
    pdufa = "pdufa"
    adcom = "adcom"
    trial_readout = "trial_readout"
    earnings = "earnings"
    conference = "conference"


class DatePrecision(str, Enum):
    day = "day"
    month = "month"
    quarter = "quarter"
    year = "year"


class Uncertainty(str, Enum):
    firm = "firm"
    window = "window"
    soft = "soft"


class Status(str, Enum):
    unverified = "unverified"
    verified = "verified"
    excluded = "excluded"
    resolved = "resolved"


class SourceOrigin(str, Enum):
    clinicaltrials_gov = "clinicaltrials_gov"
    fmp_earnings = "fmp_earnings"
    curated_pdufa = "curated_pdufa"
    ad_hoc_user = "ad_hoc_user"


class SourceType(str, Enum):
    primary = "primary"
    secondary = "secondary"


class DateType(str, Enum):
    estimated = "estimated"
    actual = "actual"


class CatalystSource(BaseModel):
    source_name: str
    source_url: str | None = None
    source_type: SourceType
    reported_date: str
    # DATA-04: the source's own ESTIMATED/ACTUAL typing. Default estimated — providers set it
    # explicitly per source; verify.py re-derives uncertainty from this, never a guess.
    date_type: DateType = DateType.estimated
    agrees: bool = True
    retrieved_at: str


class Catalyst(BaseModel):
    ticker: str
    company_name: str | None = None
    catalyst_type: CatalystType
    event_date: str  # ISO; may be YYYY, YYYY-MM, or YYYY-MM-DD
    event_date_end: str | None = None
    date_precision: DatePrecision
    uncertainty_type: Uncertainty
    status: Status = Status.unverified
    source_origin: SourceOrigin
    last_verified_at: str | None = None
    external_ref: str | None = None
    sources: list[CatalystSource]

    @field_validator("sources")
    @classmethod
    def _at_least_one_source(cls, v: list[CatalystSource]) -> list[CatalystSource]:
        if not v:
            raise ValueError(
                "a catalyst may not exist without a named source (no LLM-sourced dates)"
            )
        return v


class UniverseSnapshot(BaseModel):
    as_of_date: str
    ticker: str
    included: bool
    delisted: bool = False
    criteria_json: str | None = None
    reason: str | None = None
