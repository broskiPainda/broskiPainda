from fastapi import APIRouter, HTTPException

from app.cache.db import CaseCache
from app.models.case import StructuredCase

router = APIRouter()


@router.get("/cache/cases", response_model=list[StructuredCase])
async def list_cached_cases() -> list[StructuredCase]:
    return CaseCache().list_all()


@router.get("/cache/cases/{case_id}", response_model=StructuredCase)
async def get_cached_case(case_id: str) -> StructuredCase:
    for case in CaseCache().list_all():
        if case.id == case_id:
            return case
    raise HTTPException(status_code=404, detail="Case not found")


@router.delete("/cache/cases/{case_id}")
async def delete_cached_case(case_id: str) -> dict[str, bool]:
    deleted = CaseCache().delete(case_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"deleted": True}
