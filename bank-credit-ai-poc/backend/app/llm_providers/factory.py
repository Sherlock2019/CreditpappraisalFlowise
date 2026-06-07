from fastapi import HTTPException

from app.config import get_settings
from app.llm_providers.base import BaseLLMProvider
from app.llm_providers.custom_public_provider import CustomPublicAPIProvider
from app.llm_providers.deepseek_provider import DeepSeekProvider
from app.llm_providers.ollama_provider import OllamaMistralProvider
from app.llm_providers.openai_provider import OpenAIProvider


PROVIDER_LABELS = {
    "openai": "openai",
    "open ai": "openai",
    "OpenAI": "openai",
    "deepseek": "deepseek",
    "DeepSeek": "deepseek",
    "custom public api": "custom_public_api",
    "Custom Public API": "custom_public_api",
    "custom_public_api": "custom_public_api",
    "local mistral via ollama": "local_mistral_ollama",
    "Local Mistral via Ollama": "local_mistral_ollama",
    "local_mistral_ollama": "local_mistral_ollama",
    "ollama": "local_mistral_ollama",
    "Ollama": "local_mistral_ollama",
}


def normalize_provider(provider_name: str | None) -> str:
    settings = get_settings()
    raw = provider_name or settings.llm_provider
    return PROVIDER_LABELS.get(raw, PROVIDER_LABELS.get(raw.strip().lower(), raw.strip().lower()))


def get_default_model(provider_name: str | None) -> str:
    settings = get_settings()
    provider = normalize_provider(provider_name)
    if provider == "deepseek":
        return settings.deepseek_model
    if provider == "custom_public_api":
        return settings.custom_public_api_model or ""
    if provider == "local_mistral_ollama":
        return settings.ollama_model
    return settings.openai_model


def resolve_runtime_model(provider_name: str | None, requested_model: str | None = None) -> str:
    provider = normalize_provider(provider_name)
    if requested_model and provider in {"local_mistral_ollama", "custom_public_api"}:
        return requested_model.strip()
    return get_default_model(provider)


def provider_options() -> list[dict[str, str]]:
    settings = get_settings()
    return [
        {"label": "OpenAI", "value": "openai", "default_model": settings.openai_model},
        {"label": "DeepSeek", "value": "deepseek", "default_model": settings.deepseek_model},
        {"label": "Custom Public API", "value": "custom_public_api", "default_model": settings.custom_public_api_model or ""},
        {"label": "Local Mistral via Ollama", "value": "local_mistral_ollama", "default_model": settings.ollama_model},
    ]


def get_llm_provider(
    provider_name: str | None,
    custom_public_api_base_url: str | None = None,
    custom_public_api_key: str | None = None,
    custom_public_api_model: str | None = None,
    llm_model: str | None = None,
) -> BaseLLMProvider:
    settings = get_settings()
    provider = normalize_provider(provider_name)

    if provider == "openai":
        return OpenAIProvider(settings.openai_api_key, settings.openai_model)
    if provider == "deepseek":
        return DeepSeekProvider(settings.deepseek_api_key, settings.deepseek_model, settings.deepseek_base_url)
    if provider == "local_mistral_ollama":
        return OllamaMistralProvider(settings.ollama_base_url, llm_model or settings.ollama_model)
    if provider == "custom_public_api":
        base_url = custom_public_api_base_url or settings.custom_public_api_base_url
        api_key = custom_public_api_key or settings.custom_public_api_key
        model = custom_public_api_model or settings.custom_public_api_model
        if not base_url or not api_key or not model:
            raise HTTPException(status_code=400, detail="Custom Public API requires base URL, API key, and model.")
        return CustomPublicAPIProvider(base_url, api_key, model)

    raise HTTPException(status_code=400, detail=f"Unsupported LLM provider: {provider_name}")
