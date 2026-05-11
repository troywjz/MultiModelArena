from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .models import ModelConfig


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ArenaConfig:
    models: list[ModelConfig]
    output_root: Path = Path("runs")
    dry_run: bool = False


def _env_key(alias: str, field: str) -> str:
    normalized = alias.upper().replace("-", "_")
    return f"ARENA_MODEL_{normalized}_{field}"


def _split_models(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_float_env(alias: str, field: str, default: float) -> float:
    raw = os.environ.get(_env_key(alias, field), str(default)).strip()
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{_env_key(alias, field)} 必须是数字") from exc


def _parse_int_env(alias: str, field: str, default: int | None) -> int | None:
    raw = os.environ.get(_env_key(alias, field), "" if default is None else str(default)).strip()
    if raw == "":
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{_env_key(alias, field)} 必须是整数") from exc


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def load_config(*, use_dotenv: bool = True, dry_run: bool = False, provider_override: str | None = None) -> ArenaConfig:
    if use_dotenv:
        load_dotenv()

    aliases = _split_models(os.environ.get("ARENA_MODELS", ""))
    if not aliases:
        aliases = ["fake_architect", "fake_reviewer"]

    models: list[ModelConfig] = []
    for alias in aliases:
        provider = provider_override or os.environ.get(_env_key(alias, "PROVIDER"), "fake").strip()
        model_name = (
            os.environ.get(_env_key(alias, "MODEL_NAME"), "")
            or os.environ.get(_env_key(alias, "NAME"), "")
            or alias
        ).strip()
        base_url = os.environ.get(_env_key(alias, "BASE_URL"), "").strip().rstrip("/")
        api_key = os.environ.get(_env_key(alias, "API_KEY"), "").strip()
        role_hint = os.environ.get(_env_key(alias, "ROLE_HINT"), "").strip()
        temperature = _parse_float_env(alias, "TEMPERATURE", 0.2)
        max_tokens = _parse_int_env(alias, "MAX_TOKENS", 1024)
        top_p = _parse_float_env(alias, "TOP_P", 1.0)
        timeout_seconds = _parse_float_env(alias, "TIMEOUT_SECONDS", 60)
        retry_count = _parse_int_env(alias, "RETRY_COUNT", 0)
        if retry_count is None:
            retry_count = 0

        if provider == "openai_compatible":
            if not base_url:
                raise ConfigError(f"{alias} 缺少 {_env_key(alias, 'BASE_URL')}")
            if not api_key:
                raise ConfigError(f"{alias} 缺少 {_env_key(alias, 'API_KEY')}")

        models.append(
            ModelConfig(
                alias=alias,
                provider=provider,
                model_name=model_name,
                base_url=base_url,
                api_key=api_key,
                role_hint=role_hint,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                timeout_seconds=timeout_seconds,
                retry_count=retry_count,
            )
        )

    output_root = Path(os.environ.get("ARENA_OUTPUT_DIR", "runs"))
    return ArenaConfig(models=models, output_root=output_root, dry_run=dry_run)
