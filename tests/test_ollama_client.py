import json
from urllib.error import HTTPError, URLError

import pytest

from app.planner.ollama_client import (
    OllamaClient,
    OllamaConnectionError,
    OllamaModelError,
    OllamaResponseError,
)


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.body


def test_generate_returns_model_response(monkeypatch):
    def fake_urlopen(request, timeout):
        assert request.full_url == "http://localhost:11434/api/generate"
        assert json.loads(request.data) == {
            "model": "qwen2.5:3b",
            "prompt": "Plan this task",
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }
        assert timeout == 30
        return FakeResponse(b'{"response":"{\\"task_id\\": \\"task_001\\"}"}')

    monkeypatch.setattr("app.planner.ollama_client.urlopen", fake_urlopen)

    assert OllamaClient().generate("Plan this task") == '{"task_id": "task_001"}'


def test_generate_reports_connection_failure(monkeypatch):
    monkeypatch.setattr(
        "app.planner.ollama_client.urlopen",
        lambda request, timeout: (_ for _ in ()).throw(URLError("offline")),
    )

    with pytest.raises(OllamaConnectionError, match="Could not connect"):
        OllamaClient().generate("Plan this task")


def test_generate_rejects_empty_response(monkeypatch):
    monkeypatch.setattr(
        "app.planner.ollama_client.urlopen",
        lambda request, timeout: FakeResponse(b'{"response":"  "}'),
    )

    with pytest.raises(OllamaResponseError, match="empty model response"):
        OllamaClient().generate("Plan this task")


def test_generate_rejects_non_object_response(monkeypatch):
    monkeypatch.setattr(
        "app.planner.ollama_client.urlopen",
        lambda request, timeout: FakeResponse(b"[]"),
    )

    with pytest.raises(OllamaResponseError, match="non-object response"):
        OllamaClient().generate("Plan this task")


def test_generate_reports_missing_model(monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 404, "not found", {}, None)

    monkeypatch.setattr("app.planner.ollama_client.urlopen", fake_urlopen)

    with pytest.raises(OllamaModelError, match="ollama pull qwen2.5:3b"):
        OllamaClient().generate("Plan this task")
