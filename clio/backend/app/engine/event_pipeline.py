"""Orchestrates the historical-event-analysis pipeline as an async event
stream, mirroring pipeline.py's shape but anchored on a single real event
instead of a hypothetical scenario + options:

  identify the event -> verify/structure it as the primary case -> nominate
  comparable analogues -> verify those -> score similarity against the
  primary case -> base rates from the primary case's own dimensions ->
  synthesize.

The primary case's own assessments/counterfactuals/lessons (from Step 3's
structuring) are the direct answer to "was this decision right or wrong,
and what could have changed the effects" — everything after that step is
context around it, not a replacement for it.
"""
from collections.abc import AsyncIterator
from typing import Any

from app.cache.db import CaseCache, CostLogStore
from app.engine.cost_tracking import track_cost
from app.engine.step2_nominate import NominatedCandidate
from app.engine.step3_verify import verify_and_enrich
from app.engine.step4_similarity import score_similarity_against_case
from app.engine.step5_base_rates import build_base_rate_table
from app.engine.step_event_identify import identify_event
from app.engine.step_event_nominate import nominate_comparable_analogues
from app.engine.step_event_synthesis import synthesize_event_report
from app.sources.cow import CoWDataClient
from app.sources.wikidata import WikidataClient
from app.sources.wikipedia import WikipediaClient


async def run_event_pipeline(
    event_query_id: str,
    raw_text: str,
    cache: CaseCache | None = None,
    wiki_client: WikipediaClient | None = None,
    wikidata_client: WikidataClient | None = None,
    cow_client: CoWDataClient | None = None,
    cost_log_store: CostLogStore | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yields SSE-shaped event dicts. The last substantive event is always
    either "event_report_ready" or "event_pipeline_error"; a final
    "cost_summary" event always follows it."""
    cache = cache or CaseCache()
    cost_log_store = cost_log_store or CostLogStore()
    report_id: str | None = None

    with track_cost() as tracker:
        yield {"event": "step_started", "data": {"step": "E1", "name": "identify_event"}}
        identified = await identify_event(raw_text)

        if not identified.found:
            yield {
                "event": "event_pipeline_error",
                "data": {
                    "step": "E1",
                    "error": identified.not_found_reason
                    or "Could not resolve this to a specific, verifiable historical event.",
                },
            }
            summary = tracker.summary()
            cost_log_store.log(event_query_id, report_id, summary)
            yield {"event": "cost_summary", "data": summary}
            return

        yield {
            "event": "step_completed",
            "data": {
                "step": "E1",
                "name": "identify_event",
                "name_resolved": identified.name,
                "wikipedia_title": identified.wikipedia_title,
            },
        }

        yield {"event": "step_started", "data": {"step": "E2", "name": "verify_primary_case"}}
        primary_candidate = NominatedCandidate(
            name=identified.name,
            approximate_dates=identified.approximate_dates,
            structural_rationale="primary case under analysis",
            wikipedia_title=identified.wikipedia_title,
        )
        primary_result = await verify_and_enrich(
            raw_text, [primary_candidate], cache=cache, wiki_client=wiki_client, wikidata_client=wikidata_client
        )

        if not primary_result.verified:
            reason = primary_result.dropped[0].reason if primary_result.dropped else "verification failed"
            yield {
                "event": "event_pipeline_error",
                "data": {"step": "E2", "error": f"Could not verify '{identified.name}' against sources: {reason}"},
            }
            summary = tracker.summary()
            cost_log_store.log(event_query_id, report_id, summary)
            yield {"event": "cost_summary", "data": summary}
            return

        primary_case = primary_result.verified[0].case
        yield {
            "event": "step_completed",
            "data": {
                "step": "E2",
                "name": "verify_primary_case",
                "case_id": primary_case.id,
                "case_name": primary_case.name,
                "source_urls": [str(u) for u in primary_case.source_urls],
            },
        }

        yield {"event": "step_started", "data": {"step": "E3", "name": "nominate_comparable_analogues"}}
        candidates = await nominate_comparable_analogues(primary_case)
        yield {
            "event": "step_completed",
            "data": {"step": "E3", "name": "nominate_comparable_analogues", "candidate_count": len(candidates)},
        }

        yield {"event": "step_started", "data": {"step": "E4", "name": "verify_comparable_analogues"}}
        comparable_result = await verify_and_enrich(
            primary_case.summary, candidates, cache=cache, wiki_client=wiki_client, wikidata_client=wikidata_client
        )
        for dropped in comparable_result.dropped:
            yield {
                "event": "candidate_dropped",
                "data": {"name": dropped.name, "wikipedia_title": dropped.wikipedia_title, "reason": dropped.reason},
            }
        for verified in comparable_result.verified:
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
                "step": "E4",
                "name": "verify_comparable_analogues",
                "verified_count": len(comparable_result.verified),
                "dropped_count": len(comparable_result.dropped),
            },
        }

        yield {"event": "step_started", "data": {"step": "E5", "name": "score_similarity"}}
        comparable_cases = await score_similarity_against_case(primary_case, comparable_result.verified)
        yield {
            "event": "step_completed",
            "data": {
                "step": "E5",
                "name": "score_similarity",
                "comparable_cases": [m.model_dump(mode="json") for m in comparable_cases],
            },
        }

        yield {"event": "step_started", "data": {"step": "E6", "name": "build_base_rate_table"}}
        cow_client = cow_client or CoWDataClient()
        base_rate_table = build_base_rate_table(primary_case.dimensions, cow_client=cow_client)
        yield {
            "event": "step_completed",
            "data": {"step": "E6", "name": "build_base_rate_table", "base_rate_table": base_rate_table.model_dump(mode="json")},
        }

        cases_by_id = {v.case.id: v.case for v in comparable_result.verified}
        cases_by_id[primary_case.id] = primary_case

        yield {"event": "step_started", "data": {"step": "E7", "name": "synthesize_event_report"}}
        report = await synthesize_event_report(
            event_query_id, primary_case, comparable_cases, cases_by_id, base_rate_table
        )
        report_id = report.id
        yield {"event": "step_completed", "data": {"step": "E7", "name": "synthesize_event_report", "report_id": report.id}}

        yield {"event": "event_report_ready", "data": report.model_dump(mode="json")}

        summary = tracker.summary()

    cost_log_store.log(event_query_id, report_id, summary)
    yield {"event": "cost_summary", "data": summary}
