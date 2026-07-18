"""Structured LLM calls: every pipeline step that needs Claude's judgment goes
through here so JSON parsing/validation/retry logic lives in exactly one place.

Works against either the real Anthropic API or an Anthropic-compatible
provider (e.g. z.ai's GLM endpoint) — see app/config.py's ANTHROPIC_BASE_URL.
We force structured output via tool-use (the model is required to call a
single synthetic tool whose input_schema is the target Pydantic model's JSON
schema), then validate the tool call's arguments with Pydantic. On a parse
or validation failure, we retry with the error fed back to the model.
"""
from typing import TypeVar

import anthropic
from anthropic import AsyncAnthropic
from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.engine.cost_tracking import record_usage

T = TypeVar("T", bound=BaseModel)

# Transient errors worth retrying with backoff, distinct from the validation-failure
# retry loop below (which re-prompts the model rather than just resending).
_TRANSIENT_ERRORS = (
    anthropic.APIConnectionError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)

_EMIT_TOOL_NAME = "emit_result"


class LLMStructuredCallError(Exception):
    """Raised when the model fails to produce a schema-valid response after all retries."""


def get_client() -> AsyncAnthropic:
    settings = get_settings()
    kwargs: dict = {"api_key": settings.anthropic_api_key}
    if settings.anthropic_base_url:
        kwargs["base_url"] = settings.anthropic_base_url
    return AsyncAnthropic(**kwargs)


@retry(
    retry=retry_if_exception_type(_TRANSIENT_ERRORS),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=1, max=20),
    reraise=True,
)
async def _create_with_backoff(client: AsyncAnthropic, **kwargs):
    return await client.messages.create(**kwargs)


async def structured_call(
    system: str,
    user: str,
    response_model: type[T],
    max_tokens: int = 4096,
    max_retries: int = 2,
    model: str | None = None,
    client: AsyncAnthropic | None = None,
) -> T:
    """Call Claude and force a response matching `response_model`, validated and retried."""
    settings = get_settings()
    owns_client = client is None
    active_client = client or get_client()
    model_name = model or settings.anthropic_model

    schema = response_model.model_json_schema()
    tool = {
        "name": _EMIT_TOOL_NAME,
        "description": f"Emit the result as {response_model.__name__}.",
        "input_schema": schema,
    }

    messages: list[dict] = [{"role": "user", "content": user}]
    last_error: Exception | None = None

    try:
        for attempt in range(max_retries + 1):
            response = await _create_with_backoff(
                active_client,
                model=model_name,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                tools=[tool],
                tool_choice={"type": "tool", "name": _EMIT_TOOL_NAME},
            )

            if getattr(response, "usage", None) is not None:
                record_usage(model_name, response.usage.input_tokens, response.usage.output_tokens)

            tool_use_block = next(
                (block for block in response.content if getattr(block, "type", None) == "tool_use"),
                None,
            )
            if tool_use_block is None:
                last_error = LLMStructuredCallError("model response contained no tool_use block")
                messages.append({"role": "assistant", "content": response.content})
                messages.append(
                    {
                        "role": "user",
                        "content": f"You must call the {_EMIT_TOOL_NAME} tool. Please retry.",
                    }
                )
                continue

            try:
                return response_model.model_validate(tool_use_block.input)
            except ValidationError as exc:
                last_error = exc
                messages.append({"role": "assistant", "content": response.content})
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use_block.id,
                                "content": (
                                    f"Validation failed: {exc}. Please call {_EMIT_TOOL_NAME} "
                                    "again with corrected input."
                                ),
                                "is_error": True,
                            }
                        ],
                    }
                )
                continue

        assert last_error is not None
        raise LLMStructuredCallError(
            f"Failed to get valid {response_model.__name__} after {max_retries + 1} attempts: {last_error}"
        ) from last_error
    finally:
        if owns_client:
            await active_client.close()
