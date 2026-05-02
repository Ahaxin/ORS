from crewai import LLM
from backend.providers.base import LLMProvider

class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self.api_key = api_key
        self.model = model

    def get_llm(self) -> LLM:
        return LLM(model=f"anthropic/{self.model}", api_key=self.api_key)
