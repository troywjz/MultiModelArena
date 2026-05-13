# AGENTS.md

## 项目定位

本项目从零构建一个多模型能力评估与报告工具。核心交付物是：用户配置若干 AI 模型后，运行程序，得到 Markdown 结果报告，说明每个模型的领域得分、行为指纹、适合的团队角色和形成结论的证据。

## 工作原则

- 先读 `README.md`、`docs/architecture/architecture.md`、`docs/product/requirements.md`、`docs/plans/mvp-plan.md`，再改代码。
- 复杂工程任务开始实现前，先分析目标和缺失信息；影响产品方向、数据结构、安全、成本、技术栈或核心体验的问题必须先问用户。
- 缺失信息不关键时，做保守假设，并记录到规划、README、架构说明或任务文档中。
- 开始实现前给出简短但完整的交付计划，至少包含产品目标、核心用户流程、技术方案、项目结构、验收标准和验证方式。
- 用户使用中文沟通时，新增文档、注释、提交说明默认使用中文。
- 密钥只来自环境变量或本地未提交文件，不写入仓库、日志或报告。
- AI 提示词、评测维度、评分 schema 和报告模板都视为产品工件，变更时要可追溯。
- 保持小步实现，但目标是可运行、可维护的项目结果，不交付只适合演示的半成品。
- 必须创建或更新必要的项目文件，例如 README、`docs/agents/AGENTS.md`、架构说明、运行说明和测试说明。
- 实现后必须运行项目并执行可用的测试、lint、类型检查或构建；失败时继续修复，除非存在明确阻塞。
- 如果涉及前端页面，必须启动本地服务并用浏览器检查关键页面。
- 最终汇报必须说明已完成内容、如何运行、验证结果、已知限制和下一步建议。

## 建议目录

```text
src/
  arena/
    config.py
    providers/
    evaluation/
    storage/
    reporting/
tests/
docs/
  product/
  plans/
  quality/
```

## 最小验证

项目实现后，每次任务至少运行与改动相关的命令。MVP 阶段建议逐步建立：

```powershell
python -m pytest
python -m arena run --dry-run
python -m arena report --input runs/latest
```

如果命令尚不存在，需要在最终汇报中明确说明。
