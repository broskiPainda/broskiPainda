import pytest

from app.engine import step6_counterfactuals, step7_synthesis
from app.models.counterfactual import Plausibility
from app.models.report import BaseRateTable, MatchedCase
from app.models.scenario import Scenario, ScenarioDimensions, ScenarioOption
from tests.fakes import FakeAnthropicClient
from tests.test_models import make_case


def make_scenario() -> Scenario:
    return Scenario(
        id="s1",
        raw_text="A mid-size power is considering a naval blockade of a smaller neighbor.",
        options=[
            ScenarioOption(id="o1", label="Full naval blockade", description="Blockade all ports"),
            ScenarioOption(id="o2", label="Diplomatic pressure only", description="No military action"),
        ],
        dimensions=ScenarioDimensions(),
    )


def _dispatcher(client):
    async def fake_structured_call(system, user, response_model, **kwargs):
        from app.engine.llm import structured_call as real_call

        return await real_call(system, user, response_model, client=client)

    return fake_structured_call


@pytest.mark.asyncio
async def test_generate_counterfactuals_covers_top_two_options(monkeypatch):
    case = make_case()
    cf_payload = {
        "counterfactuals": [
            {
                "changed_variable": "Blockade is partial rather than full",
                "narrative": "Escalation risk drops but so does coercive leverage",
                "plausibility": "medium",
                "key_assumptions": ["Target still perceives credible threat"],
            }
        ]
    }
    client = FakeAnthropicClient(
        [("Full naval blockade", cf_payload), ("Diplomatic pressure only", cf_payload)]
    )
    monkeypatch.setattr(step6_counterfactuals, "structured_call", _dispatcher(client))

    result = await step6_counterfactuals.generate_counterfactuals(make_scenario(), [case])

    assert set(result.keys()) == {"o1", "o2"}
    assert result["o1"][0].plausibility == Plausibility.MEDIUM


@pytest.mark.asyncio
async def test_generate_counterfactuals_no_options_returns_empty():
    scenario = Scenario(id="s2", raw_text="test", dimensions=ScenarioDimensions())
    result = await step6_counterfactuals.generate_counterfactuals(scenario, [])
    assert result == {}


@pytest.mark.asyncio
async def test_synthesize_report_assembles_all_sections(monkeypatch):
    case = make_case()
    matched = [
        MatchedCase(case_id=case.id, similarity_score=0.9, matched_dimensions=[], mismatched_dimensions=[])
    ]
    base_rates = BaseRateTable(query_definition="test query", n_cases=10, rows=[], source="Correlates of War")

    synthesis_payload = {
        "option_assessments": [
            {
                "option_id": "o1",
                "option_label": "Full naval blockade",
                "decision_quality_summary": "Sound given available information",
                "supporting_reasoning": "Matches the Cuban Missile Crisis pattern closely",
            }
        ],
        "best_analogue_deep_dive": "Cuban Missile Crisis is the strongest match because...",
        "negative_analogue_warning": "",
        "red_team_paragraph": "The reference class may be too narrow because...",
        "confidence_statement": "Moderate confidence",
        "what_would_change_assessment": "Confirmation of alliance commitments",
    }
    client = FakeAnthropicClient([("mid-size power", synthesis_payload)])
    monkeypatch.setattr(step7_synthesis, "structured_call", _dispatcher(client))

    report = await step7_synthesis.synthesize_report(
        make_scenario(), matched, {case.id: case}, base_rates, {"o1": []}
    )

    assert report.scenario_id == "s1"
    assert report.best_analogue_case_id == case.id
    assert len(report.option_assessments) == 1
    assert report.option_assessments[0].decision_quality_summary == "Sound given available information"
    assert report.base_rate_table.n_cases == 10
    assert "does not predict outcomes" in report.disclaimer
    assert str(case.source_urls[0]) in [str(u) for u in report.source_urls]
