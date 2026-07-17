"""Step 4 — Similarity scoring.

Weighted dimension overlap between the scenario and each verified case.
Claude classifies each of the 12 dimensions as matched or mismatched
(dimension values are free text, so this needs judgment, not string
equality); the weighting and ranking themselves are deterministic Python
using DEFAULT_DIMENSION_WEIGHTS. Top 5 by weighted score are kept, plus the
negative analogue (if verified) even if it doesn't rank in the top 5 —
mismatches are surfaced prominently ("where this analogy breaks down").
"""
import asyncio

from pydantic import BaseModel, Field

from app.engine.llm import structured_call
from app.engine.step3_verify import VerifiedCandidate
from app.models.dimensions import DEFAULT_DIMENSION_WEIGHTS, Dimension
from app.models.report import MatchedCase
from app.models.scenario import Scenario

SYSTEM_PROMPT = """You are comparing a decision scenario to a historical case, dimension by \
dimension, for analogical-reasoning purposes. For EACH of the 12 structural dimensions, decide \
whether the scenario's value and the historical case's value describe a materially similar \
structural situation (matches=true) or a materially different one (matches=false). Be \
discriminating — superficial wording overlap is not enough; judge whether the underlying \
structural situation matches. Give a one-sentence note explaining your call for each dimension."""


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


async def _score_case(scenario: Scenario, candidate: VerifiedCandidate) -> MatchedCase:
    scenario_dims = scenario.dimensions.as_dict()
    case_dims = candidate.case.dimensions.as_dict()
    lines = []
    for dim in Dimension:
        lines.append(f"- {dim.value}: scenario={scenario_dims.get(dim, '')!r} | case={case_dims.get(dim, '')!r}")
    user_prompt = f"Scenario: {scenario.raw_text}\nCase: {candidate.case.name} ({candidate.case.dates})\n\n" + "\n".join(lines)

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


async def score_similarity(
    scenario: Scenario, candidates: list[VerifiedCandidate], top_n: int = 5
) -> list[MatchedCase]:
    if not candidates:
        return []

    scored = await asyncio.gather(*[_score_case(scenario, c) for c in candidates])
    ranked = sorted(scored, key=lambda m: m.similarity_score, reverse=True)

    top = ranked[:top_n]
    top_ids = {m.case_id for m in top}

    negative = next((m for m in ranked if m.is_negative_analogue), None)
    if negative is not None and negative.case_id not in top_ids:
        top.append(negative)

    return top
