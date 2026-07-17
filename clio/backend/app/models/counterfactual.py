from enum import Enum

from pydantic import BaseModel, Field


class Plausibility(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Counterfactual(BaseModel):
    """A minimal-rewrite branch: change exactly one variable, hold all else constant."""

    changed_variable: str
    narrative: str
    plausibility: Plausibility
    key_assumptions: list[str] = Field(default_factory=list)
