# 编排当前模型能力评测。
# 输入：模型配置和任务；输出：评测摘要和落盘记录。
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from uuid import uuid4

from arena.config import ArenaConfig
from arena.embeddings import EmbeddingCache
from arena.models import ModelConfig
from arena.providers import build_provider

from .models import AssessmentModelResult, AssessmentPhaseResponse, AssessmentRunSummary, AssessmentTask
from .protocol import build_assessment_messages, parse_json_response
from .scoring import score_assessment_result
from .semantic_scoring import apply_semantic_scoring
from .store import AssessmentRunStore
from .tasks import DEFAULT_ASSESSMENT_TASKS


class AssessmentEvaluator:
    def __init__(self, config: ArenaConfig, tasks: list[AssessmentTask] | None = None) -> None:
        self.config = config
        self.tasks = tasks or DEFAULT_ASSESSMENT_TASKS

    def run(self) -> AssessmentRunSummary:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        output_dir = self.config.output_root / run_id
        known_secrets = [model.api_key for model in self.config.models]
        if self.config.embedding is not None:
            known_secrets.append(self.config.embedding.api_key)
        store = AssessmentRunStore(output_dir, known_secrets=known_secrets)
        providers = {model.alias: build_provider(model) for model in self.config.models}
        groups = _group_models_by_request_endpoint(self.config.models)
        results_by_alias: dict[str, AssessmentModelResult] = {}

        # 同一个 base_url 视为同一请求入口，组内串行，避免对同一供应商网关地址并发压测。
        # 不同请求入口之间并发执行，用于同时评测不同供应商或不同网关地址的模型。
        with ThreadPoolExecutor(max_workers=max(1, len(groups))) as executor:
            futures = [
                executor.submit(self._run_model_group, group_models, providers, store)
                for group_models in groups.values()
            ]
            for future in as_completed(futures):
                for result in future.result():
                    results_by_alias[result.alias] = result

        results = [results_by_alias[model.alias] for model in self.config.models if model.alias in results_by_alias]
        if self.config.embedding is not None:
            self._apply_semantic_scoring(results)

        summary = AssessmentRunSummary(
            run_id=run_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            output_dir=output_dir,
            tasks=self.tasks,
            results=results,
        )
        store.write_summary(summary)
        return summary

    def _run_model_group(
        self,
        models: list[ModelConfig],
        providers: dict[str, object],
        store: AssessmentRunStore,
    ) -> list[AssessmentModelResult]:
        results: list[AssessmentModelResult] = []
        for model in models:
            result = self._run_one_model(model, providers[model.alias], store)
            results.append(result)
        return results

    def _run_one_model(
        self,
        model: ModelConfig,
        provider: object,
        store: AssessmentRunStore,
    ) -> AssessmentModelResult:
        result = AssessmentModelResult(
            alias=model.alias,
            model_name=model.model_name,
            provider=model.provider,
            role_hint=model.role_hint,
            temperature=model.temperature,
        )
        for task in self.tasks:
            previous_parsed = None
            phases = [None, *task.mutations]
            for mutation in phases:
                phase_id = "baseline" if mutation is None else mutation.id
                messages = build_assessment_messages(task, mutation=mutation, previous_response=previous_parsed)
                prompt_text = messages[-1]["content"]
                try:
                    response = provider.complete(messages)
                    parsed, parse_error = parse_json_response(response.text)
                    if parsed is not None:
                        previous_parsed = parsed
                    phase_response = AssessmentPhaseResponse(
                        task_id=task.id,
                        phase_id=phase_id,
                        prompt=prompt_text,
                        raw_text=response.text,
                        parsed=parsed,
                        parse_error=parse_error,
                        usage=response.usage,
                    )
                    result.responses.append(phase_response)
                    store.record_event(
                        "assessment_response",
                        {
                            "alias": model.alias,
                            "task_id": task.id,
                            "phase_id": phase_id,
                            "raw_text": response.text,
                            "parsed": parsed,
                            "parse_error": parse_error,
                            "usage": response.usage,
                        },
                    )
                except Exception as exc:  # noqa: BLE001 - 单模型/单阶段失败需要记录并继续
                    error = f"{task.id}/{phase_id}: {exc}"
                    result.errors.append(error)
                    store.record_event(
                        "assessment_error",
                        {"alias": model.alias, "task_id": task.id, "phase_id": phase_id, "error": str(exc)},
                    )
        score_assessment_result(result, self.tasks)
        return result

    def _apply_semantic_scoring(self, results: list[AssessmentModelResult]) -> None:
        if self.config.embedding is None:
            return
        embedding_cache = EmbeddingCache(self.config.embedding)
        for result in results:
            try:
                apply_semantic_scoring(result, embedding_config=self.config.embedding, embedding_cache=embedding_cache)
            except Exception as exc:  # noqa: BLE001 - 语义评分失败不应丢掉已经完成的模型回答
                result.errors.append(f"语义评分失败: {exc}")


def _group_models_by_request_endpoint(models: list[ModelConfig]) -> dict[str, list[ModelConfig]]:
    groups: dict[str, list[ModelConfig]] = defaultdict(list)
    for model in models:
        groups[_request_endpoint_key(model)].append(model)
    return dict(groups)


def _request_endpoint_key(model: ModelConfig) -> str:
    if model.provider == "fake":
        return f"fake:{model.alias}"
    return model.base_url.strip().rstrip("/").lower()
