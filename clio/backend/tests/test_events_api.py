import pytest
from fastapi.testclient import TestClient

from app.cache.db import reset_engine_cache
from app.config import get_settings
from app.models.event import EventAnalysisReport, EventQuery, EventQueryStatus


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
    get_settings.cache_clear()
    reset_engine_cache()

    from app.main import app

    yield TestClient(app)

    get_settings.cache_clear()
    reset_engine_cache()


def test_create_event_query_identified(client, monkeypatch):
    async def fake_identify_event(raw_text):
        from app.engine.step_event_identify import IdentifiedEvent

        return IdentifiedEvent(found=True, name="Operation Cyclone", approximate_dates="1979-1989", wikipedia_title="Operation Cyclone")

    monkeypatch.setattr("app.api.events.identify_event", fake_identify_event)

    response = client.post("/api/events", json={"raw_text": "US backing the Mujahideen against the USSR"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "identified"
    assert body["wikipedia_title"] == "Operation Cyclone"


def test_create_event_query_not_found(client, monkeypatch):
    async def fake_identify_event(raw_text):
        from app.engine.step_event_identify import IdentifiedEvent

        return IdentifiedEvent(found=False, not_found_reason="Too vague")

    monkeypatch.setattr("app.api.events.identify_event", fake_identify_event)

    response = client.post("/api/events", json={"raw_text": "something vague"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_found"
    assert body["not_found_reason"] == "Too vague"


def test_analyze_rejects_not_found_event(client, monkeypatch):
    async def fake_identify_event(raw_text):
        from app.engine.step_event_identify import IdentifiedEvent

        return IdentifiedEvent(found=False, not_found_reason="Too vague")

    monkeypatch.setattr("app.api.events.identify_event", fake_identify_event)
    created = client.post("/api/events", json={"raw_text": "something vague"}).json()

    response = client.post(f"/api/events/{created['id']}/analyze")
    assert response.status_code == 409


def test_analyze_saves_report_and_completes_event(client, monkeypatch):
    async def fake_identify_event(raw_text):
        from app.engine.step_event_identify import IdentifiedEvent

        return IdentifiedEvent(found=True, name="Operation Cyclone", approximate_dates="1979-1989", wikipedia_title="Operation Cyclone")

    monkeypatch.setattr("app.api.events.identify_event", fake_identify_event)
    created = client.post("/api/events", json={"raw_text": "US backing the Mujahideen"}).json()

    report = EventAnalysisReport(
        id="er1", event_query_id=created["id"], primary_case_id="case1", confidence_statement="moderate"
    )

    async def fake_pipeline(event_query_id, raw_text, cache=None):
        yield {"event": "step_started", "data": {"step": "E1", "name": "identify_event"}}
        yield {"event": "event_report_ready", "data": report.model_dump(mode="json")}

    monkeypatch.setattr("app.api.events.run_event_pipeline", fake_pipeline)

    with client.stream("POST", f"/api/events/{created['id']}/analyze") as response:
        assert response.status_code == 200
        "".join(response.iter_text())

    event_after = client.get(f"/api/events/{created['id']}").json()
    assert event_after["status"] == "complete"

    fetched_report = client.get(f"/api/events/{created['id']}/report")
    assert fetched_report.status_code == 200
    assert fetched_report.json()["confidence_statement"] == "moderate"


def test_get_event_report_not_found_before_analysis(client, monkeypatch):
    async def fake_identify_event(raw_text):
        from app.engine.step_event_identify import IdentifiedEvent

        return IdentifiedEvent(found=True, name="Operation Cyclone", approximate_dates="1979-1989", wikipedia_title="Operation Cyclone")

    monkeypatch.setattr("app.api.events.identify_event", fake_identify_event)
    created = client.post("/api/events", json={"raw_text": "US backing the Mujahideen"}).json()

    response = client.get(f"/api/events/{created['id']}/report")
    assert response.status_code == 404


def test_event_history_lists_created_queries(client, monkeypatch):
    async def fake_identify_event(raw_text):
        from app.engine.step_event_identify import IdentifiedEvent

        return IdentifiedEvent(found=True, name="Operation Cyclone", approximate_dates="1979-1989", wikipedia_title="Operation Cyclone")

    monkeypatch.setattr("app.api.events.identify_event", fake_identify_event)
    client.post("/api/events", json={"raw_text": "US backing the Mujahideen"})

    response = client.get("/api/event-history")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_event_query_not_found(client):
    assert client.get("/api/events/nonexistent").status_code == 404
