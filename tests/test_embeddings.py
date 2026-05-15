# 检查 embedding 向量缓存。
# 输入：fake embedding 和 SQLite 缓存；输出：pytest 断言结果。
import json
import sqlite3

from arena.embeddings import EmbeddingCache
from arena.models import EmbeddingConfig


def test_embedding_cache_stores_returned_vector_dimensions_when_unset(tmp_path):
    cache_path = tmp_path / "embedding-cache.sqlite3"
    config = EmbeddingConfig(
        provider="fake",
        base_url="fake://embedding",
        model_name="fake-embedding",
        dimensions=None,
        cache_path=cache_path,
    )

    vector = EmbeddingCache(config).get_vectors(["测试维度写入"])[0]

    with sqlite3.connect(cache_path) as conn:
        row = conn.execute("select dimensions, vector_json from embedding_cache").fetchone()

    assert row[0] == str(len(vector))
    assert len(json.loads(row[1])) == len(vector)


def test_embedding_cache_migrates_blank_legacy_dimensions(tmp_path):
    cache_path = tmp_path / "embedding-cache.sqlite3"
    text = "旧缓存维度迁移"
    config = EmbeddingConfig(
        provider="fake",
        base_url="fake://embedding",
        model_name="fake-embedding",
        dimensions=None,
        cache_path=cache_path,
    )
    legacy_vector = [0.1, 0.2, 0.3]
    with sqlite3.connect(cache_path) as conn:
        conn.execute(
            """
            create table embedding_cache (
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
        conn.execute(
            """
            insert into embedding_cache (
                provider, base_url, model_name, dimensions, encoding_format, text_hash, text, vector_json, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                config.provider,
                config.base_url,
                config.model_name,
                "",
                config.encoding_format,
                "legacy-hash",
                text,
                json.dumps(legacy_vector),
                "2026-05-15T00:00:00+00:00",
            ),
        )

    EmbeddingCache(config)

    with sqlite3.connect(cache_path) as conn:
        rows = conn.execute("select dimensions, vector_json from embedding_cache").fetchall()

    assert rows == [("3", json.dumps(legacy_vector))]
