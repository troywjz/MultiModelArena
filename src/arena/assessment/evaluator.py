from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from arena.config import ArenaConfig
from arena.providers import build_provider

from .models import AssessmentModelResult, AssessmentPhaseResponse, AssessmentRunSummary, AssessmentTask
from .protocol import build_assessment_messages, parse_json_response
from .scoring import score_assessment_result
from .store import AssessmentRunStore
from .tasks import DEFAULT_ASSESSMENT_TASKS


class AssessmentEvaluator:
    def __init__(self, config: ArenaConfig, tasks: list[AssessmentTask] | None = None) -> None:
        self.config = config
        self.tasks = tasks or DEFAULT_ASSESSMENT_TASKS

    def run(self) -> AssessmentRunSummary:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        output_dir = self.config.output_root / run_id
        store = AssessmentRunStore(output_dir, known_secrets=[model.api_key for model in self.config.models])
        providers = {model.alias: build_provider(model) for model in self.config.models}
        results: list[AssessmentModelResult] = []

        for model in self.config.models:
            result = AssessmentModelResult(
                alias=model.alias,
                model_name=model.model_name,
                provider=model.provider,
                role_hint=model.role_hint,
                temperature=model.temperature,
            )
            provider = providers[model.alias]
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
            results.append(result)

        summary = AssessmentRunSummary(
            run_id=run_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            output_dir=output_dir,
            tasks=self.tasks,
            results=results,
        )
        store.write_summary(summary)
        return summary
