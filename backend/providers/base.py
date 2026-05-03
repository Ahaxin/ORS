from abc import ABC, abstractmethod
from crewai import LLM

DEFAULT_TIMEOUT_MINUTES = 10


class LLMProvider(ABC):
    is_local: bool = False
    concurrency: int = 1
    name: str

    def __init__(self) -> None:
        self.timeout_seconds: int = DEFAULT_TIMEOUT_MINUTES * 60

    @abstractmethod
    def get_llm(self) -> LLM:
        ...
