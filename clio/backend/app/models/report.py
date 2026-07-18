from pydantic import BaseModel, Field, HttpUrl

from app.models.case import StructuredCase
from app.models.counterfactual import Counterfactual
from app.models.dimensions import Dimension

STANDING_DISCLAIMER = (
    "CLIO informs judgment through historical analogy; it does not predict "
    "outcomes or replace human decision-making. Cases are machine-structured "
    "from open sources and may contain errors — verify before relying on them."
)


class MatchedCase(BaseModel):
    case_id: str
    similarity_score: float = Field(ge=0.0, le=1.0)
    matched_dimensions: list[Dimension] = Field(default_factory=list)
    mismatched_dimensions: list[Dimension] = Field(default_factory=list)
    is_negative_analogue: bool = False


class BaseRateRow(BaseModel):
    outcome: str  # e.g. "initiator achieved objectives" | "stalemate" | "failed"
    count: int
    pct: float


class BaseRateTable(BaseModel):
    query_definition: str  # human-readable description of the CoW/UCDP filter used, for transparency
    n_cases: int
    rows: list[BaseRateRow]
    mean_duration_days: float | None = None
    escalation_to_war_rate: float | None = None
    source: str  # "Correlates of War" | "UCDP"


class OptionAssessment(BaseModel):
    option_id: str
    option_label: str
    decision_quality_summary: str  # explicitly NOT an outcome prediction
    supporting_reasoning: str
    counterfactuals: list[Counterfactual] = Field(default_factory=list)


class Report(BaseModel):
    id: str
    scenario_id: str
    matched_cases: list[MatchedCase] = Field(default_factory=list)
    negative_analogue_case_id: str | None = None
    negative_analogue_warning: str = ""
    best_analogue_case_id: str | None = None
    best_analogue_deep_dive: str = ""
    option_assessments: list[OptionAssessment] = Field(default_factory=list)
    base_rate_table: BaseRateTable | None = None
    red_team_paragraph: str = ""
    confidence_statement: str = ""
    what_would_change_assessment: str = ""
    disclaimer: str = STANDING_DISCLAIMER
    source_urls: list[HttpUrl] = Field(default_factory=list)
    generated_at: str | None = None


class ReportWithCases(Report):
    """Report expanded with full case bodies, for the Analysis View / PDF export."""

    cases: list[StructuredCase] = Field(default_factory=list)
