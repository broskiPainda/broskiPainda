from app.cache.semantic import SemanticCaseIndex


def test_add_and_find_similar_exact_text(tmp_path):
    index = SemanticCaseIndex(chroma_path=tmp_path / "chroma")
    index.add("case-1", "Cuban Missile Crisis", "A 1962 Cold War confrontation over Soviet missiles in Cuba.")

    matches = index.find_similar("Cuban Missile Crisis", "A 1962 Cold War confrontation over Soviet missiles in Cuba.")

    assert len(matches) >= 1
    assert matches[0][0] == "case-1"


def test_find_similar_empty_index_returns_empty(tmp_path):
    index = SemanticCaseIndex(chroma_path=tmp_path / "chroma")
    assert index.find_similar("Anything") == []


def test_find_similar_respects_max_distance(tmp_path):
    index = SemanticCaseIndex(chroma_path=tmp_path / "chroma")
    index.add("case-1", "Cuban Missile Crisis", "A 1962 Cold War confrontation over Soviet missiles in Cuba.")

    matches = index.find_similar("Completely unrelated topic about baking bread", max_distance=0.01)

    assert matches == []


def test_delete_removes_entry(tmp_path):
    index = SemanticCaseIndex(chroma_path=tmp_path / "chroma")
    index.add("case-1", "Cuban Missile Crisis", "A 1962 Cold War confrontation.")
    index.delete("case-1")

    matches = index.find_similar("Cuban Missile Crisis", "A 1962 Cold War confrontation.")
    assert matches == []


def test_add_is_best_effort_on_failure(tmp_path, monkeypatch):
    index = SemanticCaseIndex(chroma_path=tmp_path / "chroma")

    def broken_get_collection():
        raise RuntimeError("simulated chroma failure")

    monkeypatch.setattr(index, "_get_collection", broken_get_collection)
    index.add("case-1", "Name", "Summary")  # must not raise
    assert index.find_similar("Name") == []  # also must not raise
