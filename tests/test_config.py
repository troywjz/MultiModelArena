from arena.config import load_config


def test_load_config_defaults_to_fake_models(monkeypatch):
    monkeypatch.delenv("ARENA_MODELS", raising=False)

    config = load_config(use_dotenv=False)

    assert [model.alias for model in config.models] == ["fake_architect", "fake_reviewer"]
    assert all(model.provider == "fake" for model in config.models)


def test_load_config_reads_model_environment(monkeypatch):
    monkeypatch.setenv("ARENA_MODELS", "deepseek_chat")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_PROVIDER", "openai_compatible")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_BASE_URL", "https://api.example.test/v1")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_API_KEY", "sk-test-secret")
    monkeypatch.setenv("ARENA_MODEL_DEEPSEEK_CHAT_NAME", "deepseek-chat")

    config = load_config(use_dotenv=False)

    assert len(config.models) == 1
    assert config.models[0].provider == "openai_compatible"
    assert config.models[0].model_name == "deepseek-chat"
