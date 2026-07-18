import pytest

from app.cache.db import CaseCache, CostLogStore
from app.engine import step_event_identify
from app.engine.event_pipeline import run_event_pipeline
from tests.fakes import FakeAnthropicClient


def _dispatcher(client):
    async def fake_structured_call(system, user, response_model, **kwargs):
        from app.engine.llm import structured_call as real_call

        return await real_call(system, user, response_model, client=client)

    return fake_structured_call


@pytest.mark.asyncio
async def test_event_pipeline_stops_cleanly_when_not_identifiable(monkeypatch, tmp_path):
    payload = {
        "found": False,
        "not_found_reason": "Too vague to resolve to one specific event.",
    }
    client = FakeAnthropicClient([("something vague", payload)])
    monkeypatch.setattr(step_event_identify, "structured_call", _dispatcher(client))

    cache = CaseCache(sqlite_path=tmp_path / "cache.db")
    cost_log_store = CostLogStore(sqlite_path=tmp_path / "cache.db")

    events = []
    async for event in run_event_pipeline(
        "event-1", "something vague happened once", cache=cache, cost_log_store=cost_log_store
    ):
        events.append(event)

    error_events = [e for e in events if e["event"] == "event_pipeline_error"]
    assert len(error_events) == 1
    assert error_events[0]["data"]["step"] == "E1"
    assert "vague" in error_events[0]["data"]["error"].lower()

    # Pipeline must stop cleanly — no later steps should have run.
    assert not any(e["event"] == "event_report_ready" for e in events)
    step_events = {e["data"]["step"] for e in events if e["event"] == "step_completed"}
    assert step_events == set()

    cost_events = [e for e in events if e["event"] == "cost_summary"]
    assert len(cost_events) == 1
