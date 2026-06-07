import httpx
from urllib.parse import urlparse

from app.llm_providers.base import BaseLLMProvider


class OllamaMistralProvider(BaseLLMProvider):
    provider_name = "local_mistral_ollama"

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.default_model = model

    def _candidate_base_urls(self) -> list[str]:
        parsed = urlparse(self.base_url)
        candidates = [self.base_url]
        if parsed.hostname in {"host.docker.internal", "localhost", "127.0.0.1", "::1"}:
            candidates.extend(
                [
                    "http://host.docker.internal:11434",
                    "http://127.0.0.1:11434",
                    "http://localhost:11434",
                    "http://[::1]:11434",
                ]
            )
        return list(dict.fromkeys(candidate.rstrip("/") for candidate in candidates))

    def chat(self, messages: list[dict], temperature: float = 0.2, max_tokens: int = 1200) -> str:
        model_candidates = list(dict.fromkeys([self.default_model, "gemma2:9b", "mistral:7b-instruct", "mistral"]))
        errors: list[str] = []
        for base_url in self._candidate_base_urls():
            for model in model_candidates:
                payload = {
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                }
                try:
                    response = httpx.post(f"{base_url}/api/chat", json=payload, timeout=120)
                    response.raise_for_status()
                    data = response.json()
                    self.default_model = model
                    return data.get("message", {}).get("content", "")
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404:
                        errors.append(f"{base_url} model {model}: {exc.response.text[:160]}")
                        continue
                    errors.append(f"{base_url} model {model}: {exc}")
                    break
                except Exception as exc:
                    errors.append(f"{base_url} model {model}: {exc}")
                    break
        raise RuntimeError("Ollama is not reachable. Tried " + "; ".join(errors))
