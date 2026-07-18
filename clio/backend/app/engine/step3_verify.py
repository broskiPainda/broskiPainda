"""Step 3 — Verify + enrich (the hallucination firewall).

For each nominated candidate, concurrently:
  - Fetch Wikipedia summary + lead sections via REST API
  - Fetch Wikidata entity facts via SPARQL
  - If either fetch hard-fails, or the fetched facts don't corroborate the
    nomination (e.g. wildly different dates), DROP the candidate and log why
  - Check the SQLite cache first (key: normalized event name); on a cache
    hit, skip fetch+structuring entirely
  - On a cache miss: Claude structures the full StructuredCase grounded ONLY
    in the fetched text (narrative fields must not add unsupported facts;
    analytical fields must reference sourced facts), then it's cached with
    its source_urls attached.
"""
import asyncio
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.cache.db import CaseCache
from app.engine.llm import structured_call
from app.engine.step2_nominate import NominatedCandidate
from app.models.case import (
    Actor,
    ActorRole,
    CaseDimensions,
    Decision,
    Lesson,
    Outcome,
    StructuredCase,
)
from app.sources.wikidata import WikidataClient, WikidataFacts
from app.sources.wikipedia import WikipediaClient, WikipediaNotFoundError, WikipediaSummary

DATE_TOLERANCE_YEARS = 20

STRUCTURING_SYSTEM_PROMPT = """You are a historian structuring a verified historical case for \
analogical decision analysis. You are given: the scenario this case is being compared against, \
the candidate case's name, and grounding text fetched from Wikipedia (and structured facts from \
Wikidata).

STRICT RULE: for narrative fields (summary, pre_event, decision, execution_notes, outcomes) you \
must ONLY use facts present in the grounding text below. Do not add names, dates, numbers, or \
events that are not supported by the provided text. If the grounding text doesn't specify \
something (e.g. exact decision process), write "not specified in available sources" rather than \
inventing detail.

For analytical fields (assessments, counterfactuals, lessons, adversary_calculus) you may reason \
using your own judgment, but that reasoning must reference facts from the grounding text, not \
facts you're inventing. Judge decision quality on soundness given information available at the \
time — never as a retroactive verdict on the outcome.

Fill in a value for each of the 12 structural dimensions (power_asymmetry, \
alliance_architecture, domestic_constraints, geography, time_pressure, \
information_environment, escalation_position, economic_interdependence, \
third_party_involvement, regime_types, stakes_framing, technology_era) describing THIS \
historical case."""


@dataclass
class DroppedCandidate:
    name: str
    wikipedia_title: str
    reason: str


@dataclass
class VerifiedCandidate:
    case: StructuredCase
    from_cache: bool
    is_negative_analogue: bool = False


@dataclass
class VerificationResult:
    verified: list[VerifiedCandidate] = field(default_factory=list)
    dropped: list[DroppedCandidate] = field(default_factory=list)


class _CaseStructuringOutput(BaseModel):
    era: str
    dates: str
    summary: str
    actors: list[Actor] = Field(default_factory=list)
    pre_event_context: str
    objectives_by_actor: dict[str, str] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list)
    options_on_table: list[str] = Field(default_factory=list)
    info_available_at_time: list[str] = Field(default_factory=list)
    info_unknown_at_time: list[str] = Field(default_factory=list)
    decision_chosen_option: str
    decision_maker: str
    decision_process: str
    dissenting_voices: list[str] = Field(default_factory=list)
    decision_time_pressure: str
    execution_notes: str
    outcomes: list[Outcome] = Field(default_factory=list)
    adversary_calculus: str
    lessons: list[Lesson] = Field(default_factory=list)
    power_asymmetry: str
    alliance_architecture: str
    domestic_constraints: str
    geography: str
    time_pressure: str
    information_environment: str
    escalation_position: str
    economic_interdependence: str
    third_party_involvement: str
    regime_types: str
    stakes_framing: str
    technology_era: str


def _extract_year(text: str) -> int | None:
    match = re.search(r"\b(1[0-9]{3}|20[0-9]{2})\b", text)
    return int(match.group(1)) if match else None


def _corroborates(candidate: NominatedCandidate, summary: WikipediaSummary, facts: WikidataFacts) -> bool:
    if not summary.extract.strip():
        return False
    nominated_year = _extract_year(candidate.approximate_dates)
    if nominated_year is None:
        return True
    wikidata_year = _extract_year(facts.start_date) if facts.start_date else None
    summary_year = _extract_year(summary.extract)
    reference_year = wikidata_year or summary_year
    if reference_year is None:
        return True
    return abs(reference_year - nominated_year) <= DATE_TOLERANCE_YEARS


async def _fetch_grounding(
    candidate: NominatedCandidate,
    wiki_client: WikipediaClient,
    wikidata_client: WikidataClient,
) -> tuple[WikipediaSummary, str, WikidataFacts] | DroppedCandidate:
    try:
        summary, lead_text = await asyncio.gather(
            wiki_client.get_summary(candidate.wikipedia_title),
            wiki_client.get_lead_sections(candidate.wikipedia_title),
        )
    except WikipediaNotFoundError:
        return DroppedCandidate(candidate.name, candidate.wikipedia_title, "wikipedia article not found")
    except Exception as exc:  # noqa: BLE001
        return DroppedCandidate(candidate.name, candidate.wikipedia_title, f"wikipedia fetch failed: {exc}")

    try:
        facts = await wikidata_client.get_entity_facts(candidate.wikipedia_title)
    except Exception as exc:  # noqa: BLE001
        return DroppedCandidate(candidate.name, candidate.wikipedia_title, f"wikidata fetch failed: {exc}")

    if not _corroborates(candidate, summary, facts):
        return DroppedCandidate(
            candidate.name,
            candidate.wikipedia_title,
            "fetched content does not corroborate nominated dates",
        )

    return summary, lead_text, facts


async def _structure_case(
    scenario_text: str,
    candidate: NominatedCandidate,
    summary: WikipediaSummary,
    lead_text: str,
    facts: WikidataFacts,
    source_urls: list[str],
) -> StructuredCase:
    grounding = f"""Scenario being analyzed: {scenario_text}

Candidate case: {candidate.name} ({candidate.approximate_dates})
Nomination rationale: {candidate.structural_rationale}

--- Wikipedia summary ---
{summary.extract}

--- Wikipedia lead sections ---
{lead_text}

--- Wikidata facts ---
Label: {facts.label or "unknown"}
Start date: {facts.start_date or "unknown"}
End date: {facts.end_date or "unknown"}
Participants: {", ".join(facts.participants) or "unknown"}
Part of: {", ".join(facts.part_of) or "unknown"}"""

    structured = await structured_call(
        system=STRUCTURING_SYSTEM_PROMPT,
        user=grounding,
        response_model=_CaseStructuringOutput,
        max_tokens=6000,
    )

    dimensions = CaseDimensions(
        power_asymmetry=structured.power_asymmetry,
        alliance_architecture=structured.alliance_architecture,
        domestic_constraints=structured.domestic_constraints,
        geography=structured.geography,
        time_pressure=structured.time_pressure,
        information_environment=structured.information_environment,
        escalation_position=structured.escalation_position,
        economic_interdependence=structured.economic_interdependence,
        third_party_involvement=structured.third_party_involvement,
        regime_types=structured.regime_types,
        stakes_framing=structured.stakes_framing,
        technology_era=structured.technology_era,
    )

    from app.models.case import PreEvent

    return StructuredCase(
        id=str(uuid.uuid4()),
        name=candidate.name,
        era=structured.era,
        dates=structured.dates,
        source_urls=source_urls,
        summary=structured.summary,
        actors=structured.actors or [Actor(name=candidate.name, role=ActorRole.INITIATOR, regime_type="unknown")],
        pre_event=PreEvent(
            context=structured.pre_event_context,
            objectives_by_actor=structured.objectives_by_actor,
            constraints=structured.constraints,
            options_on_table=structured.options_on_table,
            info_available_at_time=structured.info_available_at_time,
            info_unknown_at_time=structured.info_unknown_at_time,
        ),
        decision=Decision(
            chosen_option=structured.decision_chosen_option,
            decision_maker=structured.decision_maker,
            process=structured.decision_process,
            dissenting_voices=structured.dissenting_voices,
            time_pressure=structured.decision_time_pressure,
        ),
        execution_notes=structured.execution_notes,
        outcomes=structured.outcomes,
        assessments=[],
        counterfactuals=[],
        adversary_calculus=structured.adversary_calculus,
        lessons=structured.lessons,
        dimensions=dimensions,
        generated_by_model=True,
        verified_against_sources=True,
        cached_at=datetime.now(timezone.utc),
    )


async def verify_and_enrich(
    scenario_text: str,
    candidates: list[NominatedCandidate],
    cache: CaseCache | None = None,
    wiki_client: WikipediaClient | None = None,
    wikidata_client: WikidataClient | None = None,
) -> VerificationResult:
    cache = cache or CaseCache()
    owns_wiki = wiki_client is None
    owns_wikidata = wikidata_client is None
    wiki_client = wiki_client or WikipediaClient()
    wikidata_client = wikidata_client or WikidataClient()

    result = VerificationResult()

    def _lookup_cached(candidate: NominatedCandidate) -> StructuredCase | None:
        # Exact normalized-name match first; falls back to the semantic index for
        # near-duplicate phrasings the exact match misses (best-effort, see semantic.py).
        return cache.get_by_name(candidate.name) or cache.find_semantic_duplicate(candidate.name)

    try:
        for candidate in candidates:
            cached_case = _lookup_cached(candidate)
            if cached_case is not None:
                result.verified.append(
                    VerifiedCandidate(
                        case=cached_case,
                        from_cache=True,
                        is_negative_analogue=candidate.is_negative_analogue,
                    )
                )

        remaining = [c for c in candidates if _lookup_cached(c) is None]

        fetch_results = await asyncio.gather(
            *[_fetch_grounding(c, wiki_client, wikidata_client) for c in remaining]
        )

        structuring_jobs = []
        for candidate, fetch_result in zip(remaining, fetch_results):
            if isinstance(fetch_result, DroppedCandidate):
                result.dropped.append(fetch_result)
                continue
            summary, lead_text, facts = fetch_result
            source_urls = [summary.content_urls_desktop or f"https://en.wikipedia.org/wiki/{candidate.wikipedia_title.replace(' ', '_')}"]
            structuring_jobs.append((candidate, summary, lead_text, facts, source_urls))

        structured_cases = await asyncio.gather(
            *[
                _structure_case(scenario_text, candidate, summary, lead_text, facts, source_urls)
                for candidate, summary, lead_text, facts, source_urls in structuring_jobs
            ],
            return_exceptions=True,
        )

        for (candidate, *_rest), structured in zip(structuring_jobs, structured_cases):
            if isinstance(structured, Exception):
                result.dropped.append(
                    DroppedCandidate(candidate.name, candidate.wikipedia_title, f"structuring failed: {structured}")
                )
                continue
            cache.put(structured)
            result.verified.append(
                VerifiedCandidate(
                    case=structured,
                    from_cache=False,
                    is_negative_analogue=candidate.is_negative_analogue,
                )
            )

        return result
    finally:
        if owns_wiki:
            await wiki_client.aclose()
        if owns_wikidata:
            await wikidata_client.aclose()
