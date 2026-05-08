import json

from arena.config import ArenaConfig
from arena.evaluation import Evaluator
from arena.models import ModelConfig, Task
from arena.reporting import generate_html_report


def test_report_contains_model_scores_and_no_secret(tmp_path):
    config = ArenaConfig(
        models=[
            ModelConfig(
                alias="secret_model",
                provider="fake",
                model_name="fake-secret",
                api_key="sk-test-secret-value",
            )
        ],
        output_root=tmp_path,
    )
    summary = Evaluator(config, tasks=[Task(id="t1", title="任务", prompt="请给出结构化回答。")]).run()
    data = json.loads((summary.output_dir / "summary.json").read_text(encoding="utf-8"))

    report_path = generate_html_report(data, summary.output_dir / "report.html")
    html = report_path.read_text(encoding="utf-8")

    assert "fake-secret" in html
    assert "平均分" in html
    assert "sk-test-secret-value" not in html
