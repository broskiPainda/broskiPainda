import sqlite3

import pytest

from app.engine.step5_base_rates import build_base_rate_table
from app.models.case import CaseDimensions
from app.models.scenario import Scenario, ScenarioDimensions
from app.sources.cow import CoWDataClient


@pytest.fixture
def cow_db(tmp_path):
    db_path = tmp_path / "clio_test.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE cow_mids (
            dispute_number INTEGER, side_a_state TEXT, side_b_state TEXT,
            start_year INTEGER, end_year INTEGER, hostility_level INTEGER, outcome INTEGER
        );
        CREATE TABLE cow_wars (
            war_number INTEGER, war_name TEXT, start_year INTEGER,
            end_year INTEGER, outcome INTEGER, duration_days INTEGER
        );
        CREATE TABLE cow_capabilities (state_name TEXT, year INTEGER, cinc REAL);
        """
    )
    conn.executemany(
        "INSERT INTO cow_mids VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (1, "USA", "", 1990, 1991, 5, 1),  # war, initiator achieved
            (2, "GBR", "", 1985, 1985, 3, 5),  # sub-war, stalemate
            (3, "FRA", "", 1970, 1972, 5, 8),  # war, other
            (4, "RUS", "", 1960, 1960, 2, 1),  # below threshold, excluded from sub-war filter
        ],
    )
    conn.commit()
    conn.close()
    return db_path


def test_build_base_rate_table_sub_war_filter(cow_db):
    scenario = Scenario(
        id="s1",
        raw_text="test",
        dimensions=ScenarioDimensions(stakes_framing="sovereignty dispute", escalation_position="limited"),
    )
    table = build_base_rate_table(scenario.dimensions, cow_client=CoWDataClient(sqlite_path=cow_db))

    assert table.source == "Correlates of War"
    assert table.n_cases == 3  # excludes the hostility_level=2 dispute
    outcomes = {row.outcome: row.count for row in table.rows}
    assert outcomes["initiator achieved objectives"] == 1
    assert outcomes["stalemate"] == 1
    assert outcomes["failed / other outcome"] == 1
    assert table.escalation_to_war_rate == pytest.approx(2 / 3, abs=0.01)
    assert "hostility_level" in table.query_definition


def test_build_base_rate_table_war_only_filter(cow_db):
    scenario = Scenario(
        id="s2",
        raw_text="test",
        dimensions=ScenarioDimensions(stakes_framing="existential war risk", escalation_position="total war"),
    )
    table = build_base_rate_table(scenario.dimensions, cow_client=CoWDataClient(sqlite_path=cow_db))

    assert table.n_cases == 2  # only hostility_level == 5
    assert table.escalation_to_war_rate == pytest.approx(1.0)


def test_build_base_rate_table_unavailable(tmp_path):
    scenario = Scenario(id="s3", raw_text="test", dimensions=ScenarioDimensions())
    table = build_base_rate_table(scenario.dimensions, cow_client=CoWDataClient(sqlite_path=tmp_path / "missing.db"))

    assert table.n_cases == 0
    assert table.rows == []
    assert "not available" in table.query_definition


def test_build_base_rate_table_accepts_case_dimensions(cow_db):
    """The event-analysis mode passes a StructuredCase's CaseDimensions directly (no Scenario
    involved) — same field names as ScenarioDimensions, so this should just work."""
    dims = CaseDimensions(**{k: "" for k in CaseDimensions.model_fields})
    dims.stakes_framing = "existential war risk"
    dims.escalation_position = "total war"

    table = build_base_rate_table(dims, cow_client=CoWDataClient(sqlite_path=cow_db))

    assert table.n_cases == 2  # only hostility_level == 5, same filter as the scenario-based test
