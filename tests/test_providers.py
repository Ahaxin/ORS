from backend.providers.lmstudio_provider import LMStudioProvider
from backend.providers.openai_provider import OpenAIProvider
from backend.providers.anthropic_provider import AnthropicProvider
from backend.providers.gemini_provider import GeminiProvider
from backend.providers.router import ProviderRouter

_cfg = {
    "default_model": "lmstudio",
    "retry_policy": "auto",
    "providers": {
        "lmstudio": {"base_url": "http://localhost:1234/v1", "default_model": "qwen2.5-coder"},
        "openai": {"api_key": "sk-test", "default_model": "gpt-4o-mini"},
        "anthropic": {"api_key": "sk-test", "default_model": "claude-sonnet-4-6"},
        "gemini": {"api_key": "sk-test", "default_model": "gemini-2.0-flash"},
    }
}


def test_lmstudio_provider_name():
    p = LMStudioProvider(base_url="http://localhost:1234/v1", model="qwen2.5-coder")
    assert p.name == "lmstudio"


def test_lmstudio_is_local():
    p = LMStudioProvider(base_url="http://localhost:1234/v1", model="qwen2.5-coder")
    assert p.is_local is True


def test_cloud_providers_not_local():
    for Provider, kwargs in [
        (OpenAIProvider, {"api_key": "sk-test", "model": "gpt-4o-mini"}),
        (AnthropicProvider, {"api_key": "sk-test", "model": "claude-sonnet-4-6"}),
        (GeminiProvider, {"api_key": "sk-test", "model": "gemini-2.0-flash"}),
    ]:
        p = Provider(**kwargs)
        assert p.is_local is False


def test_cloud_provider_names():
    assert OpenAIProvider(api_key="sk-test").name == "openai"
    assert AnthropicProvider(api_key="sk-test").name == "anthropic"
    assert GeminiProvider(api_key="sk-test").name == "gemini"


def test_router_returns_correct_provider():
    router = ProviderRouter(_cfg)
    assert router.get_provider("lmstudio").name == "lmstudio"
    assert router.get_provider("openai").name == "openai"


def test_router_applies_pending_at_boundary():
    router = ProviderRouter(_cfg)
    router.set_pending_model("openai")
    router.apply_pending()
    assert router.active_model == "openai"
    assert router.pending_model is None


def test_auto_retry_local_model():
    router = ProviderRouter({**_cfg, "retry_policy": "auto"})
    assert router.should_auto_retry() is True


def test_hybrid_retry_local_is_auto():
    router = ProviderRouter({**_cfg, "retry_policy": "hybrid"})
    assert router.should_auto_retry() is True  # lmstudio is local


def test_hybrid_retry_cloud_is_pause():
    cfg = {**_cfg, "default_model": "openai", "retry_policy": "hybrid"}
    router = ProviderRouter(cfg)
    assert router.should_auto_retry() is False  # openai is not local


def test_provider_default_concurrency():
    p = LMStudioProvider(base_url="http://localhost:1234/v1", model="qwen")
    assert p.concurrency == 1


def test_provider_custom_concurrency():
    p = OpenAIProvider(api_key="sk-test", model="gpt-4o-mini", concurrency=4)
    assert p.concurrency == 4


def test_router_passes_concurrency():
    cfg = {
        **_cfg,
        "providers": {
            **_cfg["providers"],
            "openai": {"api_key": "sk-test", "default_model": "gpt-4o-mini", "concurrency": 4},
        }
    }
    router = ProviderRouter(cfg)
    assert router.get_provider("openai").concurrency == 4


def test_router_default_concurrency_when_absent():
    router = ProviderRouter(_cfg)  # _cfg has no concurrency keys
    assert router.get_provider("lmstudio").concurrency == 1
