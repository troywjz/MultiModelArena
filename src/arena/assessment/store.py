# 保存当前评测运行记录。
# 输入：评测摘要和事件；输出：JSON、JSONL 和 SQLite 文件。
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from threading import Lock
import time
from pathlib import Path
from typing import Any

from arena.security import redact_text

from .models import AssessmentRunSummary


class AssessmentRunStore:
    def __init__(self, output_dir: Path, known_secrets: list[str] | None = None) -> None:
        self.output_dir = output_dir
        self.known_secrets = known_secrets or []
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.output_dir / "events.jsonl"
        self.summary_path = self.output_dir / "summary.json"
        self.db_path = self.output_dir / "summary.sqlite3"
        self._event_lock = Lock()
        self._pending_event_lines: list[str] = []
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                create table if not exists assessment_model_results (
                    alias text primary key,
                    model_name text not null,
                    provider text not null,
                    temperature real,
                    total_score real not null,
                    diagnostic_scores text not null,
                    method_fingerprint text not null,
                    semantic_scores text not null default '{}',
                    semantic_role_fit text not null default '{}',
                    role_fit text not null,
                    failures text not null,
                    errors text not null
                )
                """
            )
            conn.execute(
                """
                create table if not exists assessment_domain_scores (
                    alias text not null,
                    domain text not null,
                    score real not null,
                    primary key (alias, domain)
                )
                """
            )

    def record_event(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {"type": event_type, "payload": payload}
        safe = json.loads(redact_text(json.dumps(event, ensure_ascii=False), self.known_secrets))
        # 不同请求入口会并发写事件文件；加锁保证 JSONL 不会交错写入半行。
        with self._event_lock:
            line = json.dumps(safe, ensure_ascii=False) + "\n"
            try:
                self._append_event_line(line)
            except PermissionError as exc:
                # 事件日志是审计材料，不能因为 Windows 文件短暂占用而把模型成功响应误判为模型失败。
                # 先放入内存队列，写 summary 前再补写；如果仍失败，只影响 events.jsonl 完整度。
                self._pending_event_lines.append(line)
                print(f"警告：事件日志暂时无法写入，已延后重试：{exc}", file=sys.stderr)

    def _append_event_line(self, line: str) -> None:
        # Windows 上偶发的杀毒/索引扫描可能短暂占用文件；这里重试避免丢掉整次评估。
        for attempt in range(20):
            try:
                with self.events_path.open("a", encoding="utf-8") as file:
                    file.write(line)
                return
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(min(0.5 * (attempt + 1), 3.0))

    def write_summary(self, summary: AssessmentRunSummary) -> None:
        self._flush_pending_events()
        data = summary.to_dict()
        safe_data = json.loads(redact_text(json.dumps(data, ensure_ascii=False), self.known_secrets))
        self.summary_path.write_text(json.dumps(safe_data, ensure_ascii=False, indent=2), encoding="utf-8")
        self._write_sqlite(summary)
        self._update_latest()

    def _flush_pending_events(self) -> None:
        if not self._pending_event_lines:
            return
        remaining: list[str] = []
        for line in self._pending_event_lines:
            try:
                self._append_event_line(line)
            except PermissionError as exc:
                remaining.append(line)
                print(f"警告：事件日志补写失败，本次 summary 仍会继续生成：{exc}", file=sys.stderr)
        self._pending_event_lines = remaining

    def _update_latest(self) -> None:
        latest = self.output_dir.parent / "latest"
        for attempt in range(5):
            try:
                if latest.exists() or latest.is_symlink():
                    if latest.is_dir() and not latest.is_symlink():
                        shutil.rmtree(latest)
                    else:
                        latest.unlink()
                shutil.copytree(self.output_dir, latest)
                return
            except PermissionError as exc:
                if attempt == 4:
                    print(f"警告：runs/latest 更新失败，请直接使用运行目录 {self.output_dir}：{exc}", file=sys.stderr)
                    return
                time.sleep(min(0.5 * (attempt + 1), 3.0))

    def _write_sqlite(self, summary: AssessmentRunSummary) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("delete from assessment_model_results")
            conn.execute("delete from assessment_domain_scores")
            _ensure_column(conn, "assessment_model_results", "semantic_scores", "text not null default '{}'")
            _ensure_column(conn, "assessment_model_results", "semantic_role_fit", "text not null default '{}'")
            for result in summary.results:
                conn.execute(
                    """
                    insert into assessment_model_results (
                        alias, model_name, provider, temperature, total_score, diagnostic_scores, method_fingerprint, semantic_scores, semantic_role_fit, role_fit, failures, errors
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.alias,
                        result.model_name,
                        result.provider,
                        result.temperature,
                        result.total_score,
                        json.dumps(result.diagnostic_scores, ensure_ascii=False),
                        json.dumps(result.method_fingerprint, ensure_ascii=False),
                        json.dumps(result.semantic_scores, ensure_ascii=False),
                        json.dumps(result.semantic_role_fit, ensure_ascii=False),
                        json.dumps(result.role_fit, ensure_ascii=False),
                        json.dumps(result.failures, ensure_ascii=False),
                        json.dumps(result.errors, ensure_ascii=False),
                    ),
                )
                for domain, score in result.domain_scores.items():
                    conn.execute(
                        "insert into assessment_domain_scores (alias, domain, score) values (?, ?, ?)",
                        (result.alias, domain, score),
                    )


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute(f"pragma table_info({table_name})")}
    if column_name not in columns:
        conn.execute(f"alter table {table_name} add column {column_name} {definition}")
