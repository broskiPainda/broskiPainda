import httpx
import pytest
import respx

from app.sources.wikipedia import WikipediaClient, WikipediaNotFoundError


@pytest.mark.asyncio
@respx.mock
async def test_get_summary_success():
    respx.get("https://en.wikipedia.org/api/rest_v1/page/summary/Cuban_Missile_Crisis").mock(
        return_value=httpx.Response(
            200,
            json={
                "title": "Cuban Missile Crisis",
                "extract": "A 13-day confrontation in October 1962.",
                "description": "1962 Cold War confrontation",
                "pageid": 12345,
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Cuban_Missile_Crisis"}},
            },
        )
    )
    async with WikipediaClient() as client:
        summary = await client.get_summary("Cuban Missile Crisis")

    assert summary.title == "Cuban Missile Crisis"
    assert "1962" in summary.extract
    assert summary.page_id == 12345


@pytest.mark.asyncio
@respx.mock
async def test_get_summary_not_found_raises():
    respx.get("https://en.wikipedia.org/api/rest_v1/page/summary/Nonexistent_Article_Xyz").mock(
        return_value=httpx.Response(404, json={"type": "not_found"})
    )
    async with WikipediaClient() as client:
        with pytest.raises(WikipediaNotFoundError):
            await client.get_summary("Nonexistent Article Xyz")


@pytest.mark.asyncio
@respx.mock
async def test_get_summary_retries_on_429_then_succeeds():
    route = respx.get("https://en.wikipedia.org/api/rest_v1/page/summary/Test_Event")
    route.side_effect = [
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(200, json={"title": "Test Event", "extract": "ok"}),
    ]
    async with WikipediaClient() as client:
        summary = await client.get_summary("Test Event")

    assert summary.extract == "ok"
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_get_lead_sections_strips_html():
    respx.get("https://en.wikipedia.org/api/rest_v1/page/html/Test_Event").mock(
        return_value=httpx.Response(200, text="<html><body><p>Hello <b>world</b></p></body></html>")
    )
    async with WikipediaClient() as client:
        text = await client.get_lead_sections("Test Event")

    assert "Hello" in text and "world" in text
    assert "<" not in text
