"""Shared async HTTP helper: descriptive User-Agent + polite rate-limit backoff.

Per Wikipedia/Wikidata API etiquette, every request carries a descriptive
User-Agent including contact info, and 429s back off with exponential delay
rather than hammering the endpoint.
"""
import asyncio

import httpx

from app.config import get_settings


class RateLimitedClient:
    def __init__(self, base_url: str = "", timeout: float = 15.0, max_retries: int = 3):
        settings = get_settings()
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
            headers={"User-Agent": settings.user_agent},
        )
        self.max_retries = max_retries

    async def get(self, url: str, **kwargs) -> httpx.Response:
        delay = 1.0
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.get(url, **kwargs)
            except httpx.TransportError as exc:
                last_exc = exc
            else:
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else delay
                    await asyncio.sleep(wait)
                    delay *= 2
                    continue
                return response
            if attempt < self.max_retries:
                await asyncio.sleep(delay)
                delay *= 2
        assert last_exc is not None
        raise last_exc

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "RateLimitedClient":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()
