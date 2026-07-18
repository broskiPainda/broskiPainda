import pytest

from app.engine import step_event_identify
from tests.fakes import FakeAnthropicClient


def _dispatcher(client):
    async def fake_structured_call(system, user, response_model, **kwargs):
        from app.engine.llm import structured_call as real_call

        return await real_call(system, user, response_model, client=client)

    return fake_structured_call


@pytest.mark.asyncio
async def test_identify_event_resolves_to_real_event(monkeypatch):
    payload = {
        "found": True,
        "name": "Operation Cyclone",
        "approximate_dates": "1979-1989",
        "wikipedia_title": "Operation Cyclone",
        "not_found_reason": "",
    }
    client = FakeAnthropicClient([("Mujahideen", payload)])
    monkeypatch.setattr(step_event_identify, "structured_call", _dispatcher(client))

    result = await step_event_identify.identify_event(
        "The USA backed the Mujahideen as a proxy against the USSR in Afghanistan."
    )

    assert result.found is True
    assert result.wikipedia_title == "Operation Cyclone"


@pytest.mark.asyncio
async def test_identify_event_reports_not_found(monkeypatch):
    payload = {
        "found": False,
        "not_found_reason": "Too vague to resolve to a single specific event.",
    }
    client = FakeAnthropicClient([("vague thing", payload)])
    monkeypatch.setattr(step_event_identify, "structured_call", _dispatcher(client))

    result = await step_event_identify.identify_event("some vague thing that happened once")

    assert result.found is False
    assert "vague" in result.not_found_reason.lower()
