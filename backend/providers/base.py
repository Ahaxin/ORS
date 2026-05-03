from abc import ABC, abstractmethod
from crewai import LLM


class LLMProvider(ABC):
    is_local: bool = False
    concurrency: int = 1
    name: str

    def __init__(self) -> None:
        self.timeout_seconds: int = 600

    @abstractmethod
    def get_llm(self) -> LLM:
        ...
