# StructuredCase Schema

Defined in `backend/app/models/case.py`. This is the stable contract other
components (similarity engine, base-rate mapper, future KG loader) depend
on — treat field renames as breaking changes.

```
StructuredCase
  id: str
  name: str
  era: str
  dates: str
  source_urls: list[HttpUrl]
  summary: str
  actors: list[Actor]                # name, role (initiator|target|third_party), regime_type
  pre_event: PreEvent
    context: str
    objectives_by_actor: dict[str, str]
    constraints: list[str]
    options_on_table: list[str]
    info_available_at_time: list[str]
    info_unknown_at_time: list[str]
  decision: Decision
    chosen_option: str
    decision_maker: str
    process: str
    dissenting_voices: list[str]
    time_pressure: str
  execution_notes: str
  outcomes: list[Outcome]             # horizon (immediate|5yr|25yr), description, valence
  assessments: list[Assessment]       # axis (decision|execution|outcome), score_1_10, reasoning
  counterfactuals: list[Counterfactual]  # changed_variable, narrative, plausibility
  adversary_calculus: str
  lessons: list[Lesson]               # principle, transferability_limits
  dimensions: CaseDimensions           # the 12 structural dimensions, see below
  generated_by_model: bool = True
  verified_against_sources: bool
  cached_at: datetime | None
```

## The 12 structural dimensions

Defined as the `Dimension` enum in `backend/app/models/dimensions.py`:

`power_asymmetry`, `alliance_architecture`, `domestic_constraints`,
`geography`, `time_pressure`, `information_environment`,
`escalation_position`, `economic_interdependence`,
`third_party_involvement`, `regime_types`, `stakes_framing`,
`technology_era`.

Both `Scenario` (user input side) and `StructuredCase` (historical case
side) carry a value for each dimension as free text, so Step 4's similarity
scoring can compare them directly. Default weights (`DEFAULT_DIMENSION_WEIGHTS`
in the same module) weight `power_asymmetry`, `stakes_framing`, and
`escalation_position` at 2.0; all others at 1.0. Configurable in settings.

## Provenance and grounding rules

- `source_urls` must be populated before a case is cached — Step 3 drops
  any candidate that fails to fetch or corroborate from Wikipedia/Wikidata.
- Narrative fields (`summary`, `pre_event`, `decision`, `execution_notes`,
  `outcomes`) must be grounded in the fetched source text.
- Analytical fields (`assessments`, `counterfactuals`, `lessons`,
  `adversary_calculus`) are Claude's reasoning over the sourced facts, not
  independently sourced, but must not contradict them.
- `generated_by_model` is always `True` in v1 — there is no curated case
  base. The frontend must show a "machine-generated, not curated" badge
  wherever a case is displayed.
