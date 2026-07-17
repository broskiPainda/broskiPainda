"""Wikipedia REST API client — fetches article summaries and lead sections.

Used in pipeline Step 3 (verify + enrich) to ground candidate analogues in
real source text before Claude structures them into a StructuredCase.
"""
from pydantic import BaseModel

from app.config import get_settings
from app.sources.http import RateLimitedClient


class WikipediaSummary(BaseModel):
    title: str
    extract: str
    description: str | None = None
    content_urls_desktop: str | None = None
    page_id: int | None = None


class WikipediaNotFoundError(Exception):
    pass


class WikipediaClient:
    def __init__(self, client: RateLimitedClient | None = None):
        settings = get_settings()
        self._owns_client = client is None
        self._client = client or RateLimitedClient(base_url=settings.wikipedia_api_base)

    async def get_summary(self, title: str) -> WikipediaSummary:
        """Fetch the REST summary endpoint for an exact article title."""
        safe_title = title.replace(" ", "_")
        response = await self._client.get(f"/page/summary/{safe_title}")
        if response.status_code == 404:
            raise WikipediaNotFoundError(f"No Wikipedia article titled {title!r}")
        response.raise_for_status()
        data = response.json()
        return WikipediaSummary(
            title=data.get("title", title),
            extract=data.get("extract", ""),
            description=data.get("description"),
            content_urls_desktop=(data.get("content_urls", {}).get("desktop", {}) or {}).get("page"),
            page_id=data.get("pageid"),
        )

    async def get_lead_sections(self, title: str, max_chars: int = 4000) -> str:
        """Fetch plain-text lead content (first sections) for grounding case structuring."""
        safe_title = title.replace(" ", "_")
        response = await self._client.get(
            f"/page/html/{safe_title}",
            headers={"Accept": "text/html"},
        )
        if response.status_code == 404:
            raise WikipediaNotFoundError(f"No Wikipedia article titled {title!r}")
        response.raise_for_status()
        text = _strip_html(response.text)
        return text[:max_chars]

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "WikipediaClient":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()


def _strip_html(html: str) -> str:
    """Minimal tag stripper — good enough for grounding text, not for display."""
    import re

    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
