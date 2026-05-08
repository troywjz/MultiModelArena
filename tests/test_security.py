from arena.security import redact_text


def test_redact_text_masks_known_secret():
    text = "Authorization: Bearer sk-test-secret-value"

    redacted = redact_text(text, ["sk-test-secret-value"])

    assert "sk-test-secret-value" not in redacted
    assert "sk-t...alue" in redacted
