"""Step E3 — Comparable-analogue nomination for the event-analysis mode.

Same output shape as Step 2 (NominatedCandidate), but seeded from an
already-verified primary historical case rather than a hypothetical
scenario: "given this real event, what OTHER historical events are
structurally comparable?" Also nominates a negative analogue, for the same
reason Step 2 does — to warn against a tempting but misleading comparison.
"""
from pydantic import BaseModel, Field

from app.engine.llm import structured_call
from app.engine.step2_nominate import NominatedCandidate
from app.models.case import StructuredCase

SYSTEM_PROMPT = """You are a historian nominating comparable historical events for a case that \
has already been researched and verified. Given the primary case's summary and structural \
dimensions, propose 6 to 8 OTHER historical cases that are structurally comparable — NOT the \
primary case itself, and not simply other events in the same war/conflict unless they represent \
a genuinely distinct comparable decision.

Requirements:
- Range broadly across eras and regions.
- For each candidate, give: a short name, approximate date range, a one-line structural \
  rationale explaining WHY it's comparable (referencing specific dimensions), and the EXACT \
  title of the English Wikipedia article about it.
- Include AT LEAST ONE negative analogue: a case that superficially resembles the primary case \
  (similar surface framing, e.g. "another proxy war" or "another covert program") but is \
  structurally different in ways that would mislead. Mark it with is_negative_analogue=true.
- Do not invent cases or Wikipedia titles — only nominate cases you are confident are real and \
  have real English Wikipedia articles."""


class StepEventComparableNomination(BaseModel):
    candidates: list[NominatedCandidate] = Field(min_length=1)


async def nominate_comparable_analogues(primary_case: StructuredCase) -> list[NominatedCandidate]:
    dims = primary_case.dimensions.as_dict()
    dims_text = "\n".join(f"- {dim.value}: {value}" for dim, value in dims.items() if value)

    user_prompt = f"""Primary case: {primary_case.name} ({primary_case.dates})
Summary: {primary_case.summary}

Structural dimensions:
{dims_text or "(none available)"}"""

    result = await structured_call(
        system=SYSTEM_PROMPT,
        user=user_prompt,
        response_model=StepEventComparableNomination,
        max_tokens=4096,
    )
    return result.candidates
