from abc import ABC, abstractmethod


class LLMProvider(ABC):
    name: str
    is_local: bool = False

    @abstractmethod
    def get_llm(self):
        """Return a CrewAI-compatible LLM instance."""
        ...
