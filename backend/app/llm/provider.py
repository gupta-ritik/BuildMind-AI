"""
LLM provider abstraction.

CodePilot must not be locked to a single LLM vendor. Any provider that
exposes an OpenAI-compatible chat-completions API (OpenAI, Groq, Together,
Anyscale, local vLLM, etc.) can be plugged in purely through environment
variables — no code changes required.
"""
from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.config import Settings, get_settings

# Known base URLs for OpenAI-compatible providers. Anything not listed here
# falls back to `llm_base_url` from settings, or plain OpenAI if unset.
_PROVIDER_BASE_URLS: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "anyscale": "https://api.endpoints.anyscale.com/v1",
    "openai": "https://api.openai.com/v1",
}


def get_chat_model(settings: Settings | None = None, temperature: float = 0.1) -> ChatOpenAI:
    """
    Build a LangChain chat model for whatever provider is configured.

    Raises a clear error if no API key is available rather than silently
    failing at call time.
    """
    settings = settings or get_settings()

    api_key = settings.resolved_llm_api_key()
    if not api_key:
        raise RuntimeError(
            f"No API key configured for LLM_PROVIDER={settings.llm_provider!r}. "
            "Set the matching *_API_KEY environment variable."
        )

    base_url = settings.llm_base_url or _PROVIDER_BASE_URLS.get(settings.llm_provider)

    return ChatOpenAI(
        model=settings.llm_model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        timeout=120,
        max_retries=2,
    )
