"""SQLite-backed structured-case cache + scenario history.

The case cache is keyed by normalized event name (Step 3's cache-hit check
happens before any fetch/structuring work, so a repeat scenario referencing
"the Cuban Missile Crisis" doesn't re-fetch and re-structure it).
"""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlmodel import Field, Session, SQLModel, create_engine, select

from app.cache.semantic import SemanticCaseIndex
from app.config import get_settings
from app.models.case import StructuredCase
from app.models.event import EventAnalysisReport, EventQuery
from app.models.report import Report
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


class ReportRecord(SQLModel, table=True):
    __tablename__ = "reports"

    id: str = Field(primary_key=True)
    scenario_id: str = Field(index=True)
    report_json: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CostLogRecord(SQLModel, table=True):
    __tablename__ = "cost_logs"

    id: int | None = Field(default=None, primary_key=True)
    # Holds either a scenario id or an event_query id, depending on which pipeline logged it —
    # both are opaque string ids, and cost logs don't otherwise need to know which mode ran.
    scenario_id: str = Field(index=True)
    report_id: str | None = Field(default=None, index=True)
    call_count: int
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    logged_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventQueryRecord(SQLModel, table=True):
    __tablename__ = "event_queries"

    id: str = Field(primary_key=True)
    raw_text: str
    status: str
    event_query_json: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventReportRecord(SQLModel, table=True):
    __tablename__ = "event_reports"

    id: str = Field(primary_key=True)
    event_query_id: str = Field(index=True)
    report_json: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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
    def __init__(self, sqlite_path: Path | None = None, chroma_path: Path | None = None):
        self.engine = get_engine(sqlite_path)
        # When a caller passes an explicit sqlite_path (tests, or a custom deployment) but no
        # chroma_path, default the semantic index alongside it rather than to the global
        # settings path — otherwise every test run would write into the real project's
        # data/chroma/ directory.
        resolved_chroma_path = chroma_path or (sqlite_path.parent / "chroma" if sqlite_path else None)
        self._semantic = SemanticCaseIndex(chroma_path=resolved_chroma_path)

    def get_by_name(self, name: str) -> StructuredCase | None:
        normalized = normalize_case_name(name)
        with Session(self.engine) as session:
            row = session.exec(
                select(CachedCase).where(CachedCase.normalized_name == normalized)
            ).first()
        if row is None:
            return None
        return StructuredCase.model_validate_json(row.case_json)

    def find_semantic_duplicate(self, name: str, summary: str = "") -> StructuredCase | None:
        """Catches near-duplicate names the exact normalized-name lookup misses (e.g. Claude
        nominating slightly different phrasings of the same case across scenarios). Best-effort
        — returns None if the semantic index is unavailable for any reason."""
        matches = self._semantic.find_similar(name, summary)
        for case_id, _matched_name, _distance in matches:
            with Session(self.engine) as session:
                row = session.exec(select(CachedCase).where(CachedCase.id == case_id)).first()
            if row is not None:
                return StructuredCase.model_validate_json(row.case_json)
        return None

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
        self._semantic.add(case.id, case.name, case.summary)

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
        self._semantic.delete(case_id)
        return True

    def evict_stale(self, max_age_days: int = 90) -> int:
        """Delete cases not refreshed in over max_age_days. Cases are cached transiently
        (see docs/ARCHITECTURE.md) — this keeps the cache from growing unbounded and
        ensures old cases eventually get re-fetched/re-verified against current sources."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        with Session(self.engine) as session:
            rows = session.exec(select(CachedCase).where(CachedCase.cached_at < cutoff)).all()
            ids = [row.id for row in rows]
            for row in rows:
                session.delete(row)
            session.commit()
        for case_id in ids:
            self._semantic.delete(case_id)
        return len(ids)

    def evict_lru(self, max_entries: int = 1000) -> int:
        """Cap total cache size, evicting the least-recently-cached entries first."""
        with Session(self.engine) as session:
            total = session.exec(select(CachedCase)).all()
            if len(total) <= max_entries:
                return 0
            overflow = sorted(total, key=lambda r: r.cached_at)[: len(total) - max_entries]
            ids = [row.id for row in overflow]
            for row in overflow:
                session.delete(row)
            session.commit()
        for case_id in ids:
            self._semantic.delete(case_id)
        return len(ids)


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


class ReportStore:
    def __init__(self, sqlite_path: Path | None = None):
        self.engine = get_engine(sqlite_path)

    def save(self, report: Report) -> None:
        with Session(self.engine) as session:
            existing = session.get(ReportRecord, report.id)
            payload = report.model_dump_json()
            if existing:
                existing.report_json = payload
                session.add(existing)
            else:
                session.add(
                    ReportRecord(id=report.id, scenario_id=report.scenario_id, report_json=payload)
                )
            session.commit()

    def get(self, report_id: str) -> Report | None:
        with Session(self.engine) as session:
            row = session.get(ReportRecord, report_id)
        if row is None:
            return None
        return Report.model_validate_json(row.report_json)

    def get_latest_for_scenario(self, scenario_id: str) -> Report | None:
        with Session(self.engine) as session:
            row = session.exec(
                select(ReportRecord)
                .where(ReportRecord.scenario_id == scenario_id)
                .order_by(ReportRecord.generated_at.desc())
            ).first()
        if row is None:
            return None
        return Report.model_validate_json(row.report_json)


class CostLogStore:
    def __init__(self, sqlite_path: Path | None = None):
        self.engine = get_engine(sqlite_path)

    def log(self, scenario_id: str, report_id: str | None, summary: dict) -> None:
        with Session(self.engine) as session:
            session.add(
                CostLogRecord(
                    scenario_id=scenario_id,
                    report_id=report_id,
                    call_count=summary["call_count"],
                    input_tokens=summary["input_tokens"],
                    output_tokens=summary["output_tokens"],
                    estimated_cost_usd=summary["estimated_cost_usd"],
                )
            )
            session.commit()

    def list_for_scenario(self, scenario_id: str) -> list[CostLogRecord]:
        with Session(self.engine) as session:
            return list(
                session.exec(
                    select(CostLogRecord)
                    .where(CostLogRecord.scenario_id == scenario_id)
                    .order_by(CostLogRecord.logged_at.desc())
                ).all()
            )


class EventQueryStore:
    def __init__(self, sqlite_path: Path | None = None):
        self.engine = get_engine(sqlite_path)

    def save(self, event_query: EventQuery) -> None:
        with Session(self.engine) as session:
            existing = session.get(EventQueryRecord, event_query.id)
            payload = event_query.model_dump_json()
            if existing:
                existing.raw_text = event_query.raw_text
                existing.status = event_query.status.value
                existing.event_query_json = payload
                session.add(existing)
            else:
                session.add(
                    EventQueryRecord(
                        id=event_query.id,
                        raw_text=event_query.raw_text,
                        status=event_query.status.value,
                        event_query_json=payload,
                    )
                )
            session.commit()

    def get(self, event_query_id: str) -> EventQuery | None:
        with Session(self.engine) as session:
            row = session.get(EventQueryRecord, event_query_id)
        if row is None:
            return None
        return EventQuery.model_validate_json(row.event_query_json)

    def list_all(self) -> list[EventQuery]:
        with Session(self.engine) as session:
            rows = session.exec(select(EventQueryRecord).order_by(EventQueryRecord.created_at.desc())).all()
        return [EventQuery.model_validate_json(row.event_query_json) for row in rows]


class EventReportStore:
    def __init__(self, sqlite_path: Path | None = None):
        self.engine = get_engine(sqlite_path)

    def save(self, report: EventAnalysisReport) -> None:
        with Session(self.engine) as session:
            existing = session.get(EventReportRecord, report.id)
            payload = report.model_dump_json()
            if existing:
                existing.report_json = payload
                session.add(existing)
            else:
                session.add(
                    EventReportRecord(id=report.id, event_query_id=report.event_query_id, report_json=payload)
                )
            session.commit()

    def get_latest_for_event(self, event_query_id: str) -> EventAnalysisReport | None:
        with Session(self.engine) as session:
            row = session.exec(
                select(EventReportRecord)
                .where(EventReportRecord.event_query_id == event_query_id)
                .order_by(EventReportRecord.generated_at.desc())
            ).first()
        if row is None:
            return None
        return EventAnalysisReport.model_validate_json(row.report_json)
