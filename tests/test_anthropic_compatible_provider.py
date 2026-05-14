# 检查 Anthropic 兼容模型调用适配器。
# 输入：模拟 HTTP 响应和模型配置；输出：pytest 断言结果。
import json

from arena.models import ModelConfig
from arena.providers.anthropic_compatible import AnthropicCompatibleProvider


class FakeHTTPResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_anthropic_compatible_provider_uses_messages_endpoint_and_text_block(monkeypatch):
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["api_key"] = request.headers["X-api-key"]
        return FakeHTTPResponse(
            {
                "content": [
                    {"type": "thinking", "thinking": "hidden"},
                    {"type": "text", "text": '{"recommended_option":"A"}'},
                ],
                "usage": {"input_tokens": 10, "output_tokens": 20},
                "stop_reason": "end_turn",
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = AnthropicCompatibleProvider(
        ModelConfig(
            alias="minimax_t01",
            provider="anthropic_compatible",
            model_name="MiniMax-M2.7",
            base_url="https://api.minimaxi.com/anthropic/v1",
            api_key="sk-test-secret",
            max_tokens=1024,
        )
    )

    response = provider.complete(
        [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "user prompt"},
        ]
    )

    assert captured["url"] == "https://api.minimaxi.com/anthropic/v1/messages"
    assert captured["payload"]["system"] == "system prompt"
    assert captured["payload"]["messages"] == [{"role": "user", "content": "user prompt"}]
    assert captured["payload"]["max_tokens"] == 1024
    assert captured["api_key"] == "sk-test-secret"
    assert response.text == '{"recommended_option":"A"}'
    assert response.usage["finish_reason"] == "end_turn"
    assert response.usage["content_block_types"] == "thinking,text"
    assert response.usage["text_block_count"] == 1


def test_anthropic_compatible_provider_allows_missing_text_block(monkeypatch):
    def fake_urlopen(request, timeout):
        return FakeHTTPResponse(
            {
                "content": [{"type": "thinking", "thinking": "only thinking"}],
                "usage": {"input_tokens": 10, "output_tokens": 1024},
                "stop_reason": "max_tokens",
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = AnthropicCompatibleProvider(
        ModelConfig(
            alias="minimax_t01",
            provider="anthropic_compatible",
            model_name="MiniMax-M2.7",
            base_url="https://api.minimaxi.com/anthropic/v1",
            api_key="sk-test-secret",
            max_tokens=1024,
        )
    )

    response = provider.complete([{"role": "user", "content": "user prompt"}])

    assert response.text == ""
    assert response.usage["finish_reason"] == "max_tokens"
    assert response.usage["content_block_types"] == "thinking"
    assert response.usage["text_block_count"] == 0


def test_anthropic_compatible_provider_omits_max_tokens_when_unset(monkeypatch):
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse(
            {
                "content": [{"type": "text", "text": '{"recommended_option":"A"}'}],
                "usage": {"input_tokens": 10, "output_tokens": 20},
                "stop_reason": "end_turn",
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = AnthropicCompatibleProvider(
        ModelConfig(
            alias="minimax_t01",
            provider="anthropic_compatible",
            model_name="MiniMax-M2.7",
            base_url="https://api.minimaxi.com/anthropic/v1",
            api_key="sk-test-secret",
            max_tokens=None,
        )
    )

    provider.complete([{"role": "user", "content": "user prompt"}])

    assert "max_tokens" not in captured["payload"]


def test_anthropic_compatible_provider_omits_top_p_when_unset(monkeypatch):
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeHTTPResponse(
            {
                "content": [{"type": "text", "text": '{"recommended_option":"A"}'}],
                "usage": {"input_tokens": 10, "output_tokens": 20},
                "stop_reason": "end_turn",
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    provider = AnthropicCompatibleProvider(
        ModelConfig(
            alias="minimax_t01",
            provider="anthropic_compatible",
            model_name="MiniMax-M2.7",
            base_url="https://api.minimaxi.com/anthropic/v1",
            api_key="sk-test-secret",
            top_p=None,
        )
    )

    provider.complete([{"role": "user", "content": "user prompt"}])

    assert "top_p" not in captured["payload"]
