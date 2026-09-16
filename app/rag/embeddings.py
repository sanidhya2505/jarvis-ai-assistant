"""
Embedding generation, provider-agnostic.

- If an LLM API key is configured and the provider is OpenAI-compatible,
  uses that provider's embeddings endpoint.
- Otherwise falls back to a local sentence-transformers model, so semantic
  search keeps working fully offline (spec section 21: Offline Mode).
"""
from __future__ import annotations

from functools import lru_cache

from app.config.settings import get_settings
from app.core.logging_config import get_logger

logger = get_logger("jarvis.ai")
settings = get_settings()


@lru_cache
def _local_model():
    from sentence_transformers import SentenceTransformer
    # Small, fast, good-enough general-purpose embedding model that runs on CPU.
    return SentenceTransformer("all-MiniLM-L6-v2")


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    if settings.llm_api_key and settings.llm_provider in ("openai",):
        try:
            return _embed_via_openai_compatible(texts)
        except Exception as exc:
            logger.warning("Remote embeddings failed (%s) — falling back to local model", exc)

    return _local_model().encode(texts, normalize_embeddings=True).tolist()


def _embed_via_openai_compatible(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI
    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    response = client.embeddings.create(model=settings.embedding_model, input=texts)
    return [item.embedding for item in response.data]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]
