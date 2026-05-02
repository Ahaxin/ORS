from backend.providers.lmstudio_provider import LMStudioProvider


def test_lmstudio_provider_name():
    p = LMStudioProvider(base_url="http://localhost:1234/v1", model="qwen2.5-coder")
    assert p.name == "lmstudio"


def test_lmstudio_is_local():
    p = LMStudioProvider(base_url="http://localhost:1234/v1", model="qwen2.5-coder")
    assert p.is_local is True
