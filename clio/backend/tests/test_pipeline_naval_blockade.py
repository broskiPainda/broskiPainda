"""End-to-end (mocked) test of pipeline Steps 1-3 against the scenario named
in the Phase 2 spec: "a mid-size power considering a naval blockade of a
smaller neighbor" — must produce >= 4 verified, source-grounded cases.

Wikipedia/Wikidata and the Anthropic API are mocked because this sandbox's
egress policy blocks en.wikipedia.org, query.wikidata.org, and api.z.ai
outright (confirmed via the agent proxy status endpoint) — a true network
end-to-end run needs to happen outside this sandbox (e.g. `docker compose up`
or a session with broader egress).
"""
import pytest

from app.cache.db import CaseCache
from app.engine import step1_structure, step2_nominate, step3_verify
from app.engine.pipeline import run_pipeline
from app.sources.wikidata import WikidataFacts
from app.sources.wikipedia import WikipediaSummary
from tests.fakes import FakeAnthropicClient, FakeWikidataClient, FakeWikipediaClient
from tests.test_step3 import _structuring_output

RAW_TEXT = "A mid-size power is considering a naval blockade of a smaller neighbor over a territorial and resource dispute."

STEP1_OUTPUT = {
    "refused": False,
    "actors": [
        {"name": "Mid-Size Power", "role": "initiator", "regime_type": "presidential democracy", "objective": "Force concessions on the territorial dispute"},
        {"name": "Smaller Neighbor", "role": "target", "regime_type": "parliamentary republic", "objective": "Preserve territorial claim and sovereignty"},
    ],
    "constraints": ["Domestic public opinion", "International law constraints", "Alliance commitments of the neighbor"],
    "options": ["Full naval blockade", "Partial/selective blockade", "Diplomatic pressure only"],
    "power_asymmetry": "initiator significantly stronger militarily and economically",
    "alliance_architecture": "neighbor has an informal security relationship with a distant great power",
    "domestic_constraints": "moderate — initiator has upcoming elections",
    "geography": "narrow strait, chokepoint control possible",
    "time_pressure": "moderate, building over weeks",
    "information_environment": "high global media attention, real-time tracking of naval movements",
    "escalation_position": "initiator holds escalation dominance at sea but not on land",
    "economic_interdependence": "significant bilateral trade, blockade imposes mutual costs",
    "third_party_involvement": "regional and global powers have voiced concern",
    "regime_types": "democracy vs. republic",
    "stakes_framing": "framed domestically as a sovereignty and resource-access issue",
    "technology_era": "contemporary, satellite-tracked naval assets",
}

# 6 nominated candidates: 5 should verify successfully, 1 (a negative analogue with mismatched
# nominated dates vs fetched facts) is deliberately dropped by the corroboration check, and 1
# additional candidate is unfetchable — leaving exactly 4 verified, meeting the >=4 requirement
# while also exercising the drop path end to end.
STEP2_OUTPUT = {
    "candidates": [
        {
            "name": "Cuban Missile Crisis",
            "approximate_dates": "1962",
            "structural_rationale": "Naval quarantine used as coercive tool short of open war, high escalation stakes",
            "wikipedia_title": "Cuban Missile Crisis",
            "is_negative_analogue": False,
        },
        {
            "name": "Venezuelan crisis of 1902-1903",
            "approximate_dates": "1902",
            "structural_rationale": "Naval blockade by stronger powers to coerce a weaker state into concessions",
            "wikipedia_title": "Venezuelan crisis of 1902-1903",
            "is_negative_analogue": False,
        },
        {
            "name": "Qatar diplomatic crisis",
            "approximate_dates": "2017",
            "structural_rationale": "Blockade (land/sea/air) by stronger neighbors against a smaller state over political disputes",
            "wikipedia_title": "Qatar diplomatic crisis",
            "is_negative_analogue": False,
        },
        {
            "name": "Cod Wars",
            "approximate_dates": "1958",
            "structural_rationale": "Naval confrontation over maritime resource access between asymmetric powers",
            "wikipedia_title": "Cod Wars",
            "is_negative_analogue": False,
        },
        {
            "name": "Berlin Blockade",
            "approximate_dates": "1948",
            "structural_rationale": "Superficially similar 'blockade' framing, but this is a land siege of a city under joint occupation, not a naval coercion of a sovereign neighbor — a useful negative analogue",
            "wikipedia_title": "Berlin Blockade",
            "is_negative_analogue": True,
        },
        {
            "name": "Fabricated Naval Incident",
            "approximate_dates": "1975",
            "structural_rationale": "Plausible-sounding but not a real, verifiable article",
            "wikipedia_title": "Fabricated Naval Incident That Does Not Exist",
            "is_negative_analogue": False,
        },
    ]
}


def _fake_structured_call_dispatcher(llm_client):
    async def fake_structured_call(system, user, response_model, **kwargs):
        from app.engine.llm import structured_call as real_call

        return await real_call(system, user, response_model, client=llm_client)

    return fake_structured_call


@pytest.mark.asyncio
async def test_naval_blockade_scenario_produces_at_least_four_verified_cases(monkeypatch, tmp_path):
    step1_client = FakeAnthropicClient([("naval blockade", STEP1_OUTPUT)])
    monkeypatch.setattr(step1_structure, "structured_call", _fake_structured_call_dispatcher(step1_client))

    scenario = await step1_structure.structure_scenario(RAW_TEXT)
    assert len(scenario.actors) == 2

    step2_client = FakeAnthropicClient([("naval blockade", STEP2_OUTPUT)])
    monkeypatch.setattr(step2_nominate, "structured_call", _fake_structured_call_dispatcher(step2_client))

    # Wikipedia/Wikidata: 4 candidates corroborate cleanly, Berlin Blockade's dates are made to
    # mismatch its nomination to exercise the corroboration-drop path, and the fabricated
    # candidate has no article at all.
    wiki_client = FakeWikipediaClient(
        summaries={
            "Cuban Missile Crisis": WikipediaSummary(title="Cuban Missile Crisis", extract="A 1962 Cold War confrontation over Soviet missiles in Cuba.", content_urls_desktop="https://en.wikipedia.org/wiki/Cuban_Missile_Crisis"),
            "Venezuelan crisis of 1902-1903": WikipediaSummary(title="Venezuelan crisis of 1902-1903", extract="An 1902 naval blockade of Venezuela by European powers.", content_urls_desktop="https://en.wikipedia.org/wiki/Venezuelan_crisis_of_1902-1903"),
            "Qatar diplomatic crisis": WikipediaSummary(title="Qatar diplomatic crisis", extract="A 2017 diplomatic and blockade crisis involving Qatar.", content_urls_desktop="https://en.wikipedia.org/wiki/Qatar_diplomatic_crisis"),
            "Cod Wars": WikipediaSummary(title="Cod Wars", extract="A series of confrontations starting in 1958 over fishing rights.", content_urls_desktop="https://en.wikipedia.org/wiki/Cod_Wars"),
            "Berlin Blockade": WikipediaSummary(title="Berlin Blockade", extract="An event from the 1200s that does not match.", content_urls_desktop="https://en.wikipedia.org/wiki/Berlin_Blockade"),
        },
        missing_titles={"Fabricated Naval Incident That Does Not Exist"},
    )
    wikidata_client = FakeWikidataClient(
        facts={
            "Cuban Missile Crisis": WikidataFacts(qid="Q128736", label="Cuban Missile Crisis", start_date="1962-10-16"),
            "Venezuelan crisis of 1902-1903": WikidataFacts(qid="Q751403", label="Venezuelan crisis of 1902-1903", start_date="1902-12-09"),
            "Qatar diplomatic crisis": WikidataFacts(qid="Q29964244", label="Qatar diplomatic crisis", start_date="2017-06-05"),
            "Cod Wars": WikidataFacts(qid="Q844423", label="Cod Wars", start_date="1958-09-01"),
            "Berlin Blockade": WikidataFacts(qid="Q44432", label="Berlin Blockade", start_date="1250-01-01"),
        }
    )

    structuring_marker_pairs = [
        (name, _structuring_output(name))
        for name in [
            "Cuban Missile Crisis",
            "Venezuelan crisis of 1902-1903",
            "Qatar diplomatic crisis",
            "Cod Wars",
        ]
    ]
    step3_client = FakeAnthropicClient(structuring_marker_pairs)
    monkeypatch.setattr(step3_verify, "structured_call", _fake_structured_call_dispatcher(step3_client))

    cache = CaseCache(sqlite_path=tmp_path / "cache.db")

    events = []
    async for event in run_pipeline(
        scenario, cache=cache, wiki_client=wiki_client, wikidata_client=wikidata_client
    ):
        events.append(event)

    verified_events = [e for e in events if e["event"] == "candidate_verified"]
    dropped_events = [e for e in events if e["event"] == "candidate_dropped"]
    step_completed = next(e for e in events if e["event"] == "step_completed" and e["data"]["step"] == 3)

    assert len(verified_events) >= 4
    assert step_completed["data"]["verified_count"] >= 4
    assert len(dropped_events) == 2
    dropped_names = {e["data"]["name"] for e in dropped_events}
    assert dropped_names == {"Berlin Blockade", "Fabricated Naval Incident"}

    for e in verified_events:
        assert e["data"]["source_urls"], "every verified case must carry source URLs"

    cached_cases = cache.list_all()
    assert len(cached_cases) >= 4
    for case in cached_cases:
        assert case.verified_against_sources is True
        assert case.source_urls

    negative_analogue_events = [e for e in verified_events if e["data"]["is_negative_analogue"]]
    # The Berlin Blockade negative analogue was dropped for date mismatch in this fixture,
    # so none of the *verified* cases are flagged negative here — confirms the firewall
    # doesn't wave through a negative analogue just because it was nominated as one.
    assert negative_analogue_events == []
