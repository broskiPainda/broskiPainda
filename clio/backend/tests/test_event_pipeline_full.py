"""Full event-analysis pipeline test: E1-E7 end to end (mocked LLM + sources
+ CoW SQLite) produces a complete EventAnalysisReport, using the example
from the feature request: "the USA backed the Mujahideen as a proxy against
the USSR in Afghanistan."
"""
import sqlite3

import pytest

from app.cache.db import CaseCache, CostLogStore
from app.engine import (
    step3_verify,
    step4_similarity,
    step_event_identify,
    step_event_nominate,
    step_event_synthesis,
)
from app.engine.event_pipeline import run_event_pipeline
from app.models.dimensions import Dimension
from app.sources.cow import CoWDataClient
from app.sources.wikidata import WikidataFacts
from app.sources.wikipedia import WikipediaSummary
from tests.fakes import FakeAnthropicClient, FakeWikidataClient, FakeWikipediaClient
from tests.test_step3 import _structuring_output

RAW_TEXT = "The USA backed the Mujahideen as a proxy against the USSR in Afghanistan."


@pytest.fixture
def cow_db(tmp_path):
    db_path = tmp_path / "cow_test.db"
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
        [(1, "USA", "", 1979, 1989, 4, 1), (2, "SUN", "", 1979, 1989, 5, 8)],
    )
    conn.commit()
    conn.close()
    return db_path


def _dispatcher(client):
    async def fake_structured_call(system, user, response_model, **kwargs):
        from app.engine.llm import structured_call as real_call

        return await real_call(system, user, response_model, client=client)

    return fake_structured_call


@pytest.mark.asyncio
async def test_full_event_pipeline_produces_complete_report(monkeypatch, tmp_path, cow_db):
    identify_payload = {
        "found": True,
        "name": "Operation Cyclone",
        "approximate_dates": "1979-1989",
        "wikipedia_title": "Operation Cyclone",
        "not_found_reason": "",
    }
    identify_client = FakeAnthropicClient([("Mujahideen", identify_payload)])
    monkeypatch.setattr(step_event_identify, "structured_call", _dispatcher(identify_client))

    comparable_payload = {
        "candidates": [
            {
                "name": "Soviet–Afghan War",
                "approximate_dates": "1979-1989",
                "structural_rationale": "The direct conflict Operation Cyclone was waged within",
                "wikipedia_title": "Soviet–Afghan War",
                "is_negative_analogue": False,
            },
            {
                "name": "Bay of Pigs Invasion",
                "approximate_dates": "1961",
                "structural_rationale": "Superficially similar covert-action framing, but an overt "
                "direct invasion rather than sustained proxy support — negative analogue",
                "wikipedia_title": "Bay of Pigs Invasion",
                "is_negative_analogue": True,
            },
        ]
    }
    comparable_client = FakeAnthropicClient([("Operation Cyclone", comparable_payload)])
    monkeypatch.setattr(step_event_nominate, "structured_call", _dispatcher(comparable_client))

    wiki_client = FakeWikipediaClient(
        summaries={
            "Operation Cyclone": WikipediaSummary(
                title="Operation Cyclone", extract="A CIA program from 1979 arming Afghan Mujahideen against Soviet forces.",
                content_urls_desktop="https://en.wikipedia.org/wiki/Operation_Cyclone",
            ),
            "Soviet–Afghan War": WikipediaSummary(
                title="Soviet–Afghan War", extract="A 1979-1989 conflict between Soviet forces and Afghan insurgents.",
                content_urls_desktop="https://en.wikipedia.org/wiki/Soviet%E2%80%93Afghan_War",
            ),
            "Bay of Pigs Invasion": WikipediaSummary(
                title="Bay of Pigs Invasion", extract="A failed 1961 CIA-backed invasion of Cuba.",
                content_urls_desktop="https://en.wikipedia.org/wiki/Bay_of_Pigs_Invasion",
            ),
        }
    )
    wikidata_client = FakeWikidataClient(
        facts={
            "Operation Cyclone": WikidataFacts(qid="Q1", label="Operation Cyclone", start_date="1979-07-03"),
            "Soviet–Afghan War": WikidataFacts(qid="Q2", label="Soviet–Afghan War", start_date="1979-12-24"),
            "Bay of Pigs Invasion": WikidataFacts(qid="Q3", label="Bay of Pigs Invasion", start_date="1961-04-17"),
        }
    )

    step3_client = FakeAnthropicClient(
        [
            ("Operation Cyclone", _structuring_output("Operation Cyclone")),
            ("Soviet–Afghan War", _structuring_output("Soviet–Afghan War")),
            ("Bay of Pigs Invasion", _structuring_output("Bay of Pigs Invasion")),
        ]
    )
    monkeypatch.setattr(step3_verify, "structured_call", _dispatcher(step3_client))

    all_match = {"dimension_matches": [{"dimension": d.value, "matches": True, "note": "n/a"} for d in Dimension]}
    step4_client = FakeAnthropicClient(
        [("Soviet–Afghan War", all_match), ("Bay of Pigs Invasion", all_match)]
    )
    monkeypatch.setattr(step4_similarity, "structured_call", _dispatcher(step4_client))

    synthesis_payload = {
        "assessment_narrative": "Sound decision given available information; the covert-support "
        "model achieved its immediate strategic aim of raising Soviet costs.",
        "red_team_paragraph": "The comparable-case set may be too narrow.",
        "confidence_statement": "Moderate confidence.",
        "what_would_change_assessment": "Better information on long-run second-order effects.",
    }
    synthesis_client = FakeAnthropicClient([("Operation Cyclone", synthesis_payload)])
    monkeypatch.setattr(step_event_synthesis, "structured_call", _dispatcher(synthesis_client))

    cache = CaseCache(sqlite_path=tmp_path / "cache.db")
    cow_client = CoWDataClient(sqlite_path=cow_db)
    cost_log_store = CostLogStore(sqlite_path=tmp_path / "cache.db")

    events = []
    async for event in run_event_pipeline(
        "event-1",
        RAW_TEXT,
        cache=cache,
        wiki_client=wiki_client,
        wikidata_client=wikidata_client,
        cow_client=cow_client,
        cost_log_store=cost_log_store,
    ):
        events.append(event)

    report_events = [e for e in events if e["event"] == "event_report_ready"]
    assert len(report_events) == 1
    report_data = report_events[0]["data"]

    assert report_data["primary_case_id"]
    assert len(report_data["comparable_cases"]) == 2
    assert any(c["is_negative_analogue"] for c in report_data["comparable_cases"])
    assert report_data["base_rate_table"]["n_cases"] == 2
    assert "Sound decision" in report_data["assessment_narrative"]
    assert "does not predict outcomes" in report_data["disclaimer"]

    step_events = {e["data"]["step"] for e in events if e["event"] == "step_completed"}
    assert step_events == {"E1", "E2", "E3", "E4", "E5", "E6", "E7"}

    cost_events = [e for e in events if e["event"] == "cost_summary"]
    assert len(cost_events) == 1
    assert "estimated_cost_usd" in cost_events[0]["data"]
