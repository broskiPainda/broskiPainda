import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.cache.db import CaseCache, EventQueryStore, EventReportStore
from app.engine.event_pipeline import run_event_pipeline
from app.engine.step_event_identify import identify_event
from app.models.event import (
    EventAnalysisReport,
    EventQuery,
    EventQueryCreateRequest,
    EventQueryStatus,
)

router = APIRouter()


@router.post("/events", response_model=EventQuery)
async def create_event_query(request: EventQueryCreateRequest) -> EventQuery:
    identified = await identify_event(request.raw_text)

    event_query = EventQuery(
        id=str(uuid.uuid4()),
        raw_text=request.raw_text,
        status=EventQueryStatus.IDENTIFIED if identified.found else EventQueryStatus.NOT_FOUND,
        resolved_name=identified.name,
        resolved_dates=identified.approximate_dates,
        wikipedia_title=identified.wikipedia_title,
        not_found_reason=identified.not_found_reason,
        created_at=datetime.now(timezone.utc),
    )
    EventQueryStore().save(event_query)
    return event_query


@router.post("/events/{event_query_id}/analyze")
async def analyze_event(event_query_id: str):
    store = EventQueryStore()
    event_query = store.get(event_query_id)
    if event_query is None:
        raise HTTPException(status_code=404, detail="Event query not found")
    if event_query.status not in (
        EventQueryStatus.IDENTIFIED,
        EventQueryStatus.ANALYZING,
        EventQueryStatus.COMPLETE,
    ):
        raise HTTPException(
            status_code=409,
            detail="This text could not be resolved to a specific historical event "
            f"({event_query.not_found_reason or 'unknown reason'}); nothing to analyze.",
        )

    event_query.status = EventQueryStatus.ANALYZING
    store.save(event_query)

    async def event_generator():
        cache = CaseCache()
        report_store = EventReportStore()
        async for event in run_event_pipeline(event_query_id, event_query.raw_text, cache=cache):
            if event["event"] == "event_report_ready":
                report = EventAnalysisReport.model_validate(event["data"])
                report_store.save(report)
                event_query.status = EventQueryStatus.COMPLETE
                store.save(event_query)
            elif event["event"] == "event_pipeline_error":
                event_query.status = EventQueryStatus.IDENTIFIED
                store.save(event_query)
            yield {"event": event["event"], "data": json.dumps(event["data"])}

    return EventSourceResponse(event_generator())


@router.get("/events/{event_query_id}", response_model=EventQuery)
async def get_event_query(event_query_id: str) -> EventQuery:
    event_query = EventQueryStore().get(event_query_id)
    if event_query is None:
        raise HTTPException(status_code=404, detail="Event query not found")
    return event_query


@router.get("/events/{event_query_id}/report", response_model=EventAnalysisReport)
async def get_event_report(event_query_id: str) -> EventAnalysisReport:
    event_query = EventQueryStore().get(event_query_id)
    if event_query is None:
        raise HTTPException(status_code=404, detail="Event query not found")
    report = EventReportStore().get_latest_for_event(event_query_id)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="No report yet for this event — run POST /api/events/{id}/analyze first.",
        )
    return report


@router.get("/event-history")
async def list_event_history() -> list[EventQuery]:
    return EventQueryStore().list_all()
