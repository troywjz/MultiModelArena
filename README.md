# MultiModelMultiAgentArena

MultiModelMultiAgentArena 是一个面向 AI 大模型横向评估的本地运行工具。用户通过环境变量配置多个模型供应商、模型名称、请求地址和 API Key，运行一次评测流程后，得到一个 Markdown 结果报告。当前主流程聚焦个人行动领域能力评估，使用结构化任务、扰动脚本和程序化规则评分，避免用模型裁判作为主分基础。

## 项目目标

- 让多个大模型围绕结构化个人行动领域任务进行多阶段回答和扰动测试。
- 输出统一、可比较、可追溯的模型评估结论，主分来自程序化规则而不是模型裁判。
- 用 Markdown 报告展示领域分、Decision Quality 评分框架结果、行为指纹、适合角色、证据摘录和原始记录文件链接。
- 支持用户通过环境变量切换模型供应商和模型列表，不把密钥写入仓库。

## 推荐技术栈

- 后端与评测编排：Python。
- 结果报告：本地 Markdown 文件。
- 数据落盘：SQLite + JSONL 原始记录。
- 验证：pytest、CLI 端到端运行和报告内容检查。
- 配置：`.env` 环境变量，本仓库只提交 `.env.example`。

## 当前阶段

当前仓库已经实现 MVP 的本地最小闭环：

1. 从环境变量或 `.env` 读取模型配置。
2. 用 fake provider 或 OpenAI-compatible provider 运行模型能力评估。
3. 保存 `events.jsonl`、`summary.json` 和 `summary.sqlite3`。
4. 在根目录 `report-output/` 生成本地 Markdown 结果报告。
5. 保留旧版多模型互评命令，同时新增 `assessment-run` 作为当前主流程。

## 快速开始

无需真实 API Key，可以先跑 fake provider：

```powershell
python -m arena assessment-run --provider fake
python -m arena assessment-report --input runs/latest
```

报告会写入根目录 `report-output/`，文件名格式为：

```text
model-arena-YYYYMMDD-HHMMSS-参与模型名称.md
```

例如：

```text
report-output/model-arena-20260511-153000-gpt_gemini_claude_minimax_kimi_glm_qwen_mimo_seed_deepseek.md
```

文件名中的模型名称会归一化到模型家族，不写供应商和版本号。

如果要只检查配置：

```powershell
python -m arena assessment-run --dry-run
```

旧版互评流程仍可运行：

```powershell
python -m arena run --provider fake
```

## 配置真实模型

复制 `.env.example` 为本地 `.env`，填入模型列表和密钥。真实 `.env` 已被 `.gitignore` 忽略。

```text
ARENA_MODELS=deepseek_chat,qwen_max
ARENA_MODEL_DEEPSEEK_CHAT_PROVIDER=openai_compatible
ARENA_MODEL_DEEPSEEK_CHAT_BASE_URL=https://api.example.com/v1
ARENA_MODEL_DEEPSEEK_CHAT_API_KEY=sk-...
ARENA_MODEL_DEEPSEEK_CHAT_MODEL_NAME=deepseek-chat
```

当前真实模型适配器优先支持 OpenAI-compatible Chat Completions 接口。

每个模型可配置：

```text
ARENA_MODEL_<ALIAS>_TEMPERATURE=0.2
ARENA_MODEL_<ALIAS>_MAX_TOKENS=1024
ARENA_MODEL_<ALIAS>_TOP_P=1.0
ARENA_MODEL_<ALIAS>_TIMEOUT_SECONDS=60
ARENA_MODEL_<ALIAS>_RETRY_COUNT=0
```

本地 `.env` 已预留 `minimax_t01`、`minimax_t04`、`minimax_t08`、`kimi`、`qwen`、`glm`、`deepseek`、`mimo`、`seed`。当前 `ARENA_MODELS` 默认只启用 minimax 三档温度，稍后要启用其他模型时，把对应别名追加到 `ARENA_MODELS` 并填入 `BASE_URL`、`API_KEY`、`MODEL_NAME` 即可。`MODEL_NAME` 是供应商实际模型名称；旧字段 `NAME` 仍兼容，但不推荐继续使用。

`minimax_t01`、`minimax_t04`、`minimax_t08` 用于同一个 minimax 模型的 0.1、0.4、0.8 三档温度测试。`MAX_TOKENS=1024` 是当前推荐默认值，目标是让模型生成简短但充分的核心结构化答案。使用 `--provider fake` 时会临时覆盖 provider，不需要真实密钥。

## 模型能力评估主流程

当前主流程遵循 [项目规划](项目规划.md)：

- 4 个一级领域：个人生活、事业与成长、人际与关系、资源与风险。它们是评测领域，不代表当前项目会替用户做真实决策。
- 每个领域 1 道基准题，每题 2 个扰动。
- 模型必须输出结构化 JSON。
- 程序化评分覆盖 JSON 完整性、备选方案数量、坏方案规避、专业边界、扰动响应和行动计划。
- 模型裁判不进入主分，只能作为后续报告摘要或人工复核辅助。
- 测试题在 [src/arena/assessment/tasks.py](src/arena/assessment/tasks.py)，可以直接查看和修改。

## 验证

```powershell
pytest
python -m arena --help
python -m arena assessment-run --dry-run
python -m arena assessment-run --provider fake
python -m arena assessment-report --input runs/latest
```

注意：当前机器上的 `D:\python312\python.exe` 没有安装 pytest，但系统可用 `pytest.exe` 已通过测试。

## 文档地图

- [产品需求](docs/product/requirements.md)
- [架构说明](ARCHITECTURE.md)
- [工作流](WORKFLOW.md)
- [测试策略](docs/quality/test-strategy.md)
- [MVP 计划](docs/plans/mvp-plan.md)
