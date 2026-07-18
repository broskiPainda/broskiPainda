import httpx
import pytest
import respx

from app.sources.ucdp import UcdpClient


@pytest.mark.asyncio
@respx.mock
async def test_query_conflicts_parses_results():
    respx.get("https://ucdpapi.pcr.uu.se/api/ucdpprioconflict/24.1").mock(
        return_value=httpx.Response(
            200,
            json={
                "Result": [
                    {
                        "conflict_id": "333",
                        "location": "Testland",
                        "side_a": "Government of Testland",
                        "side_b": "Rebel Group X",
                        "year": "2015",
                        "intensity_level": "2",
                        "type_of_conflict": "3",
                    },
                    {"conflict_id": "not-an-int", "location": "Bad Row"},
                ]
            },
        )
    )
    async with UcdpClient() as client:
        conflicts = await client.query_conflicts(year=2015)

    assert len(conflicts) == 1
    assert conflicts[0].conflict_id == 333
    assert conflicts[0].intensity_level == 2


@pytest.mark.asyncio
@respx.mock
async def test_is_reachable_true_on_200():
    respx.get("https://ucdpapi.pcr.uu.se/api/ucdpprioconflict/24.1").mock(return_value=httpx.Response(200, json={"Result": []}))
    async with UcdpClient() as client:
        assert await client.is_reachable() is True


@pytest.mark.asyncio
@respx.mock
async def test_is_reachable_false_on_error():
    respx.get("https://ucdpapi.pcr.uu.se/api/ucdpprioconflict/24.1").mock(return_value=httpx.Response(500))
    async with UcdpClient() as client:
        assert await client.is_reachable() is False
