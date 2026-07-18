"""Step 1 — Scenario structuring.

Claude extracts actors + roles + objectives, constraints, options under
consideration, and values for all 12 dimensions from the user's free text.
The result is returned to the frontend as an editable confirmation card —
the pipeline does not proceed past this step until the user confirms
(garbage in, garbage out).
"""
import uuid

from pydantic import BaseModel, Field

from app.engine.llm import structured_call
from app.models.case import Actor, ActorRole
from app.models.scenario import Scenario, ScenarioDimensions, ScenarioOption, ScenarioStatus

SYSTEM_PROMPT = """You are a political-military analyst extracting the structure of a decision \
scenario for historical-analogy analysis. Given a free-text scenario, extract:

- The actors involved, each with a role (initiator, target, or third_party) and a short \
  description of their regime type (e.g. "presidential democracy", "one-party state", \
  "military junta", "parliamentary monarchy").
- Each actor's objectives, in one sentence per actor.
- The constraints each side is operating under (domestic, alliance, resource, legal, etc.).
- The concrete options apparently under consideration by the deciding actor.
- A value for each of these 12 structural dimensions, describing THIS scenario in one short \
  phrase each: power_asymmetry, alliance_architecture, domestic_constraints, geography, \
  time_pressure, information_environment, escalation_position, economic_interdependence, \
  third_party_involvement, regime_types, stakes_framing, technology_era.

This is strategic-political analysis only. If the input describes operational or tactical \
military planning (specific targeting, weapons employment, troop movements, attack timing), \
refuse by setting refused=true and explaining why in refusal_reason; leave other fields empty."""


class ExtractedActor(BaseModel):
    name: str
    role: ActorRole
    regime_type: str
    objective: str = ""


class StepOneExtraction(BaseModel):
    refused: bool = False
    refusal_reason: str = ""
    actors: list[ExtractedActor] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)
    power_asymmetry: str = ""
    alliance_architecture: str = ""
    domestic_constraints: str = ""
    geography: str = ""
    time_pressure: str = ""
    information_environment: str = ""
    escalation_position: str = ""
    economic_interdependence: str = ""
    third_party_involvement: str = ""
    regime_types: str = ""
    stakes_framing: str = ""
    technology_era: str = ""


class ScenarioRefusedError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


async def structure_scenario(raw_text: str) -> Scenario:
    extraction = await structured_call(
        system=SYSTEM_PROMPT,
        user=f"Scenario:\n\n{raw_text}",
        response_model=StepOneExtraction,
    )

    if extraction.refused:
        raise ScenarioRefusedError(
            extraction.refusal_reason or "This request describes operational/tactical military "
            "planning, which CLIO does not support. CLIO operates at the strategic-political "
            "level only."
        )

    actors = [
        Actor(name=a.name, role=a.role, regime_type=a.regime_type) for a in extraction.actors
    ]
    objectives_by_actor = {a.name: a.objective for a in extraction.actors if a.objective}
    options = [
        ScenarioOption(id=str(uuid.uuid4()), label=label) for label in extraction.options
    ]
    dimensions = ScenarioDimensions(
        power_asymmetry=extraction.power_asymmetry,
        alliance_architecture=extraction.alliance_architecture,
        domestic_constraints=extraction.domestic_constraints,
        geography=extraction.geography,
        time_pressure=extraction.time_pressure,
        information_environment=extraction.information_environment,
        escalation_position=extraction.escalation_position,
        economic_interdependence=extraction.economic_interdependence,
        third_party_involvement=extraction.third_party_involvement,
        regime_types=extraction.regime_types,
        stakes_framing=extraction.stakes_framing,
        technology_era=extraction.technology_era,
    )

    return Scenario(
        id=str(uuid.uuid4()),
        raw_text=raw_text,
        status=ScenarioStatus.DRAFT,
        actors=actors,
        objectives_by_actor=objectives_by_actor,
        constraints=extraction.constraints,
        options=options,
        dimensions=dimensions,
    )
