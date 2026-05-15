# 调用 embedding 接口并缓存向量。
# 输入：文本片段；输出：向量列表和 SQLite 缓存。
from __future__ import annotations

import json
import math
import re
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from arena.models import EmbeddingConfig
from arena.security import redact_text


@dataclass(frozen=True)
class EmbeddingVector:
    text_hash: str
    vector: list[float]


class OpenAICompatibleEmbeddingClient:
    def __init__(self, config: EmbeddingConfig) -> None:
        self.config = config

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        url = f"{self.config.base_url}/embeddings"
        payload: dict[str, object] = {
            "model": self.config.model_name,
            "input": texts,
            "encoding_format": self.config.encoding_format,
        }
        if self.config.dimensions is not None:
            payload["dimensions"] = self.config.dimensions
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        data = self._post(url, body)
        try:
            items = sorted(data["data"], key=lambda item: item.get("index", 0))
            return [[float(value) for value in item["embedding"]] for item in items]
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Embedding 响应缺少 data[].embedding") from exc

    def _post(self, url: str, body: bytes) -> dict:
        attempts = self.config.retry_count + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            request = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.config.api_key}",
                },
                method="POST",
            )
            try:
                with self._open(request) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                last_error = exc
                error_body = exc.read().decode("utf-8", errors="replace")
                safe_error = redact_text(error_body, [self.config.api_key])
                if exc.code < 500 and exc.code != 429:
                    raise RuntimeError(f"Embedding 调用失败 HTTP {exc.code}: {safe_error}") from exc
                if attempt == attempts - 1:
                    raise RuntimeError(f"Embedding 调用失败 HTTP {exc.code}: {safe_error}") from exc
            except urllib.error.URLError as exc:
                last_error = exc
                if attempt == attempts - 1:
                    raise RuntimeError(f"Embedding 调用失败: {redact_text(str(exc), [self.config.api_key])}") from exc
            time.sleep(min(2**attempt, 8))
        raise RuntimeError(f"Embedding 调用失败: {last_error}")

    def _open(self, request: urllib.request.Request):
        if self.config.disable_proxy:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            return opener.open(request, timeout=self.config.timeout_seconds)
        return urllib.request.urlopen(request, timeout=self.config.timeout_seconds)


class FakeEmbeddingClient:
    def __init__(self, config: EmbeddingConfig) -> None:
        self.config = config

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_fake_embedding(text, self.config.dimensions or 16) for text in texts]


def build_embedding_client(config: EmbeddingConfig) -> OpenAICompatibleEmbeddingClient | FakeEmbeddingClient:
    if config.provider == "fake":
        return FakeEmbeddingClient(config)
    if config.provider == "openai_compatible":
        return OpenAICompatibleEmbeddingClient(config)
    raise RuntimeError(f"不支持的 embedding provider：{config.provider}")


class EmbeddingCache:
    def __init__(self, config: EmbeddingConfig, client: OpenAICompatibleEmbeddingClient | FakeEmbeddingClient | None = None) -> None:
        self.config = config
        self.client = client or build_embedding_client(config)
        self.path = Path(config.cache_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def get_vectors(self, texts: list[str]) -> list[list[float]]:
        normalized = [_normalize_text(text) for text in texts]
        cached: dict[str, list[float]] = {}
        missing_by_hash: dict[str, str] = {}
        for text in normalized:
            text_hash = _hash_text(text)
            vector = self._read_vector(text_hash)
            if vector is None:
                missing_by_hash[text_hash] = text
            else:
                cached[text_hash] = vector

        missing_items = list(missing_by_hash.items())
        for offset in range(0, len(missing_items), self.config.batch_size):
            batch = missing_items[offset : offset + self.config.batch_size]
            vectors = self.client.embed([text for _text_hash, text in batch])
            if len(vectors) != len(batch):
                raise RuntimeError("Embedding 返回数量和请求文本数量不一致")
            for (text_hash, text), vector in zip(batch, vectors, strict=True):
                self._write_vector(text_hash, text, vector)
                cached[text_hash] = vector

        return [cached[_hash_text(text)] for text in normalized]

    def _init_db(self) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                create table if not exists embedding_cache (
                    provider text not null,
                    base_url text not null,
                    model_name text not null,
                    dimensions text not null,
                    encoding_format text not null,
                    text_hash text not null,
                    text text not null,
                    vector_json text not null,
                    created_at text not null,
                    primary key (provider, base_url, model_name, dimensions, encoding_format, text_hash)
                )
                """
            )
            self._migrate_blank_dimensions(conn)

    def _read_vector(self, text_hash: str) -> list[float] | None:
        configured_dimensions = _configured_dimensions_key(self.config)
        with sqlite3.connect(self.path) as conn:
            if configured_dimensions is None:
                row = conn.execute(
                    """
                    select vector_json from embedding_cache
                    where provider = ? and base_url = ? and model_name = ? and encoding_format = ? and text_hash = ?
                    order by created_at desc
                    """,
                    (self.config.provider, self.config.base_url, self.config.model_name, self.config.encoding_format, text_hash),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    select vector_json from embedding_cache
                    where provider = ? and base_url = ? and model_name = ? and dimensions = ? and encoding_format = ? and text_hash = ?
                    """,
                    (*self._cache_scope(configured_dimensions), text_hash),
                ).fetchone()
        if row is None:
            return None
        return [float(value) for value in json.loads(row[0])]

    def _write_vector(self, text_hash: str, text: str, vector: list[float]) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                insert or replace into embedding_cache (
                    provider, base_url, model_name, dimensions, encoding_format, text_hash, text, vector_json, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    *self._cache_scope(_vector_dimensions_key(vector, self.config)),
                    text_hash,
                    text,
                    json.dumps(vector),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def _cache_scope(self, dimensions: str) -> tuple[str, str, str, str, str]:
        return (
            self.config.provider,
            self.config.base_url,
            self.config.model_name,
            dimensions,
            self.config.encoding_format,
        )

    def _migrate_blank_dimensions(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            select provider, base_url, model_name, encoding_format, text_hash, text, vector_json, created_at
            from embedding_cache
            where dimensions = ''
            """
        ).fetchall()
        for provider, base_url, model_name, encoding_format, text_hash, text, vector_json, created_at in rows:
            try:
                vector = [float(value) for value in json.loads(vector_json)]
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            dimensions = str(len(vector))
            conn.execute(
                """
                insert or replace into embedding_cache (
                    provider, base_url, model_name, dimensions, encoding_format, text_hash, text, vector_json, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (provider, base_url, model_name, dimensions, encoding_format, text_hash, text, vector_json, created_at),
            )
            conn.execute(
                """
                delete from embedding_cache
                where provider = ? and base_url = ? and model_name = ? and dimensions = '' and encoding_format = ? and text_hash = ?
                """,
                (provider, base_url, model_name, encoding_format, text_hash),
            )


def _normalize_text(text: str) -> str:
    return str(text).strip()


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _configured_dimensions_key(config: EmbeddingConfig) -> str | None:
    if config.dimensions is None:
        return None
    return str(config.dimensions)


def _vector_dimensions_key(vector: list[float], config: EmbeddingConfig) -> str:
    dimensions = len(vector)
    if config.dimensions is not None and dimensions != config.dimensions:
        raise RuntimeError(f"Embedding 返回维度 {dimensions} 与配置维度 {config.dimensions} 不一致")
    return str(dimensions)


def _fake_embedding(text: str, dimensions: int) -> list[float]:
    if dimensions <= 0:
        raise RuntimeError("fake embedding 维度必须为正整数")
    vector = [0.0] * dimensions
    for token in _fake_tokens(text):
        digest = sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % dimensions
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        weight = 1.0 + (digest[3] % 7) / 10
        vector[index] += sign * weight
    if not any(vector):
        vector[0] = 1.0
    length = math.sqrt(sum(value * value for value in vector))
    return [round(value / length, 8) for value in vector]


def _fake_tokens(text: str) -> list[str]:
    normalized = _normalize_text(text).lower()
    words = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", normalized)
    if words:
        return words
    return list(normalized) or [""]
