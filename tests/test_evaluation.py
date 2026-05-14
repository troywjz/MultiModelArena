# 检查旧版评测流程。
# 输入：fake 模型配置；输出：pytest 断言结果。
from arena.config import ArenaConfig
from arena.evaluation import Evaluator
from arena.models import ModelConfig, Task


def test_evaluator_runs_fake_models(tmp_path):
    config = ArenaConfig(
        models=[
            ModelConfig(alias="a", provider="fake", model_name="fake-a", role_hint="架构评审者"),
            ModelConfig(alias="b", provider="fake", model_name="fake-b", role_hint="测试与质量审查者"),
        ],
        output_root=tmp_path,
    )
    tasks = [Task(id="t1", title="任务", prompt="请分析测试、风险和实现方案。")]

    summary = Evaluator(config, tasks=tasks).run()

    assert len(summary.results) == 2
    assert (summary.output_dir / "events.jsonl").exists()
    assert (summary.output_dir / "summary.json").exists()
    assert (summary.output_dir / "summary.sqlite3").exists()
    assert (tmp_path / "latest" / "summary.json").exists()
    assert all(result.average_score > 0 for result in summary.results)
