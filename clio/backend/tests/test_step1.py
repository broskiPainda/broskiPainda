import pytest

from app.engine import step1_structure
from app.models.case import ActorRole
from app.models.scenario import ScenarioStatus
from tests.fakes import FakeAnthropicClient

RAW_TEXT = "A mid-size power is considering a naval blockade of a smaller neighbor over a territorial dispute."


@pytest.mark.asyncio
async def test_structure_scenario_happy_path(monkeypatch):
    tool_input = {
        "refused": False,
        "actors": [
            {"name": "Mid-Size Power", "role": "initiator", "regime_type": "presidential democracy", "objective": "Coerce neighbor into concessions"},
            {"name": "Smaller Neighbor", "role": "target", "regime_type": "parliamentary republic", "objective": "Preserve territorial claim"},
        ],
        "constraints": ["Domestic public opinion", "Alliance commitments"],
        "options": ["Full naval blockade", "Partial blockade", "Diplomatic pressure only"],
        "power_asymmetry": "initiator significantly stronger militarily",
        "alliance_architecture": "neighbor has informal security guarantee from a third power",
        "domestic_constraints": "moderate — election within a year",
        "geography": "shared maritime border, narrow strait",
        "time_pressure": "moderate",
        "information_environment": "high — global media attention",
        "escalation_position": "initiator has escalation dominance at sea",
        "economic_interdependence": "significant trade dependency",
        "third_party_involvement": "regional power has stated interest",
        "regime_types": "democracy vs. republic",
        "stakes_framing": "framed as sovereignty dispute",
        "technology_era": "contemporary",
    }
    client = FakeAnthropicClient([("naval blockade", tool_input)])

    async def fake_structured_call(system, user, response_model, **kwargs):
        from app.engine.llm import structured_call as real_call

        return await real_call(system, user, response_model, client=client)

    monkeypatch.setattr(step1_structure, "structured_call", fake_structured_call)

    scenario = await step1_structure.structure_scenario(RAW_TEXT)

    assert scenario.status == ScenarioStatus.DRAFT
    assert len(scenario.actors) == 2
    assert scenario.actors[0].role == ActorRole.INITIATOR
    assert "Mid-Size Power" in scenario.objectives_by_actor
    assert len(scenario.options) == 3
    assert scenario.dimensions.power_asymmetry == "initiator significantly stronger militarily"


@pytest.mark.asyncio
async def test_structure_scenario_refuses_tactical_request(monkeypatch):
    tool_input = {
        "refused": True,
        "refusal_reason": "This requests specific weapons employment and targeting details, which is tactical military planning.",
    }
    client = FakeAnthropicClient([("artillery", tool_input)])

    async def fake_structured_call(system, user, response_model, **kwargs):
        from app.engine.llm import structured_call as real_call

        return await real_call(system, user, response_model, client=client)

    monkeypatch.setattr(step1_structure, "structured_call", fake_structured_call)

    with pytest.raises(step1_structure.ScenarioRefusedError):
        await step1_structure.structure_scenario("Plan precise artillery targeting coordinates for the assault.")
