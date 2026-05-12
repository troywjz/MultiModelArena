import json

from arena.config import ArenaConfig
from arena.assessment.evaluator import AssessmentEvaluator
from arena.assessment.report import generate_assessment_markdown_report
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

    report_path = generate_assessment_markdown_report(data, summary.output_dir / "report.md")
    markdown = report_path.read_text(encoding="utf-8")

    assert "# 模型能力评估报告" in markdown
    assert "Assessment Quality" in markdown
    assert "fake-a（温度 0.2）" in markdown
    assert "- Temperature：0.2" in markdown
    assert "## 原始记录文件" in markdown
    assert "\\summary.json" not in markdown
    assert "## 完整回答证据" not in markdown
    assert "```json" not in markdown
    assert "sk-test-secret-value" not in markdown


def test_assessment_report_marks_all_parse_failures_invalid(tmp_path):
    data = {
        "run_id": "invalid-json-run",
        "created_at": "2026-05-12T00:00:00+00:00",
        "output_dir": str(tmp_path),
        "tasks": [
            {
                "id": "task_1",
                "domain": "个人生活",
                "title": "测试任务",
                "prompt": "请给出结构化建议。",
                "visible_constraints": [],
                "acceptable_options": [],
                "bad_options": [],
                "mutations": [],
            }
        ],
        "results": [
            {
                "alias": "bad_json",
                "model_name": "bad-json-model",
                "provider": "fake",
                "responses": [{"parsed": None, "parse_error": "Expecting value"}],
                "domain_scores": {},
                "quality_scores": {},
                "behavior_fingerprint": {},
                "role_fit": {"通用主持专家": 0.0},
                "rule_scores": {"json_complete": 0.0},
                "total_score": 0.0,
                "evidence": [],
                "failures": ["task_1/baseline: JSON 解析失败"],
                "errors": [],
            }
        ],
        "summary": "本次主分仅来自程序化规则，不包含模型裁判。",
    }

    report_path = generate_assessment_markdown_report(data, tmp_path / "report.md")
    markdown = report_path.read_text(encoding="utf-8")

    assert "## 有效性提示" in markdown
    assert "没有任何可解析的 JSON 响应" in markdown
    assert "本次总评分仅来自程序化规则" in markdown
    assert "| 1 | bad-json-model | fake | 0.0 | 待定 |" in markdown
    assert "- 推荐角色：待定" in markdown


def test_assessment_report_infers_temperature_from_alias_for_old_summaries(tmp_path):
    data = {
        "run_id": "old-minimax-run",
        "created_at": "2026-05-12T00:00:00+00:00",
        "output_dir": str(tmp_path),
        "tasks": [
            {
                "id": "task_1",
                "domain": "个人生活",
                "title": "测试任务",
                "prompt": "请给出结构化建议。",
                "visible_constraints": [],
                "acceptable_options": [],
                "bad_options": [],
                "mutations": [],
            }
        ],
        "results": [
            {
                "alias": "minimax_t08",
                "model_name": "MiniMax-M2.7",
                "provider": "anthropic_compatible",
                "responses": [{"parsed": {"ok": True}}],
                "domain_scores": {"个人生活": 8.0},
                "quality_scores": {},
                "behavior_fingerprint": {},
                "role_fit": {"信息审查专家": 10.0},
                "rule_scores": {},
                "total_score": 8.0,
                "evidence": [],
                "failures": [],
                "errors": [],
            }
        ],
        "summary": "MiniMax-M2.7: 总分 8.0/10",
    }

    report_path = generate_assessment_markdown_report(data, tmp_path / "report.md")
    markdown = report_path.read_text(encoding="utf-8")

    assert "MiniMax-M2.7（温度 0.8）" in markdown
    assert "- Temperature：0.8" in markdown
