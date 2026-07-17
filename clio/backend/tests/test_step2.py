import pytest

from app.engine import step2_nominate
from app.models.case import Actor, ActorRole
from app.models.scenario import Scenario, ScenarioDimensions, ScenarioOption
from tests.fakes import FakeAnthropicClient


def make_scenario() -> Scenario:
    return Scenario(
        id="s1",
        raw_text="A mid-size power is considering a naval blockade of a smaller neighbor.",
        actors=[
            Actor(name="Mid-Size Power", role=ActorRole.INITIATOR, regime_type="democracy"),
            Actor(name="Smaller Neighbor", role=ActorRole.TARGET, regime_type="republic"),
        ],
        options=[ScenarioOption(id="o1", label="Full naval blockade")],
        dimensions=ScenarioDimensions(power_asymmetry="initiator stronger", stakes_framing="sovereignty dispute"),
    )


@pytest.mark.asyncio
async def test_nominate_analogues_returns_candidates_with_negative_analogue(monkeypatch):
    tool_input = {
        "candidates": [
            {
                "name": "Cuban Missile Crisis",
                "approximate_dates": "1962",
                "structural_rationale": "Naval quarantine as coercive tool short of war",
                "wikipedia_title": "Cuban Missile Crisis",
                "is_negative_analogue": False,
            },
            {
                "name": "ABC Blockade",
                "approximate_dates": "1902",
                "structural_rationale": "Naval blockade to force debt repayment",
                "wikipedia_title": "Venezuelan crisis of 1902-1903",
                "is_negative_analogue": False,
            },
            {
                "name": "Berlin Blockade",
                "approximate_dates": "1948",
                "structural_rationale": "Blockade as siege of a city, not a state",
                "wikipedia_title": "Berlin Blockade",
                "is_negative_analogue": True,
            },
        ]
    }
    client = FakeAnthropicClient([("naval blockade", tool_input)])

    async def fake_structured_call(system, user, response_model, **kwargs):
        from app.engine.llm import structured_call as real_call

        return await real_call(system, user, response_model, client=client)

    monkeypatch.setattr(step2_nominate, "structured_call", fake_structured_call)

    candidates = await step2_nominate.nominate_analogues(make_scenario())

    assert len(candidates) == 3
    assert any(c.is_negative_analogue for c in candidates)
    assert {c.wikipedia_title for c in candidates} == {
        "Cuban Missile Crisis",
        "Venezuelan crisis of 1902-1903",
        "Berlin Blockade",
    }
