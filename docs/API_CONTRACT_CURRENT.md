# FinSight 当前核心 API 契约

本文记录当前默认链路 `frontend-vue -> FastAPI` 的核心接口。所有接口默认只提供研究复查能力，不构成投资建议。

## 状态与 Demo

| Method | Path | 用途 |
|---|---|---|
| GET | `/health` | 后端健康检查 |
| GET | `/api/me` | 当前用户身份 |
| GET | `/api/demo/status` | Demo Mode 状态、数据来源、缺失配置 |

`FINSIGHT_DEMO_MODE=true` 时，核心读取接口在真实数据为空时返回只读示例数据。响应中可能出现 `data_source=demo`、`freshness_status=demo` 或 `source=demo`。

## 工作台与研究流

| Method | Path | 关键字段 |
|---|---|---|
| GET | `/api/today` | `summary`, `portfolio_snapshot`, `watchlist_movers`, `reports_to_review`, `next_actions` |
| GET | `/api/what-changed` | `items[].reason`, `items[].severity`, `items[].target_route` |
| GET | `/api/research-quality` | `summary.health_score`, `top_issues`, `next_actions` |
| GET | `/api/timeline/{symbol}` | `events[].event_type`, `events[].severity`, `events[].evidence` |

## 资产、报告、笔记

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/portfolio/summary` | 持仓、成本、市值、盈亏、价格来源 |
| PUT | `/api/portfolio/positions/{ticker}` | 新增或更新单个持仓 |
| GET | `/api/reports/index` | 报告资产库列表，含收藏、标签、质量状态 |
| GET | `/api/reports/replay/{report_id}` | 读取报告详情与引用 |
| GET | `/api/research-notes` | 研究笔记列表，支持 ticker 与搜索 |
| POST | `/api/research-notes` | 创建研究笔记 |

## 标的发现与行情

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/screener/filters/meta` | 股票发现筛选元数据 |
| POST | `/api/screener/run` | 股票发现结果；无 FMP 时优先 fallback |
| GET | `/api/quote/{symbol}` | 报价 |
| GET | `/api/kline/{symbol}` | K 线 |
| GET | `/api/dashboard/insights` | 多维 AI 洞察 |

## 数据可信约定

- 关键结论应带 `source`、`as_of`、`freshness_status`、`confidence` 或 EvidencePanel 可展示字段。
- `demo` 表示示例数据，只用于体验流程。
- `live` 表示来自实时或近实时服务。
- `stale` 表示数据过期，需要复查。
- `quality_state=warn/block` 时，前端必须展示降级或质检提示。
