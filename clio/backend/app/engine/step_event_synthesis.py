"""Step E7 — Event-analysis synthesis.

The primary case's own assessments/counterfactuals/lessons (produced when
Step 3 structured it) already ARE the direct answer to "was this decision
right or wrong, and what could have changed the effects" — this step just
weaves them into a readable narrative verdict, alongside a red-team
paragraph, confidence statement, and what-would-change-this note, informed
by the comparable analogues and base-rate context gathered around it.
"""
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel

from app.engine.llm import structured_call
from app.models.case import StructuredCase
from app.models.event import EventAnalysisReport
from app.models.report import BaseRateTable, MatchedCase

SYSTEM_PROMPT = """You are writing the synthesis for a retrospective analysis of a real \
historical decision. You are given: the primary case (with its own decision/execution/outcome \
assessments, counterfactuals, and lessons, already researched and source-grounded), a set of \
comparable historical cases, and a base-rate table computed from real conflict data.

Write:
- assessment_narrative: a readable prose verdict synthesizing the primary case's own \
  assessments — was the decision sound GIVEN THE INFORMATION AVAILABLE AT THE TIME (not \
  judged by hindsight of the outcome), was execution sound, and how did it actually turn out. \
  Explicitly distinguish decision quality from outcome — a sound decision can have a bad \
  outcome and vice versa. Reference the case's own counterfactuals for "what could have changed \
  the effects."
- red_team_paragraph: the strongest argument against this whole assessment — attack the \
  framing, the choice of comparable cases, or the base-rate reference class.
- confidence_statement: how confident this assessment should be taken, and why.
- what_would_change_assessment: what new information would most change this assessment.

Ground every claim in the primary case's own researched content and the comparable cases \
provided — do not introduce new historical claims not present in what you're given."""


class StepEventSynthesisOutput(BaseModel):
    assessment_narrative: str
    red_team_paragraph: str
    confidence_statement: str
    what_would_change_assessment: str


def _comparable_cases_text(comparable: list[MatchedCase], cases_by_id: dict[str, StructuredCase]) -> str:
    lines = []
    for m in comparable:
        case = cases_by_id.get(m.case_id)
        if case is None:
            continue
        tag = " [NEGATIVE ANALOGUE]" if m.is_negative_analogue else ""
        lines.append(f"- {case.name}{tag} (similarity {m.similarity_score:.2f}): {case.summary}")
    return "\n".join(lines) if lines else "(no comparable cases)"


def _primary_case_text(case: StructuredCase) -> str:
    assessments = "\n".join(
        f"  - {a.axis.value}: {a.score_1_10}/10 — {a.reasoning}" for a in case.assessments
    ) or "  (no assessments recorded)"
    counterfactuals = "\n".join(
        f"  - {cf.changed_variable} -> {cf.narrative} (plausibility: {cf.plausibility.value})"
        for cf in case.counterfactuals
    ) or "  (no counterfactuals recorded)"
    lessons = "\n".join(f"  - {l.principle} (limits: {l.transferability_limits})" for l in case.lessons) or "  (none)"

    return f"""{case.name} ({case.dates})
Summary: {case.summary}
Decision: {case.decision.chosen_option} by {case.decision.decision_maker}
Adversary calculus: {case.adversary_calculus}
Assessments:
{assessments}
Counterfactuals:
{counterfactuals}
Lessons:
{lessons}"""


def _base_rate_text(table: BaseRateTable | None) -> str:
    if table is None or table.n_cases == 0:
        return "(no base-rate data available)"
    rows = "; ".join(f"{r.outcome}: {r.count} ({r.pct}%)" for r in table.rows)
    return f"N={table.n_cases}, query: {table.query_definition}. Outcomes: {rows}."


async def synthesize_event_report(
    event_query_id: str,
    primary_case: StructuredCase,
    comparable_cases: list[MatchedCase],
    cases_by_id: dict[str, StructuredCase],
    base_rate_table: BaseRateTable,
) -> EventAnalysisReport:
    user_prompt = f"""Primary case:
{_primary_case_text(primary_case)}

Comparable cases:
{_comparable_cases_text(comparable_cases, cases_by_id)}

Base-rate table:
{_base_rate_text(base_rate_table)}"""

    synthesis = await structured_call(
        system=SYSTEM_PROMPT,
        user=user_prompt,
        response_model=StepEventSynthesisOutput,
        max_tokens=4096,
    )

    all_sources = {str(url) for case in cases_by_id.values() for url in case.source_urls}

    return EventAnalysisReport(
        id=str(uuid.uuid4()),
        event_query_id=event_query_id,
        primary_case_id=primary_case.id,
        comparable_cases=comparable_cases,
        base_rate_table=base_rate_table,
        assessment_narrative=synthesis.assessment_narrative,
        red_team_paragraph=synthesis.red_team_paragraph,
        confidence_statement=synthesis.confidence_statement,
        what_would_change_assessment=synthesis.what_would_change_assessment,
        source_urls=list(all_sources),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
