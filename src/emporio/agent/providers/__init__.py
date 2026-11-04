from emporio.agent.providers.base import LLMProvider, ProviderError
from emporio.agent.providers.rate_limit import RateLimitedProvider
from emporio.settings import Settings


def create_provider(settings: Settings) -> LLMProvider:
    provider = _create_base_provider(settings)
    if settings.min_interval_seconds > 0:
        return RateLimitedProvider(provider, settings.min_interval_seconds)
    return provider


def _create_base_provider(settings: Settings) -> LLMProvider:
    if settings.provider == "gemini":
        from emporio.agent.providers.gemini import GeminiProvider

        return GeminiProvider(api_key=settings.api_key, model=settings.model)
    if settings.provider == "openai":
        from emporio.agent.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(api_key=settings.api_key, model=settings.model)
    raise ProviderError(f"Unsupported provider: {settings.provider}")


__all__ = ["LLMProvider", "ProviderError", "create_provider"]
