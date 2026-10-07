# -*- coding: utf-8 -*-
"""Portfolio Optimizer Tests"""
from __future__ import annotations

import json
import math

from backend.services.portfolio_optimizer import optimize_portfolio


def _moving_returns(n: int = 30) -> list[float]:
    return [0.01 if i % 2 == 0 else -0.02 for i in range(n)]


def test_flat_series_does_not_leak_nan_into_correlation():
    """停牌股/恒定价标的的日收益全为 0 → np.corrcoef 对零方差行产生 NaN，
    透传进 correlation_matrix.data → FastAPI 序列化出裸 NaN 字面量 →
    前端 JSON.parse 抛 SyntaxError，整个优化结果页渲染失败。"""
    result = optimize_portfolio(
        returns_matrix=[
            [0.0] * 30,          # FLAT：零方差行（停牌/数据恒定）
            _moving_returns(),   # MOV：正常波动
        ],
        tickers=["FLAT", "MOV"],
        n_simulations=50,
    )

    corr = result["correlation_matrix"]["data"]
    assert all(
        math.isfinite(value)
        for row in corr
        for value in row
    ), f"correlation matrix contains non-finite values: {corr}"

    # 与 FastAPI JSONResponse 等价：响应必须能被严格 JSON 序列化
    json.dumps(result, allow_nan=False)


def test_normal_inputs_produce_finite_output():
    result = optimize_portfolio(
        returns_matrix=[
            _moving_returns(),
            [-0.015 if i % 3 == 0 else 0.008 for i in range(30)],
        ],
        tickers=["AAA", "BBB"],
        n_simulations=50,
    )

    # 正常输入下整个响应树也应全有限（防御将来新增 NaN 泄露路径）
    json.dumps(result, allow_nan=False)
    assert result["max_sharpe_portfolio"]["sharpe_ratio"] is not None


def test_short_history_ticker_marked_failed_not_500(monkeypatch):
    """路由 closes 门槛 <20 与 optimizer 门槛 returns>=20 错位一天：
    恰好 20 个收盘价的 ticker（新 IPO）通过守卫 → 只产 19 个 returns →
    min_len 对齐后 optimizer 抛 ValueError → 整个请求 500，连数据充足的
    其他 ticker 一起陪葬。正确行为是把短历史 ticker 计入 failed 继续。"""
    import backend.tools as tools_mod
    from backend.api.portfolio_router import (
        PortfolioOptimizeRequest,
        optimize_portfolio_endpoint,
    )

    def _kline(n: int) -> dict:
        return {
            "kline_data": [
                {"close": 100.0 + i * 0.1} for i in range(n)
            ]
        }

    def fake_hist(ticker: str, *args, **kwargs):
        return _kline(20 if ticker == "IPO20" else 60)

    monkeypatch.setattr(tools_mod, "get_stock_historical_data", fake_hist)

    request = PortfolioOptimizeRequest(
        tickers=["IPO20", "FULL1", "FULL2"], n_simulations=100,
    )
    result = optimize_portfolio_endpoint(request)

    assert "IPO20" not in result["tickers"]
    assert any("IPO20" in w for w in result.get("warnings", []))


def test_optimize_endpoint_filters_derived_non_finite_returns(monkeypatch):
    """close 只经 safe_float(有限)+>0 过滤——c0 为极小有限值（1e-320）时
    c1/c0 导出收益率比值溢出 inf：inf 进 returns_matrix → np.cov/mean 产
    nan → 前沿点/max_sharpe/min_vol/eq_baseline 全吐 NaN → 响应 JSON 出
    NaN 字面量（同 895e341 risk_attribution 派生溢出修复类）。"""
    import backend.tools as tools_mod
    from backend.api.portfolio_router import (
        PortfolioOptimizeRequest,
        optimize_portfolio_endpoint,
    )
    from backend.services import portfolio_optimizer

    rows = [{"close": c} for c in ([100.0] * 30 + [1e-320, 200.0])]
    monkeypatch.setattr(
        tools_mod,
        "get_stock_historical_data",
        lambda *args, **kwargs: {"kline_data": rows},
    )
    captured: dict = {}

    def _fake_optimize(**kwargs):
        captured.update(kwargs)
        return {"success": True}

    monkeypatch.setattr(portfolio_optimizer, "optimize_portfolio", _fake_optimize)

    optimize_portfolio_endpoint(
        PortfolioOptimizeRequest(tickers=["AAA", "BBB"], n_simulations=100)
    )

    assert captured["returns_matrix"]
    for series in captured["returns_matrix"]:
        assert all(math.isfinite(r) for r in series), f"inf 导出收益率泄漏: {series}"


def test_optimize_portfolio_rejects_non_finite_returns_input():
    """优化器入口无有限校验：nan/inf 收益率进 np.mean/cov → 响应体吐
    NaN/Infinity（任何调用方，不止路由）。直接拒绝比产出畸形结果更安全。"""
    import pytest

    with pytest.raises(ValueError, match="非有限"):
        optimize_portfolio(
            returns_matrix=[
                [0.01] * 25,
                [float("inf")] * 25,
            ],
            tickers=["A", "B"],
            n_simulations=50,
        )


def test_near_singular_cov_sqrt_does_not_leak_nan():
    """近完美负相关对（正股+反向ETF/多空对冲）让 np.cov 产出浮点非半正定
    矩阵：真实协方差二次型 ≥0，但负特征值 ~-1e-18 时 w@cov@w 取到微小
    负数 → np.sqrt(负) = nan → volatility/max_sharpe/eq_baseline 字段吐
    NaN → FastAPI 序列化出裸 NaN 字面量 → 前端 JSON.parse 崩（同本文件
    correlation NaN 修复类）。二次型真实值 ≥0，负数纯浮点噪声，钳到 0。"""
    r1 = [0.01 if i % 2 == 0 else -0.02 for i in range(30)]
    # 确定性微扰使 |cov12| 略超 sqrt(cov11*cov22)：eq_w 二次型 = -1.7e-18
    eps = [1e-14 if i % 2 == 0 else -1e-14 for i in range(30)]
    r2 = [-v + e for v, e in zip(r1, eps)]

    result = optimize_portfolio(
        returns_matrix=[r1, r2],
        tickers=["LONG", "INVERSE"],
        n_simulations=100,
    )

    assert math.isfinite(
        result["equal_weight_baseline"]["annual_volatility"]
    ), f"eq_vol NaN 泄漏: {result['equal_weight_baseline']}"
    json.dumps(result, allow_nan=False)
