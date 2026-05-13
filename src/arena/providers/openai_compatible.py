from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from arena.models import ProviderResponse
from arena.security import redact_text

from .base import Provider


class OpenAICompatibleProvider(Provider):
    def complete(self, messages: list[dict[str, str]]) -> ProviderResponse:
        url = f"{self.config.base_url}/chat/completions"
        payload = {
            "model": self.config.model_name,
            "messages": messages,
            "temperature": self.config.temperature,
        }
        if self.config.top_p is not None:
            payload["top_p"] = self.config.top_p
        if self.config.max_tokens is not None:
            payload[self._token_limit_field()] = self.config.max_tokens
        body = json.dumps(payload).encode("utf-8")
        data = self._post(url, body)

        try:
            choice = data["choices"][0]
            text = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("模型响应缺少 choices[0].message.content") from exc
        usage = dict(data.get("usage", {}))
        finish_reason = choice.get("finish_reason")
        if finish_reason:
            usage["finish_reason"] = finish_reason
        return ProviderResponse(text=text, usage=usage, raw=data)

    def _token_limit_field(self) -> str:
        configured = self.config.token_limit_field
        if configured != "auto":
            return configured
        provider_marker = f"{self.config.base_url} {self.config.model_name}".lower()
        if "minimaxi" in provider_marker or "minimax" in provider_marker:
            return "max_completion_tokens"
        return "max_tokens"

    def _post(self, url: str, body: bytes) -> dict:
        attempts = self.config.retry_count + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            request = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.config.api_key}",
                },
                method="POST",
            )
            try:
                with self._open(request) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code < 500 and exc.code != 429:
                    error_body = exc.read().decode("utf-8", errors="replace")
                    safe_error = redact_text(error_body, [self.config.api_key])
                    raise RuntimeError(f"模型调用失败 HTTP {exc.code}: {safe_error}") from exc
                if attempt == attempts - 1:
                    error_body = exc.read().decode("utf-8", errors="replace")
                    safe_error = redact_text(error_body, [self.config.api_key])
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
