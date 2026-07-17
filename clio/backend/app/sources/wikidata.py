"""Wikidata SPARQL client — fetches structured entity facts (dates, participants, part-of).

Used alongside the Wikipedia client in Step 3 as a second, independent
grounding source: a candidate is dropped if either fetch fails or the
content doesn't corroborate the nomination.
"""
from pydantic import BaseModel

from app.config import get_settings
from app.sources.http import RateLimitedClient

_ENTITY_BY_TITLE_QUERY = """
SELECT ?item ?itemLabel ?startDate ?endDate ?participantLabel ?partOfLabel WHERE {{
  ?article schema:about ?item ;
           schema:isPartOf <https://en.wikipedia.org/> ;
           schema:name "{title}"@en .
  OPTIONAL {{ ?item wdt:P580 ?startDate. }}
  OPTIONAL {{ ?item wdt:P582 ?endDate. }}
  OPTIONAL {{ ?item wdt:P710 ?participant. }}
  OPTIONAL {{ ?item wdt:P361 ?partOf. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT 50
"""


class WikidataFacts(BaseModel):
    qid: str | None = None
    label: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    participants: list[str] = []
    part_of: list[str] = []

    @property
    def found(self) -> bool:
        return self.qid is not None


class WikidataClient:
    def __init__(self, client: RateLimitedClient | None = None):
        settings = get_settings()
        self._owns_client = client is None
        self._client = client or RateLimitedClient(base_url=settings.wikidata_sparql_endpoint.rsplit("/sparql", 1)[0])
        self._sparql_path = "/sparql"

    async def get_entity_facts(self, wikipedia_title: str) -> WikidataFacts:
        query = _ENTITY_BY_TITLE_QUERY.format(title=wikipedia_title.replace('"', '\\"'))
        response = await self._client.get(
            self._sparql_path,
            params={"query": query, "format": "json"},
            headers={"Accept": "application/sparql-results+json"},
        )
        response.raise_for_status()
        bindings = response.json().get("results", {}).get("bindings", [])
        if not bindings:
            return WikidataFacts()

        first = bindings[0]
        qid = first["item"]["value"].rsplit("/", 1)[-1] if "item" in first else None
        label = first.get("itemLabel", {}).get("value")
        start_date = first.get("startDate", {}).get("value")
        end_date = first.get("endDate", {}).get("value")
        participants = sorted({b["participantLabel"]["value"] for b in bindings if "participantLabel" in b})
        part_of = sorted({b["partOfLabel"]["value"] for b in bindings if "partOfLabel" in b})

        return WikidataFacts(
            qid=qid,
            label=label,
            start_date=start_date,
            end_date=end_date,
            participants=participants,
            part_of=part_of,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "WikidataClient":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()
