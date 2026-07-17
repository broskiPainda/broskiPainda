"""StructuredCase: the core case schema.

This is the future-KG migration contract (see docs/MIGRATION_TO_KG.md) — keep
field names and shapes stable. Narrative fields (summary, pre_event,
decision, execution_notes, outcomes) must be grounded in fetched source text.
Analytical fields (assessments, counterfactuals, lessons) are Claude's
reasoning but must reference sourced facts.
"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl

from app.models.assessment import Assessment
from app.models.counterfactual import Counterfactual
from app.models.dimensions import Dimension


class ActorRole(str, Enum):
    INITIATOR = "initiator"
    TARGET = "target"
    THIRD_PARTY = "third_party"


class Actor(BaseModel):
    name: str
    role: ActorRole
    regime_type: str


class PreEvent(BaseModel):
    context: str
    objectives_by_actor: dict[str, str] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    options_on_table: list[str] = Field(default_factory=list)
    info_available_at_time: list[str] = Field(default_factory=list)
    info_unknown_at_time: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    chosen_option: str
    decision_maker: str
    process: str
    dissenting_voices: list[str] = Field(default_factory=list)
    time_pressure: str


class OutcomeHorizon(str, Enum):
    IMMEDIATE = "immediate"
    FIVE_YEAR = "5yr"
    TWENTYFIVE_YEAR = "25yr"


class OutcomeValence(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    MIXED = "mixed"


class Outcome(BaseModel):
    horizon: OutcomeHorizon
    description: str
    valence: OutcomeValence


class Lesson(BaseModel):
    principle: str
    transferability_limits: str


class CaseDimensions(BaseModel):
    """Values for the 12 structural dimensions, keyed by Dimension enum."""

    power_asymmetry: str
    alliance_architecture: str
    domestic_constraints: str
    geography: str
    time_pressure: str
    information_environment: str
    escalation_position: str
    economic_interdependence: str
    third_party_involvement: str
    regime_types: str
    stakes_framing: str
    technology_era: str

    def as_dict(self) -> dict[Dimension, str]:
        return {Dimension(k): v for k, v in self.model_dump().items()}


class StructuredCase(BaseModel):
    id: str
    name: str
    era: str
    dates: str
    source_urls: list[HttpUrl] = Field(default_factory=list)
    summary: str
    actors: list[Actor] = Field(default_factory=list)
    pre_event: PreEvent
    decision: Decision
    execution_notes: str
    outcomes: list[Outcome] = Field(default_factory=list)
    assessments: list[Assessment] = Field(default_factory=list)
    counterfactuals: list[Counterfactual] = Field(default_factory=list)
    adversary_calculus: str
    lessons: list[Lesson] = Field(default_factory=list)
    dimensions: CaseDimensions
    generated_by_model: bool = True
    verified_against_sources: bool = False
    cached_at: datetime | None = None
