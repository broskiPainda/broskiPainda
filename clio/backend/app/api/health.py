"""GET /api/health — checks Anthropic API key presence, Wikipedia/Wikidata
reachability, and CoW data presence, so the frontend/ops can tell at a glance
whether the app is fully configured.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings
from app.sources.cow import CoWDataClient
from app.sources.http import RateLimitedClient

router = APIRouter()


class ComponentStatus(BaseModel):
    ok: bool
    detail: str = ""


class HealthResponse(BaseModel):
    status: str  # "ok" | "degraded"
    anthropic: ComponentStatus
    wikipedia: ComponentStatus
    wikidata: ComponentStatus
    cow_data: ComponentStatus


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()

    anthropic_status = ComponentStatus(
        ok=bool(settings.anthropic_api_key),
        detail="ANTHROPIC_API_KEY not set" if not settings.anthropic_api_key else "key present",
    )

    wikipedia_status = await _check_http(settings.wikipedia_api_base + "/page/summary/Earth")
    wikidata_status = await _check_http(
        settings.wikidata_sparql_endpoint, params={"query": "SELECT * WHERE { ?s ?p ?o } LIMIT 1", "format": "json"}
    )

    cow_client = CoWDataClient()
    cow_available = cow_client.is_available()
    cow_status = ComponentStatus(
        ok=cow_available,
        detail="CoW tables present" if cow_available else "run backend/scripts/setup_data.py",
    )

    components = [anthropic_status, wikipedia_status, wikidata_status, cow_status]
    overall = "ok" if all(c.ok for c in components) else "degraded"

    return HealthResponse(
        status=overall,
        anthropic=anthropic_status,
        wikipedia=wikipedia_status,
        wikidata=wikidata_status,
        cow_data=cow_status,
    )


async def _check_http(url: str, params: dict | None = None) -> ComponentStatus:
    try:
        async with RateLimitedClient(max_retries=0) as client:
            response = await client.get(url, params=params, timeout=5.0)
        ok = response.status_code < 500
        return ComponentStatus(ok=ok, detail=f"HTTP {response.status_code}")
    except Exception as exc:  # noqa: BLE001 - health check must never raise
        return ComponentStatus(ok=False, detail=str(exc))
