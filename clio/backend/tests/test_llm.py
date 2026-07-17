import pytest
from pydantic import BaseModel

from app.engine.llm import LLMStructuredCallError, structured_call
from tests.fakes import FakeAnthropicClient


class Simple(BaseModel):
    value: str
    count: int


@pytest.mark.asyncio
async def test_structured_call_returns_validated_model():
    client = FakeAnthropicClient([("hello", {"value": "ok", "count": 3})])
    result = await structured_call("system", "hello world", Simple, client=client)
    assert result == Simple(value="ok", count=3)


@pytest.mark.asyncio
async def test_structured_call_retries_on_validation_error_then_succeeds():
    # First response is missing required field "count" -> triggers a validation error retry.
    responses = [("hello", {"value": "bad"})]
    client = FakeAnthropicClient(responses)

    # Patch the fake to return a bad response first, then a good one on retry by
    # using a stateful marker list mutated after the first call.
    call_log = []

    async def create(*, model, max_tokens, system, messages, tools, tool_choice):
        call_log.append(1)
        from tests.fakes import FakeToolResponse

        if len(call_log) == 1:
            return FakeToolResponse({"value": "bad"})
        return FakeToolResponse({"value": "ok", "count": 5})

    client.messages.create = create
    result = await structured_call("system", "hello world", Simple, client=client, max_retries=2)
    assert result.count == 5
    assert len(call_log) == 2


@pytest.mark.asyncio
async def test_structured_call_raises_after_exhausting_retries():
    call_log = []

    async def create(*, model, max_tokens, system, messages, tools, tool_choice):
        call_log.append(1)
        from tests.fakes import FakeToolResponse

        return FakeToolResponse({"value": "bad"})  # always missing "count"

    client = FakeAnthropicClient([])
    client.messages.create = create

    with pytest.raises(LLMStructuredCallError):
        await structured_call("system", "hello world", Simple, client=client, max_retries=1)
    assert len(call_log) == 2
