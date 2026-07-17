"""SQLite-backed structured-case cache + scenario history.

The case cache is keyed by normalized event name (Step 3's cache-hit check
happens before any fetch/structuring work, so a repeat scenario referencing
"the Cuban Missile Crisis" doesn't re-fetch and re-structure it).
"""
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Field, Session, SQLModel, create_engine, select

from app.config import get_settings
from app.models.case import StructuredCase
from app.models.scenario import Scenario


def normalize_case_name(name: str) -> str:
    lowered = name.strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")


class CachedCase(SQLModel, table=True):
    __tablename__ = "cached_cases"

    id: str = Field(primary_key=True)
    normalized_name: str = Field(index=True, unique=True)
    name: str
    case_json: str
    cached_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ScenarioRecord(SQLModel, table=True):
    __tablename__ = "scenarios"

    id: str = Field(primary_key=True)
    raw_text: str
    status: str
    scenario_json: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


_engine = None


def get_engine(sqlite_path: Path | None = None):
    global _engine
    if _engine is not None and sqlite_path is None:
        return _engine
    path = sqlite_path or get_settings().sqlite_path
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    if sqlite_path is None:
        _engine = engine
    return engine


def reset_engine_cache() -> None:
    """Test helper: clear the cached module-level engine so a new sqlite_path takes effect."""
    global _engine
    _engine = None


class CaseCache:
    def __init__(self, sqlite_path: Path | None = None):
        self.engine = get_engine(sqlite_path)

    def get_by_name(self, name: str) -> StructuredCase | None:
        normalized = normalize_case_name(name)
        with Session(self.engine) as session:
            row = session.exec(
                select(CachedCase).where(CachedCase.normalized_name == normalized)
            ).first()
        if row is None:
            return None
        return StructuredCase.model_validate_json(row.case_json)

    def put(self, case: StructuredCase) -> None:
        normalized = normalize_case_name(case.name)
        with Session(self.engine) as session:
            existing = session.exec(
                select(CachedCase).where(CachedCase.normalized_name == normalized)
            ).first()
            payload = case.model_dump_json()
            if existing:
                existing.case_json = payload
                existing.name = case.name
                existing.cached_at = datetime.now(timezone.utc)
                session.add(existing)
            else:
                session.add(
                    CachedCase(
                        id=case.id,
                        normalized_name=normalized,
                        name=case.name,
                        case_json=payload,
                    )
                )
            session.commit()

    def list_all(self) -> list[StructuredCase]:
        with Session(self.engine) as session:
            rows = session.exec(select(CachedCase)).all()
        return [StructuredCase.model_validate_json(row.case_json) for row in rows]

    def delete(self, case_id: str) -> bool:
        with Session(self.engine) as session:
            row = session.exec(select(CachedCase).where(CachedCase.id == case_id)).first()
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True


class ScenarioStore:
    def __init__(self, sqlite_path: Path | None = None):
        self.engine = get_engine(sqlite_path)

    def save(self, scenario: Scenario) -> None:
        with Session(self.engine) as session:
            existing = session.get(ScenarioRecord, scenario.id)
            payload = scenario.model_dump_json()
            now = datetime.now(timezone.utc)
            if existing:
                existing.raw_text = scenario.raw_text
                existing.status = scenario.status.value
                existing.scenario_json = payload
                existing.updated_at = now
                session.add(existing)
            else:
                session.add(
                    ScenarioRecord(
                        id=scenario.id,
                        raw_text=scenario.raw_text,
                        status=scenario.status.value,
                        scenario_json=payload,
                        created_at=now,
                        updated_at=now,
                    )
                )
            session.commit()

    def get(self, scenario_id: str) -> Scenario | None:
        with Session(self.engine) as session:
            row = session.get(ScenarioRecord, scenario_id)
        if row is None:
            return None
        return Scenario.model_validate_json(row.scenario_json)

    def list_all(self) -> list[Scenario]:
        with Session(self.engine) as session:
            rows = session.exec(select(ScenarioRecord).order_by(ScenarioRecord.created_at.desc())).all()
        return [Scenario.model_validate_json(row.scenario_json) for row in rows]
