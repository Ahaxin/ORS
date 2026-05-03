from crewai import LLM
from backend.providers.base import LLMProvider

class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6", concurrency: int = 1):
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.concurrency = concurrency

    def get_llm(self) -> LLM:
        return LLM(model=f"anthropic/{self.model}", api_key=self.api_key)
