# -*- coding: utf-8 -*-
"""R103 回归：diagnostics 的 collection 过滤必须下推到 SQL（LIMIT 之前）。

现状 list_documents/list_chunks/list_hits 先 `LIMIT :limit` 截断全表，
再在 Python 侧按 collection 丢弃不匹配行——多个 collection 共存时，
`/diagnostics/rag/collections/{collection}/documents` 等端点在目标
collection 有数据的情况下仍返回空/欠满页。谓词必须进入 WHERE。
"""
from __future__ import annotations


class _Result:
    def mappings(self):
        return self

    def all(self):
        return []


def _capture_store(captured):
    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, sql, params=None):
            captured["sql"] = str(sql)
            captured["params"] = dict(params or {})
            return _Result()

    class _Engine:
        def connect(self):
            return _Conn()

    class _Store:
        _engine = _Engine()

        def ensure_schema(self):
            return True

    return _Store()


def test_list_documents_filters_collection_in_sql():
    from backend.rag.observability_runtime import _sql_list_documents

    captured: dict = {}
    _sql_list_documents(_capture_store(captured), collection="news", limit=5)

    sql = captured["sql"]
    assert "collection" in captured["params"], "collection 谓词未进入 SQL 参数"
    assert "->>'collection'" in sql
    # 谓词必须出现在 LIMIT 之前（WHERE 段），否则仍是截断后丢弃
    assert sql.find("->>'collection'") < sql.find("LIMIT")


def test_list_chunks_filters_collection_in_sql():
    from backend.rag.observability_runtime import _sql_list_chunks

    captured: dict = {}
    _sql_list_chunks(_capture_store(captured), collection="news", limit=5)

    sql = captured["sql"]
    assert "collection" in captured["params"]
    assert "->>'collection'" in sql
    assert sql.find("->>'collection'") < sql.find("LIMIT")


def test_list_hits_filters_collection_in_sql():
    from backend.rag.observability_runtime import _sql_list_hits

    captured: dict = {}
    _sql_list_hits(_capture_store(captured), collection="news", limit=5)

    sql = captured["sql"]
    assert "collection" in captured["params"]
    # rag_retrieval_hits.collection 是真实列
    assert "rh.collection = :collection" in sql
    assert sql.find("rh.collection = :collection") < sql.find("LIMIT")
