# MVP 执行计划

## 目标

实现一个端到端最小闭环：读取多个模型配置，运行内置评测任务，保存过程数据，生成本地 HTML 可视化报告。

## 里程碑 1：项目骨架

- [x] 初始化 Python 包结构。
- [x] 增加 `.env.example`。
- [x] 定义模型配置 schema。
- [x] 增加基础 CLI：`run`、`report`、`serve`。
- [x] 增加最小单元测试。

验收：

```powershell
python -m pytest
python -m arena --help
```

## 里程碑 2：模型调用适配

- [x] 实现 OpenAI-compatible provider。
- [x] 支持超时和错误归一化。
- [x] 对日志和错误信息做密钥脱敏。
- [x] 增加 fake provider 用于离线测试。
- [ ] 增加重试策略。

验收：

```powershell
python -m pytest tests/test_provider*.py
python -m arena run --dry-run
```

## 里程碑 3：评测编排

- [x] 定义任务、轮次、评分维度和角色 schema。
- [x] 实现独立回答、互评、修订和规则化汇总流程。
- [x] 保存 JSONL 原始事件和 SQLite 汇总数据。
- [x] 某个模型失败时继续执行其他模型。
- [ ] 将规则化汇总升级为可配置裁判模型或固定基准。

验收：

```powershell
python -m pytest tests/test_evaluation*.py
python -m arena run --provider fake
```

## 里程碑 4：HTML 报告

- [x] 生成静态 HTML 报告。
- [x] 展示总览、模型卡片、维度对比和任务证据。
- [x] 增加基本图表，使用内联 CSS 和少量原生 JS。
- [x] 确认报告不包含 API Key。
- [ ] 增加更明确的局限性区块。

验收：

```powershell
python -m arena report --input runs/latest
```

## 里程碑 5：浏览器验证和文档补齐

- [ ] 增加 Playwright 冒烟测试或手动截图检查。
- [x] 更新 README 的本地运行步骤。
- [ ] 补充已知限制和后续路线图。

验收：

```powershell
python -m pytest
python -m arena run --provider fake
python -m arena report --input runs/latest
```

## 关键风险

- 不同供应商兼容接口的细节差异较大，需要先以 OpenAI-compatible 最小字段为准。
- 模型自评和互评可能偏差明显，报告必须展示证据和局限。
- 成本和耗时随模型数量、任务数量、轮次增加而快速上升，需要默认限制。
- 多模型输出结构可能不稳定，需要 schema 校验和失败降级。
