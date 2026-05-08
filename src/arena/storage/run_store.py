from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from arena.models import RunSummary
from arena.security import redact_text


class RunStore:
    def __init__(self, output_dir: Path, known_secrets: list[str] | None = None) -> None:
        self.output_dir = output_dir
        self.known_secrets = known_secrets or []
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.output_dir / "events.jsonl"
        self.summary_path = self.output_dir / "summary.json"
        self.db_path = self.output_dir / "summary.sqlite3"
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                create table if not exists model_results (
                    alias text primary key,
                    model_name text not null,
                    provider text not null,
                    average_score real not null,
                    recommended_roles text not null,
                    errors text not null
                )
                """
            )
            conn.execute(
                """
                create table if not exists dimension_scores (
                    alias text not null,
                    dimension text not null,
                    score integer not null,
                    primary key (alias, dimension)
                )
                """
            )

    def record_event(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {"type": event_type, "payload": payload}
        safe = json.loads(redact_text(json.dumps(event, ensure_ascii=False), self.known_secrets))
        with self.events_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(safe, ensure_ascii=False) + "\n")

    def write_summary(self, summary: RunSummary) -> None:
        data = summary.to_dict()
        safe_data = json.loads(redact_text(json.dumps(data, ensure_ascii=False), self.known_secrets))
        self.summary_path.write_text(
            json.dumps(safe_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._write_sqlite(summary)
        latest = self.output_dir.parent / "latest"
        if latest.exists() or latest.is_symlink():
            if latest.is_dir() and not latest.is_symlink():
                shutil.rmtree(latest)
            else:
                latest.unlink()
        shutil.copytree(self.output_dir, latest)

    def _write_sqlite(self, summary: RunSummary) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("delete from model_results")
            conn.execute("delete from dimension_scores")
            for result in summary.results:
                conn.execute(
                    """
                    insert into model_results (
                        alias, model_name, provider, average_score, recommended_roles, errors
                    ) values (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.alias,
                        result.model_name,
                        result.provider,
                        result.average_score,
                        json.dumps(result.recommended_roles, ensure_ascii=False),
                        json.dumps(result.errors, ensure_ascii=False),
                    ),
                )
                for dimension, score in result.scores.items():
                    conn.execute(
                        "insert into dimension_scores (alias, dimension, score) values (?, ?, ?)",
                        (result.alias, dimension, score),
                    )


def load_summary(input_dir: Path) -> dict[str, Any]:
    summary_path = input_dir / "summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"找不到运行摘要: {summary_path}")
    return json.loads(summary_path.read_text(encoding="utf-8"))
