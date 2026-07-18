"""Retrieval-quality test suite (Phase 5).

A Munich-1938-like appeasement scenario must nominate appeasement-class
analogues (Munich Agreement, Sudetenland crisis, Rhineland remilitarization,
etc.) — this is the concrete acceptance bar from the build spec.

Two tiers:
  1. A mocked test (always runs, no network/API key needed) that pins down
     the *checker* logic (contains_keyword_class) against both a passing
     and a failing fixture, and exercises the full nominate_analogues() path
     with a canned appeasement-class response.
  2. A live test that calls the real Claude/z.ai API and asserts the
     checker against real nomination output. Skipped by default — set
     CLIO_LIVE_LLM_TESTS=1 (and a working ANTHROPIC_API_KEY /
     CLIO_ANTHROPIC_BASE_URL) to run it. This sandbox's egress policy blocks
     the LLM endpoint outright, so it cannot run here; it's meant to be run
     in a normal dev/CI environment with real network access.
"""
import os

import pytest

from app.engine import step2_nominate
from app.engine.retrieval_quality import APPEASEMENT_KEYWORDS, contains_keyword_class
from app.engine.step2_nominate import NominatedCandidate
from app.models.case import Actor, ActorRole
from app.models.scenario import Scenario, ScenarioDimensions
from tests.fakes import FakeAnthropicClient

APPEASEMENT_SCENARIO_TEXT = (
    "A great power is demanding the cession of a border region of a smaller neighboring "
    "democracy, home to a large co-ethnic minority, threatening war if refused. Other major "
    "powers are debating whether to accept the demand to avoid a wider war, despite a mutual "
    "defense treaty with the smaller state."
)


def make_appeasement_scenario() -> Scenario:
    return Scenario(
        id="munich-like-1",
        raw_text=APPEASEMENT_SCENARIO_TEXT,
        actors=[
            Actor(name="Revisionist Great Power", role=ActorRole.INITIATOR, regime_type="authoritarian"),
            Actor(name="Border Democracy", role=ActorRole.TARGET, regime_type="parliamentary democracy"),
            Actor(name="Guarantor Powers", role=ActorRole.THIRD_PARTY, regime_type="mixed democracies"),
        ],
        dimensions=ScenarioDimensions(
            power_asymmetry="initiator far stronger",
            stakes_framing="territorial cession under threat of war",
            escalation_position="initiator threatens general war",
            alliance_architecture="target has a mutual defense treaty third parties are reluctant to honor",
        ),
    )


def test_checker_detects_appeasement_class_candidates():
    candidates = [
        NominatedCandidate(
            name="Munich Agreement",
            approximate_dates="1938",
            structural_rationale="Great powers ceded the Sudetenland to avoid war",
            wikipedia_title="Munich Agreement",
        ),
        NominatedCandidate(
            name="Unrelated Trade Dispute",
            approximate_dates="1995",
            structural_rationale="A tariff dispute between two large economies",
            wikipedia_title="Some Trade Dispute",
        ),
    ]
    assert contains_keyword_class(candidates, APPEASEMENT_KEYWORDS) is True


def test_checker_returns_false_when_no_candidate_matches():
    candidates = [
        NominatedCandidate(
            name="Cod Wars",
            approximate_dates="1958",
            structural_rationale="Fishing rights confrontation",
            wikipedia_title="Cod Wars",
        ),
        NominatedCandidate(
            name="Suez Crisis",
            approximate_dates="1956",
            structural_rationale="Canal nationalization dispute",
            wikipedia_title="Suez Crisis",
        ),
    ]
    assert contains_keyword_class(candidates, APPEASEMENT_KEYWORDS) is False


@pytest.mark.asyncio
async def test_nominate_analogues_appeasement_scenario_mocked(monkeypatch):
    """Pins the full Step 2 path: given a scenario shaped like Munich 1938, a
    canned-but-realistic nomination response must pass the appeasement-class
    check. This is a regression harness for the checker + wiring, not proof
    the real model nominates well — see the live test below for that."""
    payload = {
        "candidates": [
            {
                "name": "Munich Agreement",
                "approximate_dates": "September 1938",
                "structural_rationale": "Territorial cession of a democracy's borderland to a stronger "
                "revisionist power under threat of war, with third-party guarantors declining to intervene",
                "wikipedia_title": "Munich Agreement",
                "is_negative_analogue": False,
            },
            {
                "name": "Remilitarization of the Rhineland",
                "approximate_dates": "1936",
                "structural_rationale": "Earlier test of the same revisionist power's willingness to violate "
                "treaty terms without meaningful pushback",
                "wikipedia_title": "Remilitarization of the Rhineland",
                "is_negative_analogue": False,
            },
            {
                "name": "Falklands War",
                "approximate_dates": "1982",
                "structural_rationale": "Superficially a territorial dispute but resolved by force rather "
                "than negotiated cession, and lacks the multi-party guarantor dynamic — negative analogue",
                "wikipedia_title": "Falklands War",
                "is_negative_analogue": True,
            },
        ]
    }
    client = FakeAnthropicClient([("border region", payload)])

    async def fake_structured_call(system, user, response_model, **kwargs):
        from app.engine.llm import structured_call as real_call

        return await real_call(system, user, response_model, client=client)

    monkeypatch.setattr(step2_nominate, "structured_call", fake_structured_call)

    candidates = await step2_nominate.nominate_analogues(make_appeasement_scenario())

    assert contains_keyword_class(candidates, APPEASEMENT_KEYWORDS) is True
    assert any(c.is_negative_analogue for c in candidates)


LIVE_LLM_TESTS_ENABLED = os.environ.get("CLIO_LIVE_LLM_TESTS") == "1"


@pytest.mark.asyncio
@pytest.mark.skipif(
    not LIVE_LLM_TESTS_ENABLED,
    reason="Live LLM retrieval-quality test — set CLIO_LIVE_LLM_TESTS=1 with a working API "
    "key/endpoint to run. Requires real network access; this sandbox's egress policy blocks it.",
)
async def test_nominate_analogues_appeasement_scenario_live():
    candidates = await step2_nominate.nominate_analogues(make_appeasement_scenario())
    assert contains_keyword_class(candidates, APPEASEMENT_KEYWORDS), (
        f"Expected an appeasement-class analogue (Munich, Sudetenland, Rhineland, etc.) among "
        f"nominated candidates, got: {[c.name for c in candidates]}"
    )
