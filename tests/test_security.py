# 检查安全脱敏规则是否生效。
# 输入：带密钥的文本或报告；输出：pytest 断言结果。
from arena.security import redact_text


def test_redact_text_masks_known_secret():
    text = "Authorization: Bearer sk-test-secret-value"

    redacted = redact_text(text, ["sk-test-secret-value"])

    assert "sk-test-secret-value" not in redacted
    assert "sk-t...alue" in redacted
