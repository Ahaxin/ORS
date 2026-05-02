from crewai import LLM
from backend.providers.base import LLMProvider

class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model

    def get_llm(self) -> LLM:
        return LLM(model=self.model, api_key=self.api_key)
