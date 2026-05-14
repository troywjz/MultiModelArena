# 生成报告输出文件路径。
# 输入：运行摘要；输出：Markdown 文件路径。
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any


REPORT_OUTPUT_DIR = Path("report-output")

KNOWN_MODEL_FAMILIES = [
    ("deepseek", "deepseek"),
    ("claude", "claude"),
    ("gemini", "gemini"),
    ("minimax", "minimax"),
    ("moonshot", "kimi"),
    ("kimi", "kimi"),
    ("glm", "glm"),
    ("qwen", "qwen"),
    ("mimo", "mimo"),
    ("doubao", "seed"),
    ("seed", "seed"),
    ("chatgpt", "gpt"),
    ("gpt", "gpt"),
    ("openai", "gpt"),
]

VERSION_TOKENS = {
    "chat",
    "instruct",
    "latest",
    "max",
    "mini",
    "preview",
    "pro",
    "sonnet",
    "haiku",
    "opus",
    "flash",
    "turbo",
}


def default_report_output_path(summary: dict[str, Any], *, output_dir: Path = REPORT_OUTPUT_DIR) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    model_slug = model_slug_from_summary(summary)
    return output_dir / f"model-arena-{timestamp}-{model_slug}.md"


def model_slug_from_summary(summary: dict[str, Any]) -> str:
    names = [str(result.get("model_name") or result.get("alias") or "model") for result in summary.get("results", [])]
    families: list[str] = []
    for name in names:
        family = model_family_slug(name)
        if family not in families:
            families.append(family)
    return "_".join(families) if families else "models"


def model_family_slug(model_name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", model_name.lower()).strip("_")
    if not normalized:
        return "model"
    tokens = [token for token in normalized.split("_") if token]
    joined = "_".join(tokens)
    for needle, family in KNOWN_MODEL_FAMILIES:
        if needle in tokens or joined.startswith(needle):
            return family
    for token in tokens:
        if token and not token.isdigit() and token not in VERSION_TOKENS and not re.fullmatch(r"v?\d+(\d+)?", token):
            return token
    return tokens[0]
