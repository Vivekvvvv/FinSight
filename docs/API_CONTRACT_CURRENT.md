# FinSight 当前核心 API 契约

本文记录当前默认链路 `frontend-vue -> FastAPI` 的核心接口。所有接口默认只提供研究复查能力，不构成投资建议。

## 状态、Demo 与数据源

| Method | Path | 用途 |
|---|---|---|
| GET | `/health` | 后端健康检查 |
| GET | `/api/me` | 当前用户身份 |
| GET | `/api/demo/status` | Demo Mode 状态，保留旧接口兼容 |
| GET | `/api/data-sources/status` | US/CN/HK、LLM、RAG、Auth 的 Live/Fallback/Demo/Missing 状态 |

`/api/data-sources/status` 返回：

- `overall_status`: `demo | live_ready | fallback_ready | needs_config`
- `components[]`: 每个数据源的 `key / label / status / detail / required_action`
- `missing_services`: 缺失的生产配置项
- `as_of`: 状态检测时间

## 市场数据与 evidence

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/quote/{symbol}` | 报价；真实源失败且 Demo Mode 开启时返回差异化 Demo 数据 |
| GET | `/api/kline/{symbol}` | K 线；支持真实源、免费兜底、缓存和 Demo；非 Demo 模式下内部获取失败返回 `502 {"detail":"Kline data unavailable"}` |
| GET | `/api/stock/intraday/{symbol}` | 分时数据；非 Demo 模式下内部获取失败返回 `502 {"detail":"Intraday data unavailable"}` |
| GET | `/api/financials/{symbol}` | 财务指标；真实数据为空时可回落到 Demo |
| GET | `/api/screener/filters/meta` | 股票发现筛选元数据 |
| POST | `/api/screener/run` | 股票发现结果；无 FMP 时走 yfinance 或静态候选池兜底 |

行情、K 线、财务数据应携带统一可信字段：

```json
{
  "source": "demo",
  "as_of": "2026-06-13T00:00:00+00:00",
  "freshness_status": "demo",
  "fallback_level": 2,
  "evidence": {
    "source": "demo",
    "as_of": "2026-06-13T00:00:00+00:00",
    "freshness_status": "demo",
    "fallback_level": 2,
    "degraded": true,
    "stale_data": false
  }
}
```

语义约定：

- `live`: 真实或近实时服务返回。
- `fallback`: 免费兜底源返回，例如 yfinance、BaoStock。
- `cached`: 本地缓存返回。
- `demo`: 明确标注的演示数据，不冒充实时行情。
- `stale`: 数据过期，需要复查。

## 工作台与研究流

| Method | Path | 关键字段 |
|---|---|---|
| GET | `/api/today` | `summary`, `portfolio_snapshot`, `reports_to_review`, `next_actions` |
| GET | `/api/what-changed` | `items[].reason`, `items[].severity`, `items[].target_route` |
| GET | `/api/research-quality` | `summary.health_score`, `top_issues` |
| GET | `/api/timeline/{symbol}` | `events[].event_type`, `events[].severity`, `events[].evidence` |

`next_actions` 可包含研究生命周期动作：

- `research_review`: 标的仍处于 `new / watching / reviewing` 状态，需要进入 Dossier 继续复查。
- `risk_check`: 持仓风险复查。
- `refresh_report`: 报告过期或质量问题复查。
- `check_alert`: 新提醒复查。

## 自选、持仓、报告、笔记

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/user/watchlist` | 自选列表，含 `group / priority / watch_reason / research_status` |
| POST | `/api/user/watchlist/add` | 加入自选，可写入 `research_status` |
| POST | `/api/user/watchlist/update` | 更新自选元信息和研究状态 |
| GET | `/api/portfolio/summary` | 持仓、成本、市值、盈亏、价格来源 |
| PUT | `/api/portfolio/positions/{ticker}` | 新增或更新单个持仓 |
| GET | `/api/reports/index` | 报告资产库列表，含收藏、标签、质量状态 |
| GET | `/api/reports/replay/{report_id}` | 报告详情与引用 |
| GET | `/api/research-notes` | 研究笔记列表，支持 ticker 与搜索 |
| POST | `/api/research-notes` | 创建研究笔记 |

`research_status` 当前允许：

```text
new / watching / reviewing / resolved / archived
```

第一版主要由股票发现和自选列表写入，Today Workspace 消费它生成复查队列。

## AI 输出边界

- Chat、Dossier 标的研究和报告生成内容必须保持“研究复查建议”语义。`/api/dashboard*` 作为兼容数据层存在，不再代表独立主页面。
- 不得输出买入、卖出、持有、目标价、止盈止损、仓位比例、收益承诺或个性化交易决策。
- 兼容字段 `recommendation` 可保留，但内容必须是“优先复查 / 继续观察 / 证据不足 / 风险升高”等研究立场。
