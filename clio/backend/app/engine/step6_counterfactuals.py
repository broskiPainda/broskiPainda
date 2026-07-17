"""Step 6 — Counterfactuals.

For the user's top 2 options, generate minimal-rewrite branches (change
exactly one variable, hold all else constant), grounded in the verified
analogues' own counterfactuals, each with a plausibility rating and key
assumptions.
"""
import asyncio

from pydantic import BaseModel, Field

from app.engine.llm import structured_call
from app.models.case import StructuredCase
from app.models.counterfactual import Counterfactual
from app.models.scenario import Scenario, ScenarioOption

SYSTEM_PROMPT = """You are constructing counterfactual branches for one option under \
consideration in a decision scenario. Given the scenario, the option, and grounding drawn from \
verified historical analogues (including their own counterfactuals), produce 2-3 MINIMAL-\
REWRITE counterfactuals: each changes exactly ONE variable from the scenario's actual trajectory \
and holds everything else constant. For each, give: the single changed variable, a narrative of \
how events would plausibly unfold differently, a plausibility rating (low/medium/high), and the \
key assumptions your narrative depends on. Ground your reasoning in patterns from the analogues \
provided — do not invent unrelated scenarios."""


class StepSixCounterfactuals(BaseModel):
    counterfactuals: list[Counterfactual] = Field(min_length=1)


def _grounding_text(cases: list[StructuredCase]) -> str:
    blocks = []
    for case in cases:
        cf_text = "; ".join(
            f"{cf.changed_variable} -> {cf.narrative} (plausibility: {cf.plausibility.value})"
            for cf in case.counterfactuals
        ) or "(no counterfactuals recorded for this case)"
        blocks.append(f"- {case.name} ({case.dates}): {case.summary}\n  Case counterfactuals: {cf_text}")
    return "\n".join(blocks) if blocks else "(no verified analogues available)"


async def _counterfactuals_for_option(
    scenario: Scenario, option: ScenarioOption, cases: list[StructuredCase]
) -> list[Counterfactual]:
    user_prompt = f"""Scenario: {scenario.raw_text}

Option under consideration: {option.label}
{option.description}

Grounding from verified historical analogues:
{_grounding_text(cases)}"""

    result = await structured_call(
        system=SYSTEM_PROMPT,
        user=user_prompt,
        response_model=StepSixCounterfactuals,
    )
    return result.counterfactuals


async def generate_counterfactuals(
    scenario: Scenario, cases: list[StructuredCase], top_n_options: int = 2
) -> dict[str, list[Counterfactual]]:
    options = scenario.options[:top_n_options]
    if not options:
        return {}

    results = await asyncio.gather(*[_counterfactuals_for_option(scenario, o, cases) for o in options])
    return {option.id: cfs for option, cfs in zip(options, results)}
