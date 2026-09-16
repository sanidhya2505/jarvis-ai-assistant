"""
LLM client abstraction.

`llm_provider` in settings selects the backend:
  - "openai": any OpenAI-compatible chat completions endpoint (OpenAI itself,
    or a local server like Ollama/LM Studio exposing the same API shape —
    just point llm_base_url at it).
  - "anthropic": Anthropic's Messages API.
  - "local": no network call at all; returns a clearly-labeled fallback so
    file search / tasks / calendar still work without any AI configured.

This keeps app/ai and app/rag decoupled from any single vendor's SDK.
"""
from __future__ import annotations

from app.config.settings import get_settings
from app.core.logging_config import get_logger

logger = get_logger("jarvis.ai")
settings = get_settings()


class LLMUnavailableError(Exception):
    pass


def chat(system_prompt: str, user_prompt: str, max_tokens: int = 800) -> str:
    """Single-turn convenience wrapper. Raises LLMUnavailableError on failure."""
    if settings.llm_provider == "local" or not settings.llm_api_key:
        raise LLMUnavailableError(
            "No LLM provider configured. Set LLM_API_KEY and LLM_PROVIDER in .env "
            "to enable AI-generated answers; task/calendar/file-search commands "
            "still work without it."
        )

    try:
        if settings.llm_provider == "anthropic":
            return _chat_anthropic(system_prompt, user_prompt, max_tokens)
        return _chat_openai_compatible(system_prompt, user_prompt, max_tokens)
    except LLMUnavailableError:
        raise
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        raise LLMUnavailableError(f"AI request failed: {exc}") from exc


def _chat_openai_compatible(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    response = client.chat.completions.create(
        model=settings.llm_model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content or ""


def _chat_anthropic(system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=settings.llm_api_key)
    response = client.messages.create(
        model=settings.llm_model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(block.text for block in response.content if hasattr(block, "text"))
