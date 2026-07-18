from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.models.case import Actor
from app.models.dimensions import Dimension


class ScenarioStatus(str, Enum):
    DRAFT = "draft"          # Step 1 output, awaiting user confirmation
    CONFIRMED = "confirmed"  # user has confirmed/edited the structure
    ANALYZING = "analyzing"  # Steps 2-7 in progress
    COMPLETE = "complete"    # report available


class ScenarioDimensions(BaseModel):
    """Scenario-side values for the 12 dimensions, editable by the user as chips."""

    power_asymmetry: str = ""
    alliance_architecture: str = ""
    domestic_constraints: str = ""
    geography: str = ""
    time_pressure: str = ""
    information_environment: str = ""
    escalation_position: str = ""
    economic_interdependence: str = ""
    third_party_involvement: str = ""
    regime_types: str = ""
    stakes_framing: str = ""
    technology_era: str = ""

    def as_dict(self) -> dict[Dimension, str]:
        return {Dimension(k): v for k, v in self.model_dump().items()}


class ScenarioOption(BaseModel):
    id: str
    label: str
    description: str = ""


class Scenario(BaseModel):
    id: str
    raw_text: str
    status: ScenarioStatus = ScenarioStatus.DRAFT
    actors: list[Actor] = Field(default_factory=list)
    objectives_by_actor: dict[str, str] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    options: list[ScenarioOption] = Field(default_factory=list)
    dimensions: ScenarioDimensions = Field(default_factory=ScenarioDimensions)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ScenarioCreateRequest(BaseModel):
    raw_text: str = Field(min_length=1, max_length=8000)


class ScenarioUpdateRequest(BaseModel):
    """User-edited structure, submitted via PUT /api/scenarios/{id}."""

    actors: list[Actor] = Field(default_factory=list)
    objectives_by_actor: dict[str, str] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    options: list[ScenarioOption] = Field(default_factory=list)
    dimensions: ScenarioDimensions
