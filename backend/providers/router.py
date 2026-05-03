import yaml
from backend.providers.base import LLMProvider
from backend.providers.openai_provider import OpenAIProvider
from backend.providers.anthropic_provider import AnthropicProvider
from backend.providers.gemini_provider import GeminiProvider
from backend.providers.lmstudio_provider import LMStudioProvider


class ProviderRouter:
    def __init__(self, config: dict):
        self.config = config
        self.active_model: str = config["default_model"]
        self.pending_model: str | None = None
        self.retry_policy: str = config.get("retry_policy", "auto")

    def get_provider(self, name: str | None = None) -> LLMProvider:
        name = name or self.active_model
        cfg = self.config["providers"][name]
        concurrency = cfg.get("concurrency", 1)
        match name:
            case "openai":    return OpenAIProvider(api_key=cfg["api_key"], model=cfg["default_model"], concurrency=concurrency)
            case "anthropic": return AnthropicProvider(api_key=cfg["api_key"], model=cfg["default_model"], concurrency=concurrency)
            case "gemini":    return GeminiProvider(api_key=cfg["api_key"], model=cfg["default_model"], concurrency=concurrency)
            case "lmstudio":  return LMStudioProvider(base_url=cfg["base_url"], model=cfg["default_model"], concurrency=concurrency)
            case _: raise ValueError(f"Unknown provider: {name}")

    def set_pending_model(self, model: str):
        self.pending_model = model

    def apply_pending(self):
        if self.pending_model:
            self.active_model = self.pending_model
            self.pending_model = None

    def should_auto_retry(self) -> bool:
        if self.retry_policy == "auto":
            return True
        if self.retry_policy == "pause":
            return False
        return self.get_provider().is_local  # hybrid: auto for local, pause for cloud

    @classmethod
    def from_config_file(cls, path: str = "config.yaml") -> "ProviderRouter":
        with open(path) as f:
            return cls(yaml.safe_load(f))
