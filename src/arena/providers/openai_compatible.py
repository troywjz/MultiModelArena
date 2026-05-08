from __future__ import annotations

import json
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
            "temperature": 0.2,
        }
        body = json.dumps(payload).encode("utf-8")
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
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            safe_error = redact_text(error_body, [self.config.api_key])
            raise RuntimeError(f"模型调用失败 HTTP {exc.code}: {safe_error}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"模型调用失败: {redact_text(str(exc), [self.config.api_key])}") from exc

        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("模型响应缺少 choices[0].message.content") from exc
        return ProviderResponse(text=text, usage=data.get("usage", {}), raw=data)
