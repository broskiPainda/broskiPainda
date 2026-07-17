import pytest

from app.engine import step4_similarity
from app.engine.step3_verify import VerifiedCandidate
from app.models.dimensions import Dimension
from app.models.scenario import Scenario, ScenarioDimensions
from tests.fakes import FakeAnthropicClient
from tests.test_models import make_case


def make_scenario() -> Scenario:
    return Scenario(
        id="s1",
        raw_text="A mid-size power is considering a naval blockade of a smaller neighbor.",
        dimensions=ScenarioDimensions(power_asymmetry="asymmetric", stakes_framing="sovereignty"),
    )


def _all_match_response(matches: bool) -> dict:
    return {
        "dimension_matches": [{"dimension": d.value, "matches": matches, "note": "n/a"} for d in Dimension]
    }


@pytest.mark.asyncio
async def test_score_similarity_ranks_and_weights(monkeypatch):
    strong_cases = [make_case(id=f"s{i}", name=f"Strong Case {i}") for i in range(5)]
    negative_case = make_case(id="neg", name="Negative Case")

    marker_pairs = [(c.name, _all_match_response(True)) for c in strong_cases]
    marker_pairs.append((negative_case.name, _all_match_response(False)))
    client = FakeAnthropicClient(marker_pairs)

    async def fake_structured_call(system, user, response_model, **kwargs):
        from app.engine.llm import structured_call as real_call

        return await real_call(system, user, response_model, client=client)

    monkeypatch.setattr(step4_similarity, "structured_call", fake_structured_call)

    candidates = [VerifiedCandidate(case=c, from_cache=False, is_negative_analogue=False) for c in strong_cases]
    candidates.append(VerifiedCandidate(case=negative_case, from_cache=False, is_negative_analogue=True))

    ranked = await step4_similarity.score_similarity(make_scenario(), candidates, top_n=5)

    assert ranked[0].similarity_score == pytest.approx(1.0)
    assert len(ranked[0].mismatched_dimensions) == 0
    # The negative analogue scores 0 and wouldn't naturally make the top-5 cut alongside five
    # perfect-scoring cases — confirms it's kept anyway because it's flagged negative.
    assert len(ranked) == 6
    assert any(m.case_id == "neg" and m.is_negative_analogue for m in ranked)


@pytest.mark.asyncio
async def test_score_similarity_empty_candidates_returns_empty():
    result = await step4_similarity.score_similarity(make_scenario(), [])
    assert result == []
