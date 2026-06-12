# 数据工具层

`backend/tools/` 是 FinSight 的外部数据适配层，负责把第三方或免密数据源转换成内部稳定字段。

## 当前职责

```text
backend/tools/
├── baostock_provider.py   # A 股 BaoStock 免密行情/K线兜底
├── cn_hk_market.py        # 东方财富 CN/HK 指标、K线、财务数据
├── price.py               # US/指数/通用价格与历史行情多源回退
├── financial.py           # 财务报表与估值工具
└── screener.py            # 股票发现筛选工具
```

## 设计边界

- 工具层只做数据获取、字段归一化和降级标记，不决定产品展示。
- API 路由负责认证、缓存和 HTTP 语义。
- 前端只消费 `source/as_of/freshness_status/fallback_level`，不复制后端评分规则。
- Demo 数据只能作为明确标注的兜底，不冒充实时行情。
