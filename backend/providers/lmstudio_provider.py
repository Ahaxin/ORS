from crewai import LLM
from backend.providers.base import LLMProvider


class LMStudioProvider(LLMProvider):
    name = "lmstudio"
    is_local = True

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url
        self.model = model

    def get_llm(self):
        return LLM(model=f"openai/{self.model}", base_url=self.base_url, api_key="lm-studio")
