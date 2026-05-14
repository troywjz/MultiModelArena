# 调用 Anthropic 兼容消息接口。
# 输入：消息列表和模型配置；输出：标准化模型响应。
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from arena.models import ProviderResponse
from arena.security import redact_text

from .base import Provider


class AnthropicCompatibleProvider(Provider):
    def complete(self, messages: list[dict[str, str]]) -> ProviderResponse:
        url = f"{self.config.base_url}/messages"
        system_parts = [message["content"] for message in messages if message["role"] == "system"]
        conversation = [message for message in messages if message["role"] != "system"]
        payload = {
            "model": self.config.model_name,
            "messages": conversation,
            "temperature": self.config.temperature,
        }
        if self.config.top_p is not None:
            payload["top_p"] = self.config.top_p
        if self.config.max_tokens is not None:
            payload["max_tokens"] = self.config.max_tokens
        if system_parts:
            payload["system"] = "\n".join(system_parts)
        body = json.dumps(payload).encode("utf-8")
        data = self._post(url, body)
        text = self._text_content(data)
        usage = dict(data.get("usage", {}))
        content = data.get("content", [])
        if isinstance(content, list):
            block_types = [item.get("type", "") for item in content if isinstance(item, dict)]
            usage["content_block_types"] = ",".join(item for item in block_types if item) or "none"
            usage["text_block_count"] = sum(1 for item in content if isinstance(item, dict) and item.get("type") == "text")
        stop_reason = data.get("stop_reason")
        if stop_reason:
            usage["finish_reason"] = stop_reason
        return ProviderResponse(text=text, usage=usage, raw=data)

    def _text_content(self, data: dict) -> str:
        content = data.get("content", [])
        if not isinstance(content, list):
            raise RuntimeError("模型响应 content 不是列表")
        texts = [item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text"]
        return "\n".join(text for text in texts if text)

    def _post(self, url: str, body: bytes) -> dict:
        attempts = self.config.retry_count + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            request = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key": self.config.api_key,
                },
                method="POST",
            )
            try:
                with self._open(request) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                last_error = exc
                error_body = exc.read().decode("utf-8", errors="replace")
                safe_error = redact_text(error_body, [self.config.api_key])
                if exc.code < 500 and exc.code != 429:
                    raise RuntimeError(f"模型调用失败 HTTP {exc.code}: {safe_error}") from exc
                if attempt == attempts - 1:
                    raise RuntimeError(f"模型调用失败 HTTP {exc.code}: {safe_error}") from exc
            except urllib.error.URLError as exc:
                last_error = exc
                if attempt == attempts - 1:
                    raise RuntimeError(f"模型调用失败: {redact_text(str(exc), [self.config.api_key])}") from exc
            time.sleep(min(2**attempt, 8))
        raise RuntimeError(f"模型调用失败: {last_error}")

    def _open(self, request: urllib.request.Request):
        if self.config.disable_proxy:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            return opener.open(request, timeout=self.config.timeout_seconds)
        return urllib.request.urlopen(request, timeout=self.config.timeout_seconds)
