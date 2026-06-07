from openai import OpenAI

from app.llm_providers.base import BaseLLMProvider


class DeepSeekProvider(BaseLLMProvider):
    provider_name = "deepseek"

    def __init__(self, api_key: str, model: str, base_url: str):
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is required when LLM_PROVIDER=deepseek")
        self.default_model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def chat(self, messages: list[dict], temperature: float = 0.2, max_tokens: int = 1200) -> str:
        response = self.client.chat.completions.create(
            model=self.default_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""
