import pytest

from app.cache.db import CaseCache
from app.engine import step3_verify
from app.engine.step2_nominate import NominatedCandidate
from app.sources.wikidata import WikidataFacts
from app.sources.wikipedia import WikipediaSummary
from tests.fakes import FakeAnthropicClient, FakeWikidataClient, FakeWikipediaClient

SCENARIO_TEXT = "A mid-size power is considering a naval blockade of a smaller neighbor."


def _structuring_output(name: str) -> dict:
    dims = {
        "power_asymmetry": "asymmetric",
        "alliance_architecture": "loose",
        "domestic_constraints": "moderate",
        "geography": "maritime",
        "time_pressure": "high",
        "information_environment": "high",
        "escalation_position": "dominant",
        "economic_interdependence": "moderate",
        "third_party_involvement": "some",
        "regime_types": "mixed",
        "stakes_framing": "sovereignty",
        "technology_era": "modern",
    }
    return {
        "era": "20th century",
        "dates": "1962",
        "summary": f"Summary of {name} grounded in fetched text.",
        "actors": [{"name": name, "role": "initiator", "regime_type": "unknown"}],
        "pre_event_context": f"Context for {name}.",
        "objectives_by_actor": {name: "objective"},
        "constraints": ["constraint"],
        "options_on_table": ["option"],
        "info_available_at_time": ["info"],
        "info_unknown_at_time": ["unknown"],
        "decision_chosen_option": "chosen option",
        "decision_maker": "leader",
        "decision_process": "deliberation",
        "dissenting_voices": [],
        "decision_time_pressure": "high",
        "execution_notes": "executed as planned",
        "outcomes": [{"horizon": "immediate", "description": "resolved", "valence": "positive"}],
        "adversary_calculus": "adversary sought to avoid war",
        "lessons": [],
        **dims,
    }


@pytest.mark.asyncio
async def test_verify_and_enrich_drops_unfetchable_and_mismatched(monkeypatch, tmp_path):
    candidates = [
        NominatedCandidate(
            name="Cuban Missile Crisis",
            approximate_dates="1962",
            structural_rationale="naval quarantine",
            wikipedia_title="Cuban Missile Crisis",
        ),
        NominatedCandidate(
            name="Nonexistent Event",
            approximate_dates="1900",
            structural_rationale="fabricated",
            wikipedia_title="Totally Fictional Article Xyz",
        ),
        NominatedCandidate(
            name="Mismatched Dates Event",
            approximate_dates="1962",
            structural_rationale="dates will not match fetched facts",
            wikipedia_title="Mismatched Dates Event",
        ),
    ]

    wiki_client = FakeWikipediaClient(
        summaries={
            "Cuban Missile Crisis": WikipediaSummary(
                title="Cuban Missile Crisis", extract="A 1962 Cold War confrontation.", content_urls_desktop="https://en.wikipedia.org/wiki/Cuban_Missile_Crisis"
            ),
            "Mismatched Dates Event": WikipediaSummary(
                title="Mismatched Dates Event", extract="An event from the 1400s.", content_urls_desktop="https://en.wikipedia.org/wiki/Mismatched_Dates_Event"
            ),
        },
        missing_titles={"Totally Fictional Article Xyz"},
    )
    wikidata_client = FakeWikidataClient(
        facts={
            "Cuban Missile Crisis": WikidataFacts(qid="Q128736", label="Cuban Missile Crisis", start_date="1962-10-16"),
            "Mismatched Dates Event": WikidataFacts(qid="Q999", label="Mismatched Dates Event", start_date="1450-01-01"),
        }
    )

    llm_client = FakeAnthropicClient([("Cuban Missile Crisis", _structuring_output("Cuban Missile Crisis"))])

    async def fake_structured_call(system, user, response_model, **kwargs):
        from app.engine.llm import structured_call as real_call

        return await real_call(system, user, response_model, client=llm_client)

    monkeypatch.setattr(step3_verify, "structured_call", fake_structured_call)

    cache = CaseCache(sqlite_path=tmp_path / "cache.db")
    result = await step3_verify.verify_and_enrich(
        SCENARIO_TEXT, candidates, cache=cache, wiki_client=wiki_client, wikidata_client=wikidata_client
    )

    assert len(result.verified) == 1
    assert result.verified[0].case.name == "Cuban Missile Crisis"
    assert result.verified[0].case.verified_against_sources is True
    assert len(result.dropped) == 2
    reasons = {d.name: d.reason for d in result.dropped}
    assert "not found" in reasons["Nonexistent Event"]
    assert "corroborate" in reasons["Mismatched Dates Event"]


@pytest.mark.asyncio
async def test_verify_and_enrich_uses_cache_on_second_call(monkeypatch, tmp_path):
    candidate = NominatedCandidate(
        name="Berlin Blockade",
        approximate_dates="1948",
        structural_rationale="blockade of a city",
        wikipedia_title="Berlin Blockade",
        is_negative_analogue=True,
    )
    wiki_client = FakeWikipediaClient(
        summaries={
            "Berlin Blockade": WikipediaSummary(
                title="Berlin Blockade", extract="A 1948 Cold War crisis.", content_urls_desktop="https://en.wikipedia.org/wiki/Berlin_Blockade"
            )
        }
    )
    wikidata_client = FakeWikidataClient(
        facts={"Berlin Blockade": WikidataFacts(qid="Q44432", label="Berlin Blockade", start_date="1948-06-24")}
    )
    llm_client = FakeAnthropicClient([("Berlin Blockade", _structuring_output("Berlin Blockade"))])
    call_count = {"n": 0}

    async def fake_structured_call(system, user, response_model, **kwargs):
        call_count["n"] += 1
        from app.engine.llm import structured_call as real_call

        return await real_call(system, user, response_model, client=llm_client)

    monkeypatch.setattr(step3_verify, "structured_call", fake_structured_call)

    cache = CaseCache(sqlite_path=tmp_path / "cache.db")
    result1 = await step3_verify.verify_and_enrich(
        SCENARIO_TEXT, [candidate], cache=cache, wiki_client=wiki_client, wikidata_client=wikidata_client
    )
    assert len(result1.verified) == 1
    assert result1.verified[0].from_cache is False
    assert result1.verified[0].is_negative_analogue is True
    assert call_count["n"] == 1

    result2 = await step3_verify.verify_and_enrich(
        SCENARIO_TEXT, [candidate], cache=cache, wiki_client=wiki_client, wikidata_client=wikidata_client
    )
    assert len(result2.verified) == 1
    assert result2.verified[0].from_cache is True
    assert call_count["n"] == 1  # no additional LLM call on cache hit


@pytest.mark.asyncio
async def test_verify_and_enrich_finds_semantic_duplicate_by_differently_phrased_name(monkeypatch, tmp_path):
    """A later nomination phrasing the same case slightly differently (different exact
    normalized-name slug) should still hit the cache via the semantic index rather than
    re-fetching and re-structuring from scratch."""
    original = NominatedCandidate(
        name="Cuban Missile Crisis",
        approximate_dates="1962",
        structural_rationale="naval quarantine",
        wikipedia_title="Cuban Missile Crisis",
    )
    rephrased = NominatedCandidate(
        name="The Cuban Missile Crisis of 1962",
        approximate_dates="1962",
        structural_rationale="naval quarantine",
        wikipedia_title="Cuban Missile Crisis",
    )
    wiki_client = FakeWikipediaClient(
        summaries={
            "Cuban Missile Crisis": WikipediaSummary(
                title="Cuban Missile Crisis",
                extract="A 1962 Cold War confrontation.",
                content_urls_desktop="https://en.wikipedia.org/wiki/Cuban_Missile_Crisis",
            )
        }
    )
    wikidata_client = FakeWikidataClient(
        facts={"Cuban Missile Crisis": WikidataFacts(qid="Q128736", label="Cuban Missile Crisis", start_date="1962-10-16")}
    )
    llm_client = FakeAnthropicClient([("Cuban Missile Crisis", _structuring_output("Cuban Missile Crisis"))])
    call_count = {"n": 0}

    async def fake_structured_call(system, user, response_model, **kwargs):
        call_count["n"] += 1
        from app.engine.llm import structured_call as real_call

        return await real_call(system, user, response_model, client=llm_client)

    monkeypatch.setattr(step3_verify, "structured_call", fake_structured_call)

    cache = CaseCache(sqlite_path=tmp_path / "cache.db")
    await step3_verify.verify_and_enrich(
        SCENARIO_TEXT, [original], cache=cache, wiki_client=wiki_client, wikidata_client=wikidata_client
    )
    assert call_count["n"] == 1

    result = await step3_verify.verify_and_enrich(
        SCENARIO_TEXT, [rephrased], cache=cache, wiki_client=wiki_client, wikidata_client=wikidata_client
    )

    assert len(result.verified) == 1
    assert result.verified[0].from_cache is True
    assert call_count["n"] == 1  # semantic dedup avoided a second structuring call
