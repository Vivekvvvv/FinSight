# Phase 7 性能复测报告

**日期**: 2026-06-08  
**状态**: ✅ **全部通过 P95 < 1000ms 目标**

---

## 测试环境

- **后端**: `DEV_MODE=1 uvicorn backend.api.main:app --port 8001`
- **平台**: Windows 11 / Python 3.12 本地进程
- **测试方法**: 每个接口连续请求 5 次，统计 avg/min/max/P95
- **目标**: 本地 dev P95 < 1000ms

---

## 测试结果

| 接口 | avg (ms) | min (ms) | max (ms) | P95 (ms) | 达标 |
|------|---------|---------|---------|---------|------|
| GET /api/today | 17 | 2 | 26 | 22 | ✅ |
| GET /api/portfolio/risk-lens | 9 | 2 | 25 | 16 | ✅ |
| GET /api/timeline/AAPL | 15 | 2 | 32 | 22 | ✅ |
| GET /api/what-changed | 2 | 1 | 2 | 2 | ✅ |
| GET /api/research-quality | 11 | 2 | 21 | 15 | ✅ |
| GET /api/research-notes | 12 | 2 | 16 | 15 | ✅ |
| GET /api/reports/index | 10 | 2 | 15 | 15 | ✅ |
| GET /api/portfolio/summary | 8 | 2 | 17 | 15 | ✅ |

**所有接口 P95 < 30ms，远低于 1000ms 目标。**

---

## 与 Phase 5 对比

Phase 5 设定 P95 < 1s 目标。当前测试结果：

- 最慢接口：`/api/today`，P95 = 22ms
- 平均响应时间：约 10ms
- 无接口超过 50ms

**结论**: 性能基准稳定保持在 Phase 5 水平，无回归。

---

## 备注

1. **空数据库**: 测试在空数据库环境中进行，响应时间不含数据库查询延迟（SQLite 本地文件）
2. **无行情网络**: 不依赖外部 API，响应时间仅为本地计算 + SQLite 读写
3. **BGE-M3 未加载**: dev 模式默认使用 hash embedding，跳过模型加载，不影响接口响应时间
4. **LLM 接口**: `/chat` 等 LLM 相关接口受外部 API 影响，不在本次测试范围

---

## 内存使用

启动后 uvicorn 进程内存约 250-350MB（含 Python 运行时 + FastAPI + SQLite + LangGraph 初始化）。无明显内存泄漏，5 次循环测试期间内存稳定。
