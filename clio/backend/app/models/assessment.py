from enum import Enum

from pydantic import BaseModel, Field


class AssessmentAxis(str, Enum):
    DECISION = "decision"
    EXECUTION = "execution"
    OUTCOME = "outcome"


class Assessment(BaseModel):
    """A scored judgment along one axis of a historical case.

    Decision-quality is judged on soundness given the information available
    at the time — never as a retroactive verdict on the outcome.
    """

    axis: AssessmentAxis
    score_1_10: int = Field(ge=1, le=10)
    reasoning: str
