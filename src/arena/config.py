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


def load_config(*, use_dotenv: bool = True, dry_run: bool = False) -> ArenaConfig:
    if use_dotenv:
        load_dotenv()

    aliases = _split_models(os.environ.get("ARENA_MODELS", ""))
    if not aliases:
        aliases = ["fake_architect", "fake_reviewer"]

    models: list[ModelConfig] = []
    for alias in aliases:
        provider = os.environ.get(_env_key(alias, "PROVIDER"), "fake").strip()
        model_name = os.environ.get(_env_key(alias, "NAME"), alias).strip()
        base_url = os.environ.get(_env_key(alias, "BASE_URL"), "").strip().rstrip("/")
        api_key = os.environ.get(_env_key(alias, "API_KEY"), "").strip()
        role_hint = os.environ.get(_env_key(alias, "ROLE_HINT"), "").strip()
        timeout_raw = os.environ.get(_env_key(alias, "TIMEOUT_SECONDS"), "60")
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise ConfigError(f"{_env_key(alias, 'TIMEOUT_SECONDS')} 必须是数字") from exc

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
                timeout_seconds=timeout_seconds,
            )
        )

    output_root = Path(os.environ.get("ARENA_OUTPUT_DIR", "runs"))
    return ArenaConfig(models=models, output_root=output_root, dry_run=dry_run)
