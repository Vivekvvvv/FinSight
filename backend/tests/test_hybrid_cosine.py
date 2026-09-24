# -*- coding: utf-8 -*-
"""hybrid_service._cosine 维度不匹配的静默截断守卫。"""


def test_cosine_mismatched_dimensions_returns_zero():
    """查询向量（查询期现嵌入模型）与索引期存储向量（旧模型/配置）维度不同
    时，zip 静默截断会算出部分点积——分数仍为正、重排被污染且无告警。
    应与 notes_rag._cosine 的 len(a)!=len(b) 守卫一致，归 0.0。"""
    from backend.rag.hybrid_service import _cosine

    assert _cosine([1.0, 1.0, 1.0], [1.0, 1.0]) == 0.0
    assert _cosine([1.0, 1.0], [1.0, 1.0, 1.0]) == 0.0


def test_cosine_equal_dimensions_still_computes_dot():
    """维度一致时保持原有点积语义（该实现即点积，未归一化）。"""
    from backend.rag.hybrid_service import _cosine

    assert _cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert _cosine([1.0, 2.0], [3.0, 4.0]) == 11.0
