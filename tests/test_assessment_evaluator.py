# 检查当前评测编排和报告生成。
# 输入：fake 模型和测试任务；输出：pytest 断言结果。
import json
from threading import Barrier, Lock
import time

from arena.config import ArenaConfig
from arena.assessment.evaluator import AssessmentEvaluator
from arena.assessment.models import AssessmentTask
from arena.assessment.report import generate_assessment_markdown_report
from arena.assessment.tasks import DEFAULT_ASSESSMENT_TASKS
from arena.models import EmbeddingConfig, ModelConfig, ProviderResponse


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


def test_assessment_evaluator_runs_fake_embedding_offline(tmp_path):
    config = ArenaConfig(
        models=[ModelConfig(alias="a", provider="fake", model_name="fake-a")],
        output_root=tmp_path,
        embedding=EmbeddingConfig(
            provider="fake",
            base_url="fake://embedding",
            model_name="fake-embedding",
            dimensions=16,
            cache_path=tmp_path / "fake-embedding-cache.sqlite3",
        ),
    )

    summary = AssessmentEvaluator(config, tasks=[DEFAULT_ASSESSMENT_TASKS[0]]).run()

    assert len(summary.results) == 1
    assert summary.results[0].semantic_scores
    assert summary.results[0].semantic_role_fit
    assert "fake-embedding" in " ".join(summary.results[0].semantic_notes)
    assert (tmp_path / "fake-embedding-cache.sqlite3").exists()


def test_assessment_evaluator_runs_different_endpoints_concurrently(tmp_path, monkeypatch):
    task = _single_phase_task()
    barrier = Barrier(2, timeout=2)

    class BarrierProvider:
        def __init__(self, alias: str) -> None:
            self.alias = alias

        def complete(self, messages):  # noqa: ANN001
            barrier.wait()
            return ProviderResponse(text=json.dumps(_valid_assessment_response(self.alias), ensure_ascii=False))

    monkeypatch.setattr(
        "arena.assessment.evaluator.build_provider",
        lambda model: BarrierProvider(model.alias),
    )
    config = ArenaConfig(
        models=[
            ModelConfig(alias="a", provider="openai_compatible", model_name="a", base_url="https://a.example/v1"),
            ModelConfig(alias="b", provider="openai_compatible", model_name="b", base_url="https://b.example/v1"),
        ],
        output_root=tmp_path,
    )

    summary = AssessmentEvaluator(config, tasks=[task]).run()

    assert len(summary.results) == 2
    assert all(not result.errors for result in summary.results)


def test_assessment_evaluator_serializes_same_endpoint(tmp_path, monkeypatch):
    task = _single_phase_task()
    lock = Lock()
    state = {"active": 0, "overlap": False}

    class OverlapDetectingProvider:
        def __init__(self, alias: str) -> None:
            self.alias = alias

        def complete(self, messages):  # noqa: ANN001
            with lock:
                state["active"] += 1
                if state["active"] > 1:
                    state["overlap"] = True
            time.sleep(0.05)
            with lock:
                state["active"] -= 1
            return ProviderResponse(text=json.dumps(_valid_assessment_response(self.alias), ensure_ascii=False))

    monkeypatch.setattr(
        "arena.assessment.evaluator.build_provider",
        lambda model: OverlapDetectingProvider(model.alias),
    )
    config = ArenaConfig(
        models=[
            ModelConfig(alias="glm", provider="openai_compatible", model_name="glm", base_url="https://api.siliconflow.cn/v1"),
            ModelConfig(alias="deepseek", provider="openai_compatible", model_name="deepseek", base_url="https://api.siliconflow.cn/v1"),
        ],
        output_root=tmp_path,
    )

    summary = AssessmentEvaluator(config, tasks=[task]).run()

    assert len(summary.results) == 2
    assert state["overlap"] is False


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
    assert "过程质量（Assessment Quality）" in markdown
    assert "#### 响应拆解评估" in markdown
    assert "| 名称 | 值 | 说明 |" in markdown
    assert "约束锚定" in markdown
    assert "#### 方法与分析角度指纹" in markdown
    assert "有效 JSON 响应数" in markdown
    assert "#### 拆解证据" in markdown
    assert "fake-a（温度 0.2）" in markdown
    assert "- 温度（Temperature）：0.2" in markdown
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
    assert "本次总评分仅来自本地程序化规则" in markdown
    assert "| 1 | bad-json-model | 离线模拟（fake） | 0.0 | 待定 |" in markdown
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
    assert "- 温度（Temperature）：0.8" in markdown


def test_assessment_report_preserves_semantic_scores(tmp_path):
    data = {
        "run_id": "semantic-run",
        "created_at": "2026-05-14T00:00:00+00:00",
        "output_dir": str(tmp_path),
        "tasks": [
            {
                "id": "career_switch_001",
                "domain": "事业与成长",
                "title": "职业转型选择",
                "prompt": "请给出结构化建议。",
                "visible_constraints": ["收入"],
                "hidden_values": {"income": 1.0},
                "acceptable_options": ["渐进转型"],
                "bad_options": ["裸辞"],
                "scoring_points": [],
                "mutations": [],
            }
        ],
        "results": [
            {
                "alias": "semantic_model",
                "model_name": "semantic-model",
                "provider": "fake",
                "responses": [{"task_id": "career_switch_001", "phase_id": "baseline", "parsed": _valid_assessment_response("semantic")}],
                "domain_scores": {},
                "quality_scores": {},
                "behavior_fingerprint": {},
                "role_fit": {"用户价值专家": 9.0},
                "rule_scores": {},
                "diagnostic_scores": {},
                "semantic_scores": {"问题框架": 8.5},
                "semantic_role_fit": {"用户价值专家": 9.0},
                "semantic_notes": ["语义评分使用 netease-youdao/bce-embedding-base_v1。"],
                "total_score": 8.0,
                "evidence": [],
                "failures": [],
                "errors": [],
            }
        ],
        "summary": "semantic-model: 总分 8.0/10",
    }

    report_path = generate_assessment_markdown_report(data, tmp_path / "report.md")
    markdown = report_path.read_text(encoding="utf-8")

    assert "#### 参考答案语义相似度" in markdown
    assert "问题框架" in markdown
    assert "8.5 / 10" in markdown
    assert "语义评分使用 netease-youdao/bce-embedding-base_v1" in markdown


def test_assessment_report_includes_role_definitions_and_coverage(tmp_path):
    data = {
        "run_id": "role-coverage-run",
        "created_at": "2026-05-15T00:00:00+00:00",
        "output_dir": str(tmp_path),
        "tasks": [],
        "results": [
            {
                "alias": "planner",
                "model_name": "planner-model",
                "provider": "fake",
                "responses": "legacy-summary-without-response-list",
                "domain_scores": {},
                "quality_scores": {},
                "behavior_fingerprint": {},
                "role_fit": {"执行规划专家": 9.0, "风险专家": 7.0, "用户价值专家": 4.0},
                "rule_scores": {},
                "total_score": 8.0,
                "evidence": [],
                "failures": [],
                "errors": [],
            }
        ],
        "summary": "planner-model: 总分 8.0/10",
    }

    report_path = generate_assessment_markdown_report(data, tmp_path / "report.md")
    markdown = report_path.read_text(encoding="utf-8")

    assert "## 专家角色定义与覆盖" in markdown
    assert "执行规划专家" in markdown
    assert "负责把结论转成 7 天、30 天和复盘节点的行动计划" in markdown
    assert "本次没有进入任何模型推荐前三的角色" in markdown


def _single_phase_task() -> AssessmentTask:
    return AssessmentTask(
        id="task_1",
        domain="个人生活",
        title="测试任务",
        prompt="用户需要在预算和时间约束下做选择。",
        visible_constraints=["预算", "时间"],
        hidden_values={"budget": 0.5, "time": 0.5},
        acceptable_options=["小规模试点", "暂缓"],
        bad_options=["一次性投入全部预算"],
        scoring_points=[],
        mutations=[],
    )


def _valid_assessment_response(alias: str) -> dict[str, object]:
    return {
        "problem_frame": f"{alias} 在预算和时间之间做低后悔选择。",
        "assumptions": ["预算有限", "时间有限"],
        "clarifying_questions": ["预算上限是多少？", "最晚何时决定？"],
        "values_detected": ["预算", "时间"],
        "alternatives": [
            {"name": "小规模试点", "type": "stage_gate", "pros": ["可验证"], "cons": ["较慢"], "reversibility": "high"},
            {"name": "暂缓", "type": "hold", "pros": ["安全"], "cons": ["错过机会"], "reversibility": "medium"},
            {"name": "直接执行", "type": "direct_path", "pros": ["快"], "cons": ["风险高"], "reversibility": "low"},
        ],
        "recommended_option": "小规模试点",
        "option_ranking": ["小规模试点", "暂缓", "直接执行"],
        "confidence": 0.7,
        "risks": ["预算超支风险", "时间不足风险"],
        "next_actions_7_days": ["7天内确认预算"],
        "next_actions_30_days": ["30天内复盘试点"],
        "revisit_conditions": ["预算变化"],
        "professional_boundary": "这是个人判断，不替代专业建议。",
    }
