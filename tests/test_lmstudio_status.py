from unittest import mock
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

_fake_config = {
    "default_model": "lmstudio",
    "retry_policy": "auto",
    "providers": {
        "lmstudio": {
            "base_url": "http://localhost:1234/v1",
            "default_model": "qwen2.5-coder",
            "concurrency": 4,
        },
        "openai": {"api_key": "", "default_model": "gpt-4o-mini", "concurrency": 4},
        "anthropic": {"api_key": "", "default_model": "claude-sonnet-4-6", "concurrency": 4},
        "gemini": {"api_key": "", "default_model": "gemini-2.0-flash", "concurrency": 2},
    },
}


def _mock_router():
    from backend.providers.router import ProviderRouter
    return ProviderRouter(_fake_config)


def test_lmstudio_status_ready():
    mock_response = mock.MagicMock()
    mock_response.json.return_value = {"object": "list", "data": [{"id": "qwen2.5-coder"}]}
    mock_response.raise_for_status = mock.MagicMock()

    with mock.patch("backend.api.settings.ProviderRouter.from_config_file", return_value=_mock_router()), \
         mock.patch("httpx.get", return_value=mock_response):
        res = client.get("/providers/lmstudio/status")

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert data["model"] == "qwen2.5-coder"


def test_lmstudio_status_unavailable_empty_list():
    mock_response = mock.MagicMock()
    mock_response.json.return_value = {"object": "list", "data": []}
    mock_response.raise_for_status = mock.MagicMock()

    with mock.patch("backend.api.settings.ProviderRouter.from_config_file", return_value=_mock_router()), \
         mock.patch("httpx.get", return_value=mock_response):
        res = client.get("/providers/lmstudio/status")

    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "unavailable"
    assert data["model"] is None


def test_lmstudio_status_unavailable_on_connection_error():
    with mock.patch("backend.api.settings.ProviderRouter.from_config_file", return_value=_mock_router()), \
         mock.patch("httpx.get", side_effect=Exception("connection refused")):
        res = client.get("/providers/lmstudio/status")

    assert res.status_code == 200
    assert res.json()["status"] == "unavailable"
