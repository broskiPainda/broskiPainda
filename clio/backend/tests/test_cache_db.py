from app.cache.db import CaseCache, ScenarioStore, normalize_case_name
from app.models.scenario import Scenario, ScenarioDimensions, ScenarioStatus
from tests.test_models import make_case


def test_normalize_case_name():
    assert normalize_case_name("Cuban Missile Crisis") == "cuban-missile-crisis"
    assert normalize_case_name("  The  Berlin Blockade! ") == "the-berlin-blockade"


def test_case_cache_put_and_get_by_name(tmp_path):
    cache = CaseCache(sqlite_path=tmp_path / "c.db")
    case = make_case()
    cache.put(case)

    found = cache.get_by_name("Cuban Missile Crisis")
    assert found is not None
    assert found.id == case.id

    assert cache.get_by_name("Nonexistent Case") is None


def test_case_cache_put_overwrites_on_same_normalized_name(tmp_path):
    cache = CaseCache(sqlite_path=tmp_path / "c.db")
    case = make_case()
    cache.put(case)
    updated = make_case(id=case.id, summary="Updated summary")
    cache.put(updated)

    all_cases = cache.list_all()
    assert len(all_cases) == 1
    assert all_cases[0].summary == "Updated summary"


def test_case_cache_delete(tmp_path):
    cache = CaseCache(sqlite_path=tmp_path / "c.db")
    case = make_case()
    cache.put(case)
    assert cache.delete(case.id) is True
    assert cache.list_all() == []
    assert cache.delete(case.id) is False


def test_scenario_store_save_and_get(tmp_path):
    store = ScenarioStore(sqlite_path=tmp_path / "s.db")
    scenario = Scenario(
        id="sc1",
        raw_text="test scenario",
        status=ScenarioStatus.DRAFT,
        dimensions=ScenarioDimensions(),
    )
    store.save(scenario)

    fetched = store.get("sc1")
    assert fetched is not None
    assert fetched.raw_text == "test scenario"

    scenario.status = ScenarioStatus.CONFIRMED
    store.save(scenario)
    assert store.get("sc1").status == ScenarioStatus.CONFIRMED

    assert store.get("nonexistent") is None
    assert len(store.list_all()) == 1
