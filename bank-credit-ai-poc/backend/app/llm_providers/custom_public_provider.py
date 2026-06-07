from openai import APIConnectionError, AuthenticationError, NotFoundError, OpenAI

from app.config import get_settings
from app.llm_providers.base import BaseLLMProvider


class CustomPublicAPIProvider(BaseLLMProvider):
    provider_name = "custom_public_api"

    def __init__(self, base_url: str, api_key: str, model: str):
        if not base_url:
            raise ValueError("Custom Public API base URL is required.")
        if not api_key:
            raise ValueError("Custom Public API key is required.")
        if not model:
            raise ValueError("Custom Public API model is required.")

        settings = get_settings()
        if base_url.startswith("http://") and not settings.dev_allow_insecure_custom_api:
            raise ValueError("Custom Public API base URL must use https:// for public mode.")
        if not base_url.startswith(("https://", "http://")):
            raise ValueError("Custom Public API base URL must start with https://.")

        self.default_model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url.rstrip("/"))

    def chat(self, messages: list[dict], temperature: float = 0.2, max_tokens: int = 1200) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.default_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content or ""
        except AuthenticationError as exc:
            raise RuntimeError("Custom Public API authentication failed. Check API key.") from exc
        except NotFoundError as exc:
            raise RuntimeError("Custom Public API model not found. Check model name.") from exc
        except APIConnectionError as exc:
            raise RuntimeError("Custom Public API endpoint failed. Check base URL.") from exc
