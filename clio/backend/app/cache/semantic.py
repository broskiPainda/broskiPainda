"""ChromaDB-backed semantic index over cached cases, for dedup/reuse beyond
what the SQLite cache's exact normalized-name lookup catches (e.g. Claude
nominating "The Cuban Missile Crisis (1962)" in one scenario and "Cuban
Missile Crisis" in another — different normalized slugs, same case).

This is a best-effort enhancement layer: every public method swallows its
own failures (no network, disk issue, whatever) and degrades to "no match
found" rather than breaking the case cache's core functionality, which only
depends on SQLite.
"""
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "cases"


class SemanticCaseIndex:
    def __init__(self, chroma_path=None):
        settings = get_settings()
        self._path = chroma_path or settings.chroma_path
        self._collection = None

    def _get_collection(self):
        if self._collection is not None:
            return self._collection
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        self._path.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(
            path=str(self._path), settings=ChromaSettings(anonymized_telemetry=False)
        )
        self._collection = client.get_or_create_collection(_COLLECTION_NAME)
        return self._collection

    def add(self, case_id: str, name: str, summary: str) -> None:
        try:
            collection = self._get_collection()
            document = f"{name}. {summary[:500]}"
            collection.upsert(ids=[case_id], documents=[document], metadatas=[{"name": name}])
        except Exception as exc:  # noqa: BLE001 - best-effort enhancement, never fatal
            logger.warning("SemanticCaseIndex.add failed, continuing without semantic dedup: %s", exc)

    def find_similar(self, name: str, summary: str = "", top_k: int = 3, max_distance: float = 0.6):
        """Returns [(case_id, name, distance), ...] for near-duplicate cases, closest first."""
        try:
            collection = self._get_collection()
            if collection.count() == 0:
                return []
            query_text = f"{name}. {summary[:500]}" if summary else name
            result = collection.query(query_texts=[query_text], n_results=min(top_k, collection.count()))
            matches = []
            ids = result.get("ids", [[]])[0]
            metadatas = result.get("metadatas", [[]])[0]
            distances = result.get("distances", [[]])[0]
            for case_id, metadata, distance in zip(ids, metadatas, distances):
                if distance <= max_distance:
                    matches.append((case_id, metadata.get("name", ""), distance))
            return matches
        except Exception as exc:  # noqa: BLE001
            logger.warning("SemanticCaseIndex.find_similar failed, skipping semantic dedup: %s", exc)
            return []

    def delete(self, case_id: str) -> None:
        try:
            collection = self._get_collection()
            collection.delete(ids=[case_id])
        except Exception as exc:  # noqa: BLE001
            logger.warning("SemanticCaseIndex.delete failed: %s", exc)
