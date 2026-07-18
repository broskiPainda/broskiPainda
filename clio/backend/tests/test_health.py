import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "running"


@respx.mock
def test_health_reports_degraded_without_cow_data(client, monkeypatch, tmp_path):
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "nope.db"))
    from app.config import get_settings

    get_settings.cache_clear()

    respx.get(url__regex=r".*wikipedia\.org.*").mock(return_value=httpx.Response(200, json={}))
    respx.get(url__regex=r".*wikidata\.org.*").mock(return_value=httpx.Response(200, json={}))

    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["cow_data"]["ok"] is False
    assert body["status"] == "degraded"

    get_settings.cache_clear()
