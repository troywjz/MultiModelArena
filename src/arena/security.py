from __future__ import annotations

import re


SECRET_PATTERNS = [
    re.compile(r"(sk-[A-Za-z0-9_\-]{8,})"),
    re.compile(r"(?i)(api[_-]?key['\"]?\s*[:=]\s*['\"]?)([^'\"\s,]+)"),
    re.compile(r"(?i)(authorization['\"]?\s*[:=]\s*['\"]?Bearer\s+)([^'\"\s,]+)"),
]


def mask_secret(value: str) -> str:
    if not value:
        return value
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def redact_text(text: str, known_secrets: list[str] | None = None) -> str:
    redacted = text
    for secret in known_secrets or []:
        if secret:
            redacted = redacted.replace(secret, mask_secret(secret))
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: f"{match.group(1)}{mask_secret(match.group(2))}" if match.lastindex and match.lastindex >= 2 else mask_secret(match.group(1)), redacted)
    return redacted
