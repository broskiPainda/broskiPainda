"""Test doubles for the Anthropic client and source clients, keyed by a
substring marker in the user prompt so they work correctly under
asyncio.gather (call order across concurrent structured_call invocations is
not guaranteed).
"""
from types import SimpleNamespace

from app.sources.wikidata import WikidataFacts
from app.sources.wikipedia import WikipediaNotFoundError, WikipediaSummary


class FakeToolResponse:
    def __init__(self, tool_input: dict, tool_id: str = "tool_1"):
        self.content = [SimpleNamespace(type="tool_use", input=tool_input, id=tool_id, name="emit_result")]


class _FakeMessages:
    def __init__(self, by_marker: list[tuple[str, dict]]):
        self.by_marker = by_marker
        self.calls: list[str] = []

    async def create(self, *, model, max_tokens, system, messages, tools, tool_choice):
        user_content = messages[0]["content"] if messages else ""
        text = user_content if isinstance(user_content, str) else str(user_content)
        self.calls.append(text)
        for marker, tool_input in self.by_marker:
            if marker in text:
                return FakeToolResponse(tool_input)
        raise AssertionError(f"FakeAnthropicClient: no response configured for prompt containing: {text[:300]!r}")


class FakeAnthropicClient:
    """by_marker: list of (substring-to-match-in-user-prompt, tool_input dict to return)."""

    def __init__(self, by_marker: list[tuple[str, dict]]):
        self.messages = _FakeMessages(by_marker)

    async def close(self) -> None:
        pass


class FakeWikipediaClient:
    def __init__(
        self,
        summaries: dict[str, WikipediaSummary],
        leads: dict[str, str] | None = None,
        missing_titles: set[str] | None = None,
    ):
        self.summaries = summaries
        self.leads = leads or {}
        self.missing_titles = missing_titles or set()

    async def get_summary(self, title: str) -> WikipediaSummary:
        if title in self.missing_titles:
            raise WikipediaNotFoundError(title)
        if title not in self.summaries:
            raise WikipediaNotFoundError(title)
        return self.summaries[title]

    async def get_lead_sections(self, title: str, max_chars: int = 4000) -> str:
        if title in self.missing_titles:
            raise WikipediaNotFoundError(title)
        return self.leads.get(title, self.summaries.get(title, WikipediaSummary(title=title, extract="")).extract)

    async def aclose(self) -> None:
        pass


class FakeWikidataClient:
    def __init__(self, facts: dict[str, WikidataFacts]):
        self.facts = facts

    async def get_entity_facts(self, wikipedia_title: str) -> WikidataFacts:
        return self.facts.get(wikipedia_title, WikidataFacts())

    async def aclose(self) -> None:
        pass
