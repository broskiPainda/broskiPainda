import pytest
from fastapi.testclient import TestClient

from app.cache.db import reset_engine_cache
from app.config import get_settings
from app.models.case import Actor, ActorRole
from app.models.scenario import Scenario, ScenarioDimensions, ScenarioStatus


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    reset_engine_cache()

    from app.main import app

    yield TestClient(app)

    get_settings.cache_clear()
    reset_engine_cache()


def _canned_scenario(scenario_id: str = "sc-1", status: ScenarioStatus = ScenarioStatus.DRAFT) -> Scenario:
    return Scenario(
        id=scenario_id,
        raw_text="A mid-size power is considering a naval blockade of a smaller neighbor.",
        status=status,
        actors=[
            Actor(name="Mid-Size Power", role=ActorRole.INITIATOR, regime_type="democracy"),
            Actor(name="Smaller Neighbor", role=ActorRole.TARGET, regime_type="republic"),
        ],
        dimensions=ScenarioDimensions(power_asymmetry="initiator stronger"),
    )


def test_create_scenario(client, monkeypatch):
    async def fake_structure_scenario(raw_text):
        return _canned_scenario()

    monkeypatch.setattr("app.api.scenarios.structure_scenario", fake_structure_scenario)

    response = client.post("/api/scenarios", json={"raw_text": "naval blockade scenario"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "draft"
    assert len(body["actors"]) == 2


def test_create_scenario_refused(client, monkeypatch):
    from app.engine.step1_structure import ScenarioRefusedError

    async def fake_structure_scenario(raw_text):
        raise ScenarioRefusedError("tactical targeting request")

    monkeypatch.setattr("app.api.scenarios.structure_scenario", fake_structure_scenario)

    response = client.post("/api/scenarios", json={"raw_text": "plan artillery targeting"})
    assert response.status_code == 422
    assert "strategic-political" in response.json()["detail"]


def test_update_scenario_confirms_it(client, monkeypatch):
    async def fake_structure_scenario(raw_text):
        return _canned_scenario()

    monkeypatch.setattr("app.api.scenarios.structure_scenario", fake_structure_scenario)
    created = client.post("/api/scenarios", json={"raw_text": "naval blockade scenario"}).json()

    update_payload = {
        "actors": created["actors"],
        "objectives_by_actor": {"Mid-Size Power": "coerce concessions"},
        "constraints": ["public opinion"],
        "options": [{"id": "o1", "label": "full blockade"}],
        "dimensions": created["dimensions"],
    }
    response = client.put(f"/api/scenarios/{created['id']}", json=update_payload)
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    assert response.json()["constraints"] == ["public opinion"]


def test_update_scenario_not_found(client):
    response = client.put(
        "/api/scenarios/nonexistent",
        json={"actors": [], "objectives_by_actor": {}, "constraints": [], "options": [], "dimensions": {}},
    )
    assert response.status_code == 404


def test_analyze_requires_confirmation(client, monkeypatch):
    async def fake_structure_scenario(raw_text):
        return _canned_scenario()

    monkeypatch.setattr("app.api.scenarios.structure_scenario", fake_structure_scenario)
    created = client.post("/api/scenarios", json={"raw_text": "naval blockade scenario"}).json()

    response = client.post(f"/api/scenarios/{created['id']}/analyze")
    assert response.status_code == 409


def test_analyze_streams_pipeline_events(client, monkeypatch):
    async def fake_structure_scenario(raw_text):
        return _canned_scenario(status=ScenarioStatus.DRAFT)

    monkeypatch.setattr("app.api.scenarios.structure_scenario", fake_structure_scenario)
    created = client.post("/api/scenarios", json={"raw_text": "naval blockade scenario"}).json()

    update_payload = {
        "actors": created["actors"],
        "objectives_by_actor": {},
        "constraints": [],
        "options": [],
        "dimensions": created["dimensions"],
    }
    client.put(f"/api/scenarios/{created['id']}", json=update_payload)

    async def fake_pipeline(scenario, cache=None):
        yield {"event": "step_started", "data": {"step": 2, "name": "nominate_analogues"}}
        yield {"event": "candidate_verified", "data": {"name": "Cuban Missile Crisis", "case_id": "c1"}}

    monkeypatch.setattr("app.api.scenarios.run_pipeline", fake_pipeline)

    with client.stream("POST", f"/api/scenarios/{created['id']}/analyze") as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "step_started" in body
    assert "candidate_verified" in body
    assert "Cuban Missile Crisis" in body


def test_analyze_saves_report_and_completes_scenario(client, monkeypatch):
    from app.models.report import STANDING_DISCLAIMER, Report

    async def fake_structure_scenario(raw_text):
        return _canned_scenario(status=ScenarioStatus.DRAFT)

    monkeypatch.setattr("app.api.scenarios.structure_scenario", fake_structure_scenario)
    created = client.post("/api/scenarios", json={"raw_text": "naval blockade scenario"}).json()

    update_payload = {
        "actors": created["actors"],
        "objectives_by_actor": {},
        "constraints": [],
        "options": [],
        "dimensions": created["dimensions"],
    }
    client.put(f"/api/scenarios/{created['id']}", json=update_payload)

    report = Report(id="r1", scenario_id=created["id"], confidence_statement="moderate")

    async def fake_pipeline(scenario, cache=None):
        yield {"event": "step_started", "data": {"step": 2, "name": "nominate_analogues"}}
        yield {"event": "report_ready", "data": report.model_dump(mode="json")}

    monkeypatch.setattr("app.api.scenarios.run_pipeline", fake_pipeline)

    with client.stream("POST", f"/api/scenarios/{created['id']}/analyze") as response:
        assert response.status_code == 200
        "".join(response.iter_text())

    scenario_after = client.get(f"/api/scenarios/{created['id']}").json()
    assert scenario_after["status"] == "complete"

    fetched_report = client.get(f"/api/scenarios/{created['id']}/report")
    assert fetched_report.status_code == 200
    body = fetched_report.json()
    assert body["confidence_statement"] == "moderate"
    assert body["disclaimer"] == STANDING_DISCLAIMER


def test_get_report_not_found_before_analysis(client, monkeypatch):
    async def fake_structure_scenario(raw_text):
        return _canned_scenario()

    monkeypatch.setattr("app.api.scenarios.structure_scenario", fake_structure_scenario)
    created = client.post("/api/scenarios", json={"raw_text": "naval blockade scenario"}).json()

    response = client.get(f"/api/scenarios/{created['id']}/report")
    assert response.status_code == 404


def test_history_lists_created_scenarios(client, monkeypatch):
    async def fake_structure_scenario(raw_text):
        return _canned_scenario()

    monkeypatch.setattr("app.api.scenarios.structure_scenario", fake_structure_scenario)
    client.post("/api/scenarios", json={"raw_text": "naval blockade scenario"})

    response = client.get("/api/history")
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_cache_endpoints(client):
    from app.cache.db import CaseCache
    from tests.test_models import make_case

    assert client.get("/api/cache/cases").json() == []

    case = make_case()
    CaseCache().put(case)

    listed = client.get("/api/cache/cases").json()
    assert len(listed) == 1

    fetched = client.get(f"/api/cache/cases/{case.id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Cuban Missile Crisis"

    assert client.get("/api/cache/cases/nonexistent").status_code == 404

    deleted = client.delete(f"/api/cache/cases/{case.id}")
    assert deleted.status_code == 200
    assert client.delete(f"/api/cache/cases/{case.id}").status_code == 404
