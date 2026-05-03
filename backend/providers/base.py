from abc import ABC, abstractmethod
from crewai import LLM


class LLMProvider(ABC):
    is_local: bool = False
    concurrency: int = 1
    timeout_seconds: int = 600
    name: str

    @abstractmethod
    def get_llm(self) -> LLM:
        ...
