# 评分规则说明

本文档说明 `python -m arena assessment-run` 在拿到模型回答后如何评分。所有“评分”项都归一到 0-10 分；原始命中次数只作为证据展示，不直接当作分数。

## 总流程

1. 调用模型，要求返回严格 JSON（结构化数据格式）。
2. 解析 JSON。解析失败的轮次不再进入结构化字段计算，该轮在领域分、程序化规则分、过程质量分和响应拆解分中按 0 计入。
3. 对成功解析的 JSON 分别计算领域分、程序化规则分、过程质量分、响应拆解分、角色适配分。
4. 如果 `ARENA_EMBEDDING_ENABLED=true`，再把回答字段和本地参考答案向量化，计算参考答案语义相似度分。
5. 每个评分组先求组内均分，再把各组均分再次平均，得到总评分。

公式：

```text
总评分 = 平均值(
  领域分组均分,
  程序化规则分组均分,
  过程质量分组均分,
  响应拆解分组均分,
  参考答案语义相似度分组均分（启用 embedding 时存在）,
  角色适配分组均分
)
```

## 当前没有模型裁判

`python -m arena assessment-run` 当前没有调用模型裁判，也没有配置 judge model（裁判模型）。被测模型返回后，程序先做本地 Python 解析和规则计算；如果启用了 embedding，会调用向量化接口计算本地参考答案语义相似度。这个过程不让聊天模型参与评分。

旧版 `python -m arena run` 保留了多模型互评流程，但它不是当前主流程，结果也不会进入 `assessment-run` 的总分。

## 不是纯关键词评分

当前评分可以概括为“结构化规则 + 计数规则 + 部分关键词弱信号”，而不是“只看关键词出现次数”。

示例：

- 备选方案数量不是看文本里有没有 `1`、`2`、`3`，而是解析 JSON 后读取 `alternatives` 数组中有多少个对象。
- JSON 完整性是看必填字段是否非空。
- 行动计划是看 `next_actions_7_days`、`next_actions_30_days`、`revisit_conditions` 是否都有内容。
- 过程质量会统计 assumptions（假设）、clarifying_questions（澄清问题）、risks（风险）、pros/cons（优缺点）、option_ranking（排序）、actions（行动项）等结构字段。
- 关键词只用于少数明确场景：坏方案规避、可接受方案匹配、扰动响应、方法与分析角度识别。关键词命中是弱信号，不能单独代表答案正确。

因此，一个回答如果只堆“风险、权衡、试点、行动”等词，但 JSON 不能解析、字段不完整、没有真正列出备选方案或没有响应扰动，仍然会明显失分。

## 程序化规则评分

这些规则在 `src/arena/assessment/scoring.py` 中实现。

| 评分项 | 0-1 原始计算 | 报告分 |
|---|---|---|
| JSON 完整性 | 13 个必填字段中，非空字段数 / 13 | 原始值 × 10 |
| 备选方案数量 | `min(备选方案数量 / 3, 1)` | 原始值 × 10 |
| 坏方案规避 | 回答全文未命中任务定义的坏方案关键词为 1，否则为 0 | 原始值 × 10 |
| 专业边界 | 有专业边界提示为 1，否则为 0 | 原始值 × 10 |
| 行动计划 | 7 天行动、30 天行动、复盘条件都非空为 1，否则为 0 | 原始值 × 10 |
| 可接受方案匹配 | 推荐或前三排序命中任务定义的可接受方案关键词为 1，否则为 0 | 原始值 × 10 |
| 扰动响应 | 命中扰动预期方向、避开扰动应规避方向、相比基准回答发生变化，三项平均 | 原始值 × 10 |

这里确实包含关键词判断，但不是“提到任意关键词就加总分”。关键词只用于特定规则，例如坏方案规避、可接受方案匹配、扰动响应和方法识别；结构完整性、数量、行动计划、置信度、可逆性等也参与评分。

## 领域分

每个任务阶段会计算以下 7 项的平均值：

```text
阶段领域分 = 平均值(
  JSON 完整性,
  备选方案数量,
  坏方案规避,
  专业边界,
  行动计划,
  可接受方案匹配,
  扰动响应
)
```

基准回答没有扰动，因此扰动响应按 1 计入。某个领域的领域分是该领域所有阶段领域分的平均值，再换算到 0-10 分。

## 过程质量评分

过程质量参考 Decision Quality（决策质量）概念，但没有复制外部评分表。每项先算 0-1，再乘以 10。

| 评分项 | 计算方式 |
|---|---|
| 有效问题框架 | `是否有 problem_frame × 0.6 + min(assumptions 数量 / 2, 1) × 0.4` |
| 清晰价值识别 | `min(values_detected 数量 / max(2, min(4, 隐含价值数量)), 1)` |
| 创造性备选方案 | `min((备选方案数量 + 创造性方案数量) / 5, 1)` |
| 有用信息利用 | `min((assumptions 数量 + clarifying_questions 数量 + risks 数量) / 6, 1)` |
| 稳健推理 | `min((pros/cons 条目数 + option_ranking 数量) / 10, 1)` |
| 执行承诺 | `min((7 天行动数 + 30 天行动数 + 复盘条件数) / 7, 1)` |

## 响应拆解评分

响应拆解在 `src/arena/assessment/diagnostics.py` 中实现。它把 JSON 展平成文本后结合结构字段和关键词弱信号判断模型用了哪些分析行为。

| 评分项 | 计算方式 |
|---|---|
| 约束锚定 | 平均值：显式约束命中比例、具体数字数量 / 2、是否命中“约束检查”方法 |
| 价值拆解 | 平均值：价值条目数量比例、是否命中“用户价值识别”方法、是否有问题框架 |
| 权衡推理 | 平均值：pros/cons 条目数 / 6、排序数量 / 3、是否命中“权衡矩阵/优先级”方法 |
| 信息追问 | 平均值：假设数量 / 2、澄清问题数量 / 2、是否命中“信息缺口管理”方法 |
| 风险与可逆性 | 平均值：风险数量 / 2、含可逆性的方案数量 / 3、复盘条件数量 / 2、是否命中“风险复盘”方法 |
| 行动可执行性 | 平均值：行动数量 / 4、行动中具体数字数量 / 1、是否命中“执行计划”方法 |
| 变化适配 | 基准阶段为 1；扰动阶段看推荐是否变化、排序是否仍匹配可接受方案 |
| 校准与边界 | 平均值：是否有置信度、置信度是否在 0.35-0.9、是否有专业边界 |
| 方法多样性 | `min(命中的方法类型数 / 4, 1)` |

## 方法指纹

方法指纹分两类展示：

- 方法覆盖评分：每个方法类型按 `min(关键词命中次数 / (有效 JSON 响应数 × 2), 1) × 10` 计算，满分 10。这样同一类关键词只在多轮回答里反复出现时才会接近满分，避免所有模型轻易得到 10 分。
- 方法关键词命中次数：原始关键词命中次数，只表示证据强度，不是分数。

## 角色适配

角色适配从过程质量、响应拆解和行为计数推导，不按模型品牌预设。示例：

- 风险专家：有用信息利用、执行承诺、风险条目数、边界提示次数、风险与可逆性。
- 执行规划专家：执行承诺、行动条目数、行动可执行性。
- 权衡仲裁专家：稳健推理、清晰价值识别、权衡推理。
- 红队专家：有用信息利用、风险条目数、风险与可逆性、校准与边界。

每个角色内部先把相关信号压到 0-1 再平均，最后乘以 10。

## 参考答案语义相似度

参考答案语义相似度是当前已实现的可选评分组。启用 `ARENA_EMBEDDING_ENABLED=true` 后，程序会为每个任务阶段读取本地多个参考答案，把参考答案和模型回答拆成同一组字段片段，分别向量化后计算 cosine similarity（余弦相似度）。参考答案定义在 `src/arena/assessment/reference_answers.py`，评分逻辑在 `src/arena/assessment/semantic_scoring.py`，向量调用和缓存逻辑在 `src/arena/embeddings.py`。

语义分不应替代当前硬规则，而应作为一个新增评分组。原因是：

- 向量相似度擅长识别同义表达、改写表达和整体思路接近程度。
- 向量相似度不擅长判断 JSON 是否可解析、是否满足必填 schema（结构协议）、是否避开坏方案、是否按扰动更新、是否给出足够具体的行动项。
- 多个参考答案可以降低单一标准答案带来的偏差；每个字段取最高相似度或 Top-K 平均值，比整篇回答直接比对更稳。

启用 embedding 后的混合公式：

```text
总评分 = 平均值(
  领域分组均分,
  程序化规则分组均分,
  过程质量分组均分,
  响应拆解分组均分,
  角色适配分组均分,
  参考答案语义相似度分组均分
)
```

### 为什么先拆解再向量化

整篇回答直接向量化会过于粗糙：一个模型可能推荐方向正确，但风险和行动计划很弱；也可能文本整体接近参考答案，却漏掉专业边界。按字段拆解后，可以看到模型在哪些能力上强、哪些能力上弱。

建议字段拆解：

| 字段片段 | 含义 | 评分用途 |
|---|---|---|
| `problem_frame` | 问题框架 | 判断是否抓住核心冲突 |
| `values_detected` | 价值识别 | 判断是否识别用户偏好和隐含价值 |
| `alternatives` | 备选方案 | 判断方案集合是否接近优质参考 |
| `recommended_option + option_ranking` | 推荐与排序 | 判断结论方向是否合理 |
| `risks + revisit_conditions` | 风险与复盘 | 判断是否考虑不确定性和重新决策条件 |
| `next_actions_7_days + next_actions_30_days` | 行动计划 | 判断建议是否能落地 |
| `professional_boundary` | 专业边界 | 判断是否能校准风险和边界 |

### 参考答案缓存

参考答案向量可以放入本地数据库，避免每次运行重复付费：

1. 为每个参考答案片段计算 `content_hash`。
2. 用 `provider + embedding_model + dimensions + task_id + phase_id + segment_name + content_hash` 做缓存键。
3. 如果缓存命中，直接读取向量。
4. 如果参考答案文本修改导致 hash 变化，重新调用 embedding 模型生成向量。
5. 模型回答也可以按 `response_hash` 缓存，便于重新生成报告时不重复向量化。

SQLite 适合当前缓存：参考答案数量小、主要目标是可追溯和避免重复调用时，把向量存为 BLOB 或 JSON 即可，余弦相似度在 Python 中计算。Chroma 更适合大题库、Top-K 相似检索、元数据过滤或更接近向量数据库工作流的场景。

当前代码已经使用 SQLite 做缓存，默认路径是 `.arena-cache/embedding-cache.sqlite3`。这个目录不属于临时运行产物，不会因为清空 `runs/` 或 `report-output/` 而丢失。Chroma 没有接入当前实现。

### Embedding 模型选择

不需要一定使用 BERT。这里需要的是 embedding 模型，模型底座可以是 BERT、Qwen、BGE 或其他架构。

云端候选：

- 阿里云百炼 `text-embedding-v4`：中文和国内网络友好，支持 OpenAI-compatible embeddings 接口，默认 1024 维，也支持更低维度以节省存储和计算。
- OpenAI `text-embedding-3-small`：价格低、接口稳定，适合做通用 baseline（基线）；`text-embedding-3-large` 成本更高，适合要求更高的语义质量。
- Google `gemini-embedding-001`：适合已经使用 Gemini API 的团队。
- 硅基流动等聚合平台：适合复用已有聚合平台 key，但具体模型和价格要以平台模型列表为准。

本地实验候选：

- `BAAI/bge-small-zh-v1.5`：小尺寸中文模型，512 维，适合 8G 显存或 CPU 跑通实验。
- `BAAI/bge-m3`：多语言、多功能 embedding 模型，1024 维、8192 token、MIT 许可；效果更强但比 small 模型更重。
- `Qwen/Qwen3-Embedding-0.6B`：0.6B 级别，Apache-2.0 许可，适合想贴近 Qwen / 百炼生态的本地实验。

当前 `.env.example` 默认使用硅基流动 `netease-youdao/bce-embedding-base_v1`，因为它是 OpenAI-compatible embeddings 接口、中文可用、成本低，适合先跑通语义评分流程。

### 调用方式示例

云端 OpenAI-compatible embeddings（以硅基流动为例，项目内部直接用 urllib 实现，不依赖 openai 包）：

```json
{
  "model": "netease-youdao/bce-embedding-base_v1",
  "input": ["待向量化文本"],
  "encoding_format": "float"
}
```

请求地址是 `https://api.siliconflow.cn/v1/embeddings`。如果使用阿里云百炼或 OpenAI 官方 embedding，保持 provider 为 `openai_compatible`，只需要修改 `ARENA_EMBEDDING_BASE_URL` 和 `ARENA_EMBEDDING_MODEL`。

本地开源模型（以 `sentence-transformers` 为例）：

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("BAAI/bge-small-zh-v1.5", device="cuda")
texts = ["参考答案片段", "模型回答片段"]
vectors = model.encode(texts, normalize_embeddings=True)
similarity = float(vectors[0] @ vectors[1])
```

本地 8G 显存优先使用 small 或 0.6B 级模型。`bge-m3` 和 `Qwen3-Embedding-0.6B` 理论上也适合实验，但在 Windows、CUDA、PyTorch、Flash Attention 等环境组合下可能需要额外安装和调参；当前主流程不依赖这些本地环境。

### 价格比较注意事项

Embedding 价格变化快，文档中只记录选型方向，不把价格写死进评分代码。当前可参考：

- 阿里云百炼 `text-embedding-v4`：北京地域每千输入 Token 0.0005 元，Batch 接口 0.00025 元；支持 64 到 2048 维度，默认 1024 维。
- OpenAI `text-embedding-3-small`：每 100 万 Token 0.02 美元；`text-embedding-3-large`：每 100 万 Token 0.13 美元。
- Google `gemini-embedding-001`：每 100 万输入 Token 0.15 美元，Batch 为 0.075 美元。
- 硅基流动、OpenRouter 等聚合平台：要以平台模型页为准，适合作为“已有 key 复用”的方案，而不是评分体系的默认依赖。

当前 embedding provider 是独立配置，不和被测聊天模型混在一起：

```text
ARENA_EMBEDDING_ENABLED=false
ARENA_EMBEDDING_PROVIDER=openai_compatible
ARENA_EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
ARENA_EMBEDDING_API_KEY=
ARENA_EMBEDDING_MODEL=netease-youdao/bce-embedding-base_v1
ARENA_EMBEDDING_DIMENSIONS=None
ARENA_EMBEDDING_ENCODING_FORMAT=float
ARENA_EMBEDDING_BATCH_SIZE=16
ARENA_EMBEDDING_TIMEOUT_SECONDS=120
ARENA_EMBEDDING_RETRY_COUNT=1
ARENA_EMBEDDING_DISABLE_PROXY=false
ARENA_EMBEDDING_CACHE_PATH=.arena-cache/embedding-cache.sqlite3
ARENA_EMBEDDING_SIMILARITY_FLOOR=0.55
ARENA_EMBEDDING_SIMILARITY_CEILING=0.85
ARENA_EMBEDDING_ROLE_WEIGHT=0.35
```

`DIMENSIONS=None` 表示不传维度参数；`SIMILARITY_FLOOR` 和 `SIMILARITY_CEILING` 用于把余弦相似度线性映射到 0-10 分；`ROLE_WEIGHT` 表示语义角色适配分融合到角色评分的权重。

参考资料：

- 阿里云百炼 Embedding：<https://help.aliyun.com/zh/model-studio/embedding>
- 阿里云百炼文本向量计费：<https://help.aliyun.com/zh/model-studio/developer-reference/billing-for-text-embedding>
- OpenAI Pricing：<https://platform.openai.com/docs/pricing>
- Google Gemini API Pricing：<https://ai.google.dev/gemini-api/docs/pricing>
- Chroma 文档：<https://docs.trychroma.com/>
- BGE small 中文模型：<https://huggingface.co/BAAI/bge-small-zh-v1.5>
- BGE-M3：<https://huggingface.co/BAAI/bge-m3>
- Qwen3-Embedding-0.6B：<https://huggingface.co/Qwen/Qwen3-Embedding-0.6B>
