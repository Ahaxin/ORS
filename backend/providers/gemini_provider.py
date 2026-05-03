from crewai import LLM
from backend.providers.base import LLMProvider

class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash", concurrency: int = 1):
        self.api_key = api_key
        self.model = model
        self.concurrency = concurrency

    def get_llm(self) -> LLM:
        return LLM(model=f"gemini/{self.model}", api_key=self.api_key)
