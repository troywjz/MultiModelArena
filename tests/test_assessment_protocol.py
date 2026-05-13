from arena.assessment.protocol import build_assessment_messages, parse_json_response
from arena.assessment.tasks import DEFAULT_ASSESSMENT_TASKS


def test_default_assessment_tasks_cover_four_domains():
    domains = {task.domain for task in DEFAULT_ASSESSMENT_TASKS}

    assert domains == {"个人生活", "事业与成长", "人际与关系", "资源与风险"}
    assert all(len(task.mutations) >= 2 for task in DEFAULT_ASSESSMENT_TASKS)


def test_build_assessment_messages_contains_json_contract():
    task = DEFAULT_ASSESSMENT_TASKS[0]

    messages = build_assessment_messages(task)

    assert messages[0]["role"] == "system"
    assert "MODEL_ASSESSMENT_JSON_TASK" not in messages[1]["content"]
    assert "TASK_ID:" not in messages[1]["content"]
    assert "PHASE_ID:" not in messages[1]["content"]
    assert "输出JSON字段" in messages[1]["content"]
    assert "problem_frame" in messages[1]["content"]
    assert "700字以内" in messages[0]["content"]
    assert "依据、权衡、风险和下一步" in messages[0]["content"]


def test_parse_json_response_accepts_code_fence():
    parsed, error = parse_json_response('```json\n{"recommended_option":"A"}\n```')

    assert error == ""
    assert parsed == {"recommended_option": "A"}
