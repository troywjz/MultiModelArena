from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DIMENSIONS = [
    "准确性",
    "完整性",
    "协作性",
    "稳定性",
    "工程可用性",
    "表达质量",
]

TEAM_ROLES = [
    "需求澄清者",
    "架构评审者",
    "代码实现者",
    "测试与质量审查者",
    "文档与总结者",
    "风险与安全审查者",
]


@dataclass(frozen=True)
class ModelConfig:
    alias: str
    provider: str
    model_name: str
    base_url: str = ""
    api_key: str = ""
    role_hint: str = ""
    temperature: float = 0.2
    max_tokens: int | None = 1024
    top_p: float = 1.0
    timeout_seconds: float = 60.0
    retry_count: int = 0


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    prompt: str


@dataclass
class ProviderResponse:
    text: str
    usage: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelRunResult:
    alias: str
    model_name: str
    provider: str
    role_hint: str
    answers: dict[str, str] = field(default_factory=dict)
    peer_reviews: dict[str, str] = field(default_factory=dict)
    revisions: dict[str, str] = field(default_factory=dict)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    scores: dict[str, int] = field(default_factory=dict)
    recommended_roles: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def average_score(self) -> float:
        if not self.scores:
            return 0.0
        return round(sum(self.scores.values()) / len(self.scores), 2)


@dataclass
class RunSummary:
    run_id: str
    created_at: str
    output_dir: Path
    tasks: list[Task]
    results: list[ModelRunResult]
    consensus: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "output_dir": str(self.output_dir),
            "tasks": [task.__dict__ for task in self.tasks],
            "results": [
                {
                    "alias": result.alias,
                    "model_name": result.model_name,
                    "provider": result.provider,
                    "role_hint": result.role_hint,
                    "answers": result.answers,
                    "peer_reviews": result.peer_reviews,
                    "revisions": result.revisions,
                    "strengths": result.strengths,
                    "weaknesses": result.weaknesses,
                    "scores": result.scores,
                    "average_score": result.average_score,
                    "recommended_roles": result.recommended_roles,
                    "evidence": result.evidence,
                    "errors": result.errors,
                }
                for result in self.results
            ],
            "consensus": self.consensus,
        }
