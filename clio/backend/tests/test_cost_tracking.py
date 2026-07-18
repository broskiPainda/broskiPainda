import asyncio

from app.engine.cost_tracking import record_usage, track_cost


def test_record_usage_outside_tracker_is_a_noop():
    record_usage("glm-4.6", 100, 50)  # should not raise with no active tracker


def test_track_cost_accumulates_within_block():
    with track_cost() as tracker:
        record_usage("glm-4.6", 1000, 500)
        record_usage("glm-4.6", 2000, 1000)

    assert tracker.call_count == 2
    assert tracker.input_tokens == 3000
    assert tracker.output_tokens == 1500
    assert tracker.calls_by_model == {"glm-4.6": 2}
    assert tracker.estimated_cost_usd() > 0


def test_track_cost_isolated_across_nested_blocks():
    with track_cost() as outer:
        record_usage("glm-4.6", 100, 100)
        with track_cost() as inner:
            record_usage("glm-4.6", 200, 200)
        record_usage("glm-4.6", 50, 50)

    assert inner.call_count == 1
    assert inner.input_tokens == 200
    assert outer.call_count == 2
    assert outer.input_tokens == 150


async def _record_in_task(model, tokens_in, tokens_out):
    record_usage(model, tokens_in, tokens_out)


async def _run_concurrent_tracking():
    with track_cost() as tracker:
        await asyncio.gather(*[_record_in_task("glm-4.6", 10, 10) for _ in range(5)])
    return tracker


def test_track_cost_survives_asyncio_gather():
    tracker = asyncio.run(_run_concurrent_tracking())
    assert tracker.call_count == 5
    assert tracker.input_tokens == 50


def test_estimated_cost_zero_with_no_calls():
    with track_cost() as tracker:
        pass
    assert tracker.estimated_cost_usd() == 0.0
    assert tracker.summary()["call_count"] == 0
