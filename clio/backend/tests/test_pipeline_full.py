"""Full pipeline test: Steps 2-7 end to end (mocked LLM + sources + CoW SQLite)
produces a complete Report with a non-empty base-rate table and per-option
counterfactuals.
"""
import sqlite3

import pytest

from app.cache.db import CaseCache, CostLogStore
from app.engine import step2_nominate, step3_verify, step4_similarity, step6_counterfactuals, step7_synthesis
from app.engine.pipeline import run_pipeline
from app.models.case import Actor, ActorRole
from app.models.dimensions import Dimension
from app.models.scenario import Scenario, ScenarioDimensions, ScenarioOption
from app.sources.cow import CoWDataClient
from app.sources.wikidata import WikidataFacts
from app.sources.wikipedia import WikipediaSummary
from tests.fakes import FakeAnthropicClient, FakeWikidataClient, FakeWikipediaClient
from tests.test_step3 import _structuring_output


def make_scenario() -> Scenario:
    return Scenario(
        id="s1",
        raw_text="A mid-size power is considering a naval blockade of a smaller neighbor.",
        actors=[
            Actor(name="Mid-Size Power", role=ActorRole.INITIATOR, regime_type="democracy"),
            Actor(name="Smaller Neighbor", role=ActorRole.TARGET, regime_type="republic"),
        ],
        options=[
            ScenarioOption(id="o1", label="Full naval blockade", description="Blockade all ports"),
            ScenarioOption(id="o2", label="Diplomatic pressure only", description="No military action"),
        ],
        dimensions=ScenarioDimensions(stakes_framing="sovereignty dispute", escalation_position="limited"),
    )


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
        [(1, "USA", "", 1990, 1991, 3, 1), (2, "GBR", "", 1985, 1985, 4, 5)],
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
async def test_full_pipeline_produces_complete_report(monkeypatch, tmp_path, cow_db):
    step2_payload = {
        "candidates": [
            {
                "name": "Cuban Missile Crisis",
                "approximate_dates": "1962",
                "structural_rationale": "naval quarantine",
                "wikipedia_title": "Cuban Missile Crisis",
                "is_negative_analogue": False,
            },
            {
                "name": "Cod Wars",
                "approximate_dates": "1958",
                "structural_rationale": "resource-driven naval confrontation",
                "wikipedia_title": "Cod Wars",
                "is_negative_analogue": False,
            },
        ]
    }
    step2_client = FakeAnthropicClient([("naval blockade", step2_payload)])
    monkeypatch.setattr(step2_nominate, "structured_call", _dispatcher(step2_client))

    wiki_client = FakeWikipediaClient(
        summaries={
            "Cuban Missile Crisis": WikipediaSummary(title="Cuban Missile Crisis", extract="A 1962 Cold War confrontation.", content_urls_desktop="https://en.wikipedia.org/wiki/Cuban_Missile_Crisis"),
            "Cod Wars": WikipediaSummary(title="Cod Wars", extract="A series of confrontations starting in 1958.", content_urls_desktop="https://en.wikipedia.org/wiki/Cod_Wars"),
        }
    )
    wikidata_client = FakeWikidataClient(
        facts={
            "Cuban Missile Crisis": WikidataFacts(qid="Q128736", label="Cuban Missile Crisis", start_date="1962-10-16"),
            "Cod Wars": WikidataFacts(qid="Q844423", label="Cod Wars", start_date="1958-09-01"),
        }
    )

    step3_client = FakeAnthropicClient(
        [
            ("Cuban Missile Crisis", _structuring_output("Cuban Missile Crisis")),
            ("Cod Wars", _structuring_output("Cod Wars")),
        ]
    )
    monkeypatch.setattr(step3_verify, "structured_call", _dispatcher(step3_client))

    all_match = {"dimension_matches": [{"dimension": d.value, "matches": True, "note": "n/a"} for d in Dimension]}
    step4_client = FakeAnthropicClient(
        [("Cuban Missile Crisis", all_match), ("Cod Wars", all_match)]
    )
    monkeypatch.setattr(step4_similarity, "structured_call", _dispatcher(step4_client))

    cf_payload = {
        "counterfactuals": [
            {
                "changed_variable": "Blockade is partial rather than full",
                "narrative": "Coercive leverage drops but so does escalation risk",
                "plausibility": "medium",
                "key_assumptions": ["Adversary still perceives credible threat"],
            }
        ]
    }
    step6_client = FakeAnthropicClient(
        [("Full naval blockade", cf_payload), ("Diplomatic pressure only", cf_payload)]
    )
    monkeypatch.setattr(step6_counterfactuals, "structured_call", _dispatcher(step6_client))

    synthesis_payload = {
        "option_assessments": [
            {
                "option_id": "o1",
                "option_label": "Full naval blockade",
                "decision_quality_summary": "Sound given available information",
                "supporting_reasoning": "Consistent with the Cuban Missile Crisis pattern",
            },
            {
                "option_id": "o2",
                "option_label": "Diplomatic pressure only",
                "decision_quality_summary": "Lower risk but weaker leverage",
                "supporting_reasoning": "Consistent with slower-burn disputes like the Cod Wars",
            },
        ],
        "best_analogue_deep_dive": "Cuban Missile Crisis is the strongest structural match.",
        "negative_analogue_warning": "",
        "red_team_paragraph": "The reference class may be too narrow.",
        "confidence_statement": "Moderate confidence.",
        "what_would_change_assessment": "Confirmation of the neighbor's alliance guarantees.",
    }
    step7_client = FakeAnthropicClient([("mid-size power", synthesis_payload)])
    monkeypatch.setattr(step7_synthesis, "structured_call", _dispatcher(step7_client))

    cache = CaseCache(sqlite_path=tmp_path / "cache.db")
    cow_client = CoWDataClient(sqlite_path=cow_db)
    cost_log_store = CostLogStore(sqlite_path=tmp_path / "cache.db")

    events = []
    async for event in run_pipeline(
        make_scenario(),
        cache=cache,
        wiki_client=wiki_client,
        wikidata_client=wikidata_client,
        cow_client=cow_client,
        cost_log_store=cost_log_store,
    ):
        events.append(event)

    report_events = [e for e in events if e["event"] == "report_ready"]
    assert len(report_events) == 1
    report_data = report_events[0]["data"]

    assert len(report_data["matched_cases"]) == 2
    assert len(report_data["option_assessments"]) == 2
    assert report_data["option_assessments"][0]["counterfactuals"]
    assert report_data["base_rate_table"]["n_cases"] == 2
    assert "does not predict outcomes" in report_data["disclaimer"]
    assert report_data["best_analogue_case_id"] is not None

    step_events = {e["data"]["step"] for e in events if e["event"] == "step_completed"}
    assert step_events == {2, 3, 4, 5, 6, 7}
