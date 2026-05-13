# MultiModelArena

MultiModelArena 是一个面向 AI 大模型横向评估的本地运行工具。用户通过环境变量配置多个模型供应商、模型名称、请求地址和 API Key，运行一次评测流程后，得到一个 Markdown 结果报告。当前主流程聚焦个人行动领域能力评估，使用结构化任务、扰动脚本和程序化规则评分，避免把模型裁判分数作为核心评分依据。

## 项目目标

- 让多个大模型围绕结构化个人行动领域任务进行多阶段回答和扰动测试。
- 输出统一、可比较、可追溯的模型评估结论，总评分来自程序化规则而不是模型裁判。
- 用 Markdown 报告展示领域分、Decision Quality 概念参考下的过程质量分、响应拆解评估、行为指纹、适合角色、证据摘录和原始记录文件链接。
- 支持用户通过环境变量切换模型供应商和模型列表，不把密钥写入仓库。

## 技术栈

- 后端与评测编排：Python。
- 结果报告：本地 Markdown 文件。
- 数据落盘：SQLite + JSONL 原始记录。
- 验证：pytest、CLI 端到端运行和报告内容检查。
- 配置：`.env` 环境变量，本仓库只提交 `.env.example`。

## 当前阶段

当前仓库已经实现 MVP 的本地最小闭环：

1. 从环境变量或 `.env` 读取模型配置。
2. 用 fake provider、OpenAI-compatible provider 或 Anthropic-compatible provider 运行模型能力评估。
3. 保存 `events.jsonl`、`summary.json` 和 `summary.sqlite3`。
4. 在根目录 `report-output/` 生成本地 Markdown 结果报告。
5. 保留旧版多模型互评命令，同时新增 `assessment-run` 作为当前主流程。

## 快速开始

主流程使用本地 `.env`：先复制 `.env.example` 为 `.env`，在 `ARENA_MODELS` 中写入要评测的 alias，并为这些 alias 配好 `PROVIDER`、`BASE_URL`、`API_KEY`、`MODEL_NAME`。配置完成后，运行 `python -m arena assessment-run` 执行正式评测，再运行 `python -m arena assessment-report --input runs/latest` 生成或重建报告。

无需真实 API Key 时，可以先跑 fake provider 验证流程：

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

如果要对当前 `.env` 启用的所有模型各调用一次，检查连通性和正式评测 JSON 协议：

```powershell
python -m arena probe-model
```

该命令会读取与正式程序相同的 `.env` / 环境变量配置，对每个模型只请求一次，并发送正式评测使用的最小 JSON 协议探针。控制台默认不打印模型原始响应，只展示 alias、provider、模型名、调用成功或失败，以及失败错误。

如果只想测试某一个模型：

```powershell
python -m arena probe-model --alias minimax_t01
```

如果只想做自然语言连通性测试，可以临时指定提示词；这种模式通常不会返回正式 JSON，因此不适合作为评测协议测试：

```powershell
python -m arena probe-model --alias minimax_t01 --prompt "你是什么模型"
```

如果确实需要排查模型原始输出，可以显式打开：

```powershell
python -m arena probe-model --alias minimax_t01 --show-response
```

旧版互评流程仍可运行：

```powershell
python -m arena run --provider fake
```

CLI 命令速查：

- 正式评测主流程：`python -m arena assessment-run`
- 从最近一次运行生成报告：`python -m arena assessment-report --input runs/latest`
- 配置检查：`python -m arena assessment-run --dry-run`
- 离线 fake 评测：`python -m arena assessment-run --provider fake`
- 探针测试所有已启用模型：`python -m arena probe-model`
- 探针测试单个模型：`python -m arena probe-model --alias minimax_t01`
- 自然语言连通性测试：`python -m arena probe-model --alias minimax_t01 --prompt "你是什么模型"`
- 排查时显示原始响应：`python -m arena probe-model --alias minimax_t01 --show-response`
- 旧版互评流程：`python -m arena run --provider fake`

## 配置真实模型

复制 `.env.example` 为本地 `.env`，填入模型列表和密钥。真实 `.env` 已被 `.gitignore` 忽略。

```text
ARENA_MODELS=deepseek_chat,qwen_max
ARENA_MODEL_DEEPSEEK_CHAT_PROVIDER=openai_compatible
ARENA_MODEL_DEEPSEEK_CHAT_BASE_URL=https://api.example.com/v1
ARENA_MODEL_DEEPSEEK_CHAT_API_KEY=sk-...
ARENA_MODEL_DEEPSEEK_CHAT_MODEL_NAME=deepseek-chat
```

当前真实模型适配器支持 OpenAI-compatible Chat Completions 接口，也支持 Anthropic-compatible Messages 接口。MiniMax-M2.7 推荐使用 `anthropic_compatible`，程序会只取响应中的 `text` 内容块进入评分，避免把 `thinking` 内容块当作正式答案。

支持的 provider：

- `fake`：离线测试用，不访问外部模型。
- `openai_compatible`：OpenAI Chat Completions 兼容接口，适用于支持 `/chat/completions` 的服务。
- `anthropic_compatible`：Anthropic Messages 兼容接口，适用于支持 `/messages` 的服务。程序只取响应里的 `text` 内容块进入评分。

每个模型可配置：

```text
ARENA_MODELS=alias_a,alias_b
ARENA_OUTPUT_DIR=runs
ARENA_DISABLE_PROXY=true
ARENA_MODEL_<ALIAS>_PROVIDER=openai_compatible
ARENA_MODEL_<ALIAS>_BASE_URL=https://api.example.com/v1
ARENA_MODEL_<ALIAS>_API_KEY=sk-...
ARENA_MODEL_<ALIAS>_MODEL_NAME=model-name
ARENA_MODEL_<ALIAS>_ROLE_HINT=
ARENA_MODEL_<ALIAS>_TEMPERATURE=0.2
ARENA_MODEL_<ALIAS>_MAX_TOKENS=None
ARENA_MODEL_<ALIAS>_TOKEN_LIMIT_FIELD=auto
ARENA_MODEL_<ALIAS>_TOP_P=None
ARENA_MODEL_<ALIAS>_TIMEOUT_SECONDS=60
ARENA_MODEL_<ALIAS>_RETRY_COUNT=0
ARENA_MODEL_<ALIAS>_DISABLE_PROXY=false
```

`.env.example` 提供多个供应商配置示例。程序只会遍历 `ARENA_MODELS` 中列出的 alias；其他已经写在 `.env` 里的模型配置不会被调用。要启用某个模型，把它的 alias 追加到 `ARENA_MODELS`，并填入 `BASE_URL`、`API_KEY`、`MODEL_NAME` 即可。`MODEL_NAME` 是供应商实际模型名称；旧字段 `NAME` 仍兼容，但不推荐继续使用。

`TOKEN_LIMIT_FIELD` 用来适配不同 OpenAI-compatible 接口的输出上限字段，允许值为 `auto`、`max_tokens`、`max_completion_tokens`。`auto` 会对 MiniMax 模型或 MiniMax API 地址使用 `max_completion_tokens`，其他 OpenAI-compatible 模型默认使用 `max_tokens`。

`ARENA_DISABLE_PROXY=true` 会让 OpenAI-compatible 请求绕过环境变量和 Windows 系统代理，适合排查本机代理导致的连接中断。也可以对单个模型设置 `ARENA_MODEL_<ALIAS>_DISABLE_PROXY=true` 覆盖全局配置。

Kimi 使用 OpenAI-compatible 接口，当前模板配置为 `BASE_URL=https://api.moonshot.cn/v1`、`MODEL_NAME=kimi-k2.6`。Kimi K2.6 这类模型只接受固定温度，当前本地配置使用 `TEMPERATURE=1.0`。`TOP_P=None` 表示请求体里不传 `top_p`，由供应商使用默认值。当前 `.env.example` 已同步这些非敏感项，`ARENA_MODEL_KIMI_API_KEY` 留空。

火山方舟豆包 Seed 使用 OpenAI-compatible 接口，当前模板配置为 `BASE_URL=https://ark.cn-beijing.volces.com/api/v3`、`MODEL_NAME=doubao-seed-2-0-lite-260428`。当前 `.env.example` 已同步这些非敏感项，`ARENA_MODEL_SEED_API_KEY` 留空；只有把 `seed` 追加到 `ARENA_MODELS` 后才会实际调用。

阿里云百炼千问 Qwen 使用 OpenAI-compatible 接口，当前模板配置为 `BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`、`MODEL_NAME=qwen3.6-flash`、`TOKEN_LIMIT_FIELD=max_tokens`。当前 `.env.example` 已同步这些非敏感项，`ARENA_MODEL_QWEN_API_KEY` 留空；要启用时把 `qwen` 追加到 `ARENA_MODELS`。

硅基流动使用 OpenAI-compatible 接口，配置为 `BASE_URL=https://api.siliconflow.cn/v1`。模板里 `glm` 当前使用 `MODEL_NAME=Pro/zai-org/GLM-5.1`，`deepseek` 当前使用 `MODEL_NAME=deepseek-ai/DeepSeek-V4-Flash`，二者都使用 `TOKEN_LIMIT_FIELD=max_tokens`。如果后续从硅基流动模型列表选择了其他具体版本，只需要修改对应 `MODEL_NAME`；由于 `glm` 和 `deepseek` 共用同一个 `BASE_URL`，正式评测调度器会让它们在同一入口内串行排队，避免并发打到同一个聚合网关。

小米 MiMo 使用 OpenAI-compatible 接口，配置为 `BASE_URL=https://api.xiaomimimo.com/v1`、默认 `MODEL_NAME=mimo-v2.5-pro`。MiMo 的 OpenAI 兼容示例使用 `max_completion_tokens`，因此模板设置 `TOKEN_LIMIT_FIELD=max_completion_tokens`。

`MAX_TOKENS=None` 表示不限制模型输出 token。程序会把它解析为 Python 的 `None`，请求体里不会传输出上限字段，而不是传一个 JSON `null`。`TOP_P=None` 同理表示不传 `top_p`，使用模型服务默认值。空值也兼容同样语义；如果填写整数或小数，程序会按 provider 映射为对应参数。`minimax_t01`、`minimax_t04`、`minimax_t08` 用于同一个 minimax 模型的 0.1、0.4、0.8 三档温度测试，并默认使用 `anthropic_compatible`。使用 `--provider fake` 时会临时覆盖 provider，不需要真实密钥。

## 模型能力评估主流程

当前主流程是 `python -m arena assessment-run`，生成报告使用 `python -m arena assessment-report --input runs/latest`。旧版 `python -m arena run` 仍保留，但不是当前主要评测路径。

当前流程：

1. 读取 `ARENA_MODELS` 中列出的模型配置。
2. 对每个模型独立运行内置任务：4 个领域，每个领域 1 道基准题，每题 2 个扰动，因此每个模型默认 12 次正式评测请求。
3. 模型请求按 `BASE_URL` 分组调度。不同请求入口会并发运行；同一请求入口内部串行排队，适合多个模型共用同一个聚合网关地址的情况。
4. 要求模型输出结构化 JSON，协议在 [src/arena/assessment/protocol.py](src/arena/assessment/protocol.py)。
5. 测试题在 [src/arena/assessment/tasks.py](src/arena/assessment/tasks.py)，可以直接查看和修改。
6. 程序化评分覆盖 JSON 完整性、备选方案数量、坏方案规避、专业边界、扰动响应和行动计划，逻辑在 [src/arena/assessment/scoring.py](src/arena/assessment/scoring.py)。
7. 在不增加模型调用次数的前提下，程序会对每条响应做拆解评估，识别约束锚定、价值拆解、权衡推理、信息追问、风险与可逆性、行动可执行性、变化适配、校准边界和方法多样性，逻辑在 [src/arena/assessment/diagnostics.py](src/arena/assessment/diagnostics.py)。
8. 报告会展示模型使用过的分析角度，例如阶段门/试点验证、权衡矩阵/优先级、约束检查、风险复盘、相关方对齐、信息缺口管理、用户价值识别和执行计划，渲染逻辑在 [src/arena/assessment/report.py](src/arena/assessment/report.py)。
9. 保存 `events.jsonl`、`summary.json` 和 `summary.sqlite3`，存储逻辑在 [src/arena/assessment/store.py](src/arena/assessment/store.py)。
10. 在根目录 `report-output/` 生成 Markdown 报告。

当前 `assessment-run` 不调用模型裁判，也没有单独配置 judge model。总评分只来自本地程序化规则和响应拆解。旧版 `arena run` 会让模型互评彼此回答，但它不是当前主流程，结果也不进入 `assessment-run` 的总评分。

## 评测体系参考

当前没有导入外部题库、源码或数据集，只借鉴公开开源项目和公开评测框架的设计思想，并在本项目中改写为低成本、本地规则化拆解：

- [Decision Quality](https://www.decisioneducation.org/principles-of-decision-quality/defining-decision-quality)：概念参考。当前 `Assessment Quality` 的六个维度参考其六要素：Helpful Frame、Clear Values、Creative Alternatives、Useful Information、Sound Reasoning、Commitment to Follow Through。本项目没有复制外部评分表或权重，而是把这些概念改写为本地程序化指标。
- [HELM](https://github.com/stanford-crfm/helm)：开源协议 Apache-2.0。借鉴其“多维指标、透明证据、承认覆盖边界”的评测思路。
- [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness)：开源协议 MIT。借鉴其“任务、指标、聚合结果分离”的工程结构。
- [BIG-bench](https://github.com/google/BIG-bench)：开源协议 Apache-2.0。借鉴其“多任务覆盖”和成本可控子集的理念，但不直接使用题目数据。

如果后续直接引入第三方题目或评分规则，需要逐项确认题库许可证、引用要求和是否允许修改后再提交到仓库。

## 验证

```powershell
pytest
python -m arena --help
python -m arena assessment-run --dry-run
python -m arena assessment-run --provider fake
python -m arena assessment-report --input runs/latest
```


## 文档地图

- [产品需求](docs/product/requirements.md)
- [架构说明](docs/architecture/architecture.md)
- [工作流](docs/operations/workflow.md)
- [Agent 项目指令](docs/agents/AGENTS.md)
- [项目规划](docs/plans/项目规划.md)
- [评分规则说明](docs/quality/scoring.md)
- [测试策略](docs/quality/test-strategy.md)
- [MVP 计划](docs/plans/mvp-plan.md)

---

## English Version

MultiModelArena is a local tool for comparing AI model capabilities. Users configure model providers, model names, base URLs, and API keys through environment variables, run one evaluation pass, and receive a Markdown report. The current main flow focuses on personal-action decision tasks and uses structured tasks, perturbations, local rule scoring, and response diagnostics. Model-judge scores are not used as the core score.

## Project Goals

- Run multiple models through structured personal-action tasks and perturbation rounds.
- Produce comparable and traceable model conclusions. The total score comes from local programmatic rules, not from a model judge.
- Generate Markdown reports with domain scores, process-quality scores inspired by Decision Quality, response diagnostics, behavioral fingerprints, role fit, evidence snippets, and links to raw local records.
- Let users switch model providers and enabled model aliases through environment variables without committing secrets.

## Tech Stack

- Backend and orchestration: Python.
- Report output: local Markdown files.
- Storage: SQLite plus JSONL raw event records.
- Verification: pytest, CLI end-to-end runs, and report-content checks.
- Configuration: `.env` environment variables. The repository only commits `.env.example`.

## Current Stage

The repository has implemented the MVP local loop:

1. Load model configuration from environment variables or `.env`.
2. Run model assessment with fake provider, OpenAI-compatible provider, or Anthropic-compatible provider.
3. Save `events.jsonl`, `summary.json`, and `summary.sqlite3`.
4. Generate a local Markdown report under root-level `report-output/`.
5. Keep the legacy multi-model peer-review command while using `assessment-run` as the current main flow.

## Quick Start

The main flow uses local `.env`: copy `.env.example` to `.env`, put the enabled aliases in `ARENA_MODELS`, and configure `PROVIDER`, `BASE_URL`, `API_KEY`, and `MODEL_NAME` for those aliases. After configuration, run `python -m arena assessment-run` for the formal assessment, then run `python -m arena assessment-report --input runs/latest` to generate or rebuild the report.

Run without real API keys by using the fake provider:

```powershell
python -m arena assessment-run --provider fake
python -m arena assessment-report --input runs/latest
```

Reports are written to `report-output/` with names like:

```text
model-arena-YYYYMMDD-HHMMSS-model_families.md
```

Check configuration only:

```powershell
python -m arena assessment-run --dry-run
```

Probe all enabled models once with the same configuration used by the formal program:

```powershell
python -m arena probe-model
```

Probe one model:

```powershell
python -m arena probe-model --alias minimax_t01
```

Run a natural-language connectivity probe:

```powershell
python -m arena probe-model --alias minimax_t01 --prompt "What model are you?"
```

Print raw probe responses only when debugging:

```powershell
python -m arena probe-model --alias minimax_t01 --show-response
```

The legacy peer-review flow can still run:

```powershell
python -m arena run --provider fake
```

CLI command quick reference:

- Formal assessment flow: `python -m arena assessment-run`
- Generate report from latest run: `python -m arena assessment-report --input runs/latest`
- Configuration check: `python -m arena assessment-run --dry-run`
- Offline fake assessment: `python -m arena assessment-run --provider fake`
- Probe all enabled models: `python -m arena probe-model`
- Probe one model: `python -m arena probe-model --alias minimax_t01`
- Natural-language connectivity probe: `python -m arena probe-model --alias minimax_t01 --prompt "What model are you?"`
- Show raw probe response for debugging: `python -m arena probe-model --alias minimax_t01 --show-response`
- Legacy peer-review flow: `python -m arena run --provider fake`

## Model Configuration

Copy `.env.example` to local `.env`, then fill in model aliases and API keys. Real `.env` is ignored by Git.

Supported providers:

- `fake`: offline testing provider.
- `openai_compatible`: OpenAI Chat Completions-compatible `/chat/completions` API.
- `anthropic_compatible`: Anthropic Messages-compatible `/messages` API. The program only uses `text` content blocks for scoring.

Each model can use these fields:

```text
ARENA_MODELS=alias_a,alias_b
ARENA_OUTPUT_DIR=runs
ARENA_DISABLE_PROXY=true
ARENA_MODEL_<ALIAS>_PROVIDER=openai_compatible
ARENA_MODEL_<ALIAS>_BASE_URL=https://api.example.com/v1
ARENA_MODEL_<ALIAS>_API_KEY=sk-...
ARENA_MODEL_<ALIAS>_MODEL_NAME=model-name
ARENA_MODEL_<ALIAS>_ROLE_HINT=
ARENA_MODEL_<ALIAS>_TEMPERATURE=0.2
ARENA_MODEL_<ALIAS>_MAX_TOKENS=None
ARENA_MODEL_<ALIAS>_TOKEN_LIMIT_FIELD=auto
ARENA_MODEL_<ALIAS>_TOP_P=None
ARENA_MODEL_<ALIAS>_TIMEOUT_SECONDS=60
ARENA_MODEL_<ALIAS>_RETRY_COUNT=0
ARENA_MODEL_<ALIAS>_DISABLE_PROXY=false
```

Only aliases listed in `ARENA_MODELS` are called. Other configured blocks in `.env` are ignored until their aliases are added to `ARENA_MODELS`. `MODEL_NAME` is the provider-side model name. The legacy `NAME` field remains supported but is not recommended.

`TOKEN_LIMIT_FIELD` can be `auto`, `max_tokens`, or `max_completion_tokens`. `MAX_TOKENS=None` or a blank value means no output-token limit is sent in the request body. `TOP_P=None` has the same meaning for `top_p`: the request omits it and lets the provider use its default.

`ARENA_DISABLE_PROXY=true` disables system and environment proxies for model requests. It can be overridden per model with `ARENA_MODEL_<ALIAS>_DISABLE_PROXY=true`.

Kimi uses the OpenAI-compatible API. The current template uses `BASE_URL=https://api.moonshot.cn/v1` and `MODEL_NAME=kimi-k2.6`. For Kimi K2.6-style models that only allow fixed temperature, set `TEMPERATURE` to the provider-allowed value; the local template uses `TEMPERATURE=1.0` and `TOP_P=None`.

Volcengine Ark Doubao Seed uses the OpenAI-compatible API with `BASE_URL=https://ark.cn-beijing.volces.com/api/v3` and `MODEL_NAME=doubao-seed-2-0-lite-260428`.

Alibaba Bailian Qwen uses the OpenAI-compatible API with `BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`, current `MODEL_NAME=qwen3.6-flash`, and `TOKEN_LIMIT_FIELD=max_tokens`.

SiliconFlow uses the OpenAI-compatible API with `BASE_URL=https://api.siliconflow.cn/v1`. The template sets `glm` to `MODEL_NAME=Pro/zai-org/GLM-5.1` and `deepseek` to `MODEL_NAME=deepseek-ai/DeepSeek-V4-Flash`, both with `TOKEN_LIMIT_FIELD=max_tokens`. If you pick another model ID from SiliconFlow, update only `MODEL_NAME`. Because both aliases share the same `BASE_URL`, the assessment scheduler queues them sequentially behind that endpoint.

Xiaomi MiMo uses the OpenAI-compatible API with `BASE_URL=https://api.xiaomimimo.com/v1` and default `MODEL_NAME=mimo-v2.5-pro`. Its OpenAI-compatible example uses `max_completion_tokens`, so the template sets `TOKEN_LIMIT_FIELD=max_completion_tokens`.

## Assessment Flow

The current main flow is `python -m arena assessment-run`; report generation is `python -m arena assessment-report --input runs/latest`. The legacy `python -m arena run` command is not the current main assessment path.

Current flow:

1. Load aliases from `ARENA_MODELS`.
2. Run built-in tasks independently for every enabled model: 4 domains, 1 baseline task per domain, and 2 perturbations per task. This is 12 formal assessment requests per model by default.
3. Requests are scheduled by `BASE_URL`. Different request endpoints run concurrently; models sharing the same endpoint are queued sequentially.
4. Ask models to output structured JSON. The protocol lives in [src/arena/assessment/protocol.py](src/arena/assessment/protocol.py).
5. Assessment tasks live in [src/arena/assessment/tasks.py](src/arena/assessment/tasks.py).
6. Programmatic scoring covers JSON completeness, alternative count, bad-option avoidance, professional boundary, perturbation response, and action planning. The logic lives in [src/arena/assessment/scoring.py](src/arena/assessment/scoring.py).
7. Without increasing model calls, the program decomposes each response into constraint grounding, value decomposition, tradeoff reasoning, information seeking, risk and reversibility, execution specificity, adaptation to change, calibration boundary, and method diversity. The logic lives in [src/arena/assessment/diagnostics.py](src/arena/assessment/diagnostics.py).
8. The report shows the model's analysis-angle fingerprint, including stage-gate or pilot validation, tradeoff matrix or prioritization, constraint checking, risk review, stakeholder alignment, information-gap management, user-value identification, and execution planning. Rendering lives in [src/arena/assessment/report.py](src/arena/assessment/report.py).
9. Storage writes `events.jsonl`, `summary.json`, and `summary.sqlite3`; storage code lives in [src/arena/assessment/store.py](src/arena/assessment/store.py).
10. Markdown reports are written to `report-output/`.

The current `assessment-run` flow does not call a model judge and has no separate judge-model configuration. The total score comes only from local rules and response diagnostics. The legacy `arena run` flow can make models review each other, but it is separate from `assessment-run` and does not affect its total score.

## Evaluation References

No third-party benchmark tasks, source code, or datasets are imported. The project only adapts public evaluation ideas into local, low-cost, rule-based diagnostics:

- [Decision Quality](https://www.decisioneducation.org/principles-of-decision-quality/defining-decision-quality/): conceptual reference. `Assessment Quality` is inspired by six elements: Helpful Frame, Clear Values, Creative Alternatives, Useful Information, Sound Reasoning, and Commitment to Follow Through. This project does not copy external scoring sheets or weights.
- [HELM](https://github.com/stanford-crfm/helm): Apache-2.0. We borrow the ideas of multi-metric evaluation, transparent evidence, and explicit coverage limits.
- [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness): MIT. We borrow the engineering separation between tasks, metrics, and aggregation.
- [BIG-bench](https://github.com/google/BIG-bench): Apache-2.0. We borrow the idea of broad task coverage with cost-controlled subsets, but do not directly use its task data.

Any future direct import of third-party tasks or scoring rules must first verify the license, attribution requirements, and modification rights.

## Verification

```powershell
pytest
python -m arena --help
python -m arena assessment-run --dry-run
python -m arena assessment-run --provider fake
python -m arena assessment-report --input runs/latest
```

## Document Map

- [Product Requirements](docs/product/requirements.md)
- [Architecture](docs/architecture/architecture.md)
- [Workflow](docs/operations/workflow.md)
- [Agent Instructions](docs/agents/AGENTS.md)
- [Project Plan](docs/plans/项目规划.md)
- [Scoring Rules](docs/quality/scoring.md)
- [Test Strategy](docs/quality/test-strategy.md)
- [MVP Plan](docs/plans/mvp-plan.md)
