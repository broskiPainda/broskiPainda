"""Correlates of War (CoW) data client — queries the local SQLite tables built
by scripts/setup_data.py from the downloaded CSVs.

Used in pipeline Step 5 to build base-rate reference classes. Every number
surfaced to the user must come from these tables, never from the LLM.
"""
import sqlite3
from pathlib import Path

from pydantic import BaseModel

from app.config import get_settings


class MidRecord(BaseModel):
    """One dyadic Militarized Interstate Dispute participant-row (MIDs 5.0 dyadic)."""

    dispute_number: int
    side_a_state: str
    side_b_state: str
    start_year: int
    end_year: int | None = None
    hostility_level: int | None = None  # CoW hiplevel: 1=no militarized action .. 5=war
    outcome: int | None = None  # CoW outcome code


class WarRecord(BaseModel):
    """One Inter-State War (CoW Inter-State War data)."""

    war_number: int
    war_name: str
    side_a: list[str] = []
    side_b: list[str] = []
    start_year: int
    end_year: int | None = None
    outcome: int | None = None
    duration_days: int | None = None


class CapabilityRecord(BaseModel):
    """One country-year row from the CoW National Material Capabilities dataset."""

    state_name: str
    year: int
    cinc: float | None = None


class CoWDataUnavailableError(Exception):
    pass


class CoWDataClient:
    """Read-only query interface over the CoW SQLite tables.

    Tables (created by scripts/setup_data.py): `cow_mids`, `cow_wars`, `cow_capabilities`.
    """

    def __init__(self, sqlite_path: Path | None = None):
        settings = get_settings()
        self.sqlite_path = sqlite_path or settings.sqlite_path

    def is_available(self) -> bool:
        if not self.sqlite_path.exists():
            return False
        try:
            with self._connect() as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
            return {"cow_mids", "cow_wars", "cow_capabilities"}.issubset(tables)
        except sqlite3.Error:
            return False

    def _connect(self) -> sqlite3.Connection:
        if not self.sqlite_path.exists():
            raise CoWDataUnavailableError(
                f"CoW SQLite database not found at {self.sqlite_path}. "
                "Run `python backend/scripts/setup_data.py` first."
            )
        return sqlite3.connect(self.sqlite_path)

    def query_mids(
        self,
        min_hostility: int | None = None,
        max_hostility: int | None = None,
        limit: int = 5000,
    ) -> list[MidRecord]:
        clauses = []
        params: list = []
        if min_hostility is not None:
            clauses.append("hostility_level >= ?")
            params.append(min_hostility)
        if max_hostility is not None:
            clauses.append("hostility_level <= ?")
            params.append(max_hostility)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            "SELECT dispute_number, side_a_state, side_b_state, start_year, end_year, "
            f"hostility_level, outcome FROM cow_mids {where} LIMIT ?"
        )
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            MidRecord(
                dispute_number=r[0],
                side_a_state=r[1],
                side_b_state=r[2],
                start_year=r[3],
                end_year=r[4],
                hostility_level=r[5],
                outcome=r[6],
            )
            for r in rows
        ]

    def query_wars(self, limit: int = 5000) -> list[WarRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT war_number, war_name, start_year, end_year, outcome, duration_days "
                "FROM cow_wars LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            WarRecord(
                war_number=r[0],
                war_name=r[1],
                start_year=r[2],
                end_year=r[3],
                outcome=r[4],
                duration_days=r[5],
            )
            for r in rows
        ]

    def get_capability(self, state_name: str, year: int) -> CapabilityRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT state_name, year, cinc FROM cow_capabilities WHERE state_name = ? AND year = ?",
                (state_name, year),
            ).fetchone()
        if row is None:
            return None
        return CapabilityRecord(state_name=row[0], year=row[1], cinc=row[2])

    def cinc_ratio(self, state_a: str, state_b: str, year: int) -> float | None:
        """Return CINC(state_a) / CINC(state_b) for the given year, or None if unavailable."""
        cap_a = self.get_capability(state_a, year)
        cap_b = self.get_capability(state_b, year)
        if not cap_a or not cap_b or not cap_a.cinc or not cap_b.cinc:
            return None
        return cap_a.cinc / cap_b.cinc
