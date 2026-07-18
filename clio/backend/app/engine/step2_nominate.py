"""Step 2 — Analogue nomination.

Claude proposes 8-10 historical analogues with a one-line structural
rationale and an exact Wikipedia article title, breadth across eras, and at
least one deliberate negative analogue (a case that superficially resembles
the scenario but is structurally different) — used later to warn against
bad analogies.
"""
from pydantic import BaseModel, Field

from app.engine.llm import structured_call
from app.models.scenario import Scenario

SYSTEM_PROMPT = """You are a historian nominating candidate historical analogues for a \
political/military decision scenario. Given a structured scenario description, propose \
8 to 10 historical cases that could serve as analogues.

Requirements:
- Range broadly across eras and regions — do not cluster on one century or one theater.
- For each candidate, give: a short name, approximate date range, a one-line structural \
  rationale explaining WHY it resembles the scenario (referencing specific dimensions like \
  power asymmetry, alliance structure, escalation position, etc.), and the EXACT title of the \
  English Wikipedia article about it (so it can be looked up programmatically — get this \
  precise, including capitalization).
- Include AT LEAST ONE negative analogue: a case that superficially resembles the scenario \
  (same surface-level actors, era, or terminology) but is structurally different in ways that \
  would mislead someone who relied on it. Mark it with is_negative_analogue=true and explain \
  the structural mismatch in the rationale.
- Do not invent cases or Wikipedia titles — only nominate cases you are confident are real \
  and have real English Wikipedia articles."""


class NominatedCandidate(BaseModel):
    name: str
    approximate_dates: str
    structural_rationale: str
    wikipedia_title: str
    is_negative_analogue: bool = False


class StepTwoNomination(BaseModel):
    candidates: list[NominatedCandidate] = Field(min_length=1)


async def nominate_analogues(scenario: Scenario) -> list[NominatedCandidate]:
    dims = scenario.dimensions.as_dict()
    dims_text = "\n".join(f"- {dim.value}: {value}" for dim, value in dims.items() if value)
    actors_text = "\n".join(f"- {a.name} ({a.role.value}, {a.regime_type})" for a in scenario.actors)
    options_text = "\n".join(f"- {o.label}" for o in scenario.options) or "(none specified)"

    user_prompt = f"""Scenario: {scenario.raw_text}

Actors:
{actors_text or "(none extracted)"}

Options under consideration:
{options_text}

Structural dimensions:
{dims_text or "(none extracted)"}"""

    result = await structured_call(
        system=SYSTEM_PROMPT,
        user=user_prompt,
        response_model=StepTwoNomination,
        max_tokens=4096,
    )
    return result.candidates
