"""
Local vector database (ChromaDB, persisted to disk under data/vector_store).

Kept behind a thin wrapper so swapping to FAISS later only requires
reimplementing this module's three functions.
"""
from __future__ import annotations

from functools import lru_cache

from app.config.settings import get_settings
from app.rag.embeddings import embed_texts, embed_query

settings = get_settings()

_COLLECTION_NAME = "jarvis_knowledge"


@lru_cache
def _client():
    import chromadb
    return chromadb.PersistentClient(path=str(settings.vector_store_dir))


@lru_cache
def _collection():
    return _client().get_or_create_collection(name=_COLLECTION_NAME)


def add_chunks(ids: list[str], texts: list[str], metadatas: list[dict]) -> None:
    if not ids:
        return
    embeddings = embed_texts(texts)
    _collection().upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)


def delete_by_file_id(file_id: str) -> None:
    _collection().delete(where={"file_id": file_id})


def semantic_search(query: str, top_k: int = 5, file_id: str | None = None) -> list[dict]:
    query_embedding = embed_query(query)
    where = {"file_id": file_id} if file_id else None
    results = _collection().query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where,
    )
    hits = []
    if not results.get("ids"):
        return hits
    for i in range(len(results["ids"][0])):
        hits.append({
            "id": results["ids"][0][i],
            "text": results["documents"][0][i],
            "metadata": results["metadatas"][0][i],
            "distance": results["distances"][0][i] if results.get("distances") else None,
        })
    return hits
