"""Orchestrates the full 7-step pipeline as an async event stream consumable
by the SSE endpoint: nominate -> verify/enrich -> similarity -> base rates ->
counterfactuals -> synthesis. The final event carries the completed Report.

Every LLM call made anywhere in the run is tallied by a CostTracker (see
cost_tracking.py); the total is emitted as a "cost_summary" event and
persisted per-report via CostLogStore, so token/cost usage is visible per
analysis run without instrumenting each step individually.
"""
from collections.abc import AsyncIterator
from typing import Any

from app.cache.db import CaseCache, CostLogStore
from app.engine.cost_tracking import track_cost
from app.engine.step2_nominate import nominate_analogues
from app.engine.step3_verify import verify_and_enrich
from app.engine.step4_similarity import score_similarity
from app.engine.step5_base_rates import build_base_rate_table
from app.engine.step6_counterfactuals import generate_counterfactuals
from app.engine.step7_synthesis import synthesize_report
from app.models.scenario import Scenario
from app.sources.cow import CoWDataClient
from app.sources.wikidata import WikidataClient
from app.sources.wikipedia import WikipediaClient


async def run_pipeline(
    scenario: Scenario,
    cache: CaseCache | None = None,
    wiki_client: WikipediaClient | None = None,
    wikidata_client: WikidataClient | None = None,
    cow_client: CoWDataClient | None = None,
    cost_log_store: CostLogStore | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yields SSE-shaped event dicts: {"event": ..., "data": {...}}. The last
    substantive event is always either "report_ready" (data: the Report,
    dumped) or "pipeline_error" (data: {"step": int, "error": str}); a final
    "cost_summary" event always follows it."""
    cache = cache or CaseCache()
    cost_log_store = cost_log_store or CostLogStore()
    report_id: str | None = None

    with track_cost() as tracker:
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
                "data": {
                    "name": dropped.name,
                    "wikipedia_title": dropped.wikipedia_title,
                    "reason": dropped.reason,
                },
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

        if not result.verified:
            yield {
                "event": "pipeline_error",
                "data": {"step": 3, "error": "No candidate analogues survived verification; cannot continue."},
            }
        else:
            yield {"event": "step_started", "data": {"step": 4, "name": "score_similarity"}}
            matched_cases = await score_similarity(scenario, result.verified)
            yield {
                "event": "step_completed",
                "data": {
                    "step": 4,
                    "name": "score_similarity",
                    "matched_cases": [m.model_dump(mode="json") for m in matched_cases],
                },
            }

            yield {"event": "step_started", "data": {"step": 5, "name": "build_base_rate_table"}}
            cow_client = cow_client or CoWDataClient()
            base_rate_table = build_base_rate_table(scenario.dimensions, cow_client=cow_client)
            yield {
                "event": "step_completed",
                "data": {
                    "step": 5,
                    "name": "build_base_rate_table",
                    "base_rate_table": base_rate_table.model_dump(mode="json"),
                },
            }

            cases_by_id = {v.case.id: v.case for v in result.verified}
            top_cases = [cases_by_id[m.case_id] for m in matched_cases if m.case_id in cases_by_id]

            yield {"event": "step_started", "data": {"step": 6, "name": "generate_counterfactuals"}}
            counterfactuals_by_option = await generate_counterfactuals(scenario, top_cases)
            yield {
                "event": "step_completed",
                "data": {"step": 6, "name": "generate_counterfactuals", "option_count": len(counterfactuals_by_option)},
            }

            yield {"event": "step_started", "data": {"step": 7, "name": "synthesize_report"}}
            report = await synthesize_report(
                scenario, matched_cases, cases_by_id, base_rate_table, counterfactuals_by_option
            )
            report_id = report.id
            yield {"event": "step_completed", "data": {"step": 7, "name": "synthesize_report", "report_id": report.id}}

            yield {"event": "report_ready", "data": report.model_dump(mode="json")}

        summary = tracker.summary()

    cost_log_store.log(scenario.id, report_id, summary)
    yield {"event": "cost_summary", "data": summary}
