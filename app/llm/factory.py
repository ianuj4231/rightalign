"""Construct the configured LLM provider."""

import logging

from app.config import ApplicationSettings, get_llm_api_key, load_settings
from app.exceptions import UnsupportedLLMProviderError
from app.llm.base import LLMClient

logger = logging.getLogger(__name__)


def create_llm(settings: ApplicationSettings | None = None) -> LLMClient:
    application_settings = settings or load_settings()
    provider = application_settings.llm.provider
    api_key = get_llm_api_key(application_settings)
    logger.info("Creating configured LLM client: provider=%s", provider)

    if provider == "openrouter":
        from app.llm.openrouter import OpenRouterLLMClient

        return OpenRouterLLMClient(
            api_key=api_key,
            model=application_settings.llm.openrouter.model,
        )
    if provider == "gemini":
        from app.llm.gemini import GeminiLLMClient

        return GeminiLLMClient(
            api_key=api_key,
            model=application_settings.llm.gemini.model,
        )
    raise UnsupportedLLMProviderError(f"Unsupported LLM provider: {provider}")
