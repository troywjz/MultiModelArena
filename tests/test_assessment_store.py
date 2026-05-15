# 检查当前评测记录落盘。
# 输入：临时运行目录和模拟文件占用；输出：pytest 断言结果。
from arena.assessment.store import AssessmentRunStore


def test_record_event_queues_and_flushes_when_events_file_is_temporarily_locked(tmp_path, monkeypatch):
    store = AssessmentRunStore(tmp_path / "run")
    original_append = store._append_event_line
    calls = {"count": 0}

    def flaky_append(line: str) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise PermissionError("locked")
        original_append(line)

    monkeypatch.setattr(store, "_append_event_line", flaky_append)

    store.record_event("assessment_response", {"alias": "fake", "ok": True})
    store._flush_pending_events()

    assert store._pending_event_lines == []
    assert '"assessment_response"' in store.events_path.read_text(encoding="utf-8")
