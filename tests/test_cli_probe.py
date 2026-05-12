from arena.cli import _call_error_hint, _truncation_diagnostics, main
from arena.models import ModelConfig


def test_probe_model_prints_raw_response_and_json_check(capsys):
    exit_code = main(["probe-model", "--no-dotenv", "--provider", "fake"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "模型探针测试，目标模型数：2" in output
    assert "模式：正式评测 JSON 协议" in output
    assert "原始响应" not in output
    assert "响应原文：已隐藏" in output
    assert "正式评测 JSON 识别" in output
    assert "结果：成功" in output
    assert "字段完整性：完整" in output


def test_probe_model_custom_prompt_is_connectivity_mode(capsys):
    exit_code = main(["probe-model", "--no-dotenv", "--provider", "fake", "--alias", "fake_architect", "--prompt", "你是什么模型"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "模型探针测试，目标模型数：1" in output
    assert "模式：自定义连通性提示词" in output
    assert "结果：失败" in output
    assert "如需测试评测协议，请不要传 --prompt" in output


def test_probe_model_can_show_raw_response(capsys):
    exit_code = main(["probe-model", "--no-dotenv", "--provider", "fake", "--alias", "fake_architect", "--show-response"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "原始响应" in output


def test_truncation_diagnostics_reports_length_finish_reason():
    model = ModelConfig(alias="minimax_t01", provider="fake", model_name="fake", max_tokens=1024)

    messages = _truncation_diagnostics(model, {"completion_tokens": 1024, "finish_reason": "length"})

    assert any("输出被截断" in message for message in messages)
    assert any("ARENA_MODEL_MINIMAX_T01_MAX_TOKENS" in message for message in messages)
    assert any("输出上限说明" in message for message in messages)


def test_truncation_diagnostics_reports_anthropic_max_tokens_stop_reason():
    model = ModelConfig(alias="minimax_t01", provider="fake", model_name="fake", max_tokens=1024)

    messages = _truncation_diagnostics(model, {"output_tokens": 1024, "finish_reason": "max_tokens"})

    assert any("输出被截断" in message for message in messages)
    assert any("finish_reason=max_tokens" in message for message in messages)


def test_call_error_hint_reports_timeout_setting():
    model = ModelConfig(alias="minimax_t01", provider="fake", model_name="fake")

    hint = _call_error_hint(model, TimeoutError("The read operation timed out"))

    assert "ARENA_MODEL_MINIMAX_T01_TIMEOUT_SECONDS" in hint
    assert "180" in hint
