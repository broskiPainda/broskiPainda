"""UCDP (Uppsala Conflict Data Program) API client.

Complements CoW in Step 5's base-rate reference class — UCDP's Georeferenced
Event Dataset / conflict data covers more recent and lower-intensity
conflicts than CoW's interstate-war focus.
"""
from pydantic import BaseModel

from app.config import get_settings
from app.sources.http import RateLimitedClient


class UcdpConflict(BaseModel):
    conflict_id: int
    location: str
    side_a: str
    side_b: str
    year: int
    intensity_level: int | None = None  # 1 = minor (25-999 deaths/yr), 2 = war (1000+)
    type_of_conflict: int | None = None


class UcdpClient:
    def __init__(self, client: RateLimitedClient | None = None):
        settings = get_settings()
        self._owns_client = client is None
        self._client = client or RateLimitedClient(base_url=settings.ucdp_api_base)

    async def query_conflicts(
        self,
        year: int | None = None,
        page_size: int = 100,
    ) -> list[UcdpConflict]:
        params: dict[str, str | int] = {"pagesize": page_size}
        if year is not None:
            params["Year"] = year
        response = await self._client.get("/ucdpprioconflict/24.1", params=params)
        response.raise_for_status()
        data = response.json()
        results = data.get("Result", [])
        conflicts = []
        for item in results:
            try:
                conflicts.append(
                    UcdpConflict(
                        conflict_id=int(item["conflict_id"]),
                        location=item.get("location", ""),
                        side_a=item.get("side_a", ""),
                        side_b=item.get("side_b", ""),
                        year=int(item.get("year", year or 0)),
                        intensity_level=_safe_int(item.get("intensity_level")),
                        type_of_conflict=_safe_int(item.get("type_of_conflict")),
                    )
                )
            except (KeyError, ValueError, TypeError):
                continue
        return conflicts

    async def is_reachable(self) -> bool:
        try:
            response = await self._client.get("/ucdpprioconflict/24.1", params={"pagesize": 1})
            return response.status_code == 200
        except Exception:
            return False

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "UcdpClient":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()


def _safe_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
