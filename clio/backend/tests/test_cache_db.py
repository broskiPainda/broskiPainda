from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.cache.db import CachedCase, CaseCache, CostLogStore, ScenarioStore, normalize_case_name
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


def test_evict_stale_removes_old_entries(tmp_path):
    cache = CaseCache(sqlite_path=tmp_path / "c.db")
    fresh = make_case(id="fresh", name="Fresh Case")
    stale = make_case(id="stale", name="Stale Case")
    cache.put(fresh)
    cache.put(stale)

    with Session(cache.engine) as session:
        row = session.exec(select(CachedCase).where(CachedCase.id == "stale")).one()
        row.cached_at = datetime.now(timezone.utc) - timedelta(days=200)
        session.add(row)
        session.commit()

    evicted = cache.evict_stale(max_age_days=90)

    assert evicted == 1
    remaining = {c.id for c in cache.list_all()}
    assert remaining == {"fresh"}


def test_evict_lru_caps_total_size(tmp_path):
    cache = CaseCache(sqlite_path=tmp_path / "c.db")
    for i in range(5):
        cache.put(make_case(id=f"case-{i}", name=f"Case {i}"))
        with Session(cache.engine) as session:
            row = session.exec(select(CachedCase).where(CachedCase.id == f"case-{i}")).one()
            row.cached_at = datetime.now(timezone.utc) - timedelta(days=5 - i)
            session.add(row)
            session.commit()

    evicted = cache.evict_lru(max_entries=3)

    assert evicted == 2
    remaining = {c.id for c in cache.list_all()}
    # The two oldest (case-0, case-1) should be gone; the three most recent survive.
    assert remaining == {"case-2", "case-3", "case-4"}


def test_evict_lru_no_op_under_cap(tmp_path):
    cache = CaseCache(sqlite_path=tmp_path / "c.db")
    cache.put(make_case())
    assert cache.evict_lru(max_entries=100) == 0


def test_cost_log_store_log_and_list(tmp_path):
    store = CostLogStore(sqlite_path=tmp_path / "c.db")
    store.log("scenario-1", "report-1", {"call_count": 3, "input_tokens": 100, "output_tokens": 50, "estimated_cost_usd": 0.01})
    store.log("scenario-1", None, {"call_count": 1, "input_tokens": 10, "output_tokens": 5, "estimated_cost_usd": 0.001})
    store.log("scenario-2", "report-2", {"call_count": 2, "input_tokens": 20, "output_tokens": 10, "estimated_cost_usd": 0.002})

    logs = store.list_for_scenario("scenario-1")
    assert len(logs) == 2
    assert {log.report_id for log in logs} == {"report-1", None}
