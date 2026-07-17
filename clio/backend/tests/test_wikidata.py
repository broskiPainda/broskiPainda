import httpx
import pytest
import respx

from app.sources.wikidata import WikidataClient


@pytest.mark.asyncio
@respx.mock
async def test_get_entity_facts_found():
    respx.get("https://query.wikidata.org/sparql").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": {
                    "bindings": [
                        {
                            "item": {"value": "http://www.wikidata.org/entity/Q128736"},
                            "itemLabel": {"value": "Cuban Missile Crisis"},
                            "startDate": {"value": "1962-10-16T00:00:00Z"},
                            "endDate": {"value": "1962-10-28T00:00:00Z"},
                            "participantLabel": {"value": "United States"},
                            "partOfLabel": {"value": "Cold War"},
                        },
                        {
                            "item": {"value": "http://www.wikidata.org/entity/Q128736"},
                            "itemLabel": {"value": "Cuban Missile Crisis"},
                            "participantLabel": {"value": "Soviet Union"},
                        },
                    ]
                }
            },
        )
    )
    async with WikidataClient() as client:
        facts = await client.get_entity_facts("Cuban Missile Crisis")

    assert facts.found
    assert facts.qid == "Q128736"
    assert facts.start_date.startswith("1962-10-16")
    assert set(facts.participants) == {"United States", "Soviet Union"}
    assert facts.part_of == ["Cold War"]


@pytest.mark.asyncio
@respx.mock
async def test_get_entity_facts_not_found():
    respx.get("https://query.wikidata.org/sparql").mock(
        return_value=httpx.Response(200, json={"results": {"bindings": []}})
    )
    async with WikidataClient() as client:
        facts = await client.get_entity_facts("Totally Fictional Event Xyz")

    assert not facts.found
    assert facts.qid is None
