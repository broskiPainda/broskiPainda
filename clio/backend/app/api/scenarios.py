import json

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.cache.db import CaseCache, ScenarioStore
from app.engine.pipeline import run_pipeline
from app.engine.step1_structure import ScenarioRefusedError, structure_scenario
from app.models.scenario import (
    Scenario,
    ScenarioCreateRequest,
    ScenarioStatus,
    ScenarioUpdateRequest,
)

router = APIRouter()


@router.post("/scenarios", response_model=Scenario)
async def create_scenario(request: ScenarioCreateRequest) -> Scenario:
    try:
        scenario = await structure_scenario(request.raw_text)
    except ScenarioRefusedError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"CLIO operates at the strategic-political level only. {exc.reason}",
        ) from exc
    ScenarioStore().save(scenario)
    return scenario


@router.put("/scenarios/{scenario_id}", response_model=Scenario)
async def update_scenario(scenario_id: str, request: ScenarioUpdateRequest) -> Scenario:
    store = ScenarioStore()
    existing = store.get(scenario_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Scenario not found")

    existing.actors = request.actors
    existing.objectives_by_actor = request.objectives_by_actor
    existing.constraints = request.constraints
    existing.options = request.options
    existing.dimensions = request.dimensions
    existing.status = ScenarioStatus.CONFIRMED

    store.save(existing)
    return existing


@router.post("/scenarios/{scenario_id}/analyze")
async def analyze_scenario(scenario_id: str):
    store = ScenarioStore()
    scenario = store.get(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    if scenario.status not in (ScenarioStatus.CONFIRMED, ScenarioStatus.ANALYZING, ScenarioStatus.COMPLETE):
        raise HTTPException(
            status_code=409,
            detail="Scenario must be confirmed (PUT /api/scenarios/{id}) before analysis.",
        )

    scenario.status = ScenarioStatus.ANALYZING
    store.save(scenario)

    async def event_generator():
        cache = CaseCache()
        async for event in run_pipeline(scenario, cache=cache):
            yield {"event": event["event"], "data": json.dumps(event["data"])}

    return EventSourceResponse(event_generator())


@router.get("/scenarios/{scenario_id}", response_model=Scenario)
async def get_scenario(scenario_id: str) -> Scenario:
    scenario = ScenarioStore().get(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return scenario


@router.get("/scenarios/{scenario_id}/report")
async def get_report(scenario_id: str):
    scenario = ScenarioStore().get(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    raise HTTPException(
        status_code=501,
        detail="Report synthesis (pipeline steps 4-7) is not yet implemented — coming in Phase 3.",
    )


@router.get("/history")
async def list_history() -> list[Scenario]:
    return ScenarioStore().list_all()
