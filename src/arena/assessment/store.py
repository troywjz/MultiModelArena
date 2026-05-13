from __future__ import annotations

import json
import shutil
import sqlite3
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
            self._append_event_line(json.dumps(safe, ensure_ascii=False) + "\n")

    def _append_event_line(self, line: str) -> None:
        # Windows 上偶发的杀毒/索引扫描可能短暂占用文件；这里重试避免丢掉整次评估。
        for attempt in range(5):
            try:
                with self.events_path.open("a", encoding="utf-8") as file:
                    file.write(line)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.2 * (attempt + 1))

    def write_summary(self, summary: AssessmentRunSummary) -> None:
        data = summary.to_dict()
        safe_data = json.loads(redact_text(json.dumps(data, ensure_ascii=False), self.known_secrets))
        self.summary_path.write_text(json.dumps(safe_data, ensure_ascii=False, indent=2), encoding="utf-8")
        self._write_sqlite(summary)
        latest = self.output_dir.parent / "latest"
        if latest.exists() or latest.is_symlink():
            if latest.is_dir() and not latest.is_symlink():
                shutil.rmtree(latest)
            else:
                latest.unlink()
        shutil.copytree(self.output_dir, latest)

    def _write_sqlite(self, summary: AssessmentRunSummary) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("delete from assessment_model_results")
            conn.execute("delete from assessment_domain_scores")
            for result in summary.results:
                conn.execute(
                    """
                    insert into assessment_model_results (
                        alias, model_name, provider, temperature, total_score, diagnostic_scores, method_fingerprint, role_fit, failures, errors
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.alias,
                        result.model_name,
                        result.provider,
                        result.temperature,
                        result.total_score,
                        json.dumps(result.diagnostic_scores, ensure_ascii=False),
                        json.dumps(result.method_fingerprint, ensure_ascii=False),
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
