"""The 12 structural dimensions used to compare scenarios to historical cases.

This enum is the stable contract referenced by the similarity engine (Step 4)
and the future Neo4j migration (see docs/MIGRATION_TO_KG.md). Do not rename
values without updating cached cases.
"""
from enum import Enum


class Dimension(str, Enum):
    POWER_ASYMMETRY = "power_asymmetry"
    ALLIANCE_ARCHITECTURE = "alliance_architecture"
    DOMESTIC_CONSTRAINTS = "domestic_constraints"
    GEOGRAPHY = "geography"
    TIME_PRESSURE = "time_pressure"
    INFORMATION_ENVIRONMENT = "information_environment"
    ESCALATION_POSITION = "escalation_position"
    ECONOMIC_INTERDEPENDENCE = "economic_interdependence"
    THIRD_PARTY_INVOLVEMENT = "third_party_involvement"
    REGIME_TYPES = "regime_types"
    STAKES_FRAMING = "stakes_framing"
    TECHNOLOGY_ERA = "technology_era"


# Default similarity weights (Step 4). Configurable in settings; these three
# are weighted higher because they most strongly determine analogical fit.
DEFAULT_DIMENSION_WEIGHTS = {
    Dimension.POWER_ASYMMETRY: 2.0,
    Dimension.STAKES_FRAMING: 2.0,
    Dimension.ESCALATION_POSITION: 2.0,
    Dimension.ALLIANCE_ARCHITECTURE: 1.0,
    Dimension.DOMESTIC_CONSTRAINTS: 1.0,
    Dimension.GEOGRAPHY: 1.0,
    Dimension.TIME_PRESSURE: 1.0,
    Dimension.INFORMATION_ENVIRONMENT: 1.0,
    Dimension.ECONOMIC_INTERDEPENDENCE: 1.0,
    Dimension.THIRD_PARTY_INVOLVEMENT: 1.0,
    Dimension.REGIME_TYPES: 1.0,
    Dimension.TECHNOLOGY_ERA: 1.0,
}

ALL_DIMENSIONS = list(Dimension)
