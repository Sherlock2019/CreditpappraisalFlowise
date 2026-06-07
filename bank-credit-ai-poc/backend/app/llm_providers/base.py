from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):
    provider_name: str
    default_model: str

    @abstractmethod
    def chat(self, messages: list[dict], temperature: float = 0.2, max_tokens: int = 1200) -> str:
        raise NotImplementedError
