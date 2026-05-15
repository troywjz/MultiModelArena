# 检查环境变量配置解析。
# 输入：测试环境变量；输出：pytest 断言结果。
from arena.config import load_config


def test_load_config_defaults_to_fake_models(monkeypatch):
    monkeypatch.delenv("ARENA_MODELS", raising=False)
    monkeypatch.delenv("ARENA_EMBEDDING_ENABLED", raising=False)

    config = load_config(use_dotenv=False)

    assert [model.alias for model in config.models] == ["fake_architect", "fake_reviewer"]
    assert all(model.provider == "fake" for model in config.models)
    assert all(model.max_tokens is None for model in config.models)
    assert config.embedding is None


def test_load_config_reads_model_environment(monkeypatch):
    monkeypatch.setenv("ARENA_MODELS", "deepseek_chat")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_PROVIDER", "openai_compatible")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_BASE_URL", "https://api.example.test/v1")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_API_KEY", "sk-test-secret")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_MODEL_NAME", "deepseek-chat")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_TEMPERATURE", "0.3")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_MAX_TOKENS", "2048")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_TOKEN_LIMIT_FIELD", "max_completion_tokens")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_TOP_P", "0.9")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_RETRY_COUNT", "2")
    monkeypatch.setenv("ARENA_DISABLE_PROXY", "true")

    config = load_config(use_dotenv=False)

    assert len(config.models) == 1
    assert config.models[0].provider == "openai_compatible"
    assert config.models[0].model_name == "deepseek-chat"
    assert config.models[0].temperature == 0.3
    assert config.models[0].max_tokens == 2048
    assert config.models[0].token_limit_field == "max_completion_tokens"
    assert config.models[0].top_p == 0.9
    assert config.models[0].timeout_seconds == 120
    assert config.models[0].retry_count == 2
    assert config.models[0].disable_proxy is True


def test_load_config_treats_blank_max_tokens_as_unset(monkeypatch):
    monkeypatch.setenv("ARENA_MODELS", "deepseek_chat")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_PROVIDER", "openai_compatible")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_BASE_URL", "https://api.example.test/v1")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_API_KEY", "sk-test-secret")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_MAX_TOKENS", "")

    config = load_config(use_dotenv=False)

    assert config.models[0].max_tokens is None


def test_load_config_treats_none_max_tokens_as_unset(monkeypatch):
    monkeypatch.setenv("ARENA_MODELS", "deepseek_chat")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_PROVIDER", "openai_compatible")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_BASE_URL", "https://api.example.test/v1")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_API_KEY", "sk-test-secret")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_MAX_TOKENS", "None")

    config = load_config(use_dotenv=False)

    assert config.models[0].max_tokens is None


def test_load_config_treats_none_top_p_as_unset(monkeypatch):
    monkeypatch.setenv("ARENA_MODELS", "deepseek_chat")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_PROVIDER", "openai_compatible")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_BASE_URL", "https://api.example.test/v1")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_API_KEY", "sk-test-secret")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_TOP_P", "None")

    config = load_config(use_dotenv=False)

    assert config.models[0].top_p is None


def test_load_config_defaults_top_p_to_unset(monkeypatch):
    monkeypatch.setenv("ARENA_MODELS", "deepseek_chat")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_PROVIDER", "openai_compatible")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_BASE_URL", "https://api.example.test/v1")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_API_KEY", "sk-test-secret")
    monkeypatch.delenv("ARENA_MODEL_DEEPSEEK_CHAT_TOP_P", raising=False)

    config = load_config(use_dotenv=False)

    assert config.models[0].top_p is None


def test_load_config_model_disable_proxy_overrides_global(monkeypatch):
    monkeypatch.setenv("ARENA_MODELS", "deepseek_chat")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_PROVIDER", "openai_compatible")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_BASE_URL", "https://api.example.test/v1")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_API_KEY", "sk-test-secret")
    monkeypatch.setenv("ARENA_DISABLE_PROXY", "true")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_DISABLE_PROXY", "false")

    config = load_config(use_dotenv=False)

    assert config.models[0].disable_proxy is False


def test_load_config_provider_override_skips_openai_required_fields(monkeypatch):
    monkeypatch.setenv("ARENA_MODELS", "deepseek")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_PROVIDER", "openai_compatible")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_NAME", "deepseek-chat")

    config = load_config(use_dotenv=False, provider_override="fake")

    assert config.models[0].provider == "fake"
    assert config.models[0].model_name == "deepseek-chat"


def test_load_config_keeps_legacy_name_field(monkeypatch):
    monkeypatch.setenv("ARENA_MODELS", "legacy")
    monkeypatch.setenv("ARENA_MODEL_LEGACY_PROVIDER", "fake")
    monkeypatch.setenv("ARENA_MODEL_LEGACY_NAME", "legacy-model")

    config = load_config(use_dotenv=False)

    assert config.models[0].model_name == "legacy-model"


def test_load_config_reads_embedding_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("ARENA_MODELS", "fake")
    monkeypatch.setenv("ARENA_MODEL_FAKE_PROVIDER", "fake")
    monkeypatch.setenv("ARENA_EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("ARENA_EMBEDDING_API_KEY", "sk-embedding")
    monkeypatch.setenv("ARENA_EMBEDDING_CACHE_PATH", str(tmp_path / "cache.sqlite3"))

    config = load_config(use_dotenv=False)

    assert config.embedding is not None
    assert config.embedding.provider == "openai_compatible"
    assert config.embedding.base_url == "https://api.siliconflow.cn/v1"
    assert config.embedding.model_name == "netease-youdao/bce-embedding-base_v1"
    assert config.embedding.dimensions is None
    assert config.embedding.encoding_format == "float"
    assert config.embedding.batch_size == 16
    assert config.embedding.timeout_seconds == 120
    assert config.embedding.retry_count == 1
    assert config.embedding.cache_path == tmp_path / "cache.sqlite3"
    assert config.embedding.similarity_floor == 0.55
    assert config.embedding.similarity_ceiling == 0.85
    assert config.embedding.role_weight == 0.35


def test_load_config_uses_durable_embedding_cache_path_by_default(monkeypatch):
    monkeypatch.setenv("ARENA_MODELS", "fake")
    monkeypatch.setenv("ARENA_MODEL_FAKE_PROVIDER", "fake")
    monkeypatch.setenv("ARENA_EMBEDDING_ENABLED", "true")
    monkeypatch.setenv("ARENA_EMBEDDING_API_KEY", "sk-embedding")
    monkeypatch.delenv("ARENA_EMBEDDING_CACHE_PATH", raising=False)

    config = load_config(use_dotenv=False)

    assert config.embedding is not None
    assert config.embedding.cache_path.as_posix() == ".arena-cache/embedding-cache.sqlite3"


def test_load_config_fake_embedding_uses_separate_cache_path_by_default(monkeypatch):
    monkeypatch.setenv("ARENA_MODELS", "fake")
    monkeypatch.setenv("ARENA_MODEL_FAKE_PROVIDER", "fake")
    monkeypatch.delenv("ARENA_EMBEDDING_CACHE_PATH", raising=False)

    config = load_config(use_dotenv=False, embedding_provider_override="fake")

    assert config.embedding is not None
    assert config.embedding.cache_path.as_posix() == ".arena-cache/fake-embedding-cache.sqlite3"


def test_load_config_embedding_provider_override_enables_fake_embedding(monkeypatch, tmp_path):
    monkeypatch.setenv("ARENA_MODELS", "deepseek")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_PROVIDER", "openai_compatible")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_NAME", "deepseek-chat")
    monkeypatch.setenv("ARENA_EMBEDDING_CACHE_PATH", str(tmp_path / "fake-cache.sqlite3"))

    config = load_config(use_dotenv=False, provider_override="fake", embedding_provider_override="fake")

    assert config.embedding is not None
    assert config.embedding.provider == "fake"
    assert config.embedding.base_url == "fake://embedding"
    assert config.embedding.api_key == ""
    assert config.embedding.model_name == "fake-embedding"
    assert config.embedding.dimensions == 16
    assert config.embedding.cache_path == tmp_path / "fake-cache.sqlite3"
