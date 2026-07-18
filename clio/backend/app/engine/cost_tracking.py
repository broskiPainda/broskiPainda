"""Per-report LLM cost/token logging.

Every structured_call() records its token usage against whatever CostTracker
is active in the current async context (via contextvars, so concurrent
asyncio.gather'd calls within the same pipeline run all attribute correctly).
pipeline.py opens one tracker per analysis run and logs/persists the total.

Prices are approximate list prices in USD per million tokens, intended for
order-of-magnitude cost visibility, not billing-grade accounting.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

# USD per 1M tokens (input, output). Unknown models fall back to _DEFAULT_PRICE.
_PRICE_PER_MILLION_TOKENS = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (15.0, 75.0),
    "claude-haiku-4-5": (0.8, 4.0),
    "glm-4.6": (0.6, 2.2),
}
_DEFAULT_PRICE = (3.0, 15.0)


@dataclass
class CostTracker:
    call_count: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    calls_by_model: dict[str, int] = field(default_factory=dict)

    def record(self, model: str, input_tokens: int, output_tokens: int) -> None:
        self.call_count += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.calls_by_model[model] = self.calls_by_model.get(model, 0) + 1

    def estimated_cost_usd(self) -> float:
        # Approximate: uses the price of whichever model was called most, since a single
        # tracker may span a couple of model names in mixed-provider setups.
        if not self.calls_by_model:
            return 0.0
        dominant_model = max(self.calls_by_model, key=self.calls_by_model.get)
        in_price, out_price = _PRICE_PER_MILLION_TOKENS.get(dominant_model, _DEFAULT_PRICE)
        return round((self.input_tokens / 1_000_000) * in_price + (self.output_tokens / 1_000_000) * out_price, 4)

    def summary(self) -> dict:
        return {
            "call_count": self.call_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost_usd": self.estimated_cost_usd(),
            "calls_by_model": dict(self.calls_by_model),
        }


_current_tracker: ContextVar[CostTracker | None] = ContextVar("_current_tracker", default=None)


@contextmanager
def track_cost():
    """Context manager: `with track_cost() as tracker:` — any structured_call()
    made anywhere within the block (including in gathered coroutines spawned
    inside it) records its usage against `tracker`."""
    tracker = CostTracker()
    token = _current_tracker.set(tracker)
    try:
        yield tracker
    finally:
        _current_tracker.reset(token)


def record_usage(model: str, input_tokens: int, output_tokens: int) -> None:
    tracker = _current_tracker.get()
    if tracker is not None:
        tracker.record(model, input_tokens, output_tokens)
