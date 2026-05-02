from abc import ABC, abstractmethod

from crewai import LLM


class LLMProvider(ABC):
    is_local: bool = False

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def get_llm(self) -> LLM:
        ...
