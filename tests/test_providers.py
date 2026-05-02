from backend.providers.lmstudio_provider import LMStudioProvider
from backend.providers.openai_provider import OpenAIProvider
from backend.providers.anthropic_provider import AnthropicProvider
from backend.providers.gemini_provider import GeminiProvider


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
