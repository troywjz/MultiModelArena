from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from arena.config import ArenaConfig
from arena.models import ModelRunResult, RunSummary, Task
from arena.providers import build_provider
from arena.storage import RunStore
from arena.tasks import DEFAULT_TASKS

from .scoring import score_result


class Evaluator:
    def __init__(self, config: ArenaConfig, tasks: list[Task] | None = None) -> None:
        self.config = config
        self.tasks = tasks or DEFAULT_TASKS

    def run(self) -> RunSummary:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        output_dir = self.config.output_root / run_id
        store = RunStore(output_dir, known_secrets=[model.api_key for model in self.config.models])
        providers = {model.alias: build_provider(model) for model in self.config.models}
        results = {
            model.alias: ModelRunResult(
                alias=model.alias,
                model_name=model.model_name,
                provider=model.provider,
                role_hint=model.role_hint,
            )
            for model in self.config.models
        }

        for task in self.tasks:
            for model in self.config.models:
                result = results[model.alias]
                try:
                    response = providers[model.alias].complete(
                        [
                            {"role": "system", "content": "你是参与多模型评测的候选模型，请给出可执行、结构化、简洁的中文回答。"},
                            {"role": "user", "content": task.prompt},
                        ]
                    )
                    result.answers[task.id] = response.text
                    store.record_event(
                        "answer",
                        {"alias": model.alias, "task_id": task.id, "text": response.text, "usage": response.usage},
                    )
                except Exception as exc:  # noqa: BLE001 - 评测需要记录单模型失败并继续
                    result.errors.append(f"{task.id}: {exc}")
                    store.record_event("error", {"alias": model.alias, "task_id": task.id, "error": str(exc)})

        for task in self.tasks:
            peer_context = self._peer_context(results.values(), task.id)
            for model in self.config.models:
                result = results[model.alias]
                if task.id not in result.answers:
                    continue
                try:
                    review = providers[model.alias].complete(
                        [
                            {"role": "system", "content": "你正在匿名评审其他模型答案，请指出优点、缺点和可合并的共识。"},
                            {"role": "user", "content": f"任务：{task.prompt}\n\n候选答案：\n{peer_context}"},
                        ]
                    )
                    result.peer_reviews[task.id] = review.text
                    revision = providers[model.alias].complete(
                        [
                            {"role": "system", "content": "你需要基于同伴观点修订自己的答案，输出更稳健的最终版本。"},
                            {
                                "role": "user",
                                "content": (
                                    f"任务：{task.prompt}\n\n你的原答案：{result.answers[task.id]}\n\n"
                                    f"同伴评审：{review.text}"
                                ),
                            },
                        ]
                    )
                    result.revisions[task.id] = revision.text
                    store.record_event(
                        "review_and_revision",
                        {
                            "alias": model.alias,
                            "task_id": task.id,
                            "review": review.text,
                            "revision": revision.text,
                        },
                    )
                except Exception as exc:  # noqa: BLE001
                    result.errors.append(f"{task.id} review: {exc}")
                    store.record_event("error", {"alias": model.alias, "task_id": task.id, "error": str(exc)})

        ordered_results = list(results.values())
        for result in ordered_results:
            score_result(result)

        summary = RunSummary(
            run_id=run_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            output_dir=output_dir,
            tasks=self.tasks,
            results=ordered_results,
            consensus=self._build_consensus(ordered_results),
        )
        store.write_summary(summary)
        return summary

    def _peer_context(self, results: list[ModelRunResult] | object, task_id: str) -> str:
        lines: list[str] = []
        for index, result in enumerate(results, start=1):  # type: ignore[arg-type]
            answer = result.answers.get(task_id)
            if answer:
                lines.append(f"候选 {index}: {answer}")
        return "\n\n".join(lines)

    def _build_consensus(self, results: list[ModelRunResult]) -> str:
        if not results:
            return "没有可用模型结果。"
        ranked = sorted(results, key=lambda result: result.average_score, reverse=True)
        role_lines = [
            f"{result.model_name}：平均 {result.average_score}/10，建议角色 {', '.join(result.recommended_roles) or '待定'}"
            for result in ranked
        ]
        return "本次评测建议采用互补组合，而不是只看单一排名。\n" + "\n".join(role_lines)
