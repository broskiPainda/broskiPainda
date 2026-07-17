"""Orchestrates pipeline steps 2-3 (analogue nomination + verify/enrich) as an
async event stream consumable by the SSE endpoint. Steps 4-7 (similarity
scoring, base rates, counterfactuals, synthesis) land in Phase 3 and will
extend this generator.
"""
from collections.abc import AsyncIterator
from typing import Any

from app.cache.db import CaseCache
from app.engine.step2_nominate import nominate_analogues
from app.engine.step3_verify import verify_and_enrich
from app.models.scenario import Scenario
from app.sources.wikidata import WikidataClient
from app.sources.wikipedia import WikipediaClient


async def run_pipeline(
    scenario: Scenario,
    cache: CaseCache | None = None,
    wiki_client: WikipediaClient | None = None,
    wikidata_client: WikidataClient | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yields SSE-shaped event dicts: {"event": ..., "data": {...}}."""
    cache = cache or CaseCache()

    yield {"event": "step_started", "data": {"step": 2, "name": "nominate_analogues"}}
    candidates = await nominate_analogues(scenario)
    yield {
        "event": "step_completed",
        "data": {
            "step": 2,
            "name": "nominate_analogues",
            "candidate_count": len(candidates),
            "candidates": [c.model_dump() for c in candidates],
        },
    }

    yield {"event": "step_started", "data": {"step": 3, "name": "verify_and_enrich"}}
    result = await verify_and_enrich(
        scenario.raw_text,
        candidates,
        cache=cache,
        wiki_client=wiki_client,
        wikidata_client=wikidata_client,
    )

    for dropped in result.dropped:
        yield {
            "event": "candidate_dropped",
            "data": {"name": dropped.name, "wikipedia_title": dropped.wikipedia_title, "reason": dropped.reason},
        }
    for verified in result.verified:
        yield {
            "event": "candidate_verified",
            "data": {
                "name": verified.case.name,
                "case_id": verified.case.id,
                "from_cache": verified.from_cache,
                "is_negative_analogue": verified.is_negative_analogue,
                "source_urls": [str(u) for u in verified.case.source_urls],
            },
        }

    yield {
        "event": "step_completed",
        "data": {
            "step": 3,
            "name": "verify_and_enrich",
            "verified_count": len(result.verified),
            "dropped_count": len(result.dropped),
        },
    }

    yield {
        "event": "pipeline_paused",
        "data": {
            "reason": "Steps 4-7 (similarity scoring, base rates, counterfactuals, synthesis) "
            "are not yet implemented (Phase 3).",
            "verified_case_ids": [v.case.id for v in result.verified],
        },
    }
