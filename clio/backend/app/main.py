from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.cache import router as cache_router
from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.scenarios import router as scenarios_router

app = FastAPI(
    title="CLIO",
    description="Historical Decision Intelligence — finds and verifies historical analogues for political/military scenarios.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api", tags=["health"])
app.include_router(scenarios_router, prefix="/api", tags=["scenarios"])
app.include_router(events_router, prefix="/api", tags=["events"])
app.include_router(cache_router, prefix="/api", tags=["cache"])


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "clio-backend", "status": "running"}
