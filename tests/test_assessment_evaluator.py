import json

from arena.config import ArenaConfig
from arena.assessment.evaluator import AssessmentEvaluator
from arena.assessment.report import generate_assessment_html_report
from arena.models import ModelConfig


def test_assessment_evaluator_runs_fake_provider(tmp_path):
    config = ArenaConfig(
        models=[
            ModelConfig(alias="a", provider="fake", model_name="fake-a"),
            ModelConfig(alias="b", provider="fake", model_name="fake-b"),
        ],
        output_root=tmp_path,
    )

    summary = AssessmentEvaluator(config).run()

    assert len(summary.results) == 2
    assert (summary.output_dir / "events.jsonl").exists()
    assert (summary.output_dir / "summary.json").exists()
    assert (summary.output_dir / "summary.sqlite3").exists()
    assert (tmp_path / "latest" / "summary.json").exists()
    assert all(result.total_score > 0 for result in summary.results)


def test_assessment_report_contains_programmatic_scoring(tmp_path):
    config = ArenaConfig(
        models=[ModelConfig(alias="a", provider="fake", model_name="fake-a", api_key="sk-test-secret-value")],
        output_root=tmp_path,
    )
    summary = AssessmentEvaluator(config).run()
    data = json.loads((summary.output_dir / "summary.json").read_text(encoding="utf-8"))

    report_path = generate_assessment_html_report(data, summary.output_dir / "report.html")
    html = report_path.read_text(encoding="utf-8")

    assert "模型能力评估报告" in html
    assert "Assessment Quality" in html
    assert "sk-test-secret-value" not in html
