import pytest
from pydantic import ValidationError

from app.models import (
    Actor,
    ActorRole,
    Assessment,
    AssessmentAxis,
    CaseDimensions,
    Counterfactual,
    Decision,
    Dimension,
    Outcome,
    OutcomeHorizon,
    OutcomeValence,
    Plausibility,
    PreEvent,
    STANDING_DISCLAIMER,
    ScenarioDimensions,
    StructuredCase,
)


def _dimensions_kwargs(value: str = "test") -> dict:
    return {d.value: value for d in Dimension}


def make_case(**overrides) -> StructuredCase:
    defaults = dict(
        id="case-1",
        name="Cuban Missile Crisis",
        era="Cold War",
        dates="1962-10-16 to 1962-10-28",
        source_urls=["https://en.wikipedia.org/wiki/Cuban_Missile_Crisis"],
        summary="A 13-day confrontation between the US and USSR over missiles in Cuba.",
        actors=[
            Actor(name="United States", role=ActorRole.INITIATOR, regime_type="presidential democracy"),
            Actor(name="Soviet Union", role=ActorRole.TARGET, regime_type="one-party state"),
        ],
        pre_event=PreEvent(context="Soviet missiles discovered in Cuba."),
        decision=Decision(
            chosen_option="Naval quarantine",
            decision_maker="John F. Kennedy",
            process="ExComm deliberation",
            time_pressure="high",
        ),
        execution_notes="Quarantine enforced without direct engagement.",
        outcomes=[
            Outcome(horizon=OutcomeHorizon.IMMEDIATE, description="Missiles withdrawn", valence=OutcomeValence.POSITIVE)
        ],
        assessments=[Assessment(axis=AssessmentAxis.DECISION, score_1_10=8, reasoning="Sound given available info")],
        counterfactuals=[
            Counterfactual(
                changed_variable="US chooses airstrike instead of quarantine",
                narrative="Escalation risk rises sharply",
                plausibility=Plausibility.MEDIUM,
            )
        ],
        adversary_calculus="USSR sought to offset missile gap cheaply.",
        lessons=[],
        dimensions=CaseDimensions(**_dimensions_kwargs()),
        verified_against_sources=True,
    )
    defaults.update(overrides)
    return StructuredCase(**defaults)


def test_structured_case_round_trip():
    case = make_case()
    payload = case.model_dump_json()
    restored = StructuredCase.model_validate_json(payload)
    assert restored.name == "Cuban Missile Crisis"
    assert restored.dimensions.power_asymmetry == "test"
    assert restored.generated_by_model is True


def test_structured_case_requires_pre_event_and_dimensions():
    with pytest.raises(ValidationError):
        StructuredCase(
            id="x",
            name="x",
            era="x",
            dates="x",
            summary="x",
            decision=Decision(chosen_option="x", decision_maker="x", process="x", time_pressure="x"),
            execution_notes="x",
            adversary_calculus="x",
        )


def test_assessment_score_bounds():
    with pytest.raises(ValidationError):
        Assessment(axis=AssessmentAxis.OUTCOME, score_1_10=11, reasoning="too high")
    with pytest.raises(ValidationError):
        Assessment(axis=AssessmentAxis.OUTCOME, score_1_10=0, reasoning="too low")


def test_case_dimensions_covers_all_twelve():
    dims = CaseDimensions(**_dimensions_kwargs("v"))
    as_dict = dims.as_dict()
    assert set(as_dict.keys()) == set(Dimension)


def test_scenario_dimensions_default_empty():
    dims = ScenarioDimensions()
    assert dims.power_asymmetry == ""
    assert set(dims.as_dict().keys()) == set(Dimension)


def test_standing_disclaimer_present_by_default():
    from app.models import Report

    report = Report(id="r1", scenario_id="s1")
    assert report.disclaimer == STANDING_DISCLAIMER
    assert "does not predict outcomes" in report.disclaimer
