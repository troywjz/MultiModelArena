# 解析环境变量和本地配置。
# 输入：.env 和环境变量；输出：ArenaConfig 配置对象。
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .models import EmbeddingConfig, ModelConfig


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ArenaConfig:
    models: list[ModelConfig]
    output_root: Path = Path("runs")
    embedding: EmbeddingConfig | None = None
    dry_run: bool = False


def _default_embedding_cache_path(provider: str) -> Path:
    filename = "fake-embedding-cache.sqlite3" if provider == "fake" else "embedding-cache.sqlite3"
    return Path(".arena-cache") / filename


def _env_key(alias: str, field: str) -> str:
    normalized = alias.upper().replace("-", "_")
    return f"ARENA_MODEL_{normalized}_{field}"


def _embedding_env_key(field: str) -> str:
    return f"ARENA_EMBEDDING_{field}"


def _split_models(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_float_env(alias: str, field: str, default: float) -> float:
    raw = os.environ.get(_env_key(alias, field), str(default)).strip()
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{_env_key(alias, field)} 必须是数字") from exc


def _parse_global_float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, str(default)).strip()
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} 必须是数字") from exc


def _parse_optional_float_env(alias: str, field: str, default: float | None) -> float | None:
    raw = os.environ.get(_env_key(alias, field), "" if default is None else str(default)).strip()
    if raw.lower() in {"", "none", "null"}:
        return None
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{_env_key(alias, field)} 必须是数字、None 或留空") from exc


def _parse_int_env(alias: str, field: str, default: int | None) -> int | None:
    raw = os.environ.get(_env_key(alias, field), "" if default is None else str(default)).strip()
    if raw.lower() in {"", "none", "null"}:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{_env_key(alias, field)} 必须是整数") from exc


def _parse_global_int_env(name: str, default: int | None) -> int | None:
    raw = os.environ.get(name, "" if default is None else str(default)).strip()
    if raw.lower() in {"", "none", "null"}:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} 必须是整数") from exc


def _parse_token_limit_field(alias: str) -> str:
    value = os.environ.get(_env_key(alias, "TOKEN_LIMIT_FIELD"), "auto").strip() or "auto"
    allowed = {"auto", "max_tokens", "max_completion_tokens"}
    if value not in allowed:
        raise ConfigError(f"{_env_key(alias, 'TOKEN_LIMIT_FIELD')} 必须是 auto、max_tokens 或 max_completion_tokens")
    return value


def _parse_bool_value(name: str, value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off", ""}:
        return False
    raise ConfigError(f"{name} 必须是 true/false、1/0、yes/no 或 on/off")


def _parse_bool_env(alias: str, field: str, default: bool, *, global_field: str | None = None) -> bool:
    env_name = _env_key(alias, field)
    if env_name in os.environ:
        return _parse_bool_value(env_name, os.environ[env_name])
    if global_field and global_field in os.environ:
        return _parse_bool_value(global_field, os.environ[global_field])
    return default


def _parse_global_bool_env(name: str, default: bool) -> bool:
    if name not in os.environ:
        return default
    return _parse_bool_value(name, os.environ[name])


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


def load_config(
    *,
    use_dotenv: bool = True,
    dry_run: bool = False,
    provider_override: str | None = None,
    embedding_provider_override: str | None = None,
) -> ArenaConfig:
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
        max_tokens = _parse_int_env(alias, "MAX_TOKENS", None)
        token_limit_field = _parse_token_limit_field(alias)
        top_p = _parse_optional_float_env(alias, "TOP_P", None)
        timeout_seconds = _parse_float_env(alias, "TIMEOUT_SECONDS", 60)
        retry_count = _parse_int_env(alias, "RETRY_COUNT", 0)
        disable_proxy = _parse_bool_env(alias, "DISABLE_PROXY", False, global_field="ARENA_DISABLE_PROXY")
        if retry_count is None:
            retry_count = 0

        if provider in {"openai_compatible", "anthropic_compatible"}:
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
                token_limit_field=token_limit_field,
                top_p=top_p,
                timeout_seconds=timeout_seconds,
                retry_count=retry_count,
                disable_proxy=disable_proxy,
            )
        )

    output_root = Path(os.environ.get("ARENA_OUTPUT_DIR", "runs"))
    embedding = _load_embedding_config(output_root, provider_override=embedding_provider_override)
    return ArenaConfig(models=models, output_root=output_root, embedding=embedding, dry_run=dry_run)


def _load_embedding_config(output_root: Path, *, provider_override: str | None = None) -> EmbeddingConfig | None:
    enabled = _parse_global_bool_env(_embedding_env_key("ENABLED"), False) or provider_override is not None
    if not enabled:
        return None

    provider = provider_override or os.environ.get(_embedding_env_key("PROVIDER"), "openai_compatible").strip() or "openai_compatible"
    if provider not in {"openai_compatible", "fake"}:
        raise ConfigError("ARENA_EMBEDDING_PROVIDER 当前只支持 openai_compatible 或 fake")
    default_base_url = "fake://embedding" if provider == "fake" else "https://api.siliconflow.cn/v1"
    default_model = "fake-embedding" if provider == "fake" else "netease-youdao/bce-embedding-base_v1"
    base_url = os.environ.get(_embedding_env_key("BASE_URL"), default_base_url).strip().rstrip("/")
    api_key = os.environ.get(_embedding_env_key("API_KEY"), "").strip()
    model_name = os.environ.get(_embedding_env_key("MODEL"), default_model).strip()
    dimensions = _parse_global_int_env(_embedding_env_key("DIMENSIONS"), None)
    encoding_format = os.environ.get(_embedding_env_key("ENCODING_FORMAT"), "float").strip() or "float"
    batch_size = _parse_global_int_env(_embedding_env_key("BATCH_SIZE"), 16) or 16
    timeout_seconds = _parse_global_float_env(_embedding_env_key("TIMEOUT_SECONDS"), 120)
    retry_count = _parse_global_int_env(_embedding_env_key("RETRY_COUNT"), 1) or 0
    disable_proxy = _parse_global_bool_env(_embedding_env_key("DISABLE_PROXY"), False)
    cache_path = Path(os.environ.get(_embedding_env_key("CACHE_PATH"), str(_default_embedding_cache_path(provider))))
    similarity_floor = _parse_global_float_env(_embedding_env_key("SIMILARITY_FLOOR"), 0.55)
    similarity_ceiling = _parse_global_float_env(_embedding_env_key("SIMILARITY_CEILING"), 0.85)
    role_weight = _parse_global_float_env(_embedding_env_key("ROLE_WEIGHT"), 0.35)

    if provider == "fake":
        api_key = ""
        if dimensions is None:
            dimensions = 16

    if not base_url:
        raise ConfigError("ARENA_EMBEDDING_BASE_URL 不能为空")
    if provider != "fake" and not api_key:
        raise ConfigError("ARENA_EMBEDDING_API_KEY 不能为空；不使用语义评分时请保持 ARENA_EMBEDDING_ENABLED=false")
    if not model_name:
        raise ConfigError("ARENA_EMBEDDING_MODEL 不能为空")
    if dimensions is not None and dimensions <= 0:
        raise ConfigError("ARENA_EMBEDDING_DIMENSIONS 必须为正整数、None 或留空")
    if batch_size <= 0:
        raise ConfigError("ARENA_EMBEDDING_BATCH_SIZE 必须为正整数")
    if similarity_ceiling <= similarity_floor:
        raise ConfigError("ARENA_EMBEDDING_SIMILARITY_CEILING 必须大于 ARENA_EMBEDDING_SIMILARITY_FLOOR")
    if not 0 <= role_weight <= 1:
        raise ConfigError("ARENA_EMBEDDING_ROLE_WEIGHT 必须在 0 到 1 之间")

    return EmbeddingConfig(
        provider=provider,
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        dimensions=dimensions,
        encoding_format=encoding_format,
        batch_size=batch_size,
        timeout_seconds=timeout_seconds,
        retry_count=retry_count,
        disable_proxy=disable_proxy,
        cache_path=cache_path,
        similarity_floor=similarity_floor,
        similarity_ceiling=similarity_ceiling,
        role_weight=role_weight,
    )
