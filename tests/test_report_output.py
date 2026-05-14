# 检查报告输出路径和文件名规则。
# 输入：运行摘要数据；输出：pytest 断言结果。
from arena.report_output import model_family_slug, model_slug_from_summary


def test_model_family_slug_removes_provider_and_version_detail():
    assert model_family_slug("gpt-4.1-mini") == "gpt"
    assert model_family_slug("gemini-2.5-pro") == "gemini"
    assert model_family_slug("claude-3-5-sonnet") == "claude"
    assert model_family_slug("MiniMax-M1") == "minimax"
    assert model_family_slug("kimi-k2") == "kimi"
    assert model_family_slug("glm-4.5") == "glm"
    assert model_family_slug("qwen-max") == "qwen"
    assert model_family_slug("mimo-vl") == "mimo"
    assert model_family_slug("doubao-seed-1.6") == "seed"
    assert model_family_slug("deepseek-chat") == "deepseek"


def test_model_slug_from_summary_preserves_first_family_order():
    summary = {
        "results": [
            {"model_name": "gpt-4.1-mini"},
            {"model_name": "gemini-2.5-pro"},
            {"model_name": "claude-3-5-sonnet"},
            {"model_name": "qwen-max"},
            {"model_name": "qwen-plus"},
        ]
    }

    assert model_slug_from_summary(summary) == "gpt_gemini_claude_qwen"
