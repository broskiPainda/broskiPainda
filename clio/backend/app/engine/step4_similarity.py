"""Step 4 — Similarity scoring.

Weighted dimension overlap between a reference (a hypothetical scenario, OR
in the event-analysis mode, an already-verified primary historical case)
and each verified candidate case. Claude classifies each of the 12
dimensions as matched or mismatched (dimension values are free text, so
this needs judgment, not string equality); the weighting and ranking
themselves are deterministic Python using DEFAULT_DIMENSION_WEIGHTS. Top 5
by weighted score are kept, plus the negative analogue (if verified) even
if it doesn't rank in the top 5 — mismatches are surfaced prominently
("where this analogy breaks down").
"""
import asyncio

from pydantic import BaseModel, Field

from app.engine.llm import structured_call
from app.engine.step3_verify import VerifiedCandidate
from app.models.case import StructuredCase
from app.models.dimensions import DEFAULT_DIMENSION_WEIGHTS, Dimension
from app.models.report import MatchedCase
from app.models.scenario import Scenario

SYSTEM_PROMPT = """You are comparing a reference decision (a scenario, or a real historical \
case) to a candidate historical case, dimension by dimension, for analogical-reasoning \
purposes. For EACH of the 12 structural dimensions, decide whether the reference's value and \
the candidate case's value describe a materially similar structural situation (matches=true) or \
a materially different one (matches=false). Be discriminating — superficial wording overlap is \
not enough; judge whether the underlying structural situation matches. Give a one-sentence note \
explaining your call for each dimension."""


class DimensionMatch(BaseModel):
    dimension: str
    matches: bool
    note: str = ""


class StepFourComparison(BaseModel):
    dimension_matches: list[DimensionMatch] = Field(min_length=1)


def _weighted_score(matches: list[DimensionMatch]) -> tuple[float, list[Dimension], list[Dimension]]:
    total_weight = 0.0
    matched_weight = 0.0
    matched: list[Dimension] = []
    mismatched: list[Dimension] = []
    for dm in matches:
        try:
            dim = Dimension(dm.dimension)
        except ValueError:
            continue
        weight = DEFAULT_DIMENSION_WEIGHTS.get(dim, 1.0)
        total_weight += weight
        if dm.matches:
            matched_weight += weight
            matched.append(dim)
        else:
            mismatched.append(dim)
    score = matched_weight / total_weight if total_weight else 0.0
    return score, matched, mismatched


async def _score_against_reference(
    reference_label: str,
    reference_dims: dict[Dimension, str],
    candidate: VerifiedCandidate,
) -> MatchedCase:
    case_dims = candidate.case.dimensions.as_dict()
    lines = [
        f"- {dim.value}: reference={reference_dims.get(dim, '')!r} | case={case_dims.get(dim, '')!r}"
        for dim in Dimension
    ]
    user_prompt = (
        f"Reference: {reference_label}\nCase: {candidate.case.name} ({candidate.case.dates})\n\n"
        + "\n".join(lines)
    )

    result = await structured_call(
        system=SYSTEM_PROMPT,
        user=user_prompt,
        response_model=StepFourComparison,
    )
    score, matched, mismatched = _weighted_score(result.dimension_matches)
    return MatchedCase(
        case_id=candidate.case.id,
        similarity_score=score,
        matched_dimensions=matched,
        mismatched_dimensions=mismatched,
        is_negative_analogue=candidate.is_negative_analogue,
    )


async def _score_and_rank(
    reference_label: str,
    reference_dims: dict[Dimension, str],
    candidates: list[VerifiedCandidate],
    top_n: int,
) -> list[MatchedCase]:
    if not candidates:
        return []

    scored = await asyncio.gather(
        *[_score_against_reference(reference_label, reference_dims, c) for c in candidates]
    )
    ranked = sorted(scored, key=lambda m: m.similarity_score, reverse=True)

    top = ranked[:top_n]
    top_ids = {m.case_id for m in top}

    negative = next((m for m in ranked if m.is_negative_analogue), None)
    if negative is not None and negative.case_id not in top_ids:
        top.append(negative)

    return top


async def score_similarity(
    scenario: Scenario, candidates: list[VerifiedCandidate], top_n: int = 5
) -> list[MatchedCase]:
    return await _score_and_rank(scenario.raw_text, scenario.dimensions.as_dict(), candidates, top_n)


async def score_similarity_against_case(
    primary_case: StructuredCase, candidates: list[VerifiedCandidate], top_n: int = 5
) -> list[MatchedCase]:
    label = f"{primary_case.name} ({primary_case.dates}): {primary_case.summary}"
    return await _score_and_rank(label, primary_case.dimensions.as_dict(), candidates, top_n)
