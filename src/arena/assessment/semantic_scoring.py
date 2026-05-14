# 计算参考答案语义相似度评分。
# 输入：模型回答、参考答案和向量；输出：语义分和语义角色分。
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from arena.embeddings import EmbeddingCache
from arena.models import EmbeddingConfig

from .models import AssessmentModelResult, ROLE_FIT_RULES
from .reference_answers import SEMANTIC_SEGMENT_LABELS, reference_segments_for


def apply_semantic_scoring(
    result: AssessmentModelResult,
    *,
    embedding_config: EmbeddingConfig,
    embedding_cache: EmbeddingCache,
) -> None:
    comparisons = _collect_comparisons(result)
    if not comparisons:
        result.semantic_scores = {}
        result.semantic_role_fit = {}
        result.semantic_notes = ["没有可用于语义评分的可解析回答。"]
        return

    unique_texts = _unique_texts(
        [comparison.model_text for comparison in comparisons]
        + [reference for comparison in comparisons for reference in comparison.reference_texts]
    )
    vectors = embedding_cache.get_vectors(unique_texts)
    vector_by_text = dict(zip(unique_texts, vectors, strict=True))

    segment_hits: dict[str, list[float]] = defaultdict(list)
    role_hits: dict[str, list[float]] = defaultdict(list)
    similarity_hits: list[float] = []
    for comparison in comparisons:
        model_vector = vector_by_text[_normalize_text(comparison.model_text)]
        reference_vectors = [vector_by_text[_normalize_text(text)] for text in comparison.reference_texts]
        best_similarity = max(_cosine_similarity(model_vector, vector) for vector in reference_vectors)
        score = _similarity_to_score(
            best_similarity,
            floor=embedding_config.similarity_floor,
            ceiling=embedding_config.similarity_ceiling,
        )
        segment_hits[comparison.segment].append(score)
        similarity_hits.append(best_similarity)
        for role in comparison.roles:
            role_hits[role].append(score)

    result.semantic_scores = {
        SEMANTIC_SEGMENT_LABELS.get(segment, segment): _round_score(_average(values))
        for segment, values in segment_hits.items()
    }
    result.semantic_role_fit = {
        role: _round_score(_average(values))
        for role, values in role_hits.items()
    }
    result.role_fit = _merge_role_fit(result.role_fit, result.semantic_role_fit, embedding_config.role_weight)
    result.semantic_notes = [
        f"语义评分使用 {embedding_config.model_name}；共比较 {len(comparisons)} 个字段片段，参考答案取最高余弦相似度。",
        f"余弦相似度按 {embedding_config.similarity_floor:g}-{embedding_config.similarity_ceiling:g} 区间映射到 0-10 分；角色适配按权重 {embedding_config.role_weight:g} 融合语义分。",
        f"本次字段平均原始余弦相似度约 {_average(similarity_hits):.3f}。",
    ]


class _Comparison:
    def __init__(self, *, segment: str, roles: tuple[str, ...], model_text: str, reference_texts: tuple[str, ...]) -> None:
        self.segment = segment
        self.roles = roles
        self.model_text = model_text
        self.reference_texts = reference_texts


def _collect_comparisons(result: AssessmentModelResult) -> list[_Comparison]:
    comparisons: list[_Comparison] = []
    for response in result.responses:
        if response.parsed is None:
            continue
        references = reference_segments_for(response.task_id, response.phase_id)
        for reference in references:
            model_text = _segment_text(response.parsed, reference.segment)
            if not model_text:
                model_text = "空字段"
            comparisons.append(
                _Comparison(
                    segment=reference.segment,
                    roles=reference.roles,
                    model_text=model_text,
                    reference_texts=reference.texts,
                )
            )
    return comparisons


def _segment_text(parsed: dict[str, Any], segment: str) -> str:
    if segment == "problem_frame":
        return str(parsed.get("problem_frame", "")).strip()
    if segment == "values_detected":
        return _text_blob(parsed.get("values_detected"))
    if segment == "alternatives":
        return _alternatives_text(parsed.get("alternatives"))
    if segment == "recommendation":
        return " ".join(
            part
            for part in [
                str(parsed.get("recommended_option", "")).strip(),
                _text_blob(parsed.get("option_ranking")),
            ]
            if part
        )
    if segment == "risks_revisit":
        return " ".join(
            part
            for part in [
                _text_blob(parsed.get("risks")),
                _text_blob(parsed.get("revisit_conditions")),
            ]
            if part
        )
    if segment == "actions":
        return " ".join(
            part
            for part in [
                _text_blob(parsed.get("next_actions_7_days")),
                _text_blob(parsed.get("next_actions_30_days")),
            ]
            if part
        )
    if segment == "professional_boundary":
        return str(parsed.get("professional_boundary", "")).strip()
    return _text_blob(parsed.get(segment))


def _alternatives_text(value: Any) -> str:
    if not isinstance(value, list):
        return _text_blob(value)
    items: list[str] = []
    for alternative in value:
        if not isinstance(alternative, dict):
            items.append(str(alternative))
            continue
        items.append(
            " ".join(
                part
                for part in [
                    str(alternative.get("name", "")).strip(),
                    str(alternative.get("type", "")).strip(),
                    _text_blob(alternative.get("pros")),
                    _text_blob(alternative.get("cons")),
                    str(alternative.get("reversibility", "")).strip(),
                ]
                if part
            )
        )
    return " ".join(items)


def _text_blob(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_text_blob(item) for item in value.values()).strip()
    if isinstance(value, list):
        return " ".join(_text_blob(item) for item in value).strip()
    if value in (None, ""):
        return ""
    return str(value).strip()


def _merge_role_fit(local: dict[str, float], semantic: dict[str, float], weight: float) -> dict[str, float]:
    roles = list(ROLE_FIT_RULES)
    output: dict[str, float] = {}
    for role in roles:
        local_score = local.get(role)
        semantic_score = semantic.get(role)
        if local_score is None and semantic_score is None:
            continue
        if semantic_score is None:
            output[role] = _round_score(float(local_score or 0.0))
        elif local_score is None:
            output[role] = _round_score(semantic_score)
        else:
            output[role] = _round_score(float(local_score) * (1 - weight) + semantic_score * weight)
    return output


def _similarity_to_score(similarity: float, *, floor: float, ceiling: float) -> float:
    if ceiling <= floor:
        return 0.0
    return max(0.0, min(1.0, (similarity - floor) / (ceiling - floor))) * 10


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise RuntimeError("Embedding 向量维度不一致，无法计算余弦相似度")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _unique_texts(texts: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for text in texts:
        normalized = _normalize_text(text)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def _normalize_text(text: str) -> str:
    return str(text).strip()


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _round_score(value: float) -> float:
    return round(max(0.0, min(10.0, value)), 2)
