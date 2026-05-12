import json
import urllib.request

from arena.models import ModelConfig
from arena.providers.openai_compatible import OpenAICompatibleProvider


class FakeHTTPResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_openai_compatible_provider_uses_minimax_completion_token_field(monkeypatch):
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse(
            {
                "choices": [{"message": {"content": "{}"}, "finish_reason": "length"}],
                "usage": {"completion_tokens": 2048},
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = OpenAICompatibleProvider(
        ModelConfig(
            alias="minimax_t01",
            provider="openai_compatible",
            model_name="MiniMax-M2.7",
            base_url="https://api.minimaxi.com/v1",
            api_key="sk-test-secret",
            max_tokens=2048,
        )
    )

    response = provider.complete([{"role": "user", "content": "hi"}])

    assert captured["payload"]["max_completion_tokens"] == 2048
    assert "max_tokens" not in captured["payload"]
    assert response.usage["finish_reason"] == "length"


def test_openai_compatible_provider_keeps_generic_max_tokens(monkeypatch):
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse({"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = OpenAICompatibleProvider(
        ModelConfig(
            alias="deepseek",
            provider="openai_compatible",
            model_name="deepseek-chat",
            base_url="https://api.example.test/v1",
            api_key="sk-test-secret",
            max_tokens=1024,
        )
    )

    provider.complete([{"role": "user", "content": "hi"}])

    assert captured["payload"]["max_tokens"] == 1024
    assert "max_completion_tokens" not in captured["payload"]


def test_openai_compatible_provider_can_disable_proxy(monkeypatch):
    captured: dict[str, object] = {}

    class FakeOpener:
        def open(self, request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeHTTPResponse({"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]})

    def fake_build_opener(*handlers):
        captured["handlers"] = handlers
        return FakeOpener()

    def fake_urlopen(request, timeout):
        raise AssertionError("urlopen should not be used when disable_proxy=True")

    monkeypatch.setattr("urllib.request.build_opener", fake_build_opener)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = OpenAICompatibleProvider(
        ModelConfig(
            alias="minimax_t01",
            provider="openai_compatible",
            model_name="MiniMax-M2.7",
            base_url="https://api.minimaxi.com/v1",
            api_key="sk-test-secret",
            disable_proxy=True,
        )
    )

    provider.complete([{"role": "user", "content": "hi"}])

    assert captured["payload"]["model"] == "MiniMax-M2.7"
    assert captured["timeout"] == 60.0
    assert any(isinstance(handler, urllib.request.ProxyHandler) for handler in captured["handlers"])


def test_openai_compatible_provider_omits_token_limit_when_unset(monkeypatch):
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse({"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = OpenAICompatibleProvider(
        ModelConfig(
            alias="deepseek",
            provider="openai_compatible",
            model_name="deepseek-chat",
            base_url="https://api.example.test/v1",
            api_key="sk-test-secret",
            max_tokens=None,
        )
    )

    provider.complete([{"role": "user", "content": "hi"}])

    assert "max_tokens" not in captured["payload"]
    assert "max_completion_tokens" not in captured["payload"]
