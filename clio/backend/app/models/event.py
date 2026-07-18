"""Models for the historical-event-analysis mode: instead of "here's a
hypothetical scenario, find analogues," this is "here's something that
actually happened, was the decision right or wrong, and what could have
changed the effects." Anchored on a single StructuredCase (the "primary
case") rather than a Scenario + options.
"""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl

from app.models.report import STANDING_DISCLAIMER, BaseRateTable, MatchedCase


class EventQueryStatus(str, Enum):
    IDENTIFYING = "identifying"   # Step E1 in progress
    IDENTIFIED = "identified"     # resolved to a real event, ready to analyze
    NOT_FOUND = "not_found"       # could not confidently resolve to a real, verifiable event
    ANALYZING = "analyzing"       # pipeline running
    COMPLETE = "complete"


class EventQuery(BaseModel):
    id: str
    raw_text: str
    status: EventQueryStatus = EventQueryStatus.IDENTIFYING
    resolved_name: str = ""
    resolved_dates: str = ""
    wikipedia_title: str = ""
    not_found_reason: str = ""
    created_at: datetime | None = None


class EventQueryCreateRequest(BaseModel):
    raw_text: str = Field(min_length=1, max_length=4000)


class EventAnalysisReport(BaseModel):
    """The primary output is `primary_case`'s own assessments/counterfactuals/
    lessons (from Step 3's structuring) — that's the direct answer to "was
    this decision right or wrong, and what could have changed the effects."
    `comparable_cases` + `base_rate_table` provide historical context around
    it; `red_team_paragraph` argues against the whole assessment.
    """

    id: str
    event_query_id: str
    primary_case_id: str
    comparable_cases: list[MatchedCase] = Field(default_factory=list)
    base_rate_table: BaseRateTable | None = None
    assessment_narrative: str = ""  # prose synthesis of the primary case's own assessments
    red_team_paragraph: str = ""
    confidence_statement: str = ""
    what_would_change_assessment: str = ""
    disclaimer: str = STANDING_DISCLAIMER
    source_urls: list[HttpUrl] = Field(default_factory=list)
    generated_at: str | None = None
