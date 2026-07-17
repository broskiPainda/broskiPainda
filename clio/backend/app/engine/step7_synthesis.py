"""Step 7 — Synthesis.

Assembles the final report: per-option decision-quality assessment
(explicitly NOT an outcome prediction — judged on soundness given stated
information), a best-analogue deep dive, a negative-analogue warning, the
base-rate table (from Step 5), the counterfactual tree (from Step 6), a
red-team paragraph arguing against the whole analysis, a confidence
statement, and the standing disclaimer.
"""
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.engine.llm import structured_call
from app.models.case import StructuredCase
from app.models.counterfactual import Counterfactual
from app.models.report import BaseRateTable, MatchedCase, OptionAssessment, Report
from app.models.scenario import Scenario

SYSTEM_PROMPT = """You are writing the synthesis section of a historical-decision-intelligence \
report. You are given: the scenario, its options, the ranked verified historical analogues (with \
similarity scores and matched/mismatched dimensions), a marked negative analogue, and a base-rate \
table computed from real conflict data.

For EACH option, write a decision-quality assessment: judge the soundness of that option given \
the information actually available in the scenario — this is explicitly NOT a prediction of \
whether the option would succeed. Say so explicitly if it's not obvious.

Write a deep dive on the single best-matching analogue explaining why it's the strongest \
structural match and what it suggests.

Write a warning about the negative analogue: explain why someone might be tempted to reach for it \
and why that would be misleading, referencing the mismatched dimensions.

Write a red-team paragraph: the strongest argument against this whole analysis — attack the \
choice of analogues, the base-rate reference class, or the framing itself.

Write a confidence statement, and separately state what new information would most change this \
assessment.

Ground every claim in the analogues and base-rate data provided — do not introduce new historical \
claims not present in the analogue summaries."""


class SynthesizedOption(BaseModel):
    option_id: str
    option_label: str
    decision_quality_summary: str
    supporting_reasoning: str


class StepSevenSynthesis(BaseModel):
    option_assessments: list[SynthesizedOption] = Field(default_factory=list)
    best_analogue_deep_dive: str
    negative_analogue_warning: str = ""
    red_team_paragraph: str
    confidence_statement: str
    what_would_change_assessment: str


def _analogues_text(matched: list[MatchedCase], cases_by_id: dict[str, StructuredCase]) -> str:
    lines = []
    for m in matched:
        case = cases_by_id.get(m.case_id)
        if case is None:
            continue
        tag = " [NEGATIVE ANALOGUE]" if m.is_negative_analogue else ""
        lines.append(
            f"- {case.name}{tag} (similarity {m.similarity_score:.2f}): {case.summary}\n"
            f"  Matched dimensions: {', '.join(d.value for d in m.matched_dimensions) or 'none'}\n"
            f"  Mismatched dimensions: {', '.join(d.value for d in m.mismatched_dimensions) or 'none'}"
        )
    return "\n".join(lines) if lines else "(no verified analogues)"


def _base_rate_text(table: BaseRateTable | None) -> str:
    if table is None or table.n_cases == 0:
        return "(no base-rate data available)"
    rows = "; ".join(f"{r.outcome}: {r.count} ({r.pct}%)" for r in table.rows)
    return (
        f"N={table.n_cases}, query: {table.query_definition}. Outcomes: {rows}. "
        f"Mean duration (days, approx.): {table.mean_duration_days}. "
        f"Escalation-to-war rate: {table.escalation_to_war_rate}."
    )


async def synthesize_report(
    scenario: Scenario,
    matched_cases: list[MatchedCase],
    cases_by_id: dict[str, StructuredCase],
    base_rate_table: BaseRateTable,
    counterfactuals_by_option: dict[str, list[Counterfactual]],
) -> Report:
    options_text = "\n".join(f"- {o.id}: {o.label} — {o.description}" for o in scenario.options) or "(no options specified)"

    user_prompt = f"""Scenario: {scenario.raw_text}

Options:
{options_text}

Ranked verified analogues:
{_analogues_text(matched_cases, cases_by_id)}

Base-rate table:
{_base_rate_text(base_rate_table)}"""

    synthesis = await structured_call(
        system=SYSTEM_PROMPT,
        user=user_prompt,
        response_model=StepSevenSynthesis,
        max_tokens=6000,
    )

    option_assessments = [
        OptionAssessment(
            option_id=oa.option_id,
            option_label=oa.option_label,
            decision_quality_summary=oa.decision_quality_summary,
            supporting_reasoning=oa.supporting_reasoning,
            counterfactuals=counterfactuals_by_option.get(oa.option_id, []),
        )
        for oa in synthesis.option_assessments
    ]

    best = max(matched_cases, key=lambda m: m.similarity_score, default=None)
    negative = next((m for m in matched_cases if m.is_negative_analogue), None)

    all_sources = {
        str(url)
        for case in cases_by_id.values()
        for url in case.source_urls
    }

    return Report(
        id=str(uuid.uuid4()),
        scenario_id=scenario.id,
        matched_cases=matched_cases,
        negative_analogue_case_id=negative.case_id if negative else None,
        negative_analogue_warning=synthesis.negative_analogue_warning,
        best_analogue_case_id=best.case_id if best else None,
        best_analogue_deep_dive=synthesis.best_analogue_deep_dive,
        option_assessments=option_assessments,
        base_rate_table=base_rate_table,
        red_team_paragraph=synthesis.red_team_paragraph,
        confidence_statement=synthesis.confidence_statement,
        what_would_change_assessment=synthesis.what_would_change_assessment,
        source_urls=list(all_sources),
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
