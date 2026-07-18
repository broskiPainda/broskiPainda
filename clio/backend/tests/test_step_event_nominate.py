import pytest

from app.engine import step_event_nominate
from tests.fakes import FakeAnthropicClient
from tests.test_models import make_case


def _dispatcher(client):
    async def fake_structured_call(system, user, response_model, **kwargs):
        from app.engine.llm import structured_call as real_call

        return await real_call(system, user, response_model, client=client)

    return fake_structured_call


@pytest.mark.asyncio
async def test_nominate_comparable_analogues(monkeypatch):
    payload = {
        "candidates": [
            {
                "name": "Soviet-Afghan War",
                "approximate_dates": "1979-1989",
                "structural_rationale": "Superpower proxy conflict with covert third-party backing",
                "wikipedia_title": "Soviet–Afghan War",
                "is_negative_analogue": False,
            },
            {
                "name": "Bay of Pigs Invasion",
                "approximate_dates": "1961",
                "structural_rationale": "Superficially similar covert-action framing, but overt "
                "invasion rather than sustained proxy support — structurally different",
                "wikipedia_title": "Bay of Pigs Invasion",
                "is_negative_analogue": True,
            },
        ]
    }
    client = FakeAnthropicClient([("Cuban Missile Crisis", payload)])
    monkeypatch.setattr(step_event_nominate, "structured_call", _dispatcher(client))

    candidates = await step_event_nominate.nominate_comparable_analogues(make_case())

    assert len(candidates) == 2
    assert any(c.is_negative_analogue for c in candidates)
